import hashlib
import hmac
import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..config import get_settings


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = threading.Lock()
_ALLOWED_STREAMS = {"runtime", "generation_queue", "security_events", "llm_usage"}
_SENSITIVE_KEYS = {
    "raw_input", "prompt", "result", "resume", "content", "cookie", "token",
    "api_key", "authorization", "file_path", "exception", "traceback", "ip",
}
_MAX_LOG_BYTES = 10 * 1024 * 1024
_COMMON_FIELDS = {
    "request_id": "",
    "attempt_id": "",
    "anonymous_id_hash": "",
    "ip_hash": "",
    "stage": "",
    "status": "",
    "elapsed_ms": 0,
    "error_type": "",
}


def stable_hash(value: str | None, *, purpose: str) -> str:
    if not value:
        return ""
    settings = get_settings()
    secret = settings.ip_hash_secret.encode("utf-8")
    digest = hmac.new(secret, f"{purpose}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:20]


def _safe_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered in _SENSITIVE_KEYS or any(part in lowered for part in ("raw_input", "prompt", "cookie", "secret", "api_key")):
        return "[redacted]"
    if isinstance(value, str):
        value = re.sub(r"(?i)bearer\s+[a-z0-9._~+/-]+", "Bearer [redacted]", value)
        return value[:512]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_safe_value(key, item) for item in value[:30]]
    if isinstance(value, dict):
        return {str(k): _safe_value(str(k), v) for k, v in list(value.items())[:50]}
    return str(value)[:256]


def write_structured_log(stream: str, event_name: str, **fields: Any) -> None:
    if stream not in _ALLOWED_STREAMS:
        raise ValueError(f"Unsupported log stream: {stream}")
    payload = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "event_name": event_name,
        **_COMMON_FIELDS,
        **{key: _safe_value(key, value) for key, value in fields.items()},
    }
    try:
        with _LOCK:
            path = LOG_DIR / f"{stream}.jsonl"
            if path.exists() and path.stat().st_size >= _MAX_LOG_BYTES:
                stamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d%H%M%S")
                path.replace(LOG_DIR / f"{stream}.jsonl.{stamp}")
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        return


def cleanup_structured_logs(now: datetime | None = None) -> dict[str, int]:
    settings = get_settings()
    current = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    removed = 0
    checked = 0
    for path in LOG_DIR.glob("*.jsonl.*"):
        checked += 1
        retention = settings.security_log_retention_days if "security" in path.name or "llm" in path.name else settings.log_retention_days
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=ZoneInfo("Asia/Shanghai"))
        if modified < current - timedelta(days=retention):
            path.unlink(missing_ok=True)
            removed += 1
    return {"checked": checked, "removed": removed}
