from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


BEIJING = timezone(timedelta(hours=8))
SEVERITY_RANK = {"observe": 0, "warning": 1, "critical": 2}


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=BEIJING) if parsed.tzinfo is None else parsed.astimezone(BEIJING)


def load_jsonl(logs_dir: Path, name: str, cutoff: datetime | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(logs_dir.glob(f"{name}.jsonl*")):
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except (ValueError, json.JSONDecodeError):
                continue
            if not isinstance(row, dict):
                continue
            created_at = parse_time(row.get("created_at"))
            if cutoff and (not created_at or created_at < cutoff):
                continue
            rows.append(row)
    return rows


def is_smoke_attempt(value: Any) -> bool:
    return str(value or "").startswith("smoke_")


def percentile(values: Iterable[int | float], ratio: float) -> float | None:
    ordered = sorted(float(value) for value in values if value is not None and value >= 0)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def average(values: Iterable[int | float]) -> float | None:
    items = [float(value) for value in values]
    return sum(items) / len(items) if items else None


def cutoff_for_hours(hours: int) -> datetime:
    return datetime.now(BEIJING) - timedelta(hours=max(1, hours))


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def safe_short_commit(value: Any) -> str:
    text = str(value or "unknown").strip()
    return text[:8] if text else "unknown"
