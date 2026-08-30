from dataclasses import replace
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import models, schemas
from backend.app.database import Base
from backend.app.services.event_service import _sanitize_event_payload
from backend.app.services.resource_protection_service import ResourceProtection
from backend.app.services.security_service import (
    create_download_token,
    owns_generated_file,
    owns_generation_result,
    sign_anonymous_id,
    verify_anonymous_token,
    verify_download_token,
)
from backend.app.routers.generation import validate_raw_input
from fastapi import HTTPException
import pytest


def _protection(**overrides) -> ResourceProtection:
    service = ResourceProtection()
    service._redis = None
    service._redis_degraded = False
    service.settings = replace(service.settings, redis_url="", rate_limit_dry_run=False, **overrides)
    return service


def test_signed_anonymous_identity_rejects_tampering():
    token = sign_anonymous_id("anon_test_user")
    assert verify_anonymous_token(token) == "anon_test_user"
    assert verify_anonymous_token(token + "tampered") is None


def test_download_token_is_bound_to_file_and_owner():
    token = create_download_token(7, "anon_owner", expires_at=4_000_000_000)
    assert verify_download_token(7, "anon_owner", token) == (True, "ok")
    assert verify_download_token(8, "anon_owner", token)[0] is False
    assert verify_download_token(7, "anon_other", token)[0] is False


def test_download_token_expiry_is_distinguished_without_exposing_a_file():
    token = create_download_token(7, "anon_owner", expires_at=1)
    assert verify_download_token(7, "anon_owner", token) == (False, "expired")


def test_user_rate_limit_blocks_third_request_but_shared_ip_users_pass():
    service = _protection(user_limit_5m=2, user_limit_1h=6, user_limit_1d=20, ip_limit_5m=60)
    assert service.check_generation_rate("user-a", "campus-ip").allowed
    assert service.check_generation_rate("user-a", "campus-ip").allowed
    assert not service.check_generation_rate("user-a", "campus-ip").allowed
    for index in range(30):
        assert service.check_generation_rate(f"student-{index}", "another-campus-ip").allowed


def test_generation_admission_caps_five_active_and_fifteen_queued():
    service = _protection(max_concurrent_generations=5, max_generation_queue_size=15)
    states = [service.admit(f"attempt-{index}") for index in range(21)]
    assert [item.status for item in states[:5]] == ["running"] * 5
    assert [item.status for item in states[5:20]] == ["queued"] * 15
    assert states[20].status == "full"
    service.release("attempt-0")
    assert service.promote("attempt-5").status == "running"


def test_provider_concurrency_limit_can_lower_global_limit():
    service = _protection(
        max_concurrent_generations=5,
        model_max_concurrent_calls=3,
        max_generation_queue_size=15,
    )
    assert [service.admit(f"provider-{index}").status for index in range(4)] == [
        "running", "running", "running", "queued",
    ]


def test_production_pauses_new_generation_after_sustained_redis_failure():
    service = _protection(environment="production", redis_degraded_max_seconds=2)
    service._redis_degraded = True
    service._redis_failure_since = time.time() - 3
    decision = service.check_generation_availability()
    assert not decision.allowed
    assert decision.error_code == "PROTECTION_DEGRADED"


def test_daily_budget_stops_new_model_calls():
    service = _protection(max_daily_llm_calls=1)
    service.record_llm_usage(
        model="test-model", input_tokens=10, output_tokens=5,
        cost_cny=0.01, latency_ms=10, success=True,
    )
    decision = service.check_daily_budget()
    assert not decision.allowed
    assert decision.error_code == "DAILY_BUDGET_REACHED"


def test_event_payload_redacts_raw_input_and_tokens():
    sanitized = _sanitize_event_payload({
        "raw_input": "private resume",
        "attempt_id": "attempt-safe",
        "nested": {"download_token": "secret", "input_length": 123},
    })
    assert sanitized["raw_input"] == "[redacted]"
    assert sanitized["nested"]["download_token"] == "[redacted]"
    assert sanitized["attempt_id"] == "attempt-safe"


def test_input_length_accepts_4000_and_rejects_4001_unicode_characters():
    accepted_long, long_length = validate_raw_input("经" * 2001)
    assert long_length == 2001
    assert accepted_long == "经" * 2001
    accepted, length = validate_raw_input("经" * 4000)
    assert length == 4000
    assert accepted == "经" * 4000
    with pytest.raises(HTTPException) as exc_info:
        validate_raw_input("经" * 4001)
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail["error_code"] == "INPUT_TOO_LARGE"


def test_generation_and_file_ownership_follow_experience_owner():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    owner = models.AnonymousUser(anonymous_id="anon-owner")
    other = models.AnonymousUser(anonymous_id="anon-other")
    db.add_all([owner, other])
    db.flush()
    experience = models.ExperienceInput(
        anonymous_user_id=owner.id,
        session_id="session-owner",
        target_role="前端开发",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="项目经历",
        raw_input="完成一个真实项目并部署上线。",
    )
    db.add(experience)
    db.flush()
    payload = schemas.GenerationPayload(
        completeness_score=70,
        confirmed_facts=[], missing_questions=[], normal_version="a", bold_version="b",
        boundary_version="c", recommended_version="b", claims=[], interview_plan=[],
        knowledge_checklist=[], resume_sections=schemas.ResumeSections(),
    )
    result = models.GenerationResult(
        experience_input_id=experience.id, completeness_score=70,
        result_json=payload.model_dump_json(),
    )
    db.add(result)
    db.flush()
    file_row = models.GeneratedFile(
        generation_result_id=result.id, file_type="docx", file_path="ignored.docx",
    )
    db.add(file_row)
    db.commit()
    assert owns_generation_result(db, result.id, owner.id)
    assert not owns_generation_result(db, result.id, other.id)
    assert owns_generated_file(db, file_row.id, owner.id)
    assert not owns_generated_file(db, file_row.id, other.id)
