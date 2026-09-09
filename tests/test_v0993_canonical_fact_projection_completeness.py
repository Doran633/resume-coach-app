"""Fixed current-code replays, not snapshots of historical smoke requests."""
import sys
import copy
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import schemas
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger
from app.services.canonical_project_projection_service import (
    plan_canonical_project_projections, append_canonical_project_projection_candidates,
)
from app.services.fact_coverage_guard_service import guard_fact_coverage
from app.services.resume_section_layering_service import layer_resume_sections
from app.services.resume_fact_increment_service import ensure_resume_fact_increment
from app.services.resume_information_gain_service import ensure_information_gain
from app.services.resume_adaptive_narrative_service import organize_adaptive_narrative
from app.services.resume_project_reconciliation_service import reconcile_resume_projects
from app.services.canonical_projection_completeness_service import CanonicalProjectionCompletenessObserver
from app.services.resume_delivery_quality_gate_service import validate_resume_delivery_quality
from app.services.resume_quality_repair_router_service import route_quality_repairs
from app.services.resume_body_sanitizer_service import sanitize_resume_body
from app.services.resume_fact_dedup_service import deduplicate_resume_facts
from app.services.resume_output_firewall_service import guard_resume_output
from app.services.experience_slot_service import freeze_canonical_projection_candidates, strip_experience_slot_metadata
from app.services import canonical_project_projection_service as projection

RAW = "项目：资料检索工具\n使用 FastAPI 实现资料检索接口。\n通过 Nginx 部署服务并加入健康检查。"


def setup_case():
    build = build_canonical_semantic_build(RAW)
    views = build_canonical_consumer_views(build, aggregate_skill_evidence_from_ledger(build.ledger))
    return build, views, list(views.planner_view.eligible_facts("EXP-001"))


def payload(projects):
    return schemas.GenerationPayload(
        completeness_score=80, confirmed_facts=[], missing_questions=[],
        normal_version="", bold_version="", boundary_version="", recommended_version="",
        claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=projects),
    )


def bound(facts):
    return dict(name="资料检索工具", meta="项目经历", time="[待填写]", intro="", role="",
                source_experience_id="EXP-001", immutable_source_experience_id="EXP-001",
                source_binding_locked=True, details=[f.resume_ready_text for f in facts],
                source_fact_ids=[f.fact_id for f in facts], source_claim_ids=[f.claim_id for f in facts],
                detail_fact_ids=[[f.fact_id] for f in facts], detail_claim_ids=[[f.claim_id] for f in facts])


@pytest.mark.parametrize("transform", [layer_resume_sections, ensure_resume_fact_increment, ensure_information_gain])
def test_surviving_intro_aggregate_is_not_rebuilt_from_details(transform):
    _, _, facts = setup_case()
    project = bound(facts[1:])
    project.update(intro=facts[0].resume_ready_text, source_fact_ids=[f.fact_id for f in facts],
                   source_claim_ids=[f.claim_id for f in facts])
    original = payload([project])
    before = original.model_dump()
    result = transform(original)
    assert result.resume_sections.projects[0]["source_fact_ids"] == project["source_fact_ids"]
    assert result.resume_sections.projects[0]["source_claim_ids"] == project["source_claim_ids"]
    assert original.model_dump() == before


def test_sort_keeps_claim_rows_with_fact_rows():
    _, _, facts = setup_case()
    result = organize_adaptive_narrative(payload([bound(list(reversed(facts)))]))
    project = result.resume_sections.projects[0]
    lineage = {f.fact_id: f.claim_id for f in facts}
    assert project["detail_claim_ids"] == [[lineage[ids[0]]] for ids in project["detail_fact_ids"]]


def test_reconciliation_budget_sorts_and_limits_text_and_lineage_together():
    build, _, facts = setup_case()
    project = bound(list(reversed(facts)))
    original = payload([project])
    before = original.model_dump()
    result = reconcile_resume_projects(
        original, "", semantic_build=build, ownership_index=build.ownership_index, write_log=False,
    )
    project = result.resume_sections.projects[0]
    lineage = {fact.fact_id: fact.claim_id for fact in facts}
    assert project["detail_claim_ids"] == [[lineage[ids[0]]] for ids in project["detail_fact_ids"]]
    assert original.model_dump() == before


def test_existing_unique_owner_receives_exact_missing_fact_once():
    _, views, facts = setup_case()
    original = payload([bound(facts[:1])])
    before = original.model_dump()
    plan = plan_canonical_project_projections(original, views.planner_view)
    result = append_canonical_project_projection_candidates(original, plan)
    project = result.resume_sections.projects[0]
    assert project["details"] == [f.resume_ready_text for f in facts]
    assert project["detail_fact_ids"] == [[f.fact_id] for f in facts]
    assert project["detail_claim_ids"] == [[f.claim_id] for f in facts]
    again = append_canonical_project_projection_candidates(result, plan_canonical_project_projections(result, views.planner_view))
    assert again.model_dump() == result.model_dump()
    assert original.model_dump() == before


def test_canonical_coverage_no_longer_restores_body():
    build, _, facts = setup_case()
    original = payload([bound(facts[:1])])
    result = guard_fact_coverage(original, "", semantic_build=build, write_log=False)
    assert result.resume_sections.projects[0]["details"] == original.resume_sections.projects[0]["details"]


@pytest.mark.parametrize("kind,reason", [
    ("unbound", "no_frozen_target"), ("multiple", "multiple_frozen_targets"),
    ("unknown", "ambiguous_field_provenance"), ("aggregate", "ambiguous_field_provenance"),
    ("foreign", "invalid_aggregate_reference"), ("claim_conflict", "ambiguous_field_provenance"),
])
def test_insufficient_evidence_is_skipped_not_guessed(kind, reason):
    _, views, facts = setup_case()
    project = bound(facts[:1])
    projects = [project]
    if kind == "unbound":
        project.pop("immutable_source_experience_id")
    elif kind == "multiple":
        projects.append(copy.deepcopy(project))
    elif kind == "unknown":
        project["detail_fact_ids"] = [[]]
    elif kind == "aggregate":
        project.update(intro=facts[0].resume_ready_text, details=[], detail_fact_ids=[], detail_claim_ids=[])
    elif kind == "foreign":
        project["source_fact_ids"].append("EXP-002-F001")
    else:
        project["detail_claim_ids"] = [[facts[1].claim_id]]
    plan = plan_canonical_project_projections(payload(projects), views.planner_view)
    assert plan.detail_projections == ()
    assert dict(plan.detail_skip_counts)[reason] > 0


def test_stale_plan_and_repeated_application_do_not_overwrite_existing_text():
    _, views, facts = setup_case()
    original = payload([bound(facts[:1])])
    plan = plan_canonical_project_projections(original, views.planner_view)
    changed = original.model_copy(deep=True)
    changed.resume_sections.projects[0]["details"].append("另外的已有正文")
    assert append_canonical_project_projection_candidates(changed, plan).model_dump() == changed.model_dump()
    applied = append_canonical_project_projection_candidates(original, plan)
    assert append_canonical_project_projection_candidates(applied, plan).model_dump() == applied.model_dump()


def test_orphan_rows_cannot_attach_to_a_new_detail():
    _, views, facts = setup_case()
    project = bound(facts[:1])
    project["detail_fact_ids"].append(["EXP-999-F001"])
    project["detail_claim_ids"].append(["EXP-999-C001"])
    original = payload([project])
    result = append_canonical_project_projection_candidates(original, plan_canonical_project_projections(original, views.planner_view))
    project = result.resume_sections.projects[0]
    assert project["detail_fact_ids"] == [[f.fact_id] for f in facts]
    assert project["detail_claim_ids"] == [[f.claim_id] for f in facts]


@pytest.mark.parametrize("transform", [layer_resume_sections, ensure_resume_fact_increment, ensure_information_gain, organize_adaptive_narrative])
def test_original_indexes_and_unknown_provenance_are_preserved(transform):
    _, _, facts = setup_case()
    project = bound(facts)
    project["details"].insert(0, "")
    project["detail_fact_ids"].insert(0, ["EXP-001-F000"])
    project["detail_claim_ids"].insert(0, ["EXP-001-C000"])
    project["source_fact_ids"].insert(0, "EXP-001-F000")
    project["source_claim_ids"].insert(0, "EXP-001-C000")
    original = payload([project])
    before = original.model_dump()
    result = transform(original)
    current = result.resume_sections.projects[0]
    expected = {f.resume_ready_text: ([f.fact_id], [f.claim_id]) for f in facts}
    for text, ids, claims in zip(current["details"], current["detail_fact_ids"], current["detail_claim_ids"]):
        assert (ids, claims) == expected[text]
    assert "EXP-001-F000" not in current["source_fact_ids"]
    assert "EXP-001-C000" not in current["source_claim_ids"]
    assert original.model_dump() == before
    assert transform(result).model_dump() == result.model_dump()


@pytest.mark.parametrize("transform", [ensure_resume_fact_increment, ensure_information_gain])
@pytest.mark.parametrize("unknown", [False, True])
def test_same_text_different_or_unknown_sources_are_not_merged(transform, unknown):
    _, _, facts = setup_case()
    project = bound(facts)
    project["details"] = [facts[1].resume_ready_text] * 2
    if unknown:
        project["detail_claim_ids"] = [[], []]
    result = transform(payload([project]))
    assert result.resume_sections.projects[0]["details"] == project["details"]


def test_full_local_chain_keeps_projected_fact_and_claim_lineage():
    build, views, facts = setup_case()
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    original = payload([bound(facts[:1])])
    state_before = build.state
    observer = CanonicalProjectionCompletenessObserver(views)
    observer.checkpoint(original, "after_owner_freeze")
    result = append_canonical_project_projection_candidates(original, plan_canonical_project_projections(original, views.planner_view))
    observer.checkpoint(result, "after_canonical_project_projection_activation")
    for transform in (layer_resume_sections, ensure_resume_fact_increment, organize_adaptive_narrative,
                      ensure_information_gain, deduplicate_resume_facts, guard_resume_output):
        result = transform(result)
    result = sanitize_resume_body(result, semantic_safe=True)
    result = guard_fact_coverage(result, "", semantic_build=build, write_log=False)
    before_gate = result.model_dump()
    evaluation = validate_resume_delivery_quality(result, consumer_views=views, skill_evidence=evidence, write_log=False)
    route_quality_repairs(result, evaluation.issues, views.repair_view, stage="test", write_log=False)
    validate_resume_delivery_quality(result, consumer_views=views, skill_evidence=evidence, write_log=False)
    assert result.model_dump() == before_gate
    observer.checkpoint(result, "before_persistence")
    rows = [r for r in observer.events if r.get("experience_id") == "EXP-001"]
    assert rows[0]["projected_fact_count"] == 1
    assert rows[-1]["projected_fact_count"] == 2
    assert rows[-1]["unprojected_eligible_fact_count"] == 0
    project = result.resume_sections.projects[0]
    assert {i for row in project["detail_fact_ids"] for i in row} == {f.fact_id for f in facts}
    assert {i for row in project["detail_claim_ids"] for i in row} == {f.claim_id for f in facts}
    assert build.state == state_before
    public = strip_experience_slot_metadata(result).model_dump_json()
    assert "detail_projections" not in public


def test_existing_project_and_total_limits_and_priority_use_existing_policy():
    _, views, facts = setup_case()
    # Reuse the actual view, Ledger and production capacity constants.
    original = payload([bound([facts[0]] * 8)])
    plan = plan_canonical_project_projections(original, views.planner_view)
    assert not plan.detail_projections
    assert dict(plan.detail_skip_counts)["detail_limit"] == 1
    original = payload([bound(facts[:1]), dict(details=["existing"] * 19)])
    plan = plan_canonical_project_projections(original, views.planner_view)
    assert not plan.detail_projections
    assert dict(plan.detail_skip_counts)["detail_limit"] == 1


def test_multiple_experiences_use_only_local_facts_and_eligible_claims():
    raw = RAW + "\n\n项目二：停车数据工具\n使用 Python 实现车位状态采集。\n通过 Docker 部署停车服务。\n尚未实现自动支付。"
    build = build_canonical_semantic_build(raw)
    views = build_canonical_consumer_views(build, aggregate_skill_evidence_from_ledger(build.ledger))
    projects = []
    for owner in views.experience_ids:
        local = list(views.planner_view.eligible_facts(owner))
        if not local:
            continue
        project = bound(local[:1])
        project.update(source_experience_id=owner, immutable_source_experience_id=owner)
        projects.append(project)
    original = payload(projects)
    plan = plan_canonical_project_projections(original, views.planner_view)
    result = append_canonical_project_projection_candidates(original, plan)
    for project in result.resume_sections.projects:
        scope = views.planner_view.owner_scope(project["immutable_source_experience_id"])
        assert set(project["source_fact_ids"]) <= set(scope.eligible_fact_ids)
        assert set(project["source_claim_ids"]) <= set(scope.eligible_claim_ids)
        assert all("自动支付" not in d for d in project["details"])


def test_log_selected_and_retained_ids_never_contains_body(tmp_path, monkeypatch):
    build, views, facts = setup_case()
    original = payload([bound(facts[:1])])
    plan = plan_canonical_project_projections(original, views.planner_view)
    applied = append_canonical_project_projection_candidates(original, plan)
    _, freeze_stats = freeze_canonical_projection_candidates(applied, build.ownership_index, return_stats=True)
    monkeypatch.setattr(projection, "LOG_PATH", tmp_path / "projection.jsonl")
    projection.write_canonical_project_projection_log(plan, freeze_stats, stage="test", payload=applied)
    content = projection.LOG_PATH.read_text(encoding="utf-8")
    row = json.loads(content)
    assert row["detail_selected_count"] == row["detail_retained_count"] == 1
    assert row["detail_selected_fact_ids"] == [facts[1].fact_id]
    assert RAW not in content and "资料检索工具" not in content and "Nginx" not in content
    assert all(f.resume_ready_text not in content for f in facts)


def test_production_post_freeze_chain_and_persistence_preserve_new_projection(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app import models
    from app.services import generation_service as generation

    _, _, facts = setup_case()
    real_bind = generation.bind_projects_to_experience_slots
    # Controlled frozen-boundary fixture, not a recorded LLM response. All
    # subsequent production services, gates, projection and persistence run.
    def fixed_frozen_boundary(*args, **kwargs):
        _, stats = real_bind(*args, **kwargs)
        return payload([bound(facts[:1])]), stats

    monkeypatch.setattr(generation, "bind_projects_to_experience_slots", fixed_frozen_boundary)
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(generation, "LOG_DIR", tmp_path)
    monkeypatch.setattr(projection, "LOG_PATH", tmp_path / "projection.jsonl")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        response = generation.create_generation(db, schemas.GenerateRequest(
            anonymous_user_id="v0993", session_id="v0993", target_role="后端开发",
            mode="full_resume", packaging_level="稳妥", experience_type="项目经历", raw_input=RAW,
            attempt_id="attempt_v0993",
        ), request_id="req_v0993")
        saved = db.get(models.GenerationResult, response.generation_result_id)
        assert saved.result_json
    logs = [json.loads(line) for line in projection.LOG_PATH.read_text(encoding="utf-8").splitlines()]
    assert logs[0]["detail_selected_count"] == 1
    assert logs[-1]["detail_retained_count"] == 1
    assert logs[-1]["detail_unretained_fact_ids"] == []
