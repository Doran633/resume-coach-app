from __future__ import annotations

import argparse
import json
import shutil
import socket
import ssl
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.observability_common import BEIJING, average, cutoff_for_hours, is_smoke_attempt, load_jsonl, percentile, write_json


STATUS_RANK = {"healthy": 0, "warning": 1, "critical": 2}


def _certificate_days(public_base: str) -> int | None:
    host = urlparse(public_base).hostname
    if not host:
        return None
    try:
        with socket.create_connection((host, 443), timeout=5) as connection:
            with ssl.create_default_context().wrap_socket(connection, server_hostname=host) as secure:
                expiry = datetime.strptime(secure.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z")
        return (expiry - datetime.utcnow()).days
    except (OSError, KeyError, ValueError):
        return None


def _status(name: str, value, status: str, message: str) -> dict:
    return {"metric": name, "value": value, "status": status, "message": message}


def evaluate_slo(
    logs_dir: Path,
    *,
    hours: int = 24,
    backups_dir: Path | None = None,
    project_root: Path = ROOT,
    public_base: str = "",
) -> dict:
    cutoff = cutoff_for_hours(hours)
    queue_rows = [row for row in load_jsonl(logs_dir, "generation_queue", cutoff) if not is_smoke_attempt(row.get("attempt_id"))]
    runtime_rows = [row for row in load_jsonl(logs_dir, "runtime", cutoff) if not is_smoke_attempt(row.get("attempt_id"))]
    traced_attempts = {
        str(row.get("attempt_id")) for row in [*queue_rows, *runtime_rows]
        if row.get("request_id") and row.get("attempt_id")
    }
    queue = [row for row in queue_rows if str(row.get("attempt_id") or "") in traced_attempts]
    generation_runtime = [
        row for row in runtime_rows
        if str(row.get("attempt_id") or "") in traced_attempts
    ]
    operational_runtime = [row for row in runtime_rows if row.get("request_id")]
    success = [row for row in queue if row.get("event_name") == "generation_task_succeeded"]
    failures = [row for row in generation_runtime if row.get("event_name") == "generation_task_failed"]
    completed_attempts = len(success) + len(failures)
    success_rate = len(success) / completed_attempts if completed_attempts else None
    latencies = [float(row.get("elapsed_ms") or 0) for row in success + failures if float(row.get("elapsed_ms") or 0) > 0]
    p50 = percentile(latencies, 0.5)
    p90 = percentile(latencies, 0.9)
    sample_small = completed_attempts < 10
    metrics: list[dict] = []
    if success_rate is None:
        metrics.append(_status("generation_success_rate", None, "healthy", "暂无生成样本"))
    elif sample_small:
        metrics.append(_status("generation_success_rate", round(success_rate, 4), "healthy", "样本少于10次，仅观察"))
    else:
        status = "critical" if success_rate < 0.8 else "warning" if success_rate < 0.9 else "healthy"
        metrics.append(_status("generation_success_rate", round(success_rate, 4), status, f"完成样本 {completed_attempts} 次"))
    if p90 is None or sample_small:
        metrics.append(_status("generation_p90_ms", round(p90) if p90 else None, "healthy", "样本少于10次，仅观察" if p90 else "暂无耗时样本"))
    else:
        status = "critical" if p90 > 90_000 else "warning" if p90 > 60_000 else "healthy"
        metrics.append(_status("generation_p90_ms", round(p90), status, "P90生成耗时"))

    queue_full = sum(row.get("event_name") == "generation_admission" and row.get("status") == "full" for row in queue)
    redis_degraded = sum("redis" in str(row.get("event_name", "")).lower() and "degrad" in str(row.get("event_name", "")).lower() for row in operational_runtime)
    metrics.append(_status("queue_full_count", queue_full, "warning" if queue_full else "healthy", "队列满次数"))
    metrics.append(_status("redis_degraded_count", redis_degraded, "warning" if redis_degraded else "healthy", "Redis降级次数"))

    stability = [
        row for row in load_jsonl(logs_dir, "generation_stability", cutoff)
        if str(row.get("attempt_id") or "") in traced_attempts and row.get("generation_result_id")
    ]
    fallback_count = sum(bool(row.get("resume_section_fallback_triggered")) for row in stability)
    fallback_rate = fallback_count / len(stability) if stability else None
    fallback_status = "warning" if fallback_rate is not None and fallback_rate > 0.2 else "healthy"
    metrics.append(_status("resume_section_fallback_rate", round(fallback_rate, 4) if fallback_rate is not None else None, fallback_status, "Generation阶段Fallback触发率"))

    bound = sum(int(row.get("projects_with_source_id") or 0) for row in stability)
    missing = sum(int(row.get("projects_missing_source_id") or 0) for row in stability)
    binding_rate = bound / (bound + missing) if bound + missing else None
    binding_status = "warning" if binding_rate is not None and binding_rate < 0.9 else "healthy"
    metrics.append(_status("experience_id_binding_rate", round(binding_rate, 4) if binding_rate is not None else None, binding_status, "Experience ID项目绑定率"))

    coverage_values = [float(row["high_value_fact_coverage"]) for row in stability if row.get("high_value_fact_coverage") is not None]
    coverage = average(coverage_values)
    coverage_status = "warning" if coverage is not None and coverage < 0.8 else "healthy"
    metrics.append(_status("high_value_fact_coverage", round(coverage, 4) if coverage is not None else None, coverage_status, "高价值事实覆盖率"))

    unresolved = sum(int(row.get("unresolved_critical_issue_count") or 0) for row in stability)
    metrics.append(_status("unresolved_delivery_quality_issues", unresolved, "critical" if unresolved else "healthy", "未解决最终质量门问题"))

    docx_success = sum(row.get("event_name") == "docx_generated" for row in operational_runtime)
    docx_failed = sum(row.get("event_name") == "request_failed" and row.get("endpoint") == "/api/resume/docx" for row in operational_runtime)
    docx_total = docx_success + docx_failed
    docx_rate = docx_failed / docx_total if docx_total else None
    docx_status = "critical" if docx_rate is not None and docx_rate > 0.1 else "healthy"
    metrics.append(_status("docx_failure_rate", round(docx_rate, 4) if docx_rate is not None else None, docx_status, "DOCX失败率"))

    security = load_jsonl(logs_dir, "security_events", cutoff)
    deletion_failures = sum(row.get("event_name") == "privacy_deletion_failed" for row in security)
    metrics.append(_status("privacy_deletion_failures", deletion_failures, "critical" if deletion_failures else "healthy", "数据删除失败次数"))

    usage = load_jsonl(logs_dir, "llm_usage", cutoff)
    token_total = sum(int(row.get("input_tokens") or 0) + int(row.get("output_tokens") or 0) for row in usage)
    cost_total = round(sum(float(row.get("cost_cny") or 0) for row in usage), 4)
    metrics.append(_status("llm_tokens", token_total, "healthy", "模型Token用量"))
    metrics.append(_status("llm_cost_cny", cost_total, "healthy", "模型估算成本"))

    backups_dir = backups_dir or project_root / "backend" / "backups"
    backups = sorted(backups_dir.glob("*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True) if backups_dir.exists() else []
    backup_age = (datetime.now().timestamp() - backups[0].stat().st_mtime) / 3600 if backups else None
    backup_status = "critical" if backup_age is None or backup_age > 168 else "warning" if backup_age > 48 else "healthy"
    metrics.append(_status("backup_age_hours", round(backup_age, 1) if backup_age is not None else None, backup_status, "最近生产备份距今时间"))
    disk = shutil.disk_usage(project_root)
    disk_percent = round((disk.total - disk.free) / disk.total * 100, 1)
    disk_status = "critical" if disk_percent >= 95 else "warning" if disk_percent >= 85 else "healthy"
    metrics.append(_status("disk_used_percent", disk_percent, disk_status, "磁盘使用率"))
    cert_days = _certificate_days(public_base) if public_base else None
    cert_status = "critical" if cert_days is not None and cert_days < 7 else "warning" if cert_days is not None and cert_days < 21 else "healthy"
    metrics.append(_status("certificate_days", cert_days, cert_status, "HTTPS证书剩余天数" if public_base else "未配置公网地址，仅观察"))

    overall = max((item["status"] for item in metrics), key=lambda status: STATUS_RANK[status])
    return {
        "created_at": datetime.now(BEIJING).isoformat(),
        "hours": hours,
        "status": overall,
        "sample_count": completed_attempts,
        "smoke_traffic_excluded": True,
        "p50_ms": round(p50) if p50 else None,
        "metrics": metrics,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# Operational SLO Report", "",
        f"- 生成时间：{report['created_at']}",
        f"- 统计窗口：最近 {report['hours']} 小时",
        f"- 总体状态：{report['status']}",
        f"- 完成生成样本：{report['sample_count']}",
        "- 烟测流量：已排除", "",
        "| 指标 | 值 | 状态 | 说明 |", "|---|---:|---|---|",
    ]
    lines.extend(f"| {item['metric']} | {item['value'] if item['value'] is not None else '暂无'} | {item['status']} | {item['message']} |" for item in report["metrics"])
    lines.extend(["", "本报告只包含聚合运行指标，不包含用户输入、简历正文、Cookie、API Key或原始IP。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check privacy-safe operational SLOs.")
    parser.add_argument("--logs", type=Path, default=ROOT / "backend" / "logs")
    parser.add_argument("--out", type=Path, default=ROOT / "backend" / "reports")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--backups", type=Path, default=ROOT / "backend" / "backups")
    parser.add_argument("--public-base", default="")
    args = parser.parse_args()
    report = evaluate_slo(args.logs, hours=args.hours, backups_dir=args.backups, public_base=args.public_base)
    args.out.mkdir(parents=True, exist_ok=True)
    dated = args.out / f"operational-slo-{datetime.now(BEIJING).date().isoformat()}.md"
    dated.write_text(render_markdown(report), encoding="utf-8")
    write_json(args.out / "operational-slo-latest.json", report)
    print(dated)
    raise SystemExit(STATUS_RANK[report["status"]])


if __name__ == "__main__":
    main()
