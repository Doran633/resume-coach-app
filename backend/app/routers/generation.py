from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services.generation_service import GenerationServiceError, create_generation


router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate", response_model=schemas.GenerateResponse)
def generate(payload: schemas.GenerateRequest, db: Session = Depends(get_db)):
    if len(payload.raw_input.strip()) < 10:
        raise HTTPException(status_code=400, detail="请至少输入 10 个字符的经历描述。")
    try:
        return create_generation(db, payload)
    except GenerationServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
