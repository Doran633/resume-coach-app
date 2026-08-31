from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.observability_common import BEIJING, SEVERITY_RANK, cutoff_for_hours, load_jsonl, parse_time


QUALITY_STREAMS = {
    "resume_delivery_quality_gate": "delivery_quality_gate",
    "fact_coverage": "fact_coverage",
    "experience_boundary": "experience_boundary",
    "resume_section_fallback": "resume_section_fallback",
}


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


MAX_LINK_DISTANCE_SECONDS = 10


def _links(logs_dir: Path, cutoff) -> tuple[dict[str, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    by_attempt: dict[str, dict[str, Any]] = defaultdict(dict)
    by_result: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in load_jsonl(logs_dir, "generation_queue", cutoff) + load_jsonl(logs_dir, "runtime", cutoff):
        attempt_id = str(row.get("attempt_id") or "")
        result_id = _integer(row.get("generation_result_id"))
        link = {
            "request_id": str(row.get("request_id") or ""),
            "attempt_id": attempt_id,
            "generation_result_id": result_id,
            "file_id": _integer(row.get("file_id")),
            "created_at": row.get("created_at"),
        }
        if attempt_id:
            by_attempt[attempt_id].update({key: value for key, value in link.items() if value not in (None, "")})
        if result_id is not None:
            by_result[result_id].append({key: value for key, value in link.items() if value not in (None, "")})
    for attempt_id, link in by_attempt.items():
        result_id = link.get("generation_result_id")
        if isinstance(result_id, int):
            by_result[result_id].append(dict(link))
    return by_attempt, by_result


def _nearest_result_link(
    by_result: dict[int, list[dict[str, Any]]],
    result_id: int | None,
    created_at: Any,
) -> dict[str, Any]:
    if result_id is None:
        return {}
    target = parse_time(created_at)
    if target is None:
        return {}
    ranked: list[tuple[float, dict[str, Any]]] = []
    for link in by_result.get(result_id, []):
        linked_at = parse_time(link.get("created_at"))
        if linked_at is None:
            continue
        distance = abs((linked_at - target).total_seconds())
        if distance <= MAX_LINK_DISTANCE_SECONDS:
            ranked.append((distance, link))
    return min(ranked, key=lambda item: item[0])[1] if ranked else {}


def _incident_from_quality(name: str, row: dict[str, Any]) -> tuple[list[str], str, bool, bool] | None:
    if name == "resume_delivery_quality_gate":
        issues = row.get("issues") if isinstance(row.get("issues"), list) else []
        codes = sorted({str(item.get("issue_code")) for item in issues if isinstance(item, dict) and item.get("issue_code")})
        unresolved = int(row.get("unresolved_issue_count") or 0) > 0 or not bool(row.get("gate_passed", True))
        critical = int(row.get("critical_issue_count") or 0) > 0
        if not codes and not unresolved:
            return None
        return codes or ["DELIVERY_QUALITY_GATE_FAILED"], "critical" if critical and unresolved else "warning", bool(row.get("repaired_issue_count")), unresolved
    if name == "fact_coverage":
        values = list((row.get("coverage_by_experience_id") or {}).values())
        coverage = sum(float(value) for value in values) / len(values) if values else 1.0
        if coverage >= 0.8:
            return None
        return ["LOW_HIGH_VALUE_FACT_COVERAGE"], "warning", bool(row.get("restored_fact_count")), True
    if name == "experience_boundary":
        count = int(row.get("contamination_fixed_count") or 0)
        if count <= 0:
            return None
        return ["CROSS_EXPERIENCE_FACT"], "warning", True, False
    if name == "resume_section_fallback":
        triggered = bool(row.get("resume_fallback_triggered", row.get("changed")))
        if not triggered:
            return None
        return ["RESUME_SECTION_FALLBACK"], "warning", True, False
    return None


def collect_incidents(
    logs_dir: Path,
    *,
    hours: int = 24,
    minimum_severity: str = "warning",
    request_id: str = "",
    result_id: int | None = None,
) -> list[dict[str, Any]]:
    cutoff = cutoff_for_hours(hours)
    by_attempt, by_result = _links(logs_dir, cutoff)
    incidents: list[dict[str, Any]] = []
    runtime_rows = load_jsonl(logs_dir, "runtime", cutoff)
    for row in runtime_rows:
        if row.get("event_name") not in {"generation_task_failed", "request_failed"}:
            continue
        attempt = str(row.get("attempt_id") or "")
        link = {**by_attempt.get(attempt, {}), **row}
        incidents.append({
            "created_at": row.get("created_at"),
            "request_id": str(link.get("request_id") or ""),
            "attempt_id": attempt,
            "generation_result_id": _integer(link.get("generation_result_id")),
            "file_id": _integer(link.get("file_id")),
            "stage": "generation" if row.get("event_name") == "generation_task_failed" else str(row.get("endpoint") or "runtime"),
            "issue_codes": [str(row.get("error_code") or row.get("error_type") or "REQUEST_FAILED")],
            "severity": "critical" if row.get("event_name") == "generation_task_failed" else "warning",
            "repaired": False,
            "unresolved": True,
            "legacy": not bool(link.get("request_id")),
        })
    for name, stage in QUALITY_STREAMS.items():
        for row in load_jsonl(logs_dir, name, cutoff):
            parsed = _incident_from_quality(name, row)
            if not parsed:
                continue
            codes, severity, repaired, unresolved = parsed
            rid = _integer(row.get("generation_result_id"))
            link = _nearest_result_link(by_result, rid, row.get("created_at"))
            incidents.append({
                "created_at": row.get("created_at"),
                "request_id": str(link.get("request_id") or ""),
                "attempt_id": str(link.get("attempt_id") or ""),
                "generation_result_id": rid,
                "file_id": _integer(link.get("file_id")),
                "stage": str(row.get("stage") or stage),
                "issue_codes": codes,
                "severity": severity,
                "repaired": repaired,
                "unresolved": unresolved,
                "legacy": not bool(link.get("request_id")),
            })
    for row in load_jsonl(logs_dir, "generation_stability", cutoff):
        rid = _integer(row.get("generation_result_id"))
        quality_codes = [str(value) for value in row.get("unresolved_quality_issue_codes", []) if value]
        codes = list(quality_codes)
        fallback = bool(row.get("resume_section_fallback_triggered"))
        if not codes and not fallback:
            continue
        if fallback:
            codes.append("RESUME_SECTION_FALLBACK")
        critical_count = int(row.get("unresolved_critical_issue_count") or 0)
        link = _nearest_result_link(by_result, rid, row.get("created_at"))
        incidents.append({
            "created_at": row.get("created_at"),
            "request_id": str(link.get("request_id") or ""),
            "attempt_id": str(row.get("attempt_id") or link.get("attempt_id") or ""),
            "generation_result_id": rid,
            "file_id": _integer(link.get("file_id")),
            "stage": "generation_summary",
            "issue_codes": sorted(set(codes)),
            "severity": "critical" if critical_count else "warning",
            "repaired": fallback and not quality_codes,
            "unresolved": bool(quality_codes),
            "legacy": not bool(link.get("request_id")),
            "smoke": str(row.get("attempt_id") or "").startswith("smoke_"),
        })
    threshold = SEVERITY_RANK.get(minimum_severity, 1)
    filtered = [item for item in incidents if SEVERITY_RANK.get(item["severity"], 0) >= threshold]
    if request_id:
        filtered = [item for item in filtered if item.get("request_id") == request_id]
    if result_id is not None:
        filtered = [item for item in filtered if item.get("generation_result_id") == result_id]
    return sorted(filtered, key=lambda item: str(item.get("created_at") or ""), reverse=True)


def render_text(incidents: list[dict[str, Any]]) -> str:
    if not incidents:
        return "No matching quality incidents."
    lines = ["created_at | severity | request_id | attempt_id | result_id | file_id | stage | issue_codes | status"]
    for item in incidents:
        status = "unresolved" if item["unresolved"] else "repaired" if item["repaired"] else "observed"
        request = item["request_id"] or "legacy"
        lines.append(
            f"{item['created_at']} | {item['severity']} | {request} | {item['attempt_id'] or '-'} | "
            f"{item['generation_result_id'] or '-'} | {item['file_id'] or '-'} | {item['stage']} | "
            f"{','.join(item['issue_codes'])} | {status}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="List recent privacy-safe resume quality incidents.")
    parser.add_argument("--logs", type=Path, default=ROOT / "backend" / "logs")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--severity", choices=["warning", "critical"], default="warning")
    parser.add_argument("--request-id", default="")
    parser.add_argument("--result-id", type=int)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    incidents = collect_incidents(
        args.logs, hours=args.hours, minimum_severity=args.severity,
        request_id=args.request_id, result_id=args.result_id,
    )
    output = json.dumps(incidents, ensure_ascii=False, indent=2) if args.json else render_text(incidents)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
        print(args.out)
    else:
        print(output)


if __name__ == "__main__":
    main()
