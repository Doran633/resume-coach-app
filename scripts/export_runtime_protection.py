import argparse
import json
import shutil
import sqlite3
import ssl
import sys
from urllib.parse import urlparse
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_logs(log_dir: Path, names: list[str], days: int | None) -> list[dict]:
    cutoff = datetime.now().astimezone() - timedelta(days=days) if days else None
    rows: list[dict] = []
    for name in names:
        path = log_dir / f"{name}.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                created = datetime.fromisoformat(str(row.get("created_at", "")))
                if cutoff and created < cutoff:
                    continue
                rows.append(row)
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    return rows


def _percentile(values: list[int], ratio: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * ratio))]


def _operational_snapshot(backup_dir: Path, public_base: str = "") -> dict[str, object]:
    backups = sorted(backup_dir.glob("resume-coach-*.sqlite3"), key=lambda item: item.stat().st_mtime, reverse=True) if backup_dir.exists() else []
    backup_age_hours = round((datetime.now().timestamp() - backups[0].stat().st_mtime) / 3600, 1) if backups else None
    database_path = ROOT / "backend" / "data" / "resume_coach.db"
    database_integrity = "missing"
    if database_path.exists():
        connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
        try:
            database_integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            connection.close()
    disk = shutil.disk_usage(ROOT / "backend")
    certificate_days = None
    host = urlparse(public_base).hostname if public_base else None
    if host:
        try:
            context = ssl.create_default_context()
            with context.wrap_socket(__import__("socket").create_connection((host, 443), timeout=4), server_hostname=host) as sock:
                expires = datetime.strptime(sock.getpeercert()["notAfter"], "%b %d %H:%M:%S %Y %Z")
                certificate_days = (expires - datetime.utcnow()).days
        except (OSError, KeyError, ValueError):
            certificate_days = "unavailable"
    return {
        "backup_age_hours": backup_age_hours,
        "database_integrity": database_integrity,
        "disk_used_percent": round((disk.used / max(1, disk.total)) * 100, 1),
        "certificate_days": certificate_days,
    }


def build_report(log_dir: Path, days: int | None = None, *, backup_dir: Path | None = None, public_base: str = "") -> str:
    log_bytes = sum(path.stat().st_size for path in log_dir.glob("*.jsonl*") if path.is_file()) if log_dir.exists() else 0
    runtime = _read_logs(log_dir, ["runtime"], days)
    queue = _read_logs(log_dir, ["generation_queue"], days)
    security = _read_logs(log_dir, ["security_events"], days)
    llm = _read_logs(log_dir, ["llm_usage"], days)
    completed = [row for row in runtime if row.get("event_name") == "request_completed"]
    attempts = [row for row in queue if row.get("event_name") == "generation_admission"]
    successes = [row for row in queue if row.get("event_name") == "generation_task_succeeded"]
    failures = [row for row in runtime if row.get("event_name") == "generation_task_failed"]
    elapsed = [int(row.get("elapsed_ms") or 0) for row in successes if row.get("elapsed_ms")]
    queue_positions = [int(row.get("queue_position") or 0) for row in attempts]
    queue_waits = [int(row.get("queue_wait_ms") or 0) for row in queue if row.get("event_name") == "generation_task_started"]
    concurrency_peak = max((int(row.get("active_count") or 0) for row in attempts), default=0)
    queue_full_count = sum(row.get("status") == "full" for row in attempts)
    security_counts = Counter(str(row.get("event_name") or "unknown") for row in security)
    input_tokens = sum(int(row.get("input_tokens") or 0) for row in llm)
    output_tokens = sum(int(row.get("output_tokens") or 0) for row in llm)
    cost = sum(float(row.get("estimated_cost_cny") or 0) for row in llm)
    timeout_count = sum("timeout" in str(row.get("error_type") or "").lower() for row in runtime + security + llm)
    redis_degraded_count = sum(str(row.get("event_name") or "").startswith("redis_degraded") for row in security)
    unauthorized_count = sum(row.get("event_name") in {"unauthorized_generation_result", "unauthorized_file_access"} for row in security)
    invalid_download_count = sum(row.get("event_name") == "invalid_download_token" for row in security)
    budget_notice_count = sum(row.get("event_name") == "daily_budget_threshold_reached" for row in security)
    budget_block_count = sum(row.get("event_name") == "daily_budget_reached" for row in security)
    rate_limit_count = sum(row.get("event_name") == "generation_rate_limited" for row in security)
    cleanup_rows = [row for row in runtime if row.get("event_name") == "data_retention_completed"]
    operations = _operational_snapshot(backup_dir or ROOT / "backend" / "backups", public_base)
    success_rate = len(successes) / max(1, len(successes) + len(failures))
    lines = [
        "# Resume Coach 运行与防护报告",
        "",
        f"- 生成日期：{date.today().isoformat()}",
        f"- 统计范围：最近{days}天" if days else "- 统计范围：全部可用结构化日志",
        "",
        "## 运行情况",
        "",
        f"- HTTP完成请求：{len(completed)}",
        f"- 结构化日志占用：{log_bytes / 1024 / 1024:.2f} MB",
        f"- 生成准入记录：{len(attempts)}",
        f"- 生成成功：{len(successes)}",
        f"- 生成失败：{len(failures)}",
        f"- 生成成功率：{success_rate:.1%}",
        f"- 生成耗时P50：{int(median(elapsed)) if elapsed else 0} ms",
        f"- 生成耗时P90：{_percentile(elapsed, 0.9)} ms",
        f"- 记录到的最高排队位置：{max(queue_positions, default=0)}",
        f"- 排队等待P50：{int(median(queue_waits)) if queue_waits else 0} ms",
        f"- 排队等待P90：{_percentile(queue_waits, 0.9)} ms",
        f"- 并发峰值：{concurrency_peak}",
        f"- 队列满次数：{queue_full_count}",
        "",
        "## 模型资源",
        "",
        f"- 模型调用记录：{len(llm)}",
        f"- 输入Token：{input_tokens}",
        f"- 输出Token：{output_tokens}",
        f"- 估算成本：{cost:.4f}元",
        f"- 模型或任务超时：{timeout_count}",
        "",
        "## 防护事件",
        "",
        f"- Redis降级事件：{redis_degraded_count}",
        f"- 越权访问：{unauthorized_count}",
        f"- 无效或过期下载凭证：{invalid_download_count}",
        f"- 预算提醒/高优先级告警：{budget_notice_count}",
        f"- 预算熔断：{budget_block_count}",
        f"- 限流命中或预计命中：{rate_limit_count}",
        "",
        "## 数据与恢复",
        "",
        f"- 最近备份距今：{operations['backup_age_hours']}小时" if operations["backup_age_hours"] is not None else "- 最近备份：暂无",
        f"- 数据库完整性：{operations['database_integrity']}",
        f"- 磁盘使用率：{operations['disk_used_percent']}%",
        f"- HTTPS证书剩余天数：{operations['certificate_days']}" if operations["certificate_days"] is not None else "- HTTPS证书剩余天数：未检查",
        f"- 数据清理执行次数：{len(cleanup_rows)}",
    ]
    if security_counts:
        lines.extend(f"- {name}：{count}" for name, count in security_counts.most_common())
    else:
        lines.append("- 暂无对应日志")
    lines.extend([
        "",
        "## 隐私说明",
        "",
        "本报告仅使用脱敏运行指标，不包含用户完整输入、Prompt、简历正文、Cookie、下载Token、API Key或原始IP。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", type=Path, default=ROOT / "backend" / "logs")
    parser.add_argument("--out", type=Path, default=ROOT / "backend" / "reports")
    parser.add_argument("--days", type=int)
    parser.add_argument("--backups", type=Path, default=ROOT / "backend" / "backups")
    parser.add_argument("--public-base", default="")
    args = parser.parse_args()
    if args.logs.resolve() == (ROOT / "backend" / "logs").resolve():
        from backend.app.services.structured_log_service import cleanup_structured_logs
        cleanup_structured_logs()
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"runtime-protection-{date.today().isoformat()}.md"
    path.write_text(build_report(args.logs, args.days, backup_dir=args.backups, public_base=args.public_base), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
