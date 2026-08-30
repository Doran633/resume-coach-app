from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..services.data_lifecycle_service import delete_anonymous_user_data
from ..services.generation_task_service import generation_task_manager
from ..services.security_service import resolve_request_identity
from ..services.structured_log_service import write_structured_log


router = APIRouter(prefix="/api/privacy", tags=["privacy"])


def _normalized_origin(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _validate_request_origin(request: Request) -> None:
    supplied = request.headers.get("origin") or request.headers.get("referer", "")
    if not supplied:
        if get_settings().production:
            raise HTTPException(status_code=403, detail="请求来源无效。")
        return
    origin = _normalized_origin(supplied)
    allowed = {_normalized_origin(item) for item in get_settings().allowed_origins}
    if not origin or origin not in allowed:
        raise HTTPException(status_code=403, detail="请求来源无效。")


@router.delete("/my-data")
def delete_my_data(request: Request, response: Response, db: Session = Depends(get_db)):
    _validate_request_origin(request)
    identity = resolve_request_identity(request, response)
    if generation_task_manager.has_active_owner(identity.anonymous_id_hash):
        raise HTTPException(status_code=409, detail="当前简历仍在生成，请完成后再删除数据。")
    try:
        stats = delete_anonymous_user_data(db, identity.anonymous_id)
    except Exception as exc:
        write_structured_log(
            "security_events", "privacy_deletion_failed",
            request_id=getattr(request.state, "request_id", ""),
            anonymous_id_hash=identity.anonymous_id_hash,
            error_type=type(exc).__name__, status="failed",
        )
        raise HTTPException(status_code=500, detail="数据删除失败，请稍后重试。") from exc

    settings = get_settings()
    response.delete_cookie(
        settings.anonymous_cookie_name,
        path="/",
        secure=settings.production,
        httponly=True,
        samesite="lax",
    )
    write_structured_log(
        "security_events", "privacy_data_deleted",
        request_id=getattr(request.state, "request_id", ""),
        anonymous_id_hash=identity.anonymous_id_hash,
        status="success" if stats.files_cleanup_pending == 0 else "cleanup_pending",
        deleted_record_count=sum(value for key, value in stats.to_dict().items() if key not in {"files_removed", "files_cleanup_pending"}),
        files_removed_count=stats.files_removed,
        files_cleanup_pending_count=stats.files_cleanup_pending,
    )
    return {
        "ok": True,
        "files_cleanup_pending": stats.files_cleanup_pending,
    }
