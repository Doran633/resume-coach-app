"""Fixed current-code replays for Canonical fallback field projection."""
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import resume_section_fallback_service as fallback_service  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402


RAW = "项目：资料检索工具\n使用 FastAPI 实现资料检索接口，并完成健康检查。"


def _payload(projects):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[],
        normal_version="", bold_version="", boundary_version="", recommended_version="",
        claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=projects),
    )


def test_identity_fallback_suppresses_exact_intro_role_duplicate(monkeypatch):
    build = build_canonical_semantic_build(RAW)
    fact = build.ledger.for_experience("EXP-001")[0]
    monkeypatch.setattr(
        fallback_service,
        "resolve_role_for_experience",
        lambda *_args, **_kwargs: (fact.resume_ready_text, [fact.fact_id]),
    )
    stats = fallback_service.FallbackStats()

    [candidate] = fallback_service._projects_from_identities("", stats, semantic_build=build)

    assert candidate["intro"] == fact.resume_ready_text
    assert candidate["role"] == ""
    assert candidate["role_source_fact_ids"] == []
    assert candidate["role_source_claim_ids"] == []
    assert candidate["detail_fact_ids"][0] == [fact.fact_id]
    assert candidate["detail_claim_ids"][0] == [fact.claim_id]
    assert stats.duplicate_role_suppressed_count == 1


def test_generic_role_recovery_suppresses_only_exact_detail_with_same_lineage(monkeypatch):
    build = build_canonical_semantic_build(RAW)
    fact = build.ledger.for_experience("EXP-001")[0]
    project = {
        "name": "资料检索工具", "meta": "项目经历", "time": "[待填写]",
        "intro": "", "role": "负责相关工作", "details": [fact.resume_ready_text],
        "source_experience_id": "EXP-001", "source_binding_locked": False,
        "source_fact_ids": [fact.fact_id], "source_claim_ids": [fact.claim_id],
        "detail_fact_ids": [[fact.fact_id]], "detail_claim_ids": [[fact.claim_id]],
    }
    monkeypatch.setattr(
        fallback_service,
        "resolve_role_for_experience",
        lambda *_args, **_kwargs: (fact.resume_ready_text, [fact.fact_id]),
    )
    monkeypatch.setattr(fallback_service, "_projects_from_identities", lambda *_args, **_kwargs: [])

    result, stats = fallback_service.fill_resume_sections(
        _payload([project]), semantic_build=build, write_log=False, return_stats=True,
    )

    current = result.resume_sections.projects[0]
    assert current["role"] == ""
    assert "role_source_fact_ids" not in current
    assert stats.duplicate_role_suppressed_count == 1


def test_similar_or_different_lineage_role_is_preserved(monkeypatch):
    build = build_canonical_semantic_build(RAW)
    fact = build.ledger.for_experience("EXP-001")[0]
    project = {
        "name": "资料检索工具", "meta": "项目经历", "time": "[待填写]",
        "intro": "", "role": "负责相关工作", "details": [fact.resume_ready_text + "并进行联调"],
        "source_experience_id": "EXP-001", "source_binding_locked": False,
        "source_fact_ids": [fact.fact_id], "source_claim_ids": [fact.claim_id],
        "detail_fact_ids": [[fact.fact_id]], "detail_claim_ids": [[fact.claim_id]],
    }
    monkeypatch.setattr(
        fallback_service,
        "resolve_role_for_experience",
        lambda *_args, **_kwargs: (fact.resume_ready_text, [fact.fact_id]),
    )
    monkeypatch.setattr(fallback_service, "_projects_from_identities", lambda *_args, **_kwargs: [])

    result, stats = fallback_service.fill_resume_sections(
        _payload([project]), semantic_build=build, write_log=False, return_stats=True,
    )

    current = result.resume_sections.projects[0]
    assert current["role"] == fact.resume_ready_text
    assert current["role_source_fact_ids"] == [fact.fact_id]
    assert current["role_source_claim_ids"] == [fact.claim_id]
    assert stats.duplicate_role_suppressed_count == 0


def test_fallback_log_records_only_duplicate_suppression_count(monkeypatch, tmp_path):
    build = build_canonical_semantic_build(RAW)
    fact = build.ledger.for_experience("EXP-001")[0]
    monkeypatch.setattr(
        fallback_service,
        "resolve_role_for_experience",
        lambda *_args, **_kwargs: (fact.resume_ready_text, [fact.fact_id]),
    )
    monkeypatch.setattr(fallback_service, "LOG_DIR", tmp_path)
    monkeypatch.setattr(fallback_service, "LOG_PATH", tmp_path / "fallback.jsonl")

    fallback_service.fill_resume_sections(_payload([]), semantic_build=build, write_log=True)

    record = json.loads(fallback_service.LOG_PATH.read_text(encoding="utf-8"))
    assert record["duplicate_role_suppressed_count"] == 1
    assert fact.resume_ready_text not in fallback_service.LOG_PATH.read_text(encoding="utf-8")
