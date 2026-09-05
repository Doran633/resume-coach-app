#!/usr/bin/env python3
"""List privacy-safe Semantic Commit mutation trace events."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


DEFAULT_LOG = Path(__file__).resolve().parents[1] / "backend" / "logs" / "semantic_mutation_trace.jsonl"


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
        created_at = _parse_time(str(event.get("created_at") or ""))
        if cutoff and (created_at is None or created_at < cutoff):
            continue
        selected.append(event)
    return sorted(selected, key=lambda item: (item.get("created_at", ""), item.get("sequence", 0)))


def summarize(events: list[dict]) -> dict:
    mutations = [item for item in events if item.get("event_type") == "mutation"]
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
    return {"event_count": len(events), "mutation_count": len(mutations), "first_observed": first, "events": events}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-id", type=int)
    parser.add_argument("--request-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--hours", type=float)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args()
    report = summarize(filter_events(load_events(args.log), args))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"events: {report['event_count']}; mutations: {report['mutation_count']}")
    if not report["first_observed"]:
        print("No mutations matched the selected trace range.")
        return 0
    for code, item in report["first_observed"].items():
        print(f"{code}: first={item['first_observed_stage']} severity={item['severity']} count={item['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
