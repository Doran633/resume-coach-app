from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.list_recent_quality_incidents import collect_incidents
from scripts.observability_common import BEIJING, write_json
from scripts.operations_common import read_json, report_age_hours, worst_status


REPORT_COMPONENTS = {
    "slo": "operational-slo-latest.json",
    "quality_drift": "output-quality-drift-latest.json",
    "freshness": "operations-freshness-latest.json",
    "rate_limit": "rate-limit-rollout-latest.json",
    "database": "database-portability-latest.json",
    "rollback": "rollback-readiness-latest.json",
    "shallow_smoke": "public-smoke-shallow-latest.json",
    "full_smoke": "public-smoke-full-latest.json",
}


def _env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _git_commit(project_root: Path) -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _health(base: str) -> dict[str, Any]:
    if not base:
        return {}
    try:
        with urlopen(base.rstrip("/") + "/api/health/ready", timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _database_integrity(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            return str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            connection.close()
    except sqlite3.Error:
        return "unavailable"


def _component_status(name: str, payload: dict[str, Any]) -> str:
    if not payload:
        return "observe" if name == "full_smoke" else "warning"
    if name.endswith("smoke"):
        return "healthy" if payload.get("passed") else "critical"
    value = str(payload.get("status") or "observe")
    return value if value in {"healthy", "observe", "warning", "critical"} else "observe"


def _slo_metric(slo: dict[str, Any], name: str) -> Any:
    for item in slo.get("metrics", []):
        if isinstance(item, dict) and item.get("metric") == name:
            return item.get("value")
    return None


def _update_alerts(out_dir: Path, components: dict[str, dict[str, Any]], incidents: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    previous = read_json(out_dir / "operations-alert-latest.json")
    old_by_code = {str(item.get("issue_code")): item for item in previous.get("alerts", []) if item.get("issue_code")}
    grouped: dict[str, dict[str, Any]] = {}
    for name, entry in components.items():
        if entry["status"] not in {"warning", "critical"}:
            continue
        code = f"{name.upper()}_{entry['status'].upper()}"
        grouped[code] = {
            "severity": entry["status"], "request_ids": set(), "result_ids": set(),
            "recommended_action": f"检查 {REPORT_COMPONENTS.get(name, entry.get('report', name))} 中的具体指标",
        }
    for incident in incidents:
        if incident.get("smoke"):
            continue
        for code in incident.get("issue_codes", []):
            item = grouped.setdefault(str(code), {
                "severity": str(incident.get("severity") or "warning"),
                "request_ids": set(), "result_ids": set(),
                "recommended_action": "按问题编号查询质量事件并复核对应阶段",
            })
            if incident.get("request_id"):
                item["request_ids"].add(str(incident["request_id"]))
            if incident.get("generation_result_id") is not None:
                item["result_ids"].add(int(incident["generation_result_id"]))
    alerts = []
    for code, item in sorted(grouped.items()):
        old = old_by_code.get(code, {})
        alerts.append({
            "issue_code": code,
            "severity": item["severity"],
            "first_detected_at": old.get("first_detected_at") or now.isoformat(),
            "last_detected_at": now.isoformat(),
            "occurrence_count": int(old.get("occurrence_count") or 0) + 1,
            "related_request_ids": sorted(item["request_ids"])[-10:],
            "related_result_ids": sorted(item["result_ids"])[-10:],
            "recommended_action": item["recommended_action"],
        })
    payload = {"created_at": now.isoformat(), "alert_count": len(alerts), "alerts": alerts}
    write_json(out_dir / "operations-alert-latest.json", payload)
    lines = ["# 当前运维告警", "", f"- 生成时间：{payload['created_at']}", f"- 告警数：{len(alerts)}", ""]
    lines.extend(f"- [{item['severity']}] {item['issue_code']}：{item['recommended_action']}" for item in alerts)
    if not alerts:
        lines.append("- 当前没有 warning 或 critical 告警。")
    (out_dir / "operations-alert-latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def build_status(
    *, reports_dir: Path, logs_dir: Path, backups_dir: Path, database_path: Path,
    env_path: Path, frontend_env_path: Path, local_base: str, public_base: str,
    project_root: Path = ROOT,
) -> dict[str, Any]:
    now = datetime.now(BEIJING)
    backend_env = _env(env_path)
    frontend_env = _env(frontend_env_path)
    commit = _git_commit(project_root)
    health = _health(local_base)
    configured_version = backend_env.get("APP_VERSION") or (project_root / "VERSION").read_text(encoding="utf-8").strip()
    configured_commit = backend_env.get("BUILD_COMMIT", "")[:8]
    frontend_version = frontend_env.get("VITE_APP_VERSION", "")
    frontend_commit = frontend_env.get("VITE_BUILD_COMMIT", "")[:8]
    running_version = str(health.get("version") or "")
    running_commit = str(health.get("commit") or "")
    version_consistent = bool(
        health and configured_version == running_version
        and (not configured_commit or configured_commit == running_commit)
        and (not frontend_version or frontend_version == configured_version)
        and (not frontend_commit or frontend_commit == configured_commit)
        and (not commit or not configured_commit or commit.startswith(configured_commit))
    )
    component_payloads = {name: read_json(reports_dir / filename) for name, filename in REPORT_COMPONENTS.items()}
    components = {
        name: {"status": _component_status(name, payload), "age_hours": report_age_hours(payload), "report": filename}
        for (name, filename), payload in zip(REPORT_COMPONENTS.items(), component_payloads.values())
    }
    components["release_identity"] = {
        "status": "healthy" if version_consistent else "critical",
        "age_hours": None, "report": "health/ready + env + Git",
    }
    integrity = _database_integrity(database_path)
    components["database_integrity"] = {
        "status": "healthy" if integrity == "ok" else "critical", "age_hours": None, "report": "SQLite integrity_check",
    }
    incidents = collect_incidents(logs_dir, hours=72)
    alerts = _update_alerts(reports_dir, components, incidents, now)
    status = worst_status([entry["status"] for entry in components.values()])
    slo = component_payloads["slo"]
    drift = component_payloads["quality_drift"]
    rate = component_payloads["rate_limit"]
    database = component_payloads["database"]
    backups = sorted(backups_dir.glob("*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True) if backups_dir.exists() else []
    backup_age = (now.timestamp() - backups[0].stat().st_mtime) / 3600 if backups else None
    recommendations = list(dict.fromkeys(item["recommended_action"] for item in alerts["alerts"]))[:10]
    return {
        "created_at": now.isoformat(), "status": status,
        "release": {
            "configured_version": configured_version, "configured_commit": configured_commit,
            "running_version": running_version, "running_commit": running_commit,
            "frontend_version": frontend_version, "frontend_commit": frontend_commit,
            "git_commit": commit[:8], "consistent": version_consistent,
        },
        "runtime": {
            "health_ready": bool(health.get("ok")), "generation": health.get("generation", {}),
            "generation_success_rate": _slo_metric(slo, "generation_success_rate"),
            "generation_p50_ms": slo.get("p50_ms"), "generation_p90_ms": _slo_metric(slo, "generation_p90_ms"),
            "queue_full_count": _slo_metric(slo, "queue_full_count"),
            "redis_degraded_count": _slo_metric(slo, "redis_degraded_count"),
        },
        "quality": {"status": drift.get("status", "missing"), "sample_count": drift.get("sample_count", 0), "metrics": drift.get("metrics", {})},
        "data": {
            "database_integrity": integrity, "backup_age_hours": round(backup_age, 2) if backup_age is not None else None,
            "migration_recommendation": database.get("recommendation", "暂无审计"),
        },
        "rate_limit": {"recommendation": rate.get("recommendation", "暂无评估"), "reason": rate.get("reason", "")},
        "components": components, "alert_count": alerts["alert_count"], "recommendations": recommendations,
        "public_base_host": public_base.split("//", 1)[-1].split("/", 1)[0] if public_base else "",
    }


def render_markdown(report: dict[str, Any]) -> str:
    release = report["release"]
    runtime = report["runtime"]
    lines = [
        "# Resume Coach 公开测试运行总览", "",
        f"- 生成时间：{report['created_at']}", f"- 总体状态：{report['status']}",
        f"- 版本：{release['running_version'] or release['configured_version']} ({release['running_commit'] or release['configured_commit']})",
        f"- 前后端/Git一致：{'是' if release['consistent'] else '否'}", f"- 当前告警：{report['alert_count']}", "",
        "## 核心运行指标", "",
        f"- 健康就绪：{runtime['health_ready']}", f"- 生成成功率：{runtime['generation_success_rate']}",
        f"- P50 / P90：{runtime['generation_p50_ms']} / {runtime['generation_p90_ms']} ms",
        f"- 队列满 / Redis降级：{runtime['queue_full_count']} / {runtime['redis_degraded_count']}",
        f"- 高价值事实覆盖率：{report['quality']['metrics'].get('high_value_fact_coverage', '暂无')}",
        f"- Experience ID绑定率：{report['quality']['metrics'].get('experience_id_binding_rate', '暂无')}",
        f"- 最近备份：{report['data']['backup_age_hours'] if report['data']['backup_age_hours'] is not None else '暂无'} 小时前",
        f"- 数据库完整性：{report['data']['database_integrity']}",
        f"- 数据库建议：{report['data']['migration_recommendation']}",
        f"- 限流建议：{report['rate_limit']['recommendation']} {report['rate_limit']['reason']}", "",
        "## 子系统状态", "", "| 检查 | 状态 | 报告年龄(小时) |", "|---|---|---:|",
    ]
    lines.extend(f"| {name} | {item['status']} | {item['age_hours'] if item['age_hours'] is not None else '-'} |" for name, item in report["components"].items())
    lines.extend(["", "## 建议动作", ""])
    lines.extend(f"- {item}" for item in report["recommendations"] or ["当前没有需要立即处理的动作。"])
    lines.extend(["", "本报告不包含用户输入、完整简历、Cookie、API Key或原始IP。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a single privacy-safe public-beta operations status report.")
    parser.add_argument("--reports", type=Path, default=ROOT / "backend" / "reports")
    parser.add_argument("--logs", type=Path, default=ROOT / "backend" / "logs")
    parser.add_argument("--backups", type=Path, default=ROOT / "backend" / "backups")
    parser.add_argument("--database", type=Path, default=ROOT / "backend" / "data" / "resume_coach.db")
    parser.add_argument("--env", type=Path, default=Path("/etc/resume-coach/resume-coach.env") if os.name != "nt" else ROOT / ".env")
    parser.add_argument("--frontend-env", type=Path, default=ROOT / "frontend" / ".env.production")
    parser.add_argument("--local-base", default="http://127.0.0.1:8001")
    parser.add_argument("--public-base", default="")
    args = parser.parse_args()
    report = build_status(
        reports_dir=args.reports, logs_dir=args.logs, backups_dir=args.backups, database_path=args.database,
        env_path=args.env, frontend_env_path=args.frontend_env, local_base=args.local_base, public_base=args.public_base,
    )
    args.reports.mkdir(parents=True, exist_ok=True)
    write_json(args.reports / "operations-status-latest.json", report)
    path = args.reports / "operations-status-latest.md"
    path.write_text(render_markdown(report), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
