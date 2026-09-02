import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import canonical_semantic_state_service as state_service  # noqa: E402
from app.services.canonical_semantic_state_service import (  # noqa: E402
    build_canonical_semantic_build,
    write_canonical_fact_ownership_log,
)
from app.services.experience_boundary_guard_service import guard_experience_boundaries  # noqa: E402
from app.services.experience_slot_service import bind_projects_to_experience_slots  # noqa: E402
from app.services.fact_coverage_guard_service import guard_fact_coverage  # noqa: E402
from app.services.resume_experience_entity_dedup_service import deduplicate_resume_experience_entities  # noqa: E402
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402


RAW = """项目一：回归分析计算器
独立完成回归分析计算器，支持数据导入、多种回归模型对比和智能制图。

项目二：智能客服系统
独立开发 RAG 智能客服系统，使用 FastAPI、React 和 Docker 部署；建立 120 条测试集，命中率达到 81%。

校园经历：迎新志愿活动
参加迎新志愿活动，负责引导新生和搬运物资，没有技术开发职责。"""

SINGLE_RAW = """项目经历：课程资料助手
独立完成课程资料助手，支持资料整理与检索问答。"""


def _payload(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="", boundary_version="",
        recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(summary=[], skills=[], projects=projects, education={}, interview_preparation=[]),
    )


def test_ownership_index_is_single_owner_and_safe_projection():
    build = build_canonical_semantic_build(RAW)
    index = build.ownership_index

    assert index.fact_owner_by_id
    assert index.claim_owner_by_id
    assert all(owner in index.source_experience_ids for owner in index.fact_owner_by_id.values())
    assert all(owner in index.source_experience_ids for owner in index.claim_owner_by_id.values())
    serialized = json.dumps(index, default=lambda value: value.__dict__, ensure_ascii=False)
    assert RAW not in serialized
    assert "智能客服系统" not in serialized


def test_canonical_slot_binder_corrects_once_then_preserves_frozen_owner():
    build = build_canonical_semantic_build(RAW)
    regression_id, customer_id = [item.experience_id for item in build.identities[:2]]
    payload = _payload([{
        "name": "智能客服系统", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 客服",
        "role": "独立开发", "details": ["使用 FastAPI、React 和 Docker 部署"],
        "source_experience_id": regression_id,
    }])

    frozen, stats = bind_projects_to_experience_slots(
        payload, RAW, semantic_build=build, ownership_index=build.ownership_index, return_stats=True,
    )
    project = frozen.resume_sections.projects[0]
    assert project["immutable_source_experience_id"] == customer_id
    assert stats.frozen_project_count == 1

    project["source_experience_id"] = regression_id
    rebound, repeat_stats = bind_projects_to_experience_slots(
        frozen, RAW, semantic_build=build, ownership_index=build.ownership_index, return_stats=True,
    )
    assert rebound.resume_sections.projects[0]["immutable_source_experience_id"] == customer_id
    assert repeat_stats.owner_mutation_blocked_count == 1


def test_unowned_project_is_not_positionally_bound_in_canonical_mode():
    build = build_canonical_semantic_build(RAW)
    payload = _payload([{
        "name": "无关标题", "meta": "项目经历", "time": "[待填写]", "intro": "", "role": "", "details": ["完成相关工作"],
    }])
    result, stats = bind_projects_to_experience_slots(
        payload, RAW, semantic_build=build, ownership_index=build.ownership_index, return_stats=True,
    )
    assert "immutable_source_experience_id" not in result.resume_sections.projects[0]
    assert not result.resume_sections.projects[0].get("source_experience_id")
    assert stats.unresolved_owner_count == 1


def test_singleton_valid_candidate_freezes_despite_low_text_similarity():
    build = build_canonical_semantic_build(SINGLE_RAW)
    owner = build.identities[0].experience_id
    payload = _payload([{
        "name": "展示页面", "meta": "项目经历", "time": "[待填写]", "intro": "", "role": "", "details": ["已完成"],
        "source_experience_id": owner,
    }])

    result, stats = bind_projects_to_experience_slots(
        payload, SINGLE_RAW, semantic_build=build, ownership_index=build.ownership_index, return_stats=True,
    )
    project = result.resume_sections.projects[0]
    assert project["immutable_source_experience_id"] == owner
    assert project["source_binding_origin"] == "canonical_singleton_candidate"
    assert stats.frozen_project_count == 1


def test_singleton_candidate_rejects_foreign_fact_owner():
    build = build_canonical_semantic_build(SINGLE_RAW)
    owner = build.identities[0].experience_id
    payload = _payload([{
        "name": "展示页面", "meta": "项目经历", "time": "[待填写]", "intro": "", "role": "", "details": ["已完成"],
        "source_experience_id": owner,
        "detail_fact_ids": [["EXP-999-F001"]],
    }])

    result, stats = bind_projects_to_experience_slots(
        payload, SINGLE_RAW, semantic_build=build, ownership_index=build.ownership_index, return_stats=True,
    )
    assert "immutable_source_experience_id" not in result.resume_sections.projects[0]
    assert stats.rejected_binding_count == 1


def test_multi_experience_low_score_candidate_remains_rejected():
    build = build_canonical_semantic_build(RAW)
    candidate = build.identities[0].experience_id
    payload = _payload([{
        "name": "展示页面", "meta": "项目经历", "time": "[待填写]", "intro": "", "role": "", "details": ["已完成"],
        "source_experience_id": candidate,
    }])

    result, stats = bind_projects_to_experience_slots(
        payload, RAW, semantic_build=build, ownership_index=build.ownership_index, return_stats=True,
    )
    assert "immutable_source_experience_id" not in result.resume_sections.projects[0]
    assert stats.rejected_binding_count == 1


def test_boundary_and_coverage_remove_foreign_fact_without_moving_it():
    build = build_canonical_semantic_build(RAW)
    regression_id, customer_id, volunteer_id = [item.experience_id for item in build.identities[:3]]
    customer_fact = build.ownership_index.eligible_fact_ids_by_experience[customer_id][0]
    payload = _payload([
        {
            "name": "回归分析计算器", "meta": "项目经历", "time": "[待填写]", "intro": "回归分析",
            "role": "独立完成", "details": ["使用 FastAPI、React 和 Docker 部署"],
            "source_experience_id": regression_id, "immutable_source_experience_id": regression_id,
            "detail_fact_ids": [[customer_fact]],
        },
        {
            "name": "迎新志愿活动", "meta": "校园 / 社团经历", "time": "[待填写]", "intro": "迎新服务",
            "role": "志愿者", "details": ["引导新生和搬运物资"],
            "source_experience_id": volunteer_id, "immutable_source_experience_id": volunteer_id,
        },
    ])
    bounded = guard_experience_boundaries(
        payload, RAW, semantic_build=build, ownership_index=build.ownership_index, write_log=False,
    )
    covered = guard_fact_coverage(
        bounded, RAW, semantic_build=build, ownership_index=build.ownership_index, write_log=False,
    )
    all_text = "\n".join("\n".join(project["details"]) for project in covered.resume_sections.projects)
    assert "FastAPI" not in all_text
    assert "Docker" not in all_text
    assert all(project.get("immutable_source_experience_id") in {regression_id, volunteer_id} for project in covered.resume_sections.projects)


def test_entity_dedup_keeps_distinct_frozen_owners_separate():
    build = build_canonical_semantic_build(RAW)
    first, second = [item.experience_id for item in build.identities[:2]]
    payload = _payload([
        {"name": "同名项目", "meta": "项目经历", "time": "", "intro": "A", "role": "", "details": ["数据导入"], "source_experience_id": first, "immutable_source_experience_id": first},
        {"name": "同名项目", "meta": "项目经历", "time": "", "intro": "B", "role": "", "details": ["RAG 检索"], "source_experience_id": second, "immutable_source_experience_id": second},
    ])
    result = deduplicate_resume_experience_entities(
        payload, RAW, semantic_build=build, ownership_index=build.ownership_index, write_log=False, apply_hierarchy=False,
    )
    assert len(result.resume_sections.projects) == 2


def test_fallback_only_keeps_provisional_owner_and_safe_log_has_no_text(tmp_path):
    build = build_canonical_semantic_build(RAW)
    payload = _payload([])
    filled = fill_resume_sections(payload, raw_input=RAW, semantic_build=build, write_log=False)
    assert all(not project.get("immutable_source_experience_id") for project in filled.resume_sections.projects)

    previous = state_service.OWNERSHIP_LOG_PATH
    try:
        state_service.OWNERSHIP_LOG_PATH = tmp_path / "canonical_fact_ownership.jsonl"
        write_canonical_fact_ownership_log(build.ownership_index, stage="test", request_id="req_12345678")
        entry = state_service.OWNERSHIP_LOG_PATH.read_text(encoding="utf-8")
        assert RAW not in entry
        assert "智能客服系统" not in entry
        assert "ownership_fingerprint" in entry
    finally:
        state_service.OWNERSHIP_LOG_PATH = previous
