import copy
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import canonical_semantic_state_service as state_service  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_semantic_state_service import (  # noqa: E402
    build_canonical_semantic_build,
    build_canonical_semantic_state_from_build,
)
from app.services.experience_fact_ledger_service import (  # noqa: E402
    build_experience_fact_ledger_from_components,
)
from app.services.input_claim_resolution_service import (  # noqa: E402
    CONFIRMED,
    CURRENT,
    ELIGIBLE,
    EXCLUDED,
    NEGATIVE_CONSTRAINT,
    PLANNED,
    POSITIVE,
    STRUCTURE_MARKER,
    TARGET_ROLE_CONTEXT,
    UNCERTAIN,
    UNCERTAIN_FACT,
    USER_INSTRUCTION,
    WITHHELD,
    ClaimResolution,
    InputClaim,
    normalize_claim_eligibility,
    resolve_experience_claims,
)
from app.services.resume_skill_evidence_aggregation_service import (  # noqa: E402
    aggregate_skill_evidence_from_ledger,
)


RAW = "项目经历：资料检索工具\n使用 FastAPI 实现资料检索接口，并完成日志记录。"


def _claim(**updates) -> InputClaim:
    base = InputClaim(
        claim_id="EXP-001-C001",
        source_experience_id="EXP-001",
        source_span=(0, 8),
        subject="我",
        predicate="完成",
        object="接口开发",
        text="完成接口开发",
        semantic_role="RESUME_FACT",
        polarity=POSITIVE,
        certainty=CONFIRMED,
        temporal_status=CURRENT,
        eligibility=ELIGIBLE,
    )
    return replace(base, **updates)


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        (_claim(semantic_role=USER_INSTRUCTION), EXCLUDED),
        (_claim(semantic_role=TARGET_ROLE_CONTEXT), EXCLUDED),
        (_claim(semantic_role=STRUCTURE_MARKER), EXCLUDED),
        (_claim(semantic_role=NEGATIVE_CONSTRAINT), EXCLUDED),
        (_claim(semantic_role=UNCERTAIN_FACT), WITHHELD),
        (_claim(certainty=UNCERTAIN), WITHHELD),
        (_claim(temporal_status=PLANNED), WITHHELD),
    ],
)
def test_semantic_contract_never_keeps_ineligible_claim_as_eligible(claim, expected):
    assert normalize_claim_eligibility(claim).eligibility == expected


def test_negative_semantic_role_is_authoritative_when_auxiliary_regex_is_weaker():
    resolution = resolve_experience_claims("EXP-001", "不能夸大职责")

    assert resolution.claims[0].semantic_role == NEGATIVE_CONSTRAINT
    assert resolution.claims[0].eligibility == EXCLUDED
    assert not resolution.eligible_claims


def test_mixed_positive_and_negative_sentence_keeps_only_the_positive_atomic_claim():
    resolution = resolve_experience_claims(
        "EXP-001",
        "参与迎新引导和物资整理，没有承担技术开发职责",
    )

    assert [claim.text for claim in resolution.eligible_claims] == ["参与迎新引导和物资整理"]
    assert len(resolution.excluded_claims) == 1
    assert resolution.excluded_claims[0].semantic_role == NEGATIVE_CONSTRAINT


def test_fact_ledger_quarantines_a_more_permissive_claim_without_deleting_audit_claim():
    build = build_canonical_semantic_build(RAW)
    eligible = next(claim for claim in build.ledger.claims if claim.eligibility == ELIGIBLE)
    unsafe = replace(
        eligible,
        semantic_role=NEGATIVE_CONSTRAINT,
        polarity=POSITIVE,
        certainty=CONFIRMED,
        eligibility=ELIGIBLE,
        exclusion_reason="",
    )
    ledger = build_experience_fact_ledger_from_components(
        RAW,
        identities=build.identities,
        semantic_analyses=build.semantic_analyses,
        claim_resolutions=(ClaimResolution(claims=[unsafe]),),
    )

    assert ledger.claims[0].claim_id == unsafe.claim_id
    assert ledger.claims[0].eligibility == EXCLUDED
    assert ledger.excluded_claims == [ledger.claims[0]]
    assert ledger.facts == []
    assert ledger.quarantined_claim_ids == [unsafe.claim_id]
    assert ledger.quarantined_fact_candidate_count >= 1
    assert aggregate_skill_evidence_from_ledger(ledger) == []


@pytest.mark.parametrize("mutation", ["owner", "claim"])
def test_invalid_fact_lineage_fails_state_validation_and_blocks_consumer_views(mutation):
    build = copy.deepcopy(build_canonical_semantic_build(RAW))
    fact = build.ledger.facts[0]
    if mutation == "owner":
        fact.experience_id = "EXP-999"
    else:
        fact.claim_id = "EXP-001-C999"
    state = build_canonical_semantic_state_from_build(build)

    assert not state.validation.valid
    expected = "FACT_OWNER_MISSING" if mutation == "owner" else "FACT_CLAIM_MISSING"
    assert expected in state.validation.issue_codes
    with pytest.raises(ValueError, match="validated CanonicalSemanticState"):
        build_canonical_consumer_views(build)


def test_invalid_state_stops_before_llm_and_database_persistence(tmp_path, monkeypatch):
    invalid_build = copy.deepcopy(build_canonical_semantic_build(RAW))
    invalid_build.ledger.facts[0].claim_id = "EXP-001-C999"
    build_canonical_semantic_state_from_build(invalid_build)
    llm_called = False

    def forbidden_llm(*args, **kwargs):
        nonlocal llm_called
        llm_called = True
        raise AssertionError("LLM must not be called for an invalid canonical state")

    def forbidden_consumer(*args, **kwargs):
        raise AssertionError("Invalid canonical state must not reach downstream consumers")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setenv("LLM_MODE", "openai")
    monkeypatch.setattr(generation_service, "build_canonical_semantic_build", lambda *args, **kwargs: invalid_build)
    monkeypatch.setattr(generation_service, "build_llm_generation", forbidden_llm)
    monkeypatch.setattr(generation_service, "aggregate_skill_evidence_from_ledger", forbidden_consumer)
    monkeypatch.setattr(generation_service, "build_canonical_consumer_views", forbidden_consumer)
    monkeypatch.setattr(state_service, "ELIGIBILITY_INTEGRITY_LOG_PATH", tmp_path / "eligibility.jsonl")
    try:
        with pytest.raises(generation_service.GenerationServiceError) as raised:
            generation_service.create_generation(
                db,
                schemas.GenerateRequest(
                    anonymous_user_id="anon-v0985",
                    session_id="session-v0985",
                    target_role="后端开发",
                    mode="full_resume",
                    packaging_level="稳妥",
                    experience_type="项目经历",
                    raw_input=RAW,
                    attempt_id="attempt_v0985_invalid",
                ),
                request_id="req_v0985_invalid",
            )
        assert raised.value.code == "INVALID_CANONICAL_SEMANTIC_STATE"
        assert llm_called is False
        assert db.query(models.ExperienceInput).count() == 0
        assert db.query(models.GenerationResult).count() == 0
    finally:
        db.close()


def test_integrity_log_contains_only_ids_counts_and_fingerprint(tmp_path, monkeypatch):
    build = build_canonical_semantic_build(RAW)
    state = build.state
    assert state is not None and state.validation.valid
    monkeypatch.setattr(state_service, "ELIGIBILITY_INTEGRITY_LOG_PATH", tmp_path / "eligibility.jsonl")

    state_service.write_canonical_eligibility_integrity_log(
        build,
        state,
        stage="test",
        request_id="req_v0985_log",
        attempt_id="attempt_v0985_log",
    )
    content = state_service.ELIGIBILITY_INTEGRITY_LOG_PATH.read_text(encoding="utf-8")
    row = json.loads(content)

    assert row["validation_result"] == "valid"
    assert row["state_fingerprint"] == state.state_fingerprint
    assert row["total_fact_count"] == len(build.ledger.facts)
    assert RAW not in content
    assert "资料检索工具" not in content
    assert "FastAPI" not in content


def test_valid_build_and_state_remain_deterministic():
    first = build_canonical_semantic_build(RAW)
    second = build_canonical_semantic_build(RAW)

    assert first.state is not None and first.state.validation.valid
    assert second.state is not None and second.state.validation.valid
    assert first.state.state_fingerprint == second.state.state_fingerprint
    assert first.ownership_index.ownership_fingerprint == second.ownership_index.ownership_fingerprint
    assert first.ledger == second.ledger
