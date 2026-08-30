import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name, "").strip()
    return [item.strip() for item in raw.split(",") if item.strip()] if raw else default


@dataclass(frozen=True)
class Settings:
    environment: str
    anonymous_cookie_name: str
    anonymous_cookie_secret: str
    anonymous_cookie_max_age: int
    download_signing_secret: str
    download_token_ttl_seconds: int
    ip_hash_secret: str
    redis_url: str
    redis_degraded_max_seconds: int
    rate_limit_dry_run: bool
    max_raw_input_chars_soft: int
    max_raw_input_chars: int
    max_request_body_bytes: int
    max_concurrent_generations: int
    model_max_concurrent_calls: int
    max_generation_queue_size: int
    generation_task_ttl_seconds: int
    generation_lease_seconds: int
    user_limit_5m: int
    user_limit_1h: int
    user_limit_1d: int
    ip_limit_5m: int
    ip_limit_1h: int
    ip_limit_1d: int
    max_daily_llm_calls: int
    max_daily_llm_tokens: int
    max_daily_llm_cost_cny: float
    llm_cost_alert_ratio: float
    llm_cost_warning_ratio: float
    allowed_origins: list[str]
    allowed_hosts: list[str]
    log_retention_days: int
    security_log_retention_days: int

    @property
    def production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def secrets_ready(self) -> bool:
        weak = {"", "change-me", "dev-only-secret"}
        return (
            self.anonymous_cookie_secret not in weak
            and self.download_signing_secret not in weak
            and self.ip_hash_secret not in weak
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    environment = os.getenv("APP_ENV", "development").strip()
    return Settings(
        environment=environment,
        anonymous_cookie_name=os.getenv("ANONYMOUS_COOKIE_NAME", "resume_coach_identity").strip(),
        anonymous_cookie_secret=os.getenv("ANONYMOUS_COOKIE_SECRET", "dev-only-secret").strip(),
        anonymous_cookie_max_age=_env_int("ANONYMOUS_COOKIE_MAX_AGE", 60 * 60 * 24 * 90),
        download_signing_secret=os.getenv("DOWNLOAD_SIGNING_SECRET", "dev-only-secret").strip(),
        download_token_ttl_seconds=_env_int("DOWNLOAD_TOKEN_TTL_SECONDS", 1200),
        ip_hash_secret=os.getenv("IP_HASH_SECRET", "dev-only-secret").strip(),
        redis_url=os.getenv("REDIS_URL", "").strip(),
        redis_degraded_max_seconds=_env_int("REDIS_DEGRADED_MAX_SECONDS", 120),
        rate_limit_dry_run=_env_bool("RATE_LIMIT_DRY_RUN", True),
        max_raw_input_chars_soft=_env_int("MAX_RAW_INPUT_CHARS_SOFT", 2000),
        max_raw_input_chars=_env_int("MAX_RAW_INPUT_CHARS", 4000),
        max_request_body_bytes=_env_int("MAX_REQUEST_BODY_BYTES", 131072),
        max_concurrent_generations=_env_int("MAX_CONCURRENT_GENERATIONS", 5),
        model_max_concurrent_calls=_env_int("MODEL_MAX_CONCURRENT_CALLS", 5),
        max_generation_queue_size=_env_int("MAX_GENERATION_QUEUE_SIZE", 15),
        generation_task_ttl_seconds=_env_int("GENERATION_TASK_TTL_SECONDS", 900),
        generation_lease_seconds=_env_int("GENERATION_LEASE_SECONDS", 120),
        user_limit_5m=_env_int("GENERATION_USER_LIMIT_5M", 2),
        user_limit_1h=_env_int("GENERATION_USER_LIMIT_1H", 6),
        user_limit_1d=_env_int("GENERATION_USER_LIMIT_1D", 20),
        ip_limit_5m=_env_int("GENERATION_IP_LIMIT_5M", 60),
        ip_limit_1h=_env_int("GENERATION_IP_LIMIT_1H", 300),
        ip_limit_1d=_env_int("GENERATION_IP_LIMIT_1D", 1000),
        max_daily_llm_calls=_env_int("MAX_DAILY_LLM_CALLS", 500),
        max_daily_llm_tokens=_env_int("MAX_DAILY_LLM_TOKENS", 5_000_000),
        max_daily_llm_cost_cny=_env_float("MAX_DAILY_LLM_COST_CNY", 200.0),
        llm_cost_alert_ratio=_env_float("LLM_COST_ALERT_RATIO", 0.5),
        llm_cost_warning_ratio=_env_float("LLM_COST_WARNING_RATIO", 0.8),
        allowed_origins=_env_list(
            "ALLOWED_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"],
        ),
        allowed_hosts=_env_list("ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"]),
        log_retention_days=_env_int("LOG_RETENTION_DAYS", 30),
        security_log_retention_days=_env_int("SECURITY_LOG_RETENTION_DAYS", 90),
    )
