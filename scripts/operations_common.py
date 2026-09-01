from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from scripts.observability_common import BEIJING, parse_time, write_json


STATUS_RANK = {"healthy": 0, "observe": 0, "warning": 1, "critical": 2}


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def report_age_hours(payload: dict[str, Any], *, now: datetime | None = None) -> float | None:
    created = parse_time(payload.get("created_at"))
    if created is None:
        return None
    return ((now or datetime.now(BEIJING)) - created).total_seconds() / 3600


def worst_status(statuses: list[str], default: str = "healthy") -> str:
    return max(statuses, key=lambda item: STATUS_RANK.get(item, 0), default=default)


def write_report_pair(out_dir: Path, stem: str, payload: dict[str, Any], markdown: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = write_json(out_dir / f"{stem}.json", payload)
    markdown_path = out_dir / f"{stem}.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    return json_path, markdown_path


@contextmanager
def exclusive_operation_lock(path: Path, *, stale_after_seconds: int = 6 * 60 * 60) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        age = datetime.now().timestamp() - path.stat().st_mtime
        if age <= stale_after_seconds:
            raise RuntimeError(f"operation lock is active: {path}")
        path.unlink(missing_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"operation lock is active: {path}") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\ncreated_at={datetime.now(BEIJING).isoformat()}\n".encode())
        os.close(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        path.unlink(missing_ok=True)
