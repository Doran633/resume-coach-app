from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services.event_service import record_event


router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("")
def create_event(payload: schemas.EventCreate, request: Request, db: Session = Depends(get_db)):
    row = record_event(db, payload, user_agent=request.headers.get("user-agent"))
    return {"ok": True, "event_id": row.id}
