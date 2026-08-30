import shutil
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import models
from .config import get_settings
from .database import DATA_DIR, engine, ensure_v01_schema
from .routers import events, feedback, files, generation, identity, privacy
from .services.resource_protection_service import resource_protection
from .services.structured_log_service import cleanup_structured_logs, write_structured_log


models.Base.metadata.create_all(bind=engine)
ensure_v01_schema()

settings = get_settings()
app = FastAPI(title="Resume Coach App", version="0.7.2")

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=None if settings.production else r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_security_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip()[:96] or f"req_{uuid.uuid4().hex}"
    request.state.request_id = request_id
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > settings.max_request_body_bytes:
        write_structured_log(
            "security_events", "request_body_too_large", request_id=request_id,
            input_length=int(content_length), limit=settings.max_request_body_bytes,
        )
        return JSONResponse(
            status_code=413,
            content={"detail": {"error_code": "REQUEST_TOO_LARGE", "user_message": "请求内容过大，请精简后重试。"}},
            headers={"X-Request-ID": request_id},
        )
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        write_structured_log(
            "runtime", "request_failed", request_id=request_id, endpoint=request.url.path,
            error_type=type(exc).__name__, elapsed_ms=int((time.perf_counter() - started) * 1000),
        )
        raise
    response.headers["X-Request-ID"] = request_id
    write_structured_log(
        "runtime", "request_completed", request_id=request_id, endpoint=request.url.path,
        status_code=response.status_code, elapsed_ms=int((time.perf_counter() - started) * 1000),
    )
    return response

app.include_router(events.router)
app.include_router(identity.router)
app.include_router(generation.router)
app.include_router(files.router)
app.include_router(feedback.router)
app.include_router(privacy.router)


@app.on_event("startup")
def log_startup():
    cleanup_structured_logs()
    disk = shutil.disk_usage(DATA_DIR)
    write_structured_log(
        "runtime", "service_started", version="0.7.2", environment=settings.environment,
        redis_ready=resource_protection.redis_ready, degraded=resource_protection.degraded,
        disk_free_bytes=disk.free, status="ready",
    )


@app.on_event("shutdown")
def log_shutdown():
    write_structured_log("runtime", "service_stopped", version="0.7.2", status="stopped")


@app.get("/api/health/live")
def health_live():
    return {"ok": True, "version": "0.7.2"}


@app.get("/api/health/ready")
def health_ready():
    database_ready = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_ready = False
    disk = shutil.disk_usage(DATA_DIR)
    disk_ready = disk.free >= 100 * 1024 * 1024
    secrets_ready = settings.secrets_ready or not settings.production
    redis_ready = resource_protection.redis_ready or not settings.production
    ready = database_ready and disk_ready and secrets_ready and redis_ready
    return JSONResponse(
        status_code=200 if ready else 503,
        content={
            "ok": ready,
            "version": "0.7.2",
            "checks": {
                "database": database_ready,
                "redis": redis_ready,
                "disk": disk_ready,
                "secrets": secrets_ready,
            },
            "generation": resource_protection.snapshot(),
        },
    )


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.7.2"}
