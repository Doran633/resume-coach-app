import copy
import json
import sys
import tempfile
from pathlib import Path

from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import canonical_project_projection_service as projection_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_project_projection_service import (  # noqa: E402
    append_canonical_project_projection_candidates,
    plan_canonical_project_projections,
    write_canonical_project_projection_log,
)
from app.services.canonical_projection_completeness_service import CanonicalProjectionCompletenessObserver  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.docx_service import create_docx  # noqa: E402
from app.services.experience_slot_service import (  # noqa: E402
    contain_ownerless_projects,
    freeze_canonical_projection_candidates,
    strip_experience_slot_metadata,
)
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger  # noqa: E402
from app.services.semantic_mutation_trace_service import (  # noqa: E402
    SemanticMutationTracer,
    build_semantic_commit_snapshot,
)


RAW = """项目一：智能停车系统
完成车位状态采集和停车数据展示。

项目二：回归分析计算器
完成数据导入和回归模型对比。

校园经历：迎新志愿活动
参与新生引导和物资整理，没有技术开发职责。

科研经历：论文阅读助手
使用 FastAPI 实现论文检索与摘要阅读。"""


def _build_views():
    build = build_canonical_semantic_build(RAW)
    views = build_canonical_consumer_views(
        build,
        aggregate_skill_evidence_from_ledger(build.ledger),
    )
    return build, views


def _payload(projects=None):
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={}, education={}, summary=[], skills=[],
            projects=projects or [], interview_preparation=[],
        ),
    )


def _bound_project(owner, fact_id):
    return {
        "name": "已绑定项目",
        "meta": "项目经历",
        "time": "[待填写]",
        "intro": "已有投影。",
        "role": "",
        "details": [],
        "source_experience_id": owner,
        "immutable_source_experience_id": owner,
        "source_binding_locked": True,
        "source_fact_ids": [fact_id],
        "source_claim_ids": [],
        "detail_fact_ids": [],
        "detail_claim_ids": [],
    }


def _freeze(payload, build):
    plan = plan_canonical_project_projections(payload, _build_views()[1].planner_view)
    appended = append_canonical_project_projection_candidates(payload, plan)
    return plan, freeze_canonical_projection_candidates(
        appended,
        build.ownership_index,
        return_stats=True,
    )


def _candidate_fact_ids(project):
    return [
        *project.get("source_fact_ids", []),
        *(fact_id for row in project.get("detail_fact_ids", []) for fact_id in row),
    ]


def test_multi_experience_owners_receive_distinct_frozen_projections():
    build, views = _build_views()
    payload = _payload()
    plan = plan_canonical_project_projections(payload, views.planner_view)
    candidate_payload = append_canonical_project_projection_candidates(payload, plan)
    frozen, stats = freeze_canonical_projection_candidates(
        candidate_payload, build.ownership_index, return_stats=True,
    )

    assert stats.candidate_frozen_count == len(plan.candidates)
    assert {project["immutable_source_experience_id"] for project in frozen.resume_sections.projects} == set(views.experience_ids)
    for project in frozen.resume_sections.projects:
        owner = project["immutable_source_experience_id"]
        assert project["source_binding_locked"] is True
        assert all(build.ownership_index.fact_owner(fact_id) == owner for fact_id in _candidate_fact_ids(project))


def test_existing_owner_bound_project_is_not_duplicated_and_unowned_llm_text_is_not_reused():
    build, views = _build_views()
    first = views.experience_ids[0]
    first_fact = views.owner_scopes[first].eligible_fact_ids[0]
    unowned_llm = {
        "name": "LLM 候选", "meta": "项目经历", "time": "[待填写]",
        "intro": "LLM 专有文本不得复用", "role": "", "details": [],
    }
    payload = _payload([_bound_project(first, first_fact), unowned_llm])
    plan = plan_canonical_project_projections(payload, views.planner_view)

    assert plan.candidate_skipped_existing_count == 1
    assert all(candidate["source_experience_id"] != first for candidate in plan.candidates)
    assert "LLM 专有文本不得复用" not in json.dumps(plan.candidates, ensure_ascii=False)


def test_projection_requires_eligible_facts_and_slot_binder_rejects_foreign_provenance():
    build, views = _build_views()
    empty_build = build_canonical_semantic_build(
        "项目经历：待补充项目\n请不要根据这段说明编造技术、指标或职责。"
    )
    empty_views = build_canonical_consumer_views(empty_build)
    empty_plan = plan_canonical_project_projections(_payload(), empty_views.planner_view)
    assert empty_plan.candidates == ()

    plan = plan_canonical_project_projections(_payload(), views.planner_view)

    first, second = views.experience_ids[:2]
    candidate = next(item for item in plan.candidates if item["source_experience_id"] == first)
    candidate["detail_fact_ids"] = [[views.owner_scopes[second].eligible_fact_ids[0]]]
    candidate["detail_claim_ids"] = [[views.owner_scopes[second].eligible_claim_ids[0]]]
    rejected, stats = freeze_canonical_projection_candidates(
        _payload([candidate]), build.ownership_index, return_stats=True,
    )

    assert rejected.resume_sections.projects == []
    assert stats.candidate_rejected_count == 1


def test_planner_cannot_freeze_owner_and_containment_keeps_valid_candidate():
    build, views = _build_views()
    plan = plan_canonical_project_projections(_payload(), views.planner_view)
    candidate = plan.candidates[0]
    assert not candidate.get("immutable_source_experience_id")
    assert not candidate.get("source_binding_locked")

    frozen, stats = freeze_canonical_projection_candidates(
        append_canonical_project_projection_candidates(_payload(), plan),
        build.ownership_index,
        return_stats=True,
    )
    contained, contract = contain_ownerless_projects(
        frozen, build.ownership_index, return_stats=True, write_log=False,
    )

    assert stats.candidate_frozen_count
    assert contract.removed_unowned_project_count == 0
    assert len(contained.resume_sections.projects) == len(plan.candidates)


def test_projection_is_idempotent_and_internal_candidate_marker_is_not_persisted():
    build, views = _build_views()
    first_plan = plan_canonical_project_projections(_payload(), views.planner_view)
    frozen, _ = freeze_canonical_projection_candidates(
        append_canonical_project_projection_candidates(_payload(), first_plan),
        build.ownership_index,
        return_stats=True,
    )
    second_plan = plan_canonical_project_projections(frozen, views.planner_view)
    persisted = strip_experience_slot_metadata(frozen)

    assert second_plan.candidates == ()
    assert second_plan.candidate_skipped_existing_count == first_plan.eligible_owner_count
    assert all("canonical_projection_candidate" not in project for project in persisted.resume_sections.projects)
    assert all(project["source_experience_id"] for project in persisted.resume_sections.projects)


def test_observer_and_mutation_trace_mark_activated_projection_without_new_experience():
    build, views = _build_views()
    plan = plan_canonical_project_projections(_payload(), views.planner_view)
    frozen, _ = freeze_canonical_projection_candidates(
        append_canonical_project_projection_candidates(_payload(), plan),
        build.ownership_index,
        return_stats=True,
    )
    observer = CanonicalProjectionCompletenessObserver(views)
    observer.checkpoint(_payload(), "after_owner_freeze")
    observer.checkpoint(frozen, "after_canonical_project_projection_activation")
    final = [row for row in observer.events if row.get("experience_id") == views.experience_ids[0]][-1]
    assert final["projected_fact_count"] > 0

    tracer = SemanticMutationTracer(
        build_semantic_commit_snapshot(consumer_views=views), consumer_views=views,
    )
    tracer.checkpoint(_payload(), "after_ownerless_containment")
    tracer.checkpoint(frozen, "after_canonical_project_projection_activation")
    mutations = [row for row in tracer.events if row.get("event_type") == "mutation"]
    assert any(row["mutation_code"] == "CANONICAL_PROJECT_PROJECTION_ACTIVATED" for row in mutations)
    assert not any(row["mutation_code"] == "NEW_EXPERIENCE" for row in mutations)


def test_projection_log_is_aggregate_only(tmp_path, monkeypatch):
    build, views = _build_views()
    plan = plan_canonical_project_projections(_payload(), views.planner_view)
    _, freeze_stats = freeze_canonical_projection_candidates(
        append_canonical_project_projection_candidates(_payload(), plan),
        build.ownership_index,
        return_stats=True,
    )
    monkeypatch.setattr(projection_service, "LOG_PATH", tmp_path / "projection.jsonl")
    write_canonical_project_projection_log(plan, freeze_stats, stage="test", request_id="req_v0987")
    content = projection_service.LOG_PATH.read_text(encoding="utf-8")

    assert RAW not in content
    assert "智能停车系统" not in content
    assert "FastAPI" not in content
    record = json.loads(content)
    assert record["candidate_frozen_count"] == len(plan.candidates)


def test_docx_renders_persisted_projection_without_candidate_metadata():
    build, views = _build_views()
    plan = plan_canonical_project_projections(_payload(), views.planner_view)
    frozen, _ = freeze_canonical_projection_candidates(
        append_canonical_project_projection_candidates(_payload(), plan),
        build.ownership_index,
        return_stats=True,
    )
    persisted = strip_experience_slot_metadata(frozen)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=1, anonymous_user_id=1, session_id="s", target_role="开发", mode="full_resume",
        packaging_level="稳妥", experience_type="项目经历", raw_input=RAW,
    ))
    db.add(models.GenerationResult(
        id=987, experience_input_id=1, completeness_score=80, result_json=persisted.model_dump_json(),
    ))
    db.commit()
    from app.services import docx_service
    previous_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            docx_service.OUTPUT_DIR = Path(temp_dir)
            response = create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=987,
            ))
            text = "\n".join(item.text for item in Document(Path(temp_dir) / response.file_name).paragraphs)
            assert "智能停车系统" in text
            assert "canonical_projection_candidate" not in text
        finally:
            docx_service.OUTPUT_DIR = previous_output
            db.close()
