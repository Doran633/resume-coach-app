"""Current-code regression tests for Canonical post-commit authority closure."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.experience_boundary_guard_service import guard_experience_boundaries  # noqa: E402
from app.services.fact_coverage_guard_service import guard_fact_coverage  # noqa: E402
from app.services.resume_experience_entity_dedup_service import deduplicate_resume_experience_entities  # noqa: E402
from app.services.resume_section_integrity_service import ensure_resume_section_integrity  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger  # noqa: E402


RAW = "项目：资料检索工具\n使用 FastAPI 实现资料检索接口。\n完成健康检查。"
MULTI_RAW = RAW + "\n\n项目：数据看板\n使用 React 实现数据展示页面。"


def _payload(projects):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[],
        normal_version="", bold_version="", boundary_version="", recommended_version="",
        claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=projects),
    )


def _project(build, **overrides):
    facts = list(build.ledger.for_experience("EXP-001"))
    project = {
        "name": "项目一：资料检索工具", "meta": "项目经历", "time": "[待填写]",
        "intro": facts[0].resume_ready_text, "role": "", "details": [facts[-1].resume_ready_text],
        "source_experience_id": "EXP-001", "immutable_source_experience_id": "EXP-001",
        "source_binding_locked": True,
        "source_fact_ids": [fact.fact_id for fact in facts],
        "source_claim_ids": [fact.claim_id for fact in facts],
        "detail_fact_ids": [[facts[-1].fact_id]], "detail_claim_ids": [[facts[-1].claim_id]],
    }
    project.update(overrides)
    return project


def test_canonical_boundary_does_not_refill_removed_intro_or_role():
    # The multi-experience path reaches the Canonical cleanup loop.  This is
    # a fixed current-code replay, not a historical request snapshot.
    build = build_canonical_semantic_build(MULTI_RAW)
    source = _payload([_project(build, intro="", role="")])
    result = guard_experience_boundaries(source, "", semantic_build=build, write_log=False)
    assert result.resume_sections.projects[0]["intro"] == ""
    assert result.resume_sections.projects[0]["role"] == ""


def test_canonical_coverage_does_not_infer_an_attachment_from_text():
    build = build_canonical_semantic_build(RAW)
    fact = build.ledger.for_experience("EXP-001")[0]
    source = _payload([_project(build, details=[fact.resume_ready_text], detail_fact_ids=[[]], detail_claim_ids=[[]])])
    result = guard_fact_coverage(source, "", semantic_build=build, write_log=False)
    assert result.resume_sections.projects[0]["detail_fact_ids"] == [[]]
    assert result.resume_sections.projects[0]["detail_claim_ids"] == [[]]


def test_canonical_entity_dedup_is_observation_only_after_commit():
    build = build_canonical_semantic_build(RAW)
    first = _project(build)
    second = _project(build, name="资料检索工具", details=[])
    source = _payload([first, second])
    result = deduplicate_resume_experience_entities(source, "", semantic_build=build, write_log=False)
    assert result.model_dump() == source.model_dump()


def test_section_integrity_keeps_detail_fact_and_claim_rows_aligned():
    build = build_canonical_semantic_build(RAW)
    facts = list(build.ledger.for_experience("EXP-001"))
    source = _payload([_project(
        build,
        details=["", facts[-1].resume_ready_text],
        detail_fact_ids=[["EXP-001-F000"], [facts[-1].fact_id]],
        detail_claim_ids=[["EXP-001-C000"], [facts[-1].claim_id]],
    )])
    result = ensure_resume_section_integrity(source)
    project = result.resume_sections.projects[0]
    assert project["details"] == [facts[-1].resume_ready_text]
    assert project["detail_fact_ids"] == [[facts[-1].fact_id]]
    assert project["detail_claim_ids"] == [[facts[-1].claim_id]]


def test_project_aggregate_does_not_authorize_intro_or_role_as_field_evidence():
    build = build_canonical_semantic_build(RAW)
    views = build_canonical_consumer_views(build, aggregate_skill_evidence_from_ledger(build.ledger))
    project = _project(build, role="职责", role_source_fact_ids=[])
    assert not views.presentation_view.permits_project_field(project, "intro")
    assert not views.presentation_view.permits_project_field(project, "role")
