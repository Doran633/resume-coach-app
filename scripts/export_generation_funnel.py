import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any



ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "backend" / "data" / "resume_coach.db"
DEFAULT_LOGS = ROOT / "backend" / "logs"
DEFAULT_OUT = ROOT / "backend" / "reports"
BEIJING = timezone(timedelta(hours=8))


def is_smoke_attempt(value: Any) -> bool:
    return str(value or "").startswith("smoke_")


def parse_args():
    parser = argparse.ArgumentParser(description="Export generation reliability funnel.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path.")
    parser.add_argument("--logs", default=str(DEFAULT_LOGS), help="Structured log directory.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Report output directory.")
    parser.add_argument("--days", type=int, default=None, help="Only include recent N days.")
    return parser.parse_args()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("select 1 from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None


def _parse_payload(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _percent(numerator: int | float, denominator: int | float) -> str:
    return f"{numerator / denominator * 100:.1f}%" if denominator else "暂无可靠口径"


def _percentile(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.5)))
    return ordered[index]


def _load_events(conn: sqlite3.Connection, cutoff: datetime | None) -> list[dict[str, Any]]:
    if not _table_exists(conn, "events"):
        return []
    rows = conn.execute(
        """
        select e.id, e.event_name, e.session_id, e.payload_json, e.created_at,
               coalesce(au.anonymous_id, '') as anonymous_id
        from events e
        left join anonymous_users au on au.id = e.anonymous_user_id
        order by e.id
        """
    ).fetchall()
    result = []
    for row in rows:
        created_at = _parse_time(row["created_at"])
        if cutoff and (not created_at or created_at < cutoff):
            continue
        result.append({
            "id": row["id"],
            "event_name": row["event_name"],
            "session_id": row["session_id"],
            "anonymous_id": row["anonymous_id"],
            "created_at": created_at,
            "payload": _parse_payload(row["payload_json"]),
        })
    return result


def _load_jsonl(path: Path, cutoff: datetime | None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            row = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        created_at = _parse_time(row.get("created_at"))
        if cutoff and (not created_at or created_at < cutoff):
            continue
        rows.append(row)
    return rows


def _count_table(conn: sqlite3.Connection, table: str, cutoff: datetime | None) -> int:
    if not _table_exists(conn, table):
        return 0
    if not cutoff:
        return int(conn.execute(f"select count(*) from {table}").fetchone()[0])
    naive_cutoff = cutoff.astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
    return int(conn.execute(f"select count(*) from {table} where created_at >= ?", (naive_cutoff,)).fetchone()[0])


def build_report(db_path: Path, logs_dir: Path, days: int | None = None) -> str:
    now = datetime.now(BEIJING)
    cutoff = now.astimezone(timezone.utc) - timedelta(days=days) if days is not None else None
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        all_events = _load_events(conn, cutoff)
        smoke_event_count = sum(
            is_smoke_attempt(event["payload"].get("attempt_id"))
            or event["event_name"] == "public_smoke_test"
            for event in all_events
        )
        events = [
            event for event in all_events
            if not is_smoke_attempt(event["payload"].get("attempt_id"))
            and event["event_name"] != "public_smoke_test"
        ]
        generation_result_count = _count_table(conn, "generation_results", cutoff)
        generated_file_count = _count_table(conn, "generated_files", cutoff)
        feedback_row_count = _count_table(conn, "feedback", cutoff)
    finally:
        conn.close()

    attempts: dict[str, dict[str, Any]] = defaultdict(lambda: {"events": [], "users": set()})
    legacy_generation_events = 0
    for event in events:
        payload = event["payload"]
        attempt_id = payload.get("attempt_id")
        if event["event_name"] in {"submit_experience", "submit_followup", "generate_success", "generate_failed"} and not attempt_id:
            legacy_generation_events += 1
        if not attempt_id:
            continue
        record = attempts[str(attempt_id)]
        record["events"].append(event)
        if event["anonymous_id"]:
            record["users"].add(event["anonymous_id"])

    event_names_by_attempt = {
        attempt_id: {event["event_name"] for event in record["events"]}
        for attempt_id, record in attempts.items()
    }
    submitted = {key for key, names in event_names_by_attempt.items() if names & {"submit_experience", "submit_followup"}}
    succeeded = {key for key, names in event_names_by_attempt.items() if "generate_success" in names}
    failed = {key for key, names in event_names_by_attempt.items() if "generate_failed" in names}
    viewed = {key for key, names in event_names_by_attempt.items() if "view_generation_result" in names}
    docx_generated_attempts = {key for key, names in event_names_by_attempt.items() if "generate_docx" in names}
    downloaded_attempts = {key for key, names in event_names_by_attempt.items() if "download_docx" in names}
    feedback_attempts = {key for key, names in event_names_by_attempt.items() if "submit_feedback" in names}

    failure_types = Counter()
    latencies = []
    for attempt_id, record in attempts.items():
        for event in record["events"]:
            if event["event_name"] == "generate_failed":
                failure_types[str(event["payload"].get("error_type") or "unknown")] += 1
            if event["event_name"] in {"generate_success", "generate_failed"}:
                elapsed = event["payload"].get("elapsed_ms")
                if isinstance(elapsed, (int, float)) and elapsed >= 0:
                    latencies.append(int(elapsed))

    all_users = {event["anonymous_id"] for event in events if event["anonymous_id"]}
    submit_users = {event["anonymous_id"] for event in events if event["event_name"] in {"submit_experience", "submit_followup"} and event["anonymous_id"]}
    success_users = {event["anonymous_id"] for event in events if event["event_name"] == "generate_success" and event["anonymous_id"]}
    docx_users = {event["anonymous_id"] for event in events if event["event_name"] == "generate_docx" and event["anonymous_id"]}

    stability_logs = _load_jsonl(logs_dir / "generation_stability.jsonl", cutoff)
    fallback_logs = _load_jsonl(logs_dir / "resume_section_fallback.jsonl", cutoff)
    stable_fallback_count = sum(bool(row.get("fallback_used")) for row in stability_logs)
    section_fallback_count = sum(
        bool(row.get("resume_fallback_triggered", row.get("changed"))) and row.get("stage") == "generation"
        for row in fallback_logs
    )

    average_latency = round(sum(latencies) / len(latencies)) if latencies else None
    period = f"最近 {days} 天" if days is not None else "全部历史数据"
    lines = [
        "# Generation Funnel Report",
        "",
        f"- 生成时间（北京时间）：{now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 统计范围：{period}",
        "- 隐私说明：报告不包含用户原始经历、推荐版本或个人信息。",
        "",
        "## 数据口径状态",
        "",
        f"- 可关联 attempt_id 数量：{len(attempts)}",
        f"- 有提交事件的生成尝试：{len(submitted)}",
        f"- 缺少 attempt_id 的历史生成相关事件：{legacy_generation_events}",
        f"- 已排除烟测事件：{smoke_event_count}",
        "- 历史事件无法可靠还原单次生成链路，不会被强行计入失败尝试。" if legacy_generation_events else "- 当前生成事件均可按 attempt_id 关联。",
        "",
        "## 请求级漏斗",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 生成尝试次数 | {len(submitted)} |",
        f"| 生成成功次数 | {len(succeeded & submitted)} |",
        f"| 生成失败次数 | {len(failed & submitted)} |",
        f"| 生成成功率 | {_percent(len(succeeded & submitted), len(submitted))} |",
        f"| 成功但未进入结果页 | {len((succeeded & submitted) - viewed)} |",
        f"| 成功但未生成 DOCX | {len((succeeded & submitted) - docx_generated_attempts)} |",
        f"| DOCX 生成尝试链路数 | {len(docx_generated_attempts)} |",
        f"| DOCX 下载尝试链路数 | {len(downloaded_attempts)} |",
        f"| 反馈提交尝试链路数 | {len(feedback_attempts)} |",
        "",
        "## 数据库业务结果",
        "",
        f"- generation_results 记录数：{generation_result_count}",
        f"- generated_files 记录数：{generated_file_count}",
        f"- feedback 记录数：{feedback_row_count}",
        "- generation_results 表示后端已保存的生成结果；generated_files 表示已生成文件，两者不能混称为“生成简历数”。",
        "",
        "## 用户级转化",
        "",
        f"- 活跃匿名用户数：{len(all_users)}",
        f"- 提交生成用户数：{len(submit_users)}",
        f"- 生成成功用户数：{len(success_users)}",
        f"- 生成 DOCX 用户数：{len(docx_users)}",
        f"- 提交用户 -> 成功用户：{_percent(len(success_users), len(submit_users))}",
        f"- 成功用户 -> DOCX 用户：{_percent(len(docx_users), len(success_users))}",
        "",
        "## 耗时与失败",
        "",
        f"- 有耗时数据的请求数：{len(latencies)}",
        f"- 平均耗时：{average_latency if average_latency is not None else '暂无'} ms",
        f"- P50：{_percentile(latencies, 0.50) if latencies else '暂无'} ms",
        f"- P90：{_percentile(latencies, 0.90) if latencies else '暂无'} ms",
        f"- 超过 35 秒：{sum(value > 35000 for value in latencies)}",
        f"- 超过 60 秒：{sum(value > 60000 for value in latencies)}",
        "",
        "### 失败类型分布",
        "",
    ]
    if failure_types:
        lines.extend(["| 类型 | 次数 |", "|---|---:|"])
        lines.extend(f"| {label} | {count} |" for label, count in failure_types.most_common())
    else:
        lines.append("暂无可关联失败记录。")
    lines.extend([
        "",
        "## Fallback 可观测性",
        "",
        f"- Stable Fallback 触发次数：{stable_fallback_count if stability_logs else '暂无对应日志'}",
        f"- Generation 阶段 Resume Section Fallback 触发次数：{section_fallback_count if fallback_logs else '暂无对应日志'}",
        "",
        "## 如何解释现有 46 次请求与 27 份简历",
        "",
        "在旧事件缺少 attempt_id 时，只能将其描述为两个独立业务计数，不能直接得出 19 次生成失败。部署本版本后，应使用“生成尝试 -> 生成成功 -> 查看结果 -> 生成 DOCX -> 下载”的关联漏斗解释转化。",
        "",
    ])
    return "\n".join(lines)


def export_report(db_path: Path, logs_dir: Path, out_dir: Path, days: int | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"generation-funnel-{datetime.now(BEIJING).strftime('%Y-%m-%d')}.md"
    path.write_text(build_report(db_path, logs_dir, days), encoding="utf-8")
    return path


def main():
    args = parse_args()
    path = export_report(Path(args.db), Path(args.logs), Path(args.out), args.days)
    print(f"report: {path}")


if __name__ == "__main__":
    main()
