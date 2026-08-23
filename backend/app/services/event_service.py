import json

from sqlalchemy.orm import Session

from .. import models, schemas
from .identity_service import ensure_session, get_or_create_anonymous_user


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
        payload_json=json.dumps(event.payload, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
