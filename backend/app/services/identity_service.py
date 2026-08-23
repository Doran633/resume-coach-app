from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models


def get_or_create_anonymous_user(
    db: Session,
    anonymous_id: str,
    source: str | None = None,
    user_agent: str | None = None,
) -> models.AnonymousUser:
    user = db.query(models.AnonymousUser).filter_by(anonymous_id=anonymous_id).first()
    if user:
        user.last_seen_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user

    user = models.AnonymousUser(
        anonymous_id=anonymous_id,
        source=source,
        user_agent=user_agent,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        return user
    except IntegrityError:
        db.rollback()
        user = db.query(models.AnonymousUser).filter_by(anonymous_id=anonymous_id).first()
        if not user:
            raise
        user.last_seen_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user


def ensure_session(db: Session, user: models.AnonymousUser, session_id: str) -> models.SessionRecord:
    record = (
        db.query(models.SessionRecord)
        .filter_by(anonymous_user_id=user.id, session_id=session_id)
        .first()
    )
    if record:
        return record
    record = models.SessionRecord(anonymous_user_id=user.id, session_id=session_id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
