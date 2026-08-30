import json

from sqlalchemy.orm import Session

from .. import models, schemas
from .identity_service import ensure_session, get_or_create_anonymous_user


SENSITIVE_EVENT_KEYS = {
    "raw_input", "prompt", "result", "resume", "content", "claim", "cookie", "token",
    "authorization", "exception", "error_message", "stack", "traceback",
}


def _sanitize_event_payload(value, key: str = ""):
    if key.lower() in SENSITIVE_EVENT_KEYS or any(part in key.lower() for part in ("raw_input", "prompt", "cookie", "token")):
        return "[redacted]"
    if isinstance(value, dict):
        return {str(item_key): _sanitize_event_payload(item, str(item_key)) for item_key, item in list(value.items())[:50]}
    if isinstance(value, list):
        return [_sanitize_event_payload(item, key) for item in value[:30]]
    if isinstance(value, str):
        return value[:512]
    return value


def record_event(db: Session, event: schemas.EventCreate, user_agent: str | None = None) -> models.Event:
    user = get_or_create_anonymous_user(db, event.anonymous_user_id, user_agent=user_agent)
    ensure_session(db, user, event.session_id)
    row = models.Event(
        anonymous_user_id=user.id,
        session_id=event.session_id,
        event_name=event.event_name,
        target_role=event.target_role,
        mode=event.mode,
        packaging_level=event.packaging_level,
        payload_json=json.dumps(_sanitize_event_payload(event.payload), ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
