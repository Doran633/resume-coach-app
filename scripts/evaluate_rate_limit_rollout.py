from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.observability_common import BEIJING, cutoff_for_hours, is_smoke_attempt, load_jsonl, write_json


def evaluate_rollout(logs_dir: Path, *, hours: int = 72) -> dict[str, Any]:
    cutoff = cutoff_for_hours(hours)
    queue = [row for row in load_jsonl(logs_dir, "generation_queue", cutoff) if not is_smoke_attempt(row.get("attempt_id"))]
    security = [row for row in load_jsonl(logs_dir, "security_events", cutoff) if not is_smoke_attempt(row.get("attempt_id"))]
    admissions = [row for row in queue if row.get("event_name") == "generation_admission"]
    rate_events = [row for row in security if row.get("event_name") == "generation_rate_limited"]
    queue_full = sum(row.get("status") == "full" for row in admissions)
    users_by_ip: dict[str, set[str]] = defaultdict(set)
    for row in [*admissions, *rate_events]:
        ip_hash = str(row.get("ip_hash") or "")
        user_hash = str(row.get("anonymous_id_hash") or "")
        if ip_hash and user_hash:
            users_by_ip[ip_hash].add(user_hash)
    shared_ips = {key: users for key, users in users_by_ip.items() if len(users) >= 3}
    affected_users = {str(row.get("anonymous_id_hash")) for row in rate_events if row.get("anonymous_id_hash")}
    all_users = {str(row.get("anonymous_id_hash")) for row in admissions if row.get("anonymous_id_hash")}
    ip_limited = [row for row in rate_events if "IP_" in str(row.get("error_type") or "").upper()]
    shared_ip_hits = sum(str(row.get("ip_hash") or "") in shared_ips for row in ip_limited)
    affected_rate = len(affected_users) / len(all_users) if all_users else None

    if len(admissions) < 20:
        recommendation = "继续观察"
        reason = "非烟测准入样本少于20次"
        status = "observe"
    elif queue_full:
        recommendation = "暂不建议启用"
        reason = "已经出现队列满，优先处理容量或重试体验"
        status = "warning"
    elif shared_ip_hits or (affected_rate is not None and affected_rate > 0.1):
        recommendation = "暂不建议启用"
        reason = "限流预计影响较多用户或存在校园共享IP误伤信号"
        status = "warning"
    elif not rate_events:
        recommendation = "可以灰度启用"
        reason = "样本充足且未观察到预计限流命中；仍建议先小流量启用"
        status = "healthy"
    else:
        recommendation = "继续观察"
        reason = "存在少量限流事件，尚不足以确认是否会误伤正常用户"
        status = "observe"
    return {
        "created_at": datetime.now(BEIJING).isoformat(),
        "hours": hours,
        "status": status,
        "recommendation": recommendation,
        "reason": reason,
        "generation_admission_count": len(admissions),
        "estimated_or_actual_rate_limit_count": len(rate_events),
        "affected_anonymous_user_count": len(affected_users),
        "affected_user_rate": round(affected_rate, 4) if affected_rate is not None else None,
        "shared_ip_group_count": len(shared_ips),
        "shared_ip_limit_hit_count": shared_ip_hits,
        "queue_full_count": queue_full,
        "dry_run_event_count": sum(bool(row.get("dry_run")) for row in rate_events),
        "raw_ip_included": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join([
        "# 限流灰度启用评估", "",
        f"- 生成时间：{report['created_at']}",
        f"- 观察窗口：{report['hours']} 小时",
        f"- 建议：{report['recommendation']}",
        f"- 原因：{report['reason']}",
        f"- 生成准入：{report['generation_admission_count']}",
        f"- 限流命中或预计命中：{report['estimated_or_actual_rate_limit_count']}",
        f"- 受影响匿名用户：{report['affected_anonymous_user_count']}",
        f"- 共享IP组：{report['shared_ip_group_count']}",
        f"- 共享IP限流信号：{report['shared_ip_limit_hit_count']}",
        f"- 队列满：{report['queue_full_count']}", "",
        "报告只使用匿名哈希聚合，未输出原始IP，也不会自动修改 RATE_LIMIT_DRY_RUN。", "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate whether rate limiting is ready for a guarded rollout.")
    parser.add_argument("--logs", type=Path, default=ROOT / "backend" / "logs")
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--out", type=Path, default=ROOT / "backend" / "reports")
    args = parser.parse_args()
    report = evaluate_rollout(args.logs, hours=args.hours)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "rate-limit-rollout-latest.json", report)
    path = args.out / "rate-limit-rollout-latest.md"
    path.write_text(render_markdown(report), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
