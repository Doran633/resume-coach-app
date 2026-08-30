import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from .. import schemas
from ..config import get_settings
from ..database import SessionLocal
from .generation_service import GenerationServiceError, create_generation, get_generation_payload
from .resource_protection_service import resource_protection
from .structured_log_service import write_structured_log


@dataclass
class GenerationTaskState:
    attempt_id: str
    owner_hash: str
    status: str
    queue_position: int = 0
    generation_result_id: int | None = None
    experience_input_id: int | None = None
    error_code: str = ""
    user_message: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0


class GenerationTaskManager:
    def __init__(self) -> None:
        settings = get_settings()
        self.settings = settings
        self._executor = ThreadPoolExecutor(
            max_workers=settings.max_concurrent_generations + settings.max_generation_queue_size,
            thread_name_prefix="resume-generation",
        )
        self._states: dict[str, GenerationTaskState] = {}
        self._lock = threading.RLock()

    def _redis_key(self, attempt_id: str) -> str:
        return f"rc:generation:attempt:{attempt_id}"

    def _save(self, state: GenerationTaskState) -> None:
        state.updated_at = time.time()
        client = resource_protection._redis
        if client:
            try:
                client.setex(self._redis_key(state.attempt_id), self.settings.generation_task_ttl_seconds, json.dumps(asdict(state)))
            except Exception:
                pass
        with self._lock:
            self._states[state.attempt_id] = state

    def get(self, attempt_id: str) -> GenerationTaskState | None:
        client = resource_protection._redis
        if client:
            try:
                raw = client.get(self._redis_key(attempt_id))
                if raw:
                    return GenerationTaskState(**json.loads(raw))
            except Exception:
                pass
        with self._lock:
            return self._states.get(attempt_id)

    def submit(self, request: schemas.GenerateRequest, owner_hash: str) -> GenerationTaskState:
        attempt_id = request.attempt_id or ""
        existing = self.get(attempt_id)
        if existing:
            if existing.owner_hash != owner_hash:
                raise PermissionError("attempt owner mismatch")
            write_structured_log("security_events", "duplicate_attempt", attempt_id=attempt_id, anonymous_id_hash=owner_hash)
            return existing

        if not self._claim_owner(owner_hash, attempt_id):
            return GenerationTaskState(
                attempt_id=attempt_id, owner_hash=owner_hash, status="failed",
                error_code="GENERATION_ALREADY_RUNNING",
                user_message="当前简历正在生成，请耐心等待。",
                created_at=time.time(), updated_at=time.time(),
            )

        admission = resource_protection.admit(attempt_id)
        if admission.status == "full":
            state = GenerationTaskState(
                attempt_id=attempt_id, owner_hash=owner_hash, status="failed",
                error_code="GENERATION_QUEUE_FULL",
                user_message="当前生成任务较多，请稍后再试。",
                created_at=time.time(),
            )
            self._save(state)
            self._release_owner(owner_hash, attempt_id)
            return state

        state = GenerationTaskState(
            attempt_id=attempt_id,
            owner_hash=owner_hash,
            status=admission.status,
            queue_position=admission.queue_position,
            created_at=time.time(),
        )
        self._save(state)
        self._executor.submit(self._run, request.model_copy(deep=True), owner_hash)
        return state

    def _run(self, request: schemas.GenerateRequest, owner_hash: str) -> None:
        attempt_id = request.attempt_id or ""
        started = time.perf_counter()
        deadline = time.time() + self.settings.generation_task_ttl_seconds
        while time.time() < deadline:
            admission = resource_protection.promote(attempt_id)
            state = self.get(attempt_id)
            if not state or state.owner_hash != owner_hash:
                resource_protection.release(attempt_id)
                self._release_owner(owner_hash, attempt_id)
                return
            if admission.status == "running":
                state.status = "running"
                state.queue_position = 0
                self._save(state)
                write_structured_log(
                    "generation_queue", "generation_task_started", attempt_id=attempt_id,
                    anonymous_id_hash=owner_hash,
                    queue_wait_ms=int((time.time() - state.created_at) * 1000),
                )
                break
            if admission.status == "missing":
                state.status = "expired"
                state.error_code = "GENERATION_EXPIRED"
                state.user_message = "生成任务已过期，请重新提交。"
                self._save(state)
                self._release_owner(owner_hash, attempt_id)
                return
            state.queue_position = admission.queue_position
            self._save(state)
            time.sleep(0.4)
        else:
            state = self.get(attempt_id)
            if state:
                state.status = "expired"
                state.error_code = "GENERATION_EXPIRED"
                state.user_message = "排队等待时间过长，请重新提交。"
                self._save(state)
            resource_protection.release(attempt_id)
            self._release_owner(owner_hash, attempt_id)
            return

        stop_heartbeat = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(attempt_id, stop_heartbeat), daemon=True)
        heartbeat.start()
        db = SessionLocal()
        try:
            result = create_generation(db, request)
            state = self.get(attempt_id)
            if state:
                state.status = "succeeded"
                state.generation_result_id = result.generation_result_id
                state.experience_input_id = result.experience_input_id
                self._save(state)
            write_structured_log(
                "generation_queue", "generation_task_succeeded", attempt_id=attempt_id,
                anonymous_id_hash=owner_hash, elapsed_ms=int((time.perf_counter() - started) * 1000),
            )
        except GenerationServiceError as exc:
            messages = {
                "MODEL_TIMEOUT": "模型响应超时，请稍后重试。",
                "DAILY_BUDGET_REACHED": "今日生成容量已达到上限，请稍后再试。",
            }
            self._fail(
                attempt_id, owner_hash, exc.code,
                messages.get(exc.code, "本次生成没有成功，请稍后重试。"),
                type(exc).__name__, started,
            )
        except Exception as exc:
            self._fail(attempt_id, owner_hash, "GENERATION_FAILED", "生成服务暂时不可用，请稍后重试。", type(exc).__name__, started)
        finally:
            db.close()
            stop_heartbeat.set()
            heartbeat.join(timeout=1)
            resource_protection.release(attempt_id)
            self._release_owner(owner_hash, attempt_id)

    def _heartbeat(self, attempt_id: str, stop: threading.Event) -> None:
        interval = max(10, self.settings.generation_lease_seconds // 3)
        while not stop.wait(interval):
            resource_protection.renew(attempt_id)

    def _fail(self, attempt_id: str, owner_hash: str, code: str, message: str, error_type: str, started: float) -> None:
        state = self.get(attempt_id)
        if state:
            state.status = "failed"
            state.error_code = code
            state.user_message = message
            self._save(state)
        write_structured_log(
            "runtime", "generation_task_failed", attempt_id=attempt_id,
            anonymous_id_hash=owner_hash, error_type=error_type,
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

    def _claim_owner(self, owner_hash: str, attempt_id: str) -> bool:
        client = resource_protection._redis
        if client:
            try:
                key = f"rc:generation:owner:{owner_hash}"
                current = client.get(key)
                if current == attempt_id:
                    return True
                return bool(client.set(key, attempt_id, ex=self.settings.generation_task_ttl_seconds, nx=True))
            except Exception:
                pass
        with self._lock:
            return not any(
                state.owner_hash == owner_hash and state.status in {"queued", "running"}
                for state in self._states.values()
            )

    def _release_owner(self, owner_hash: str, attempt_id: str) -> None:
        client = resource_protection._redis
        if client:
            try:
                key = f"rc:generation:owner:{owner_hash}"
                if client.get(key) == attempt_id:
                    client.delete(key)
            except Exception:
                pass

    def response(self, state: GenerationTaskState) -> schemas.GenerationTaskResponse:
        generation = None
        if state.status == "succeeded" and state.generation_result_id:
            db = SessionLocal()
            try:
                payload = get_generation_payload(db, state.generation_result_id)
                if payload:
                    generation = schemas.GenerateResponse(
                        experience_input_id=state.experience_input_id or 0,
                        generation_result_id=state.generation_result_id,
                        result=payload,
                    )
            finally:
                db.close()
        return schemas.GenerationTaskResponse(
            attempt_id=state.attempt_id,
            status=state.status,
            queue_position=state.queue_position,
            error_code=state.error_code or None,
            user_message=state.user_message or None,
            generation=generation,
        )


generation_task_manager = GenerationTaskManager()
