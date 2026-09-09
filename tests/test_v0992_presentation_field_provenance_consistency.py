from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_projection_completeness_service import _project_fact_ids  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.fact_coverage_guard_service import guard_fact_coverage  # noqa: E402
from app.services.resume_dedup_quality_service import ensure_dedup_quality  # noqa: E402
from app.services.resume_body_sanitizer_service import sanitize_resume_body  # noqa: E402
from app.services.resume_delivery_quality_gate_service import validate_resume_delivery_quality  # noqa: E402
from app.services.resume_fact_cluster_dedup_service import deduplicate_fact_clusters  # noqa: E402
from app.services.resume_fact_dedup_service import deduplicate_resume_facts  # noqa: E402
from app.services.resume_output_firewall_service import guard_resume_output  # noqa: E402
from app.services.resume_quality_repair_router_service import route_quality_repairs  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger  # noqa: E402


OWNER = "EXP-001"
F0, F1, F2 = "EXP-001-F000", "EXP-001-F001", "EXP-001-F002"
C0, C1, C2 = "EXP-001-C000", "EXP-001-C001", "EXP-001-C002"


def _payload(project: dict) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=100,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[project]),
    )


def _project(**overrides) -> dict:
    project = {
        "name": "示例项目",
        "meta": "项目经历",
        "time": "2026.01",
        "intro": "项目概览",
        "role": "负责接口开发",
        "details": ["实现接口", "完成联调"],
        "source_experience_id": OWNER,
        "immutable_source_experience_id": OWNER,
        "source_binding_locked": True,
        "source_fact_ids": [F1, F2],
        "role_source_fact_ids": [F1],
        "detail_fact_ids": [[F1], [F2]],
        "source_claim_ids": [C1, C2],
        "role_source_claim_ids": [C1],
        "detail_claim_ids": [[C1], [C2]],
    }
    project.update(overrides)
    return project


def test_fact_dedup_uses_original_indexes_after_empty_detail_filtering():
    payload = _payload(_project(
        details=["", "实现接口", "完成联调"],
        detail_fact_ids=[[F0], [F1], [F2]],
        detail_claim_ids=[[C0], [C1], [C2]],
        source_fact_ids=[F0, F1, F2],
        source_claim_ids=[C0, C1, C2],
    ))

    result = deduplicate_resume_facts(payload, write_log=False)
    project = result.resume_sections.projects[0]

    assert project["details"] == ["实现接口", "完成联调"]
    assert project["detail_fact_ids"] == [[F1], [F2]]
    assert project["detail_claim_ids"] == [[C1], [C2]]
    assert F0 not in project["source_fact_ids"]
    assert C0 not in project["source_claim_ids"]


def test_dedup_quality_keeps_claim_rows_with_original_detail_indexes():
    payload = _payload(_project(
        details=["", "实现接口", "完成联调"],
        detail_fact_ids=[[F0], [F1], [F2]],
        detail_claim_ids=[[C0], [C1], [C2]],
        source_fact_ids=[F0, F1, F2],
        source_claim_ids=[C0, C1, C2],
    ))

    result = ensure_dedup_quality(payload, write_log=False)
    project = result.resume_sections.projects[0]

    assert project["details"] == ["实现接口", "完成联调"]
    assert project["detail_fact_ids"] == [[F1], [F2]]
    assert project["detail_claim_ids"] == [[C1], [C2]]


def test_cluster_dedup_does_not_merge_same_text_with_different_claim_provenance():
    payload = _payload(_project(
        details=["完成接口联调。", "完成接口联调。"],
        detail_fact_ids=[[F1], [F2]],
        detail_claim_ids=[[C1], [C2]],
    ))

    result = deduplicate_fact_clusters(payload, write_log=False)
    project = result.resume_sections.projects[0]

    assert project["details"] == ["完成接口联调。", "完成接口联调。"]
    assert project["detail_fact_ids"] == [[F1], [F2]]
    assert project["detail_claim_ids"] == [[C1], [C2]]


def test_fact_dedup_does_not_merge_same_text_when_field_provenance_is_unknown():
    payload = _payload(_project(
        details=["完成接口联调。", "完成接口联调。"],
        detail_fact_ids=[[], []],
        detail_claim_ids=[[], []],
        source_fact_ids=[],
        source_claim_ids=[],
    ))

    result = deduplicate_resume_facts(payload, write_log=False)
    project = result.resume_sections.projects[0]

    assert project["details"] == ["完成接口联调。", "完成接口联调。"]
    assert project["detail_fact_ids"] == [[], []]
    assert project["detail_claim_ids"] == [[], []]


def test_firewall_removes_detail_and_its_matching_attachment_row_together():
    payload = _payload(_project(
        role="",
        details=["负责相关工作", "实现接口"],
        detail_fact_ids=[[F1], [F2]],
        detail_claim_ids=[[C1], [C2]],
        source_fact_ids=[F1, F2],
        source_claim_ids=[C1, C2],
        role_source_fact_ids=[],
        role_source_claim_ids=[],
    ))

    result = guard_resume_output(payload, write_log=False)
    project = result.resume_sections.projects[0]

    assert project["details"] == ["实现接口"]
    assert project["detail_fact_ids"] == [[F2]]
    assert project["detail_claim_ids"] == [[C2]]
    assert F1 not in project["source_fact_ids"]
    assert C1 not in project["source_claim_ids"]


def test_detail_transform_does_not_replace_role_aggregate_provenance():
    payload = _payload(_project(
        role="负责接口开发",
        details=["完成联调"],
        source_fact_ids=[F1, F2],
        role_source_fact_ids=[F1],
        detail_fact_ids=[[F2]],
        source_claim_ids=[C1, C2],
        role_source_claim_ids=[C1],
        detail_claim_ids=[[C2]],
    ))

    result = deduplicate_resume_facts(payload, write_log=False)
    project = result.resume_sections.projects[0]

    assert project["source_fact_ids"] == [F1, F2]
    assert project["source_claim_ids"] == [C1, C2]
    assert project["role_source_fact_ids"] == [F1]
    assert project["role_source_claim_ids"] == [C1]


def test_fact_dedup_is_idempotent_and_does_not_mutate_input():
    payload = _payload(_project(
        details=["实现接口。", "实现接口"],
        detail_fact_ids=[[F1], [F1]],
        detail_claim_ids=[[C1], [C1]],
    ))
    before = payload.model_dump(mode="json")

    first = deduplicate_resume_facts(payload, write_log=False)
    second = deduplicate_resume_facts(first, write_log=False)

    assert payload.model_dump(mode="json") == before
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    project = first.resume_sections.projects[0]
    assert project["details"] == ["实现接口"]
    assert project["detail_fact_ids"] == [[F1]]
    assert project["detail_claim_ids"] == [[C1]]


def test_presentation_transform_coverage_gate_router_contract_keeps_exact_detail_attachment():
    build = build_canonical_semantic_build("项目：资料检索工具\n使用 FastAPI 实现资料检索接口。")
    fact = build.ledger.facts[0]
    owner = fact.immutable_experience_id
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    views = build_canonical_consumer_views(build, evidence)
    payload = _payload({
        "name": "资料检索工具",
        "meta": "项目经历",
        "time": "[待填写]",
        "intro": "",
        "role": "",
        "details": [fact.resume_ready_text],
        "source_experience_id": owner,
        "immutable_source_experience_id": owner,
        "source_binding_locked": True,
        "source_fact_ids": [fact.fact_id],
        "detail_fact_ids": [[fact.fact_id]],
        "source_claim_ids": [fact.claim_id],
        "detail_claim_ids": [[fact.claim_id]],
    })

    transformed = guard_resume_output(
        deduplicate_resume_facts(sanitize_resume_body(payload, semantic_safe=True), write_log=False),
        write_log=False,
    )
    covered = guard_fact_coverage(
        transformed,
        "",
        semantic_build=build,
        ownership_index=build.ownership_index,
        write_log=False,
    )
    before_gate = covered.model_dump(mode="json")
    evaluation = validate_resume_delivery_quality(
        covered,
        consumer_views=views,
        skill_evidence=evidence,
        write_log=False,
    )
    repaired = route_quality_repairs(
        covered,
        list(evaluation.issues),
        views.repair_view,
        stage="test",
        write_log=False,
    )
    validate_resume_delivery_quality(
        covered,
        consumer_views=views,
        skill_evidence=evidence,
        write_log=False,
    )

    assert covered.model_dump(mode="json") == before_gate
    assert repaired.stats.applied_action_count == 0
    project = covered.resume_sections.projects[0]
    assert project["detail_fact_ids"] == [[fact.fact_id]]
    assert project["detail_claim_ids"] == [[fact.claim_id]]
    assert _project_fact_ids(project) == (fact.fact_id,)
