import re
import uuid


REQUEST_ID_PATTERN = re.compile(r"req_[a-zA-Z0-9_-]{8,80}\Z")


def is_valid_request_id(value: str | None) -> bool:
    return bool(value and REQUEST_ID_PATTERN.fullmatch(value))


def resolve_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    return candidate if is_valid_request_id(candidate) else f"req_{uuid.uuid4().hex}"
