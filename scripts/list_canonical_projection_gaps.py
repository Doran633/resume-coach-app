#!/usr/bin/env python3
"""List privacy-safe canonical Experience-to-project projection gaps."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_LOG = Path(__file__).resolve().parents[1] / "backend" / "logs" / "canonical_projection_completeness.jsonl"


def _parse_time(value: object) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def _filter(events: list[dict], args: argparse.Namespace) -> list[dict]:
    cutoff = datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(hours=args.hours) if args.hours else None
    selected: list[dict] = []
    for event in events:
        if args.result_id is not None and str(event.get("generation_result_id")) != str(args.result_id):
            continue
        if args.request_id and event.get("request_id") != args.request_id:
            continue
        if args.attempt_id and event.get("attempt_id") != args.attempt_id:
            continue
        if args.experience_id and event.get("experience_id") != args.experience_id:
            continue
        created_at = _parse_time(event.get("created_at"))
        if cutoff and (created_at is None or created_at < cutoff):
            continue
        selected.append(event)
    return sorted(selected, key=lambda row: (str(row.get("created_at") or ""), int(row.get("sequence") or 0)))


def _advice(final: dict) -> str:
    codes = set(final.get("issue_codes") or [])
    if "PROJECTION_DROPPED_AFTER_OWNER_FREEZE" in codes:
        return "检查 Owner Freeze 后的 Presentation / final containment 前是否丢失本地 Fact binding。"
    if "OWNER_BOUND_PROJECT_WITHOUT_FACT_BINDING" in codes:
        return "项目 owner 已冻结，但没有当前 owner 的 Fact binding；检查投影附着而非重新绑定。"
    if "EXPERIENCE_WITHOUT_VISIBLE_PROJECT" in codes:
        return "该经历有 eligible Fact 却没有可交付 owner-bound 项目；检查 LLM/Slot Binding/Containment 的先后状态。"
    if "ELIGIBLE_FACT_UNPROJECTED" in codes:
        return "该经历仍有 eligible Fact 未进入已绑定项目；检查 Project Projection Completeness。"
    return "当前 owner 的投影完整；如仍有问题，请结合 Semantic Mutation Trace 查看字段级 provenance。"


def summarize(events: list[dict]) -> dict:
    owner_events = [row for row in events if row.get("event_type") == "projection_checkpoint"]
    unassigned = [row for row in events if row.get("event_type") == "unassigned_ownerless_containment"]
    grouped: dict[str, list[dict]] = {}
    for event in owner_events:
        experience_id = str(event.get("experience_id") or "")
        if experience_id:
            grouped.setdefault(experience_id, []).append(event)
    owners: list[dict] = []
    for experience_id, rows in sorted(grouped.items()):
        final = rows[-1]
        owners.append({
            "experience_id": experience_id,
            "canonical_experience_type": final.get("canonical_experience_type", ""),
            "checkpoint_count": len(rows),
            # The Observer records the first actionable post-freeze gap.  The
            # LLM checkpoint is useful context, but is deliberately not treated
            # as a binding failure before Slot Binding has run.
            "first_projection_gap_stage": final.get("first_projection_gap_stage", ""),
            "first_binding_gap_stage": final.get("first_binding_gap_stage", ""),
            "final": {
                key: final.get(key)
                for key in (
                    "eligible_claim_count", "eligible_fact_count", "high_value_fact_count",
                    "projected_fact_count", "fact_binding_count", "owner_bound_project_count",
                    "unowned_candidate_project_count", "removed_by_ownerless_containment_count",
                    "unprojected_eligible_fact_count", "issue_codes", "status", "stage",
                )
            },
            "advice": _advice(final),
        })
    return {
        "event_count": len(events),
        "owner_count": len(owners),
        "owners": owners,
        "unassigned_ownerless_events": [
            {
                "stage": row.get("stage"),
                "unowned_candidate_project_count": row.get("unowned_candidate_project_count", 0),
                "removed_by_ownerless_containment_count": row.get("removed_by_ownerless_containment_count", 0),
                "issue_codes": row.get("issue_codes", []),
            }
            for row in unassigned
        ],
    }


def _print_report(report: dict) -> None:
    print(f"events: {report['event_count']}; canonical owners: {report['owner_count']}")
    for owner in report["owners"]:
        final = owner["final"]
        print(
            f"{owner['experience_id']} ({owner['canonical_experience_type']}): "
            f"final={final['status']} stage={final['stage']} "
            f"eligible={final['eligible_fact_count']} projected={final['projected_fact_count']} "
            f"bound_projects={final['owner_bound_project_count']} "
            f"unprojected={final['unprojected_eligible_fact_count']}"
        )
        if final["issue_codes"]:
            print(f"  issues: {', '.join(final['issue_codes'])}")
            print(f"  first_projection_gap: {owner['first_projection_gap_stage'] or '-'}")
            print(f"  first_binding_gap: {owner['first_binding_gap_stage'] or '-'}")
            print(f"  investigate: {owner['advice']}")
    if report["unassigned_ownerless_events"]:
        print("unassigned ownerless candidates:")
        for row in report["unassigned_ownerless_events"]:
            print(
                f"  stage={row['stage']} candidates={row['unowned_candidate_project_count']} "
                f"removed={row['removed_by_ownerless_containment_count']}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-id", type=int)
    parser.add_argument("--request-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--hours", type=float)
    parser.add_argument("--experience-id")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()
    report = summarize(_filter(_load_events(args.log), args))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
