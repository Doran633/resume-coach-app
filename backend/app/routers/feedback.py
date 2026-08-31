from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.identity_service import ensure_session, get_or_create_anonymous_user
from ..services.security_service import owns_generation_result, resolve_request_identity
from ..services.structured_log_service import write_structured_log


router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("")
def submit_feedback(payload: schemas.FeedbackCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    identity = resolve_request_identity(request, response)
    user = get_or_create_anonymous_user(db, identity.anonymous_id)
    ensure_session(db, user, payload.session_id)
    if payload.generation_result_id and not owns_generation_result(db, payload.generation_result_id, user.id):
        raise HTTPException(status_code=404, detail="generation_result_id 不存在。")
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
    write_structured_log(
        "runtime", "feedback_submitted",
        request_id=getattr(request.state, "request_id", ""),
        anonymous_id_hash=identity.anonymous_id_hash,
        generation_result_id=payload.generation_result_id,
        feedback_id=row.id, status="success",
    )
    return {"ok": True, "feedback_id": row.id}
