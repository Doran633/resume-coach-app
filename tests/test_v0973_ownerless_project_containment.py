import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import experience_slot_service as slot_service  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.experience_slot_service import contain_ownerless_projects  # noqa: E402


RAW = """项目经历：课程资料助手
独立完成课程资料助手，支持资料整理与检索问答。"""

MULTI_RAW = """项目一：回归分析计算器
完成数据导入与回归模型对比。

项目二：智能客服系统
完成 RAG 检索问答与服务部署。"""


def _payload(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="", boundary_version="",
        recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(summary=[], skills=[], projects=projects, education={}, interview_preparation=[]),
    )


def _bound(owner: str, *, name: str = "课程资料助手") -> dict:
    return {
        "name": name, "meta": "项目经历", "time": "[待填写]", "intro": "完成资料整理与检索问答。",
        "role": "独立开发", "details": ["实现资料整理与检索问答。"],
        "source_experience_id": owner, "immutable_source_experience_id": owner,
        "source_binding_locked": True,
    }


def _unowned(*, name: str = "LLM 候选项目") -> dict:
    return {
        "name": name, "meta": "项目经历", "time": "[待填写]", "intro": "完成相关功能。",
        "role": "开发", "details": ["实现服务与部署。"],
        "source_experience_id": "", "source_binding_locked": False,
    }


def test_containment_removes_unowned_llm_candidate_and_keeps_frozen_fallback_project():
    build = build_canonical_semantic_build(RAW)
    owner = build.identities[0].experience_id
    payload = _payload([_unowned(), _bound(owner, name="课程资料助手")])

    result, stats = contain_ownerless_projects(payload, build.ownership_index, return_stats=True, write_log=False)

    assert [project["name"] for project in result.resume_sections.projects] == ["课程资料助手"]
    assert result.resume_sections.projects[0]["immutable_source_experience_id"] == owner
    assert stats.unowned_candidate_count == 1
    assert stats.removed_unowned_project_count == 1
    assert stats.contract_passed is True


def test_unowned_project_is_never_inferred_from_singleton_title_stack_or_position():
    build = build_canonical_semantic_build(RAW)
    candidate = _unowned(name="课程资料助手")
    candidate["details"] = ["使用同一技术栈完成检索问答。"]
    candidate["position"] = "第一个项目"

    result, stats = contain_ownerless_projects(_payload([candidate]), build.ownership_index, return_stats=True, write_log=False)

    assert result.resume_sections.projects == []
    assert stats.owner_bound_project_count == 0
    assert result.missing_questions == ["请补充无法确认归属经历的具体名称和可验证事实。"]


def test_multi_experience_unowned_candidate_is_not_merged_into_another_owner():
    build = build_canonical_semantic_build(MULTI_RAW)
    owner = build.identities[0].experience_id
    payload = _payload([_bound(owner, name="回归分析计算器"), _unowned(name="智能客服系统")])
    fact_ids_before = tuple(fact.fact_id for fact in build.ledger.facts)

    result, _ = contain_ownerless_projects(payload, build.ownership_index, return_stats=True, write_log=False)

    assert len(result.resume_sections.projects) == 1
    assert result.resume_sections.projects[0]["immutable_source_experience_id"] == owner
    assert tuple(fact.fact_id for fact in build.ledger.facts) == fact_ids_before


def test_final_containment_removes_late_unowned_project_without_changing_bound_project():
    build = build_canonical_semantic_build(RAW)
    owner = build.identities[0].experience_id
    initially_safe, _ = contain_ownerless_projects(
        _payload([_bound(owner)]), build.ownership_index, return_stats=True, write_log=False,
    )
    initially_safe.resume_sections.projects.append(_unowned(name="后续污染候选"))

    final, stats = contain_ownerless_projects(
        initially_safe, build.ownership_index, stage="before_persistence", return_stats=True, write_log=False,
    )

    assert len(final.resume_sections.projects) == 1
    assert final.resume_sections.projects[0]["immutable_source_experience_id"] == owner
    assert stats.removed_unowned_project_count == 1
    assert stats.ownerless_visible_after_count == 0


def test_contract_log_is_aggregate_only(tmp_path):
    build = build_canonical_semantic_build(RAW)
    previous = slot_service.OWNER_DELIVERY_CONTRACT_LOG_PATH
    try:
        slot_service.OWNER_DELIVERY_CONTRACT_LOG_PATH = tmp_path / "canonical_owner_delivery_contract.jsonl"
        contain_ownerless_projects(_payload([_unowned()]), build.ownership_index, request_id="req_12345678", attempt_id="attempt_safe")
        content = slot_service.OWNER_DELIVERY_CONTRACT_LOG_PATH.read_text(encoding="utf-8")
        record = json.loads(content)
        assert RAW not in content
        assert "课程资料助手" not in content
        assert "检索问答" not in content
        assert record["canonical_owner_ids"] == [build.identities[0].experience_id]
        assert record["ownerless_visible_after_count"] == 0
    finally:
        slot_service.OWNER_DELIVERY_CONTRACT_LOG_PATH = previous


def test_generation_persists_no_project_without_a_valid_frozen_owner(monkeypatch, tmp_path):
    """The final containment pass protects persistence if a late candidate appears."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        monkeypatch.setenv("LLM_MODE", "mock")
        monkeypatch.setattr(generation_service, "LOG_DIR", tmp_path)
        monkeypatch.setattr(generation_service, "build_mock_generation", lambda _request: _payload([_unowned()]))
        response = generation_service.create_generation(
            db,
            schemas.GenerateRequest(
                anonymous_user_id="anon-ownerless", session_id="session-ownerless", target_role="后端开发",
                mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW,
                attempt_id="attempt_ownerless_test",
            ),
            request_id="req_ownerless_test",
        )

        projects = response.result.resume_sections.projects
        assert all(project.get("source_experience_id") for project in projects)
        assert all(project.get("source_experience_id") == build_canonical_semantic_build(RAW).identities[0].experience_id for project in projects)
    finally:
        db.close()


def test_generation_keeps_a_normal_owner_bound_project_through_final_contract(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        monkeypatch.setenv("LLM_MODE", "mock")
        monkeypatch.setattr(generation_service, "LOG_DIR", tmp_path)
        response = generation_service.create_generation(
            db,
            schemas.GenerateRequest(
                anonymous_user_id="anon-owner-bound", session_id="session-owner-bound", target_role="后端开发",
                mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW,
                attempt_id="attempt_owner_bound_test",
            ),
            request_id="req_owner_bound_test",
        )

        projects = response.result.resume_sections.projects
        assert projects
        assert all(project.get("source_experience_id") for project in projects)
        assert all(project["source_experience_id"] == build_canonical_semantic_build(RAW).identities[0].experience_id for project in projects)
    finally:
        db.close()
