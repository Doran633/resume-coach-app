from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.observability_common import BEIJING, load_jsonl, parse_time, write_json
from scripts.operations_common import STATUS_RANK, read_json, report_age_hours, worst_status


def _latest_event_age(logs_dir: Path, event_name: str, *, now: datetime) -> float | None:
    timestamps = [
        parse_time(row.get("created_at")) for row in load_jsonl(logs_dir, "runtime")
        if row.get("event_name") == event_name
    ]
    values = [value for value in timestamps if value is not None]
    return (now - max(values)).total_seconds() / 3600 if values else None


def evaluate_freshness(
    reports_dir: Path,
    logs_dir: Path,
    backups_dir: Path,
    *,
    full_smoke_enabled: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(BEIJING)
    checks: list[dict[str, Any]] = []

    def add(name: str, age: float | None, warning: float, critical: float, *, optional: bool = False) -> None:
        if age is None:
            status = "observe" if optional else "critical"
            message = "未启用或暂无记录" if optional else "缺少运行记录"
        else:
            status = "critical" if age > critical else "warning" if age > warning else "healthy"
            message = f"距今 {age:.1f} 小时"
        checks.append({"check": name, "age_hours": round(age, 2) if age is not None else None, "status": status, "message": message})

    backups = sorted(backups_dir.glob("*.sqlite3"), key=lambda path: path.stat().st_mtime, reverse=True) if backups_dir.exists() else []
    backup_age = (current.timestamp() - backups[0].stat().st_mtime) / 3600 if backups else None
    add("database_backup", backup_age, 30, 48)
    add("database_backup_verification", _latest_event_age(logs_dir, "database_backup_verified", now=current), 168, 240)
    add("data_retention_cleanup", _latest_event_age(logs_dir, "data_retention_completed", now=current), 30, 48)

    for name, filename, warning, critical, optional in [
        ("shallow_smoke", "public-smoke-shallow-latest.json", 2, 4, False),
        ("full_smoke", "public-smoke-full-latest.json", 36, 48, not full_smoke_enabled),
        ("operational_slo", "operational-slo-latest.json", 2, 4, False),
        ("quality_drift", "output-quality-drift-latest.json", 26, 36, False),
    ]:
        payload = read_json(reports_dir / filename)
        add(name, report_age_hours(payload, now=current), warning, critical, optional=optional)
    runtime_reports = sorted(
        reports_dir.glob("runtime-protection-*.md"), key=lambda path: path.stat().st_mtime, reverse=True,
    ) if reports_dir.exists() else []
    runtime_age = (current.timestamp() - runtime_reports[0].stat().st_mtime) / 3600 if runtime_reports else None
    add("runtime_protection_report", runtime_age, 30, 48)

    status = worst_status([item["status"] for item in checks])
    return {
        "created_at": current.isoformat(),
        "status": status,
        "full_smoke_enabled": full_smoke_enabled,
        "checks": checks,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 运维任务新鲜度", "", f"- 生成时间：{report['created_at']}", f"- 状态：{report['status']}", "",
        "| 任务 | 最近运行 | 状态 | 说明 |", "|---|---:|---|---|",
    ]
    lines.extend(
        f"| {item['check']} | {item['age_hours'] if item['age_hours'] is not None else '暂无'} | {item['status']} | {item['message']} |"
        for item in report["checks"]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether public-beta operations actually ran on schedule.")
    parser.add_argument("--reports", type=Path, default=ROOT / "backend" / "reports")
    parser.add_argument("--logs", type=Path, default=ROOT / "backend" / "logs")
    parser.add_argument("--backups", type=Path, default=ROOT / "backend" / "backups")
    parser.add_argument("--full-smoke-enabled", action="store_true", default=os.getenv("ENABLE_FULL_SMOKE", "").lower() in {"1", "true", "yes", "on"})
    args = parser.parse_args()
    report = evaluate_freshness(args.reports, args.logs, args.backups, full_smoke_enabled=args.full_smoke_enabled)
    args.reports.mkdir(parents=True, exist_ok=True)
    write_json(args.reports / "operations-freshness-latest.json", report)
    (args.reports / "operations-freshness-latest.md").write_text(render_markdown(report), encoding="utf-8")
    print(args.reports / "operations-freshness-latest.md")
    raise SystemExit(STATUS_RANK.get(report["status"], 0))


if __name__ == "__main__":
    main()
