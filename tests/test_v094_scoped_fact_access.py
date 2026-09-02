import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import canonical_semantic_state_service as state_service  # noqa: E402
from app.services import experience_boundary_guard_service as boundary_service  # noqa: E402
from app.services import fact_coverage_guard_service as coverage_service  # noqa: E402
from app.services import resume_experience_entity_dedup_service as entity_dedup_service  # noqa: E402
from app.services import resume_project_reconciliation_service as reconciliation_service  # noqa: E402
from app.services.canonical_semantic_state_service import (  # noqa: E402
    CanonicalScopedFactAccessStats,
    build_canonical_semantic_build,
    canonical_fact_scope_for_owner,
    write_canonical_scoped_fact_access_log,
)
from app.services.experience_boundary_guard_service import guard_experience_boundaries  # noqa: E402
from app.services.fact_coverage_guard_service import guard_fact_coverage  # noqa: E402
from app.services.resume_experience_entity_dedup_service import deduplicate_resume_experience_entities  # noqa: E402
from app.services.resume_project_reconciliation_service import reconcile_resume_projects  # noqa: E402


RAW = """项目一：回归分析计算器
独立完成回归分析计算器，支持数据导入、多种回归模型对比和智能制图。

项目二：智能客服系统
独立开发 RAG 智能客服系统，使用 FastAPI、React 和 Docker 部署；建立 120 条测试集，命中率达到 81%。

校园经历：迎新志愿活动
参加迎新志愿活动，负责引导新生和搬运物资，没有技术开发职责。"""


def _payload(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="", boundary_version="",
        recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(summary=[], skills=[], projects=projects, education={}, interview_preparation=[]),
    )


def _frozen_projects(build):
    regression_id, customer_id, volunteer_id = [item.experience_id for item in build.identities[:3]]
    return regression_id, customer_id, volunteer_id


def test_scope_contains_only_owner_eligible_identifiers_and_no_text():
    build = build_canonical_semantic_build(RAW)
    _, customer_id, _ = _frozen_projects(build)
    scope = canonical_fact_scope_for_owner(build.ownership_index, customer_id)

    assert scope is not None
    assert scope.eligible_fact_ids
    assert all(build.ownership_index.fact_owner(fact_id) == customer_id for fact_id in scope.eligible_fact_ids)
    serialized = json.dumps(scope.__dict__, ensure_ascii=False)
    assert RAW not in serialized
    assert "智能客服系统" not in serialized
    assert "FastAPI" not in serialized


def test_cross_owner_customer_technical_facts_are_removed_from_volunteer():
    build = build_canonical_semantic_build(RAW)
    _, customer_id, volunteer_id = _frozen_projects(build)
    customer_fact = build.ownership_index.eligible_fact_ids_by_experience[customer_id][0]
    payload = _payload([{
        "name": "迎新志愿活动", "meta": "校园 / 社团经历", "time": "", "intro": "迎新服务",
        "role": "志愿者", "details": ["使用 FastAPI、React 和 Docker 部署；建立 120 条测试集，命中率达到 81%。"],
        "source_experience_id": volunteer_id, "immutable_source_experience_id": volunteer_id,
        "detail_fact_ids": [[customer_fact]],
    }])

    stats = CanonicalScopedFactAccessStats()
    result = guard_experience_boundaries(
        payload, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, scoped_access_stats=stats, write_log=False,
    )
    assert result.resume_sections.projects[0]["details"] == []
    assert stats.rejected_cross_owner_access_count == 1


def test_coverage_recovers_an_omitted_local_high_value_fact_only():
    build = build_canonical_semantic_build(RAW)
    _, customer_id, _ = _frozen_projects(build)
    payload = _payload([{
        "name": "智能客服系统", "meta": "项目经历", "time": "", "intro": "RAG 客服",
        "role": "独立开发", "details": [],
        "source_experience_id": customer_id, "immutable_source_experience_id": customer_id,
    }])

    stats = CanonicalScopedFactAccessStats()
    result = guard_fact_coverage(
        payload, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, scoped_access_stats=stats, write_log=False,
    )
    detail_text = "\n".join(result.resume_sections.projects[0]["details"])
    assert detail_text
    assert "回归分析" not in detail_text
    assert stats.local_fact_recovered_count > 0


def test_unowned_project_does_not_receive_scoped_facts():
    build = build_canonical_semantic_build(RAW)
    payload = _payload([{
        "name": "未确认项目", "meta": "项目经历", "time": "", "intro": "", "role": "", "details": ["完成相关工作"],
    }])

    stats = CanonicalScopedFactAccessStats()
    result = guard_fact_coverage(
        payload, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, scoped_access_stats=stats, write_log=False,
    )
    project = result.resume_sections.projects[0]
    assert project["details"] == ["完成相关工作"]
    assert project["source_fact_ids"] == []
    assert stats.unowned_project_skipped_count == 1


def test_canonical_consumers_do_not_rebuild_raw_input(monkeypatch):
    build = build_canonical_semantic_build(RAW)
    regression_id, customer_id, _ = _frozen_projects(build)
    payload = _payload([
        {
            "name": "回归分析计算器", "meta": "项目经历", "time": "", "intro": "回归分析",
            "role": "独立完成", "details": ["支持数据导入、多种回归模型对比和智能制图"],
            "source_experience_id": regression_id, "immutable_source_experience_id": regression_id,
        },
        {
            "name": "智能客服系统", "meta": "项目经历", "time": "", "intro": "RAG 客服",
            "role": "独立开发", "details": ["使用 FastAPI、React 和 Docker 部署"],
            "source_experience_id": customer_id, "immutable_source_experience_id": customer_id,
        },
    ])

    def fail_raw_rebuild(*_args, **_kwargs):
        raise AssertionError("canonical consumer attempted raw input rebuild")

    for module in [boundary_service, coverage_service, reconciliation_service, entity_dedup_service]:
        monkeypatch.setattr(module, "build_experience_identities", fail_raw_rebuild, raising=False)
        monkeypatch.setattr(module, "build_experience_fact_ledger", fail_raw_rebuild, raising=False)

    stats = CanonicalScopedFactAccessStats()
    value = guard_experience_boundaries(
        payload, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, scoped_access_stats=stats, write_log=False,
    )
    value = reconcile_resume_projects(
        value, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, scoped_access_stats=stats, write_log=False,
    )
    value = guard_fact_coverage(
        value, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, scoped_access_stats=stats, write_log=False,
    )
    value = deduplicate_resume_experience_entities(
        value, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, scoped_access_stats=stats, write_log=False,
    )
    assert len(value.resume_sections.projects) == 2


def test_canonical_dedup_keeps_distinct_rag_owners_separate():
    build = build_canonical_semantic_build(RAW)
    regression_id, customer_id, _ = _frozen_projects(build)
    payload = _payload([
        {"name": "RAG 工具", "meta": "项目经历", "time": "", "intro": "数据分析", "role": "", "details": ["数据导入"], "source_experience_id": regression_id, "immutable_source_experience_id": regression_id},
        {"name": "RAG 工具", "meta": "项目经历", "time": "", "intro": "知识库问答", "role": "", "details": ["RAG 检索"], "source_experience_id": customer_id, "immutable_source_experience_id": customer_id},
    ])

    result = deduplicate_resume_experience_entities(
        payload, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, write_log=False,
    )
    assert len(result.resume_sections.projects) == 2


def test_scoped_access_log_contains_only_aggregate_identifiers(tmp_path):
    build = build_canonical_semantic_build(RAW)
    stats = CanonicalScopedFactAccessStats(scoped_read_count=2, local_fact_recovered_count=1)
    previous = state_service.SCOPED_ACCESS_LOG_PATH
    try:
        state_service.SCOPED_ACCESS_LOG_PATH = tmp_path / "canonical_scoped_fact_access.jsonl"
        write_canonical_scoped_fact_access_log(build.ownership_index, stats, stage="test", request_id="req_12345678")
        entry = state_service.SCOPED_ACCESS_LOG_PATH.read_text(encoding="utf-8")
        assert RAW not in entry
        assert "智能客服系统" not in entry
        assert "FastAPI" not in entry
        assert "scoped_read_count" in entry
    finally:
        state_service.SCOPED_ACCESS_LOG_PATH = previous
