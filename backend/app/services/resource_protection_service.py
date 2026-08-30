import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..config import get_settings
from .structured_log_service import stable_hash, write_structured_log

try:
    import redis
except ImportError:  # pragma: no cover - exercised on minimal local installs
    redis = None


RATE_LUA = """
local value = redis.call('INCR', KEYS[1])
if value == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return value
"""

ADMIT_LUA = """
local now = tonumber(ARGV[1])
local lease_until = tonumber(ARGV[2])
local max_active = tonumber(ARGV[3])
local max_queue = tonumber(ARGV[4])
local attempt = ARGV[5]
local queue_cutoff = tonumber(ARGV[6])
local key_ttl = tonumber(ARGV[7])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', queue_cutoff)
local active_score = redis.call('ZSCORE', KEYS[1], attempt)
if active_score then
  redis.call('EXPIRE', KEYS[1], key_ttl)
  redis.call('EXPIRE', KEYS[2], key_ttl)
  return {'running', 0}
end
local queued_score = redis.call('ZSCORE', KEYS[2], attempt)
if queued_score then
  local rank = redis.call('ZRANK', KEYS[2], attempt)
  redis.call('EXPIRE', KEYS[1], key_ttl)
  redis.call('EXPIRE', KEYS[2], key_ttl)
  return {'queued', rank + 1}
end
if redis.call('ZCARD', KEYS[1]) < max_active then
  redis.call('ZADD', KEYS[1], lease_until, attempt)
  redis.call('EXPIRE', KEYS[1], key_ttl)
  redis.call('EXPIRE', KEYS[2], key_ttl)
  return {'running', 0}
end
if redis.call('ZCARD', KEYS[2]) >= max_queue then
  redis.call('EXPIRE', KEYS[1], key_ttl)
  redis.call('EXPIRE', KEYS[2], key_ttl)
  return {'full', -1}
end
redis.call('ZADD', KEYS[2], now, attempt)
local rank = redis.call('ZRANK', KEYS[2], attempt)
redis.call('EXPIRE', KEYS[1], key_ttl)
redis.call('EXPIRE', KEYS[2], key_ttl)
return {'queued', rank + 1}
"""

PROMOTE_LUA = """
local now = tonumber(ARGV[1])
local lease_until = tonumber(ARGV[2])
local max_active = tonumber(ARGV[3])
local attempt = ARGV[4]
local queue_cutoff = tonumber(ARGV[5])
local key_ttl = tonumber(ARGV[6])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', queue_cutoff)
if redis.call('ZSCORE', KEYS[1], attempt) then
  redis.call('EXPIRE', KEYS[1], key_ttl)
  redis.call('EXPIRE', KEYS[2], key_ttl)
  return {'running', 0}
end
local rank = redis.call('ZRANK', KEYS[2], attempt)
if not rank then
  redis.call('EXPIRE', KEYS[1], key_ttl)
  redis.call('EXPIRE', KEYS[2], key_ttl)
  return {'missing', -1}
end
if rank == 0 and redis.call('ZCARD', KEYS[1]) < max_active then
  redis.call('ZREM', KEYS[2], attempt)
  redis.call('ZADD', KEYS[1], lease_until, attempt)
  redis.call('EXPIRE', KEYS[1], key_ttl)
  redis.call('EXPIRE', KEYS[2], key_ttl)
  return {'running', 0}
end
redis.call('EXPIRE', KEYS[1], key_ttl)
redis.call('EXPIRE', KEYS[2], key_ttl)
return {'queued', rank + 1}
"""


@dataclass(frozen=True)
class ProtectionDecision:
    allowed: bool
    error_code: str = ""
    retry_after: int = 0
    dry_run: bool = False


@dataclass(frozen=True)
class AdmissionDecision:
    status: str
    queue_position: int = 0


class ResourceProtection:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._lock = threading.RLock()
        self._counters: dict[str, tuple[int, float]] = {}
        self._active: dict[str, float] = {}
        self._queue: list[str] = []
        self._sets: dict[str, tuple[set[str], float]] = {}
        self._redis: Any = None
        self._redis_degraded = False
        self._redis_failure_since: float | None = None
        if self.settings.redis_url and redis is not None:
            try:
                client = redis.Redis.from_url(self.settings.redis_url, decode_responses=True, socket_timeout=1)
                client.ping()
                self._redis = client
            except Exception:
                self._mark_redis_degraded("connection_failed")
        elif self.settings.production:
            self._mark_redis_degraded(
                "redis_dependency_missing" if redis is None else "redis_not_configured",
            )

    @property
    def redis_ready(self) -> bool:
        return self._redis is not None

    @property
    def degraded(self) -> bool:
        return self._redis_degraded or (self.settings.production and not self._redis)

    @property
    def sustained_degraded(self) -> bool:
        if not self.settings.production or not self.degraded:
            return False
        since = self._redis_failure_since or time.time()
        return time.time() - since >= self.settings.redis_degraded_max_seconds

    @property
    def effective_max_concurrent(self) -> int:
        configured = min(
            self.settings.max_concurrent_generations,
            self.settings.model_max_concurrent_calls,
        )
        return 1 if self.degraded else max(1, configured)

    def _mark_redis_degraded(self, error_type: str) -> None:
        first_failure = self._redis_failure_since is None
        self._redis_degraded = True
        self._redis_failure_since = self._redis_failure_since or time.time()
        if first_failure:
            write_structured_log(
                "security_events", "redis_degraded", error_type=error_type,
                status="conservative_mode",
            )

    def check_generation_availability(self) -> ProtectionDecision:
        if not self.sustained_degraded:
            return ProtectionDecision(True)
        write_structured_log(
            "security_events", "redis_degraded_generation_paused",
            status="blocked", error_type="sustained_redis_failure",
        )
        return ProtectionDecision(False, "PROTECTION_DEGRADED", 60)

    def _increment(self, key: str, ttl: int) -> int:
        if self._redis:
            try:
                return int(self._redis.eval(RATE_LUA, 1, key, ttl))
            except Exception:
                self._mark_redis_degraded("rate_limit_failed")
        now = time.time()
        with self._lock:
            value, expires = self._counters.get(key, (0, now + ttl))
            if expires <= now:
                value, expires = 0, now + ttl
            value += 1
            self._counters[key] = (value, expires)
            return value

    def check_generation_rate(self, anonymous_hash: str, ip_hash: str) -> ProtectionDecision:
        limits = [
            (f"rc:rate:user:{anonymous_hash}:5m", 300, self.settings.user_limit_5m, "USER_RATE_LIMITED"),
            (f"rc:rate:user:{anonymous_hash}:1h", 3600, self.settings.user_limit_1h, "USER_RATE_LIMITED"),
            (f"rc:rate:user:{anonymous_hash}:1d", 86400, self.settings.user_limit_1d, "USER_RATE_LIMITED"),
            (f"rc:rate:ip:{ip_hash}:5m", 300, self.settings.ip_limit_5m, "IP_RATE_LIMITED"),
            (f"rc:rate:ip:{ip_hash}:1h", 3600, self.settings.ip_limit_1h, "IP_RATE_LIMITED"),
            (f"rc:rate:ip:{ip_hash}:1d", 86400, self.settings.ip_limit_1d, "IP_RATE_LIMITED"),
        ]
        blocked: tuple[str, int] | None = None
        for key, ttl, maximum, code in limits:
            if self._increment(key, ttl) > maximum and blocked is None:
                blocked = (code, ttl)
        if not blocked:
            return ProtectionDecision(True)
        code, retry_after = blocked
        write_structured_log(
            "security_events", "generation_rate_limited", anonymous_id_hash=anonymous_hash,
            ip_hash=ip_hash, error_type=code, retry_after=retry_after,
            dry_run=self.settings.rate_limit_dry_run,
        )
        return ProtectionDecision(
            self.settings.rate_limit_dry_run, code, retry_after, self.settings.rate_limit_dry_run,
        )

    def observe_generation_risk(self, anonymous_hash: str, ip_hash: str, raw_input: str) -> None:
        input_fingerprint = stable_hash(" ".join(raw_input.lower().split()), purpose="input-fingerprint")
        identities_on_ip = self._observe_member(
            f"rc:risk:ip-identities:{ip_hash}", anonymous_hash, 600,
        )
        identities_for_input = self._observe_member(
            f"rc:risk:input-identities:{input_fingerprint}", anonymous_hash, 600,
        )
        if identities_on_ip >= 40:
            write_structured_log(
                "security_events", "shared_ip_identity_spike",
                anonymous_id_hash=anonymous_hash, ip_hash=ip_hash,
                status="observe", identity_count=identities_on_ip,
                stage="captcha_candidate",
            )
        if identities_for_input >= 8:
            write_structured_log(
                "security_events", "repeated_input_across_identities",
                anonymous_id_hash=anonymous_hash, ip_hash=ip_hash,
                status="observe", identity_count=identities_for_input,
                stage="captcha_candidate",
            )

    def _observe_member(self, key: str, member: str, ttl: int) -> int:
        if self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.sadd(key, member)
                pipe.expire(key, ttl)
                pipe.scard(key)
                result = pipe.execute()
                return int(result[-1])
            except Exception:
                self._mark_redis_degraded("risk_signal_failed")
        now = time.time()
        with self._lock:
            members, expires = self._sets.get(key, (set(), now + ttl))
            if expires <= now:
                members, expires = set(), now + ttl
            members.add(member)
            self._sets[key] = (members, expires)
            return len(members)

    def check_daily_budget(self) -> ProtectionDecision:
        date_key = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        calls = self._read_number(f"rc:budget:calls:{date_key}")
        tokens = self._read_number(f"rc:budget:tokens:{date_key}")
        cost = self._read_number(f"rc:budget:cost_micro:{date_key}") / 1_000_000
        blocked = (
            calls >= self.settings.max_daily_llm_calls
            or tokens >= self.settings.max_daily_llm_tokens
            or cost >= self.settings.max_daily_llm_cost_cny
        )
        if blocked:
            write_structured_log(
                "security_events", "daily_budget_reached", status="blocked", daily_calls=calls,
                daily_tokens=tokens, estimated_cost_cny=cost,
            )
            return ProtectionDecision(False, "DAILY_BUDGET_REACHED", 3600)
        return ProtectionDecision(True)

    def _read_number(self, key: str) -> int:
        if self._redis:
            try:
                return int(float(self._redis.get(key) or 0))
            except Exception:
                self._mark_redis_degraded("budget_read_failed")
        with self._lock:
            value, expires = self._counters.get(key, (0, 0))
            return int(value) if expires > time.time() else 0

    def record_llm_usage(self, *, model: str, input_tokens: int, output_tokens: int, cost_cny: float, latency_ms: int, success: bool, attempt_id: str = "") -> None:
        date_key = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        self._increment(f"rc:budget:calls:{date_key}", 172800)
        self._add_value(f"rc:budget:tokens:{date_key}", input_tokens + output_tokens, 172800)
        self._add_value(
            f"rc:budget:cost_micro:{date_key}",
            int(round(cost_cny * 1_000_000)), 172800,
        )
        daily_cost = self._read_number(f"rc:budget:cost_micro:{date_key}") / 1_000_000
        ratio = 0.0 if self.settings.max_daily_llm_cost_cny <= 0 else daily_cost / self.settings.max_daily_llm_cost_cny
        level = (
            "hard" if ratio >= 1
            else "high_priority" if ratio >= self.settings.llm_cost_warning_ratio
            else "notice" if ratio >= self.settings.llm_cost_alert_ratio
            else "normal"
        )
        write_structured_log(
            "llm_usage", "llm_call_completed", attempt_id=attempt_id, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=input_tokens + output_tokens,
            estimated_cost_cny=round(cost_cny, 6), budget_ratio=round(ratio, 4), budget_level=level,
            elapsed_ms=latency_ms, status="success" if success else "failed",
        )
        if level != "normal" and self._mark_budget_notice_once(date_key, level):
            write_structured_log(
                "security_events", "daily_budget_threshold_reached",
                status=level, estimated_cost_cny=round(daily_cost, 6),
                budget_ratio=round(ratio, 4),
            )

    def _mark_budget_notice_once(self, date_key: str, level: str) -> bool:
        key = f"rc:budget:notice:{date_key}:{level}"
        if self._redis:
            try:
                return bool(self._redis.set(key, "1", ex=172800, nx=True))
            except Exception:
                self._mark_redis_degraded("budget_notice_failed")
        now = time.time()
        with self._lock:
            _, expires = self._counters.get(key, (0, 0))
            if expires > now:
                return False
            self._counters[key] = (1, now + 172800)
            return True

    def _add_value(self, key: str, amount: int, ttl: int) -> None:
        if self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.incrby(key, amount)
                pipe.expire(key, ttl)
                pipe.execute()
                return
            except Exception:
                self._mark_redis_degraded("budget_write_failed")
        now = time.time()
        with self._lock:
            value, expires = self._counters.get(key, (0, now + ttl))
            if expires <= now:
                value, expires = 0, now + ttl
            self._counters[key] = (value + amount, expires)

    def admit(self, attempt_id: str) -> AdmissionDecision:
        now = time.time()
        max_active = self.effective_max_concurrent
        if self._redis:
            try:
                result = self._redis.eval(
                    ADMIT_LUA, 2, "rc:generation:active", "rc:generation:queue", now,
                    now + self.settings.generation_lease_seconds, max_active,
                    self.settings.max_generation_queue_size, attempt_id,
                    now - self.settings.generation_task_ttl_seconds,
                    self.settings.generation_task_ttl_seconds * 2,
                )
                status, position = str(result[0]), int(result[1])
                self._log_admission(attempt_id, status, position)
                return AdmissionDecision(status, max(position, 0))
            except Exception:
                self._mark_redis_degraded("admission_failed")
        with self._lock:
            self._expire_active(now)
            if attempt_id in self._active:
                return AdmissionDecision("running")
            if attempt_id in self._queue:
                return AdmissionDecision("queued", self._queue.index(attempt_id) + 1)
            if len(self._active) < max_active:
                self._active[attempt_id] = now + self.settings.generation_lease_seconds
                decision = AdmissionDecision("running")
            elif len(self._queue) < self.settings.max_generation_queue_size:
                self._queue.append(attempt_id)
                decision = AdmissionDecision("queued", len(self._queue))
            else:
                decision = AdmissionDecision("full")
        self._log_admission(attempt_id, decision.status, decision.queue_position)
        return decision

    def promote(self, attempt_id: str) -> AdmissionDecision:
        now = time.time()
        max_active = self.effective_max_concurrent
        if self._redis:
            try:
                result = self._redis.eval(
                    PROMOTE_LUA, 2, "rc:generation:active", "rc:generation:queue", now,
                    now + self.settings.generation_lease_seconds, max_active, attempt_id,
                    now - self.settings.generation_task_ttl_seconds,
                    self.settings.generation_task_ttl_seconds * 2,
                )
                return AdmissionDecision(str(result[0]), max(int(result[1]), 0))
            except Exception:
                self._mark_redis_degraded("queue_promotion_failed")
        with self._lock:
            self._expire_active(now)
            if attempt_id in self._active:
                return AdmissionDecision("running")
            if attempt_id not in self._queue:
                return AdmissionDecision("missing")
            if self._queue[0] == attempt_id and len(self._active) < max_active:
                self._queue.pop(0)
                self._active[attempt_id] = now + self.settings.generation_lease_seconds
                return AdmissionDecision("running")
            return AdmissionDecision("queued", self._queue.index(attempt_id) + 1)

    def renew(self, attempt_id: str) -> None:
        expiry = time.time() + self.settings.generation_lease_seconds
        if self._redis:
            try:
                self._redis.zadd("rc:generation:active", {attempt_id: expiry}, xx=True)
                self._redis.expire("rc:generation:active", self.settings.generation_task_ttl_seconds * 2)
                return
            except Exception:
                self._mark_redis_degraded("lease_renewal_failed")
        with self._lock:
            if attempt_id in self._active:
                self._active[attempt_id] = expiry

    def release(self, attempt_id: str) -> None:
        if self._redis:
            try:
                self._redis.zrem("rc:generation:active", attempt_id)
                self._redis.zrem("rc:generation:queue", attempt_id)
            except Exception:
                self._mark_redis_degraded("slot_release_failed")
        with self._lock:
            self._active.pop(attempt_id, None)
            if attempt_id in self._queue:
                self._queue.remove(attempt_id)
        write_structured_log("generation_queue", "generation_slot_released", attempt_id=attempt_id)

    def _expire_active(self, now: float) -> None:
        for key, expiry in list(self._active.items()):
            if expiry <= now:
                del self._active[key]
                write_structured_log("generation_queue", "generation_lease_recovered", attempt_id=key)

    def _log_admission(self, attempt_id: str, status: str, position: int) -> None:
        snapshot = self.snapshot()
        write_structured_log(
            "generation_queue", "generation_admission", attempt_id=attempt_id,
            status=status, queue_position=position,
            active_count=snapshot["active"], queued_count=snapshot["queued"],
            max_concurrent=self.effective_max_concurrent,
            max_queue=self.settings.max_generation_queue_size,
            redis_ready=self.redis_ready, degraded=self.degraded,
        )

    def snapshot(self) -> dict[str, Any]:
        if self._redis:
            try:
                now = time.time()
                self._redis.zremrangebyscore("rc:generation:active", "-inf", now)
                self._redis.zremrangebyscore(
                    "rc:generation:queue", "-inf",
                    now - self.settings.generation_task_ttl_seconds,
                )
                return {
                    "active": self._redis.zcard("rc:generation:active"),
                    "queued": self._redis.zcard("rc:generation:queue"),
                    "redis_ready": True,
                    "degraded": self.degraded,
                }
            except Exception:
                self._mark_redis_degraded("snapshot_failed")
        with self._lock:
            self._expire_active(time.time())
            return {"active": len(self._active), "queued": len(self._queue), "redis_ready": False, "degraded": self.degraded}


resource_protection = ResourceProtection()
