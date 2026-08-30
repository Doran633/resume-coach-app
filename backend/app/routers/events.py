from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services.event_service import record_event
from ..services.security_service import resolve_request_identity


router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("")
def create_event(payload: schemas.EventCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    identity = resolve_request_identity(request, response)
    trusted = payload.model_copy(update={"anonymous_user_id": identity.anonymous_id})
    row = record_event(db, trusted, user_agent=request.headers.get("user-agent"))
    return {"ok": True, "event_id": row.id}
