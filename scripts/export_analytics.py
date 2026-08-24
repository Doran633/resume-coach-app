import argparse
import csv
import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT_DIR / "backend" / "data" / "resume_coach.db"
DEFAULT_OUT = ROOT_DIR / "backend" / "reports"
DEFAULT_JSONL_LOG = ROOT_DIR / "backend" / "logs" / "llm_calls.jsonl"
DEFAULT_FALLBACK_LOG = ROOT_DIR / "backend" / "logs" / "resume_section_fallback.jsonl"
EVENT_NAMES = [
    "visit_home",
    "submit_experience",
    "generate_success",
    "generate_failed",
    "view_claim_risk",
    "copy_result",
    "generate_docx",
    "download_docx",
    "submit_feedback",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Export Resume Coach analytics reports.")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite database path.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory.")
    parser.add_argument("--days", type=int, default=None, help="Only include recent N days.")
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def beijing_now_text() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def to_beijing_text(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return (parsed + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")


def parse_log_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def day_stamp() -> str:
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def truncate(text: str | None, limit: int = 120) -> str:
    if not text:
        return ""
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "..."


def pct(numerator: int | float, denominator: int | float) -> str:
    if not denominator:
        return "0.0%"
    return f"{numerator / denominator * 100:.1f}%"


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type='table' and name=?",
        (table,),
    ).fetchone()
    return row is not None


def where_clause(alias: str, cutoff: datetime | None) -> tuple[str, list[Any]]:
    if not cutoff:
        return "", []
    return f" where {alias}.created_at >= ?", [cutoff.isoformat(sep=" ")]


def count_rows(conn: sqlite3.Connection, table: str, cutoff: datetime | None = None) -> int:
    if not table_exists(conn, table):
        return 0
    where, params = where_clause(table, cutoff)
    return int(conn.execute(f"select count(*) from {table}{where}", params).fetchone()[0])


def count_rows_since(conn: sqlite3.Connection, table: str, column: str, cutoff: datetime | None = None) -> int:
    if not table_exists(conn, table):
        return 0
    if not cutoff:
        return int(conn.execute(f"select count(*) from {table}").fetchone()[0])
    return int(
        conn.execute(
            f"select count(*) from {table} where {column} >= ?",
            (cutoff.isoformat(sep=" "),),
        ).fetchone()[0]
    )


def distribution(conn: sqlite3.Connection, table: str, column: str, cutoff: datetime | None = None) -> list[tuple[str, int]]:
    if not table_exists(conn, table):
        return []
    where, params = where_clause(table, cutoff)
    rows = conn.execute(
        f"""
        select coalesce({column}, '[空]') as label, count(*) as total
        from {table}
        {where}
        group by label
        order by total desc, label asc
        """,
        params,
    ).fetchall()
    return [(str(row["label"]), int(row["total"])) for row in rows]


def event_counts(conn: sqlite3.Connection, cutoff: datetime | None) -> Counter:
    counts = Counter()
    if not table_exists(conn, "events"):
        return counts
    where, params = where_clause("events", cutoff)
    rows = conn.execute(
        f"select event_name, count(*) as total from events{where} group by event_name",
        params,
    ).fetchall()
    counts.update({row["event_name"]: int(row["total"]) for row in rows})
    return counts


def export_events_csv(conn: sqlite3.Connection, path: Path, cutoff: datetime | None) -> int:
    if not table_exists(conn, "events"):
        return 0
    where = ""
    params: list[Any] = []
    if cutoff:
        where = "where e.created_at >= ?"
        params.append(cutoff.isoformat(sep=" "))
    rows = conn.execute(
        f"""
        select
            e.id,
            coalesce(au.anonymous_id, '') as anonymous_user_id,
            e.session_id,
            e.event_name,
            e.target_role,
            e.mode,
            e.packaging_level,
            e.created_at as created_at_utc
        from events e
        left join anonymous_users au on au.id = e.anonymous_user_id
        {where}
        order by e.id asc
        """,
        params,
    ).fetchall()
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["id", "anonymous_user_id", "session_id", "event_name", "target_role", "mode", "packaging_level", "created_at_beijing"])
        for row in rows:
            writer.writerow(
                [
                    row["id"],
                    row["anonymous_user_id"],
                    row["session_id"],
                    row["event_name"],
                    row["target_role"],
                    row["mode"],
                    row["packaging_level"],
                    to_beijing_text(row["created_at_utc"]),
                ]
            )
    return len(rows)


def export_inputs_csv(conn: sqlite3.Connection, path: Path, cutoff: datetime | None) -> int:
    if not table_exists(conn, "experience_inputs"):
        return 0
    where = ""
    params: list[Any] = []
    if cutoff:
        where = "where ei.created_at >= ?"
        params.append(cutoff.isoformat(sep=" "))
    rows = conn.execute(
        f"""
        select
            ei.id,
            coalesce(au.anonymous_id, '') as anonymous_user_id,
            ei.session_id,
            ei.target_role,
            ei.mode,
            ei.packaging_level,
            ei.experience_type,
            length(coalesce(ei.raw_input, '')) as raw_input_length,
            ei.created_at as created_at_utc
        from experience_inputs ei
        left join anonymous_users au on au.id = ei.anonymous_user_id
        {where}
        order by ei.id asc
        """,
        params,
    ).fetchall()
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["id", "anonymous_user_id", "session_id", "target_role", "mode", "packaging_level", "experience_type", "raw_input_length", "created_at_beijing"])
        for row in rows:
            writer.writerow(
                [
                    row["id"],
                    row["anonymous_user_id"],
                    row["session_id"],
                    row["target_role"],
                    row["mode"],
                    row["packaging_level"],
                    row["experience_type"],
                    row["raw_input_length"],
                    to_beijing_text(row["created_at_utc"]),
                ]
            )
    return len(rows)


def load_llm_logs_from_jsonl(path: Path, cutoff: datetime | None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    logs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff and item.get("created_at"):
            parsed = parse_log_datetime(item.get("created_at"))
            if parsed and parsed < cutoff:
                continue
        logs.append(item)
    return logs


def llm_stats(conn: sqlite3.Connection, cutoff: datetime | None) -> dict[str, Any]:
    rows = []
    if table_exists(conn, "llm_call_logs"):
        where, params = where_clause("llm_call_logs", cutoff)
        rows = conn.execute(
            f"""
            select model, mode, latency_ms, success, error_message, created_at
            from llm_call_logs
            {where}
            order by id asc
            """,
            params,
        ).fetchall()
    logs = [dict(row) for row in rows]
    if not logs:
        logs = load_llm_logs_from_jsonl(DEFAULT_JSONL_LOG, cutoff)

    total = len(logs)
    success = sum(1 for row in logs if int(row.get("success") or 0) == 1)
    failed = total - success
    latencies = [int(row["latency_ms"]) for row in logs if row.get("latency_ms") not in [None, ""]]
    model_counts = Counter(str(row.get("model") or "[空]") for row in logs)
    errors = Counter(truncate(row.get("error_message"), 100) for row in logs if row.get("error_message"))
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else 0,
        "model_counts": model_counts,
        "errors": errors,
    }


def load_fallback_logs(path: Path, cutoff: datetime | None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    logs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if cutoff:
            parsed = parse_log_datetime(item.get("created_at"))
            if parsed and parsed < cutoff:
                continue
        logs.append(item)
    return logs


def list_counter(logs: list[dict[str, Any]], key: str) -> Counter:
    counts = Counter()
    for item in logs:
        value = item.get(key)
        if isinstance(value, list):
            counts.update(str(part) for part in value if part)
        elif value:
            counts[str(value)] += 1
    return counts


def fallback_stats(cutoff: datetime | None) -> dict[str, Any]:
    logs = load_fallback_logs(DEFAULT_FALLBACK_LOG, cutoff)
    triggered = [item for item in logs if bool(item.get("resume_fallback_triggered", item.get("changed")))]
    stage_counts = Counter(str(item.get("stage") or "unknown") for item in triggered)
    return {
        "log_exists": DEFAULT_FALLBACK_LOG.exists(),
        "logs": logs,
        "total": len(logs),
        "triggered": len(triggered),
        "trigger_rate": pct(len(triggered), len(logs)),
        "stage_counts": stage_counts,
        "section_counts": list_counter(triggered, "fallback_sections"),
        "reason_counts": list_counter(triggered, "fallback_reasons"),
        "source_counts": list_counter(triggered, "source_fields"),
        "recent": list(reversed(triggered[-5:])),
    }


def recent_feedback(conn: sqlite3.Connection, cutoff: datetime | None) -> list[sqlite3.Row]:
    if not table_exists(conn, "feedback"):
        return []
    where, params = where_clause("feedback", cutoff)
    return conn.execute(
        f"""
        select model_comparison, value_choice, comment, created_at
        from feedback
        {where}
        order by id desc
        limit 10
        """,
        params,
    ).fetchall()


def avg_completeness(conn: sqlite3.Connection, cutoff: datetime | None) -> float:
    if not table_exists(conn, "generation_results"):
        return 0
    where, params = where_clause("generation_results", cutoff)
    row = conn.execute(
        f"select avg(completeness_score) as avg_score from generation_results{where}",
        params,
    ).fetchone()
    return round(float(row["avg_score"] or 0), 1)


def md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(item) for item in row) + " |")
    return lines


def write_summary(conn: sqlite3.Connection, path: Path, cutoff: datetime | None, days: int | None, event_total: int, input_total: int) -> None:
    counts = event_counts(conn, cutoff)
    users = count_rows_since(conn, "anonymous_users", "first_seen_at", cutoff)
    sessions = count_rows_since(conn, "sessions", "started_at", cutoff)
    generation_total = count_rows(conn, "generation_results", cutoff)
    feedback_total = count_rows(conn, "feedback", cutoff)
    llm = llm_stats(conn, cutoff)
    fallback = fallback_stats(cutoff)

    visit = counts["visit_home"]
    submit = counts["submit_experience"]
    success = counts["generate_success"]
    docx = counts["generate_docx"]

    lines = [
        "# Resume Coach Analytics Report",
        "",
        f"生成时间：{beijing_now_text()}（北京时间）",
        f"统计时间范围：{'最近 ' + str(days) + ' 天' if days else '全部数据'}",
        "时间显示：北京时间（UTC+8）",
        "",
        "## 1. 总览",
        "",
        f"- 匿名用户数：{users}",
        f"- 会话数：{sessions}",
        f"- 总事件数：{event_total}",
        f"- 经历提交数：{input_total}",
        f"- 生成结果数：{generation_total}",
        f"- 平均信息完整度：{avg_completeness(conn, cutoff)}",
        f"- DOCX 生成数：{counts['generate_docx']}",
        f"- 反馈数：{feedback_total}",
        "",
        "## 2. 核心事件",
        "",
        *md_table(["事件", "次数"], [[name, counts[name]] for name in EVENT_NAMES]),
        "",
        "## 3. 核心漏斗",
        "",
        *md_table(
            ["阶段", "数量", "转化率"],
            [
                ["访问首页", visit, "100.0%" if visit else "0.0%"],
                ["提交经历", submit, pct(submit, visit)],
                ["生成成功", success, pct(success, submit)],
                ["生成 DOCX", docx, pct(docx, success)],
                ["提交反馈", counts["submit_feedback"], pct(counts["submit_feedback"], success)],
            ],
        ),
        "",
        "## 4. 目标岗位分布",
        "",
        *md_table(["目标岗位", "次数"], [[label, total] for label, total in distribution(conn, "experience_inputs", "target_role", cutoff)] or [["暂无", 0]]),
        "",
        "## 5. 包装强度分布",
        "",
        *md_table(["包装强度", "次数"], [[label, total] for label, total in distribution(conn, "experience_inputs", "packaging_level", cutoff)] or [["暂无", 0]]),
        "",
        "## 6. 经历类型分布",
        "",
        *md_table(["经历类型", "次数"], [[label, total] for label, total in distribution(conn, "experience_inputs", "experience_type", cutoff)] or [["暂无", 0]]),
        "",
        "## 7. 反馈结果",
        "",
        "### 相比大模型效果",
        "",
        *md_table(["选项", "次数"], [[label, total] for label, total in distribution(conn, "feedback", "model_comparison", cutoff)] or [["暂无", 0]]),
        "",
        "### 价格接受度",
        "",
        *md_table(["选项", "次数"], [[label, total] for label, total in distribution(conn, "feedback", "value_choice", cutoff)] or [["暂无", 0]]),
        "",
        "## 8. LLM 调用情况",
        "",
        *md_table(
            ["指标", "值"],
            [
                ["调用次数", llm["total"]],
                ["成功次数", llm["success"]],
                ["失败次数", llm["failed"]],
                ["平均耗时 ms", llm["avg_latency_ms"]],
            ],
        ),
        "",
        "### 模型分布",
        "",
        *md_table(["模型", "次数"], [[label, total] for label, total in llm["model_counts"].most_common()] or [["暂无", 0]]),
        "",
        "### 错误摘要",
        "",
        *md_table(["错误", "次数"], [[label, total] for label, total in llm["errors"].most_common(10)] or [["暂无", 0]]),
        "",
        "## 9. Resume Fallback 监控",
        "",
    ]

    if fallback["log_exists"]:
        lines.extend(
            [
                *md_table(
                    ["指标", "值"],
                    [
                        ["fallback 调用次数", fallback["total"]],
                        ["fallback 触发次数", fallback["triggered"]],
                        ["fallback 触发率", fallback["trigger_rate"]],
                        ["generation 阶段触发次数", fallback["stage_counts"].get("generation", 0)],
                        ["docx_export 阶段触发次数", fallback["stage_counts"].get("docx_export", 0)],
                    ],
                ),
                "",
                "### fallback_sections 分布",
                "",
                *md_table(["section", "次数"], [[label, total] for label, total in fallback["section_counts"].most_common()] or [["暂无", 0]]),
                "",
                "### fallback_reasons 分布",
                "",
                *md_table(["reason", "次数"], [[label, total] for label, total in fallback["reason_counts"].most_common()] or [["暂无", 0]]),
                "",
                "### source_fields 分布",
                "",
                *md_table(["source", "次数"], [[label, total] for label, total in fallback["source_counts"].most_common()] or [["暂无", 0]]),
                "",
                "### 最近 fallback 摘录",
                "",
            ]
        )
        if fallback["recent"]:
            lines.extend(
                f"- {item.get('created_at', '')}｜generation_result_id={item.get('generation_result_id')}｜stage={item.get('stage', 'unknown')}｜sections={','.join(item.get('fallback_sections') or [])}｜reasons={','.join(item.get('fallback_reasons') or [])}"
                for item in fallback["recent"]
            )
        else:
            lines.append("- 暂无 fallback 触发记录")
    else:
        lines.append("- 暂无 fallback 日志")

    lines.extend(
        [
            "",
            "## 10. 最近反馈摘录",
        "",
    ]
    )

    feedback_rows = recent_feedback(conn, cutoff)
    if feedback_rows:
        for row in feedback_rows:
            lines.append(f"- {to_beijing_text(row['created_at'])}｜{row['model_comparison']}｜{row['value_choice']}｜{truncate(row['comment']) or '无补充'}")
    else:
        lines.append("- 暂无反馈")

    lines.extend(
        [
            "",
            "## 11. 隐私说明",
            "",
            "- 本报告不会导出用户原始经历全文。",
            "- inputs CSV 仅包含输入长度、岗位、包装强度、经历类型等元信息。",
            "- 反馈摘录最多保留 120 字。",
            "- fallback 监控只统计触发原因、补全 section、来源字段和 generation_result_id，不输出用户原始输入或完整推荐版本。",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    args = parse_args()
    db_path = Path(args.db)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    cutoff = utc_now() - timedelta(days=args.days) if args.days else None
    stamp = day_stamp()
    summary_path = out_dir / f"analytics-summary-{stamp}.md"
    events_path = out_dir / f"analytics-events-{stamp}.csv"
    inputs_path = out_dir / f"analytics-inputs-{stamp}.csv"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        event_total = export_events_csv(conn, events_path, cutoff)
        input_total = export_inputs_csv(conn, inputs_path, cutoff)
        write_summary(conn, summary_path, cutoff, args.days, event_total, input_total)
    finally:
        conn.close()

    print(f"summary: {summary_path}")
    print(f"events: {events_path}")
    print(f"inputs: {inputs_path}")


if __name__ == "__main__":
    main()
