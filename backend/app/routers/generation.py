import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Response

from .. import schemas
from ..config import get_settings
from ..services.generation_task_service import generation_task_manager
from ..services.resource_protection_service import resource_protection
from ..services.security_service import resolve_request_identity
from ..services.structured_log_service import write_structured_log


router = APIRouter(prefix="/api", tags=["generation"])


def _error(status: int, code: str, message: str, *, retry_after: int | None = None, attempt_id: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "error_code": code,
            "user_message": message,
            "retry_after": retry_after,
            "attempt_id": attempt_id,
        },
        headers={"Retry-After": str(retry_after)} if retry_after else None,
    )


def validate_raw_input(raw_input: str) -> tuple[str, int]:
    raw = raw_input.strip()
    length = len(raw)
    if length < 10:
        raise _error(400, "INPUT_TOO_SHORT", "请至少输入10个字符的经历描述。")
    if length > get_settings().max_raw_input_chars:
        raise _error(
            413, "INPUT_TOO_LARGE",
            f"当前输入超过{get_settings().max_raw_input_chars:,}字。建议保留与目标岗位最相关的经历，或分批整理后再提交。",
        )
    return raw, length


def _prepare_request(payload: schemas.GenerateRequest, request: Request, response: Response) -> tuple[schemas.GenerateRequest, str, str]:
    settings = get_settings()
    raw = payload.raw_input.strip()
    identity = resolve_request_identity(request, response)
    if len(raw) > settings.max_raw_input_chars:
        write_structured_log(
            "security_events", "input_too_large", attempt_id=payload.attempt_id or "",
            anonymous_id_hash=identity.anonymous_id_hash, ip_hash=identity.ip_hash,
            input_length=len(raw), limit=settings.max_raw_input_chars,
        )
        raise _error(
            413, "INPUT_TOO_LARGE",
            f"当前输入超过{settings.max_raw_input_chars:,}字。建议保留与目标岗位最相关的经历，或分批整理后再提交。",
            attempt_id=payload.attempt_id,
        )
    raw, _ = validate_raw_input(raw)
    attempt_id = payload.attempt_id or f"attempt_{secrets.token_urlsafe(18)}"
    trusted = payload.model_copy(update={"anonymous_user_id": identity.anonymous_id, "attempt_id": attempt_id, "raw_input": raw})
    return trusted, identity.anonymous_id_hash, identity.ip_hash


def _submit(payload: schemas.GenerateRequest, request: Request, response: Response) -> schemas.GenerationTaskResponse:
    trusted, owner_hash, ip_hash = _prepare_request(payload, request, response)
    existing = generation_task_manager.get(trusted.attempt_id or "")
    if existing:
        if existing.owner_hash != owner_hash:
            raise _error(404, "GENERATION_NOT_FOUND", "生成任务不存在。")
        return generation_task_manager.response(existing)
    availability = resource_protection.check_generation_availability()
    if not availability.allowed:
        raise _error(
            503, availability.error_code,
            "生成保护服务暂时不可用，请稍后重试。",
            retry_after=availability.retry_after, attempt_id=trusted.attempt_id,
        )
    budget = resource_protection.check_daily_budget()
    if not budget.allowed:
        raise _error(429, budget.error_code, "今日生成容量已达到上限，请稍后再试。", retry_after=budget.retry_after, attempt_id=trusted.attempt_id)
    rate = resource_protection.check_generation_rate(owner_hash, ip_hash)
    if not rate.allowed:
        message = "操作有些频繁，请稍后再试。" if rate.error_code == "USER_RATE_LIMITED" else "当前网络请求较多，请稍后再试。"
        raise _error(429, rate.error_code, message, retry_after=rate.retry_after, attempt_id=trusted.attempt_id)
    resource_protection.observe_generation_risk(owner_hash, ip_hash, trusted.raw_input)
    try:
        state = generation_task_manager.submit(trusted, owner_hash)
    except PermissionError:
        raise _error(404, "GENERATION_NOT_FOUND", "生成任务不存在。")
    return generation_task_manager.response(state)


@router.post("/generation-attempts", response_model=schemas.GenerationTaskResponse, status_code=202)
def submit_generation_attempt(payload: schemas.GenerateRequest, request: Request, response: Response):
    return _submit(payload, request, response)


@router.get("/generation-attempts/{attempt_id}", response_model=schemas.GenerationTaskResponse)
def get_generation_attempt(attempt_id: str, request: Request, response: Response):
    identity = resolve_request_identity(request, response)
    state = generation_task_manager.get(attempt_id)
    if not state or state.owner_hash != identity.anonymous_id_hash:
        raise _error(404, "GENERATION_NOT_FOUND", "生成任务不存在。")
    return generation_task_manager.response(state)


@router.post("/generate", response_model=schemas.GenerateResponse)
def generate_compatible(payload: schemas.GenerateRequest, request: Request, response: Response):
    task = _submit(payload, request, response)
    deadline = time.time() + 110
    while time.time() < deadline:
        state = generation_task_manager.get(task.attempt_id)
        if not state:
            break
        if state.status == "succeeded":
            result = generation_task_manager.response(state).generation
            if result:
                return result
        if state.status in {"failed", "expired"}:
            raise _error(502, state.error_code or "GENERATION_FAILED", state.user_message or "本次生成没有成功。", attempt_id=task.attempt_id)
        time.sleep(0.5)
    raise _error(504, "MODEL_TIMEOUT", "本次生成等待时间较长，请稍后重新尝试。", retry_after=10, attempt_id=task.attempt_id)
