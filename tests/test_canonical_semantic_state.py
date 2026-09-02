import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import canonical_semantic_state_service as state_service  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_state  # noqa: E402
from app.services.generation_service import build_mock_generation, create_generation  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """项目一：论文阅读助手
独立开发论文阅读助手，使用 Python 完成论文解析、检索和问答。
两个项目技术很像，但不是一个项目，指标不要串。
没有负责架构设计，也没有独立上线。
框架好像是 Flask，也有可能是 FastAPI，我记不太清。

项目二：智能客服系统
开发智能客服系统，使用 RAG 建立 120 条测试集，将回答相关度提升至 81%。
请不要为了让简历更丰富给其他经历编技术内容。"""


def _request() -> schemas.GenerateRequest:
    return schemas.GenerateRequest(
        anonymous_user_id="anon-test",
        session_id="session-test",
        target_role="后端开发",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="综合经历",
        raw_input=RAW,
    )


def test_shadow_state_is_deterministic_and_keeps_owner_mapping():
    first = build_canonical_semantic_state(RAW, experience_input_id=11)
    second = build_canonical_semantic_state(RAW, experience_input_id=11)

    assert first.state_fingerprint == second.state_fingerprint
    assert first.experiences == second.experiences
    assert first.claims == second.claims
    assert first.facts == second.facts
    assert first.validation.valid
    assert [(fact.fact_id, fact.source_experience_id) for fact in first.facts] == [
        (fact.fact_id, fact.source_experience_id) for fact in second.facts
    ]


def test_every_fact_has_eligible_claim_and_matching_experience_owner():
    state = build_canonical_semantic_state(RAW, experience_input_id=12)
    claims = {claim.claim_id: claim for claim in state.claims}
    experience_ids = {item.experience_id for item in state.experiences}

    assert state.facts
    for fact in state.facts:
        assert fact.source_experience_id in experience_ids
        assert fact.source_claim_ids
        for claim_id in fact.source_claim_ids:
            claim = claims[claim_id]
            assert claim.source_experience_id == fact.source_experience_id
            assert claim.eligibility == "eligible"


def test_instructions_constraints_and_uncertainty_never_become_eligible_facts():
    state = build_canonical_semantic_state(RAW, experience_input_id=13)
    fact_claim_ids = {claim_id for fact in state.facts for claim_id in fact.source_claim_ids}
    claims = {claim.claim_id: claim for claim in state.claims}

    assert any(claim.semantic_role == "USER_INSTRUCTION" for claim in state.claims)
    assert any(claim.semantic_role == "NEGATIVE_CONSTRAINT" for claim in state.claims)
    assert any(claim.semantic_role == "UNCERTAIN_FACT" for claim in state.claims)
    assert all(claims[claim_id].semantic_role == "RESUME_FACT" for claim_id in fact_claim_ids)


def test_state_and_shadow_log_do_not_contain_raw_input_or_fact_body(tmp_path):
    state = build_canonical_semantic_state(RAW, experience_input_id=14)
    serialized = json.dumps(state, default=lambda item: item.__dict__, ensure_ascii=False)
    assert RAW not in serialized
    assert "将回答相关度提升至 81%" not in serialized

    original_path = state_service.LOG_PATH
    try:
        state_service.LOG_PATH = tmp_path / "canonical_semantic_state.jsonl"
        state_service.write_canonical_semantic_state_log(
            state,
            stage="generation_shadow_saved",
            request_id="req_test1234",
            attempt_id="attempt_test1234",
            generation_result_id=99,
        )
        entry = state_service.LOG_PATH.read_text(encoding="utf-8")
        assert RAW not in entry
        assert "论文阅读助手" not in entry
        assert "120 条测试集" not in entry
        assert '"generation_result_id": 99' in entry
    finally:
        state_service.LOG_PATH = original_path


def test_shadow_state_has_no_user_visible_effect_on_fixed_payload():
    request = _request()
    before = build_mock_generation(request).model_dump()
    state = build_canonical_semantic_state(request.raw_input, experience_input_id=15)
    after = build_mock_generation(request).model_dump()

    assert state.validation.valid
    assert before == after
    assert "canonical_semantic_state" not in after


def test_generation_emits_only_safe_shadow_state_metadata(tmp_path, monkeypatch):
    original_path = state_service.LOG_PATH
    original_log_dir = generation_service.LOG_DIR
    original_mode = os.environ.get("LLM_MODE")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        monkeypatch.setenv("LLM_MODE", "mock")
        state_service.LOG_PATH = tmp_path / "canonical_semantic_state.jsonl"
        generation_service.LOG_DIR = tmp_path
        request = _request().model_copy(update={"attempt_id": "attempt_shadow1234"})
        response = create_generation(db, request, request_id="req_shadow1234")

        entries = [json.loads(line) for line in state_service.LOG_PATH.read_text(encoding="utf-8").splitlines()]
        assert [entry["stage"] for entry in entries] == ["generation_shadow_built", "generation_shadow_saved"]
        assert entries[0]["request_id"] == "req_shadow1234"
        assert entries[1]["generation_result_id"] == response.generation_result_id
        assert all(entry["attempt_id"] == "attempt_shadow1234" for entry in entries)
        assert all(RAW not in json.dumps(entry, ensure_ascii=False) for entry in entries)
        assert all("论文阅读助手" not in json.dumps(entry, ensure_ascii=False) for entry in entries)
        assert "canonical_semantic_state" not in response.result.model_dump()
    finally:
        state_service.LOG_PATH = original_path
        generation_service.LOG_DIR = original_log_dir
        db.close()
        if original_mode is None:
            os.environ.pop("LLM_MODE", None)
        else:
            os.environ["LLM_MODE"] = original_mode
