from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services.docx_service import create_docx
from ..services.identity_service import get_or_create_anonymous_user
from ..services.security_service import (
    create_download_token,
    owns_generated_file,
    owns_generation_result,
    resolve_request_identity,
    verify_download_token,
)
from ..services.structured_log_service import write_structured_log


router = APIRouter(prefix="/api", tags=["files"])


@router.post("/resume/docx", response_model=schemas.DocxResponse)
def generate_docx(payload: schemas.DocxCreate, request: Request, response: Response, db: Session = Depends(get_db)):
    identity = resolve_request_identity(request, response)
    user = get_or_create_anonymous_user(db, identity.anonymous_id)
    if not owns_generation_result(db, payload.generation_result_id, user.id):
        write_structured_log(
            "security_events", "unauthorized_generation_result", request_id=getattr(request.state, "request_id", ""),
            anonymous_id_hash=identity.anonymous_id_hash, generation_result_id=payload.generation_result_id,
        )
        raise HTTPException(status_code=404, detail="generation_result_id 不存在。")
    trusted_payload = payload.model_copy(update={"anonymous_user_id": identity.anonymous_id})
    docx_response = create_docx(db, trusted_payload)
    if not docx_response:
        raise HTTPException(status_code=404, detail="generation_result_id 不存在。")
    token = create_download_token(docx_response.file_id, identity.anonymous_id)
    write_structured_log(
        "runtime", "docx_generated", request_id=getattr(request.state, "request_id", ""),
        anonymous_id_hash=identity.anonymous_id_hash, generation_result_id=payload.generation_result_id,
        file_id=docx_response.file_id, status="success",
    )
    return docx_response.model_copy(update={"download_url": f"/api/files/{docx_response.file_id}?token={token}"})


@router.get("/files/{file_id}")
def download_file(file_id: int, request: Request, response: Response, token: str = Query(default=""), db: Session = Depends(get_db)):
    identity = resolve_request_identity(request, response)
    user = db.query(models.AnonymousUser).filter_by(anonymous_id=identity.anonymous_id).first()
    valid, reason = verify_download_token(file_id, identity.anonymous_id, token)
    if not valid or not user or not owns_generated_file(db, file_id, user.id):
        write_structured_log(
            "security_events", "invalid_download_token" if not valid else "unauthorized_file_access",
            request_id=getattr(request.state, "request_id", ""), anonymous_id_hash=identity.anonymous_id_hash,
            file_id=file_id, error_type=reason if not valid else "owner_mismatch",
        )
        error_code = "DOWNLOAD_TOKEN_EXPIRED" if reason == "expired" else "DOWNLOAD_TOKEN_INVALID"
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": error_code,
                "user_message": "下载链接已失效，请返回导出页重新生成下载链接。",
                "retry_after": None,
                "attempt_id": None,
            },
        )
    row = db.query(models.GeneratedFile).filter_by(id=file_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在。")
    path = Path(row.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已被删除。")
    write_structured_log(
        "runtime", "docx_downloaded", request_id=getattr(request.state, "request_id", ""),
        anonymous_id_hash=identity.anonymous_id_hash, file_id=file_id, status="success",
    )
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )
