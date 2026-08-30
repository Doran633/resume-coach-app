import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from fastapi import Request, Response
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings
from .structured_log_service import stable_hash, write_structured_log


@dataclass(frozen=True)
class RequestIdentity:
    anonymous_id: str
    anonymous_id_hash: str
    ip_hash: str


def _signature(secret: str, value: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def sign_anonymous_id(anonymous_id: str) -> str:
    settings = get_settings()
    return f"{anonymous_id}.{_signature(settings.anonymous_cookie_secret, anonymous_id)}"


def verify_anonymous_token(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    anonymous_id, supplied = token.rsplit(".", 1)
    if not anonymous_id or len(anonymous_id) > 80:
        return None
    expected = _signature(get_settings().anonymous_cookie_secret, anonymous_id)
    return anonymous_id if hmac.compare_digest(supplied, expected) else None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    trusted_proxy = request.client and request.client.host in {"127.0.0.1", "::1"}
    if trusted_proxy and forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def resolve_request_identity(request: Request, response: Response) -> RequestIdentity:
    settings = get_settings()
    token = request.cookies.get(settings.anonymous_cookie_name)
    anonymous_id = verify_anonymous_token(token)
    if not anonymous_id:
        if token:
            write_structured_log("security_events", "invalid_anonymous_cookie", request_id=getattr(request.state, "request_id", ""))
        anonymous_id = f"anon_{secrets.token_urlsafe(24)}"
        response.set_cookie(
            settings.anonymous_cookie_name,
            sign_anonymous_id(anonymous_id),
            max_age=settings.anonymous_cookie_max_age,
            httponly=True,
            secure=settings.production,
            samesite="lax",
            path="/",
        )
    return RequestIdentity(
        anonymous_id=anonymous_id,
        anonymous_id_hash=stable_hash(anonymous_id, purpose="anonymous"),
        ip_hash=stable_hash(_client_ip(request), purpose="ip"),
    )


def owns_generation_result(db: Session, result_id: int, anonymous_user_id: int) -> bool:
    return (
        db.query(models.GenerationResult.id)
        .join(models.ExperienceInput, models.ExperienceInput.id == models.GenerationResult.experience_input_id)
        .filter(
            models.GenerationResult.id == result_id,
            models.ExperienceInput.anonymous_user_id == anonymous_user_id,
        )
        .first()
        is not None
    )


def owns_generated_file(db: Session, file_id: int, anonymous_user_id: int) -> bool:
    return (
        db.query(models.GeneratedFile.id)
        .join(models.GenerationResult, models.GenerationResult.id == models.GeneratedFile.generation_result_id)
        .join(models.ExperienceInput, models.ExperienceInput.id == models.GenerationResult.experience_input_id)
        .filter(
            models.GeneratedFile.id == file_id,
            models.ExperienceInput.anonymous_user_id == anonymous_user_id,
        )
        .first()
        is not None
    )


def create_download_token(file_id: int, anonymous_id: str, expires_at: int | None = None) -> str:
    settings = get_settings()
    expiry = expires_at or int(time.time()) + settings.download_token_ttl_seconds
    nonce = secrets.token_urlsafe(12)
    owner_hash = stable_hash(anonymous_id, purpose="download-owner")
    body = f"{file_id}:{owner_hash}:{expiry}:{nonce}"
    return f"{expiry}.{nonce}.{_signature(settings.download_signing_secret, body)}"


def verify_download_token(file_id: int, anonymous_id: str, token: str) -> tuple[bool, str]:
    try:
        expiry_text, nonce, supplied = token.split(".", 2)
        expiry = int(expiry_text)
    except (TypeError, ValueError):
        return False, "invalid"
    if expiry < int(time.time()):
        return False, "expired"
    owner_hash = stable_hash(anonymous_id, purpose="download-owner")
    body = f"{file_id}:{owner_hash}:{expiry}:{nonce}"
    expected = _signature(get_settings().download_signing_secret, body)
    return (True, "ok") if hmac.compare_digest(supplied, expected) else (False, "invalid")
