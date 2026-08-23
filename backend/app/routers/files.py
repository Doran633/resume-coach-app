from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.docx_service import create_docx


router = APIRouter(prefix="/api", tags=["files"])


@router.post("/resume/docx", response_model=schemas.DocxResponse)
def generate_docx(payload: schemas.DocxCreate, db: Session = Depends(get_db)):
    response = create_docx(db, payload)
    if not response:
        raise HTTPException(status_code=404, detail="generation_result_id 不存在。")
    return response


@router.get("/files/{file_id}")
def download_file(file_id: int, db: Session = Depends(get_db)):
    row = db.query(models.GeneratedFile).filter_by(id=file_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在。")
    path = Path(row.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已被删除。")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )
