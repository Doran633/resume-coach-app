#!/usr/bin/env python3
"""List privacy-safe Semantic Commit mutation trace events."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_LOG = Path(__file__).resolve().parents[1] / "backend" / "logs" / "semantic_mutation_trace.jsonl"
OBSERVER_ONLY_CODES = {
    "LEXICAL_WITHHELD_OVERLAP",
    "CANONICAL_OWNER_CORRECTION",
    "PROVENANCE_METADATA_COARSENED",
    "PERSISTENCE_METADATA_STRIP",
    "SUPPORTED_PRESENTATION_REWRITE",
}


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def filter_events(events: list[dict], args: argparse.Namespace) -> list[dict]:
    cutoff = datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(hours=args.hours) if args.hours else None
    selected: list[dict] = []
    for event in events:
        if args.result_id is not None and str(event.get("generation_result_id")) != str(args.result_id):
            continue
        if args.request_id and event.get("request_id") != args.request_id:
            continue
        if args.attempt_id and event.get("attempt_id") != args.attempt_id:
            continue
        if args.project_trace_key and event.get("project_trace_key") != args.project_trace_key:
            continue
        created_at = _parse_time(str(event.get("created_at") or ""))
        if cutoff and (created_at is None or created_at < cutoff):
            continue
        selected.append(event)
    return sorted(selected, key=lambda item: (item.get("created_at", ""), item.get("sequence", 0)))


def summarize(events: list[dict]) -> dict:
    mutations = [item for item in events if item.get("event_type") == "mutation"]
    checkpoints = [item for item in events if item.get("event_type") == "checkpoint"]
    first: dict[str, dict] = {}
    for event in mutations:
        code = str(event.get("mutation_code") or "")
        if code and code not in first:
            first[code] = {
                "first_observed_stage": event.get("stage", ""),
                "severity": event.get("severity", "observe"),
                "count": 0,
            }
        if code:
            first[code]["count"] += 1
    final_checkpoint = checkpoints[-1] if checkpoints else {}
    final_active_counts = dict(final_checkpoint.get("aggregate_counts") or {})
    final_active_critical_codes = sorted(
        code for code in final_active_counts
        if code not in OBSERVER_ONLY_CODES
        and any(
            item.get("mutation_code") == code and item.get("severity") == "critical"
            for item in mutations
        )
    )
    transitions = [
        item for item in mutations
        if item.get("mutation_code") in {
            "OWNER_CHANGED", "CANONICAL_OWNER_CORRECTION", "FACT_OWNER_SCOPE_VIOLATION",
        }
    ]
    return {
        "event_count": len(events),
        "mutation_count": len(mutations),
        "first_observed": first,
        "final_active_counts": final_active_counts,
        "final_active_critical_codes": final_active_critical_codes,
        "evidence_status": "investigation_ready" if final_active_critical_codes else "observe_or_resolved",
        "transitions": transitions,
        "events": events,
    }


def _print_summary(report: dict, *, show_transitions: bool, final_only: bool) -> None:
    print(f"events: {report['event_count']}; mutations: {report['mutation_count']}")
    print(f"evidence_status: {report['evidence_status']}")
    if report["final_active_counts"]:
        print("final_active:")
        for code, count in sorted(report["final_active_counts"].items()):
            print(f"  {code}: {count}")
    else:
        print("final_active: none")
    if not final_only:
        print("first_observed:")
        if not report["first_observed"]:
            print("  none")
        for code, item in report["first_observed"].items():
            label = "observer_only" if code in OBSERVER_ONLY_CODES else item["severity"]
            print(f"  {code}: first={item['first_observed_stage']} severity={label} count={item['count']}")
    if report["final_active_critical_codes"]:
        print("root_cause_candidates:")
        for code in report["final_active_critical_codes"]:
            stage = report["first_observed"].get(code, {}).get("first_observed_stage", "")
            print(f"  {code}: first={stage}")
    else:
        print("root_cause_candidates: none; no final critical observer signal")
    if show_transitions:
        print("owner_scope_transitions:")
        if not report["transitions"]:
            print("  none")
        for item in report["transitions"]:
            print(
                "  "
                f"{item.get('mutation_code')} stage={item.get('stage')} "
                f"project={item.get('project_trace_key') or '-'} "
                f"before={item.get('owner_before') or '-'} after={item.get('owner_after') or '-'} "
                f"reason={item.get('transition_reason') or '-'}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-id", type=int)
    parser.add_argument("--request-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--hours", type=float)
    parser.add_argument("--project-trace-key")
    parser.add_argument("--show-transitions", action="store_true")
    parser.add_argument("--final-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()
    report = summarize(filter_events(load_events(args.log), args))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    _print_summary(report, show_transitions=args.show_transitions, final_only=args.final_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
