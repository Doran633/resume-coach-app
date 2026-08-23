from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.identity_service import ensure_session, get_or_create_anonymous_user


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
def submit_feedback(payload: schemas.FeedbackCreate, db: Session = Depends(get_db)):
    user = get_or_create_anonymous_user(db, payload.anonymous_user_id)
    ensure_session(db, user, payload.session_id)
    row = models.Feedback(
        anonymous_user_id=user.id,
        session_id=payload.session_id,
        generation_result_id=payload.generation_result_id,
        model_comparison=payload.model_comparison,
        value_choice=payload.value_choice,
        comment=payload.comment,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "feedback_id": row.id}
