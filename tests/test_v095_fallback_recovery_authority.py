import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import canonical_semantic_state_service as state_service  # noqa: E402
from app.services import resume_experience_validity_service as validity_service  # noqa: E402
from app.services import resume_role_resolution_service as role_service  # noqa: E402
from app.services import resume_section_fallback_service as section_service  # noqa: E402
from app.services import stable_generation_fallback_service as stable_service  # noqa: E402
from app.services.canonical_semantic_state_service import (  # noqa: E402
    CanonicalFallbackRecoveryStats,
    build_canonical_semantic_build,
    write_canonical_fallback_recovery_log,
)
from app.services.long_input_service import analyze_long_input  # noqa: E402
from app.services.resume_experience_validity_service import ensure_resume_experience_validity  # noqa: E402
from app.services.resume_role_resolution_service import resolve_resume_roles  # noqa: E402
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402
from app.services.stable_generation_fallback_service import build_stable_generation_fallback  # noqa: E402


RAW = """项目一：回归分析计算器
独立完成回归分析计算器，支持数据导入、多种回归模型对比和智能制图。

项目二：智能停车系统
负责产品服务与技术分析，使用 LoRa 无线通信和地磁传感器，实现地图寻找车位和实时路线规划。

项目三：智能客服系统
独立开发 RAG 智能客服系统，使用 FastAPI、React 和 Docker 部署；建立 120 条测试集，命中率达到 81%。

校园经历：迎新志愿活动
参加迎新志愿活动，负责引导新生和搬运物资，没有技术开发职责。

备注：不要为了让简历更丰富给志愿经历补技术；框架可能是 Flask，也可能是 FastAPI，记不清。"""


def _payload(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="", boundary_version="",
        recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(summary=[], skills=[], projects=projects, education={}, interview_preparation=[]),
    )


def _ids(build):
    return [identity.experience_id for identity in build.identities]


def test_canonical_section_fallback_uses_only_local_eligible_facts():
    build = build_canonical_semantic_build(RAW)
    filled = fill_resume_sections(
        _payload([]), raw_input="RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build, write_log=False,
    )
    by_owner = {project.get("source_experience_id"): project for project in filled.resume_sections.projects}
    volunteer_id = _ids(build)[3]
    volunteer_text = "\n".join(by_owner[volunteer_id].get("details", []))
    assert "RAG" not in volunteer_text
    assert "Docker" not in volunteer_text
    assert "120" not in volunteer_text
    assert "FastAPI" not in volunteer_text


def test_stable_fallback_keeps_parking_and_regression_facts_separate():
    build = build_canonical_semantic_build(RAW)
    request = schemas.GenerateRequest(
        anonymous_user_id="u", session_id="s", target_role="后端开发",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW,
    )
    result = build_stable_generation_fallback(
        request, analyze_long_input(RAW), semantic_build=build,
    )
    projects = {project["source_experience_id"]: project for project in result.resume_sections.projects}
    regression_id, parking_id = _ids(build)[:2]
    assert "LoRa" not in "\n".join(projects[regression_id]["details"])
    assert "回归" not in "\n".join(projects[parking_id]["details"])
    assert "Flask" not in result.model_dump_json()
    assert "不要为了让简历更丰富" not in result.model_dump_json()


def test_canonical_role_recovery_requires_immutable_owner():
    build = build_canonical_semantic_build(RAW)
    customer_id = _ids(build)[2]
    unowned = _payload([{
        "name": "未确认项目", "meta": "项目经历", "time": "", "intro": "", "role": "负责相关工作", "details": [],
        "source_experience_id": customer_id,
    }])
    stats = CanonicalFallbackRecoveryStats()
    result = resolve_resume_roles(
        unowned, "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, recovery_stats=stats, write_log=False,
    )
    project = result.resume_sections.projects[0]
    assert project["role"] == ""
    assert "immutable_source_experience_id" not in project
    assert stats.unowned_project_skipped_count == 1


def test_canonical_role_recovery_uses_only_frozen_local_fact():
    build = build_canonical_semantic_build(RAW)
    customer_id, volunteer_id = _ids(build)[2:4]
    result = resolve_resume_roles(
        _payload([
            {
                "name": "智能客服系统", "meta": "项目经历", "time": "", "intro": "", "role": "负责相关工作", "details": [],
                "source_experience_id": customer_id, "immutable_source_experience_id": customer_id,
            },
            {
                "name": "迎新志愿活动", "meta": "校园 / 社团经历", "time": "", "intro": "", "role": "负责相关工作", "details": [],
                "source_experience_id": volunteer_id, "immutable_source_experience_id": volunteer_id,
            },
        ]),
        "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build, ownership_index=build.ownership_index, write_log=False,
    )
    roles = [project["role"] for project in result.resume_sections.projects]
    assert "RAG" in roles[0]
    assert "RAG" not in roles[1]


def test_canonical_validity_never_recovers_generic_project_from_raw_input():
    build = build_canonical_semantic_build(RAW)
    result = ensure_resume_experience_validity(
        _payload([{
            "name": "其他经历", "meta": "项目经历", "time": "", "intro": "", "role": "", "details": ["完成相关工作"],
            "source_experience_id": _ids(build)[0],
        }]),
        "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build, ownership_index=build.ownership_index, write_log=False,
    )
    assert result.resume_sections.projects == []
    assert result.missing_questions


def test_canonical_fallback_consumers_do_not_rebuild_raw_input(monkeypatch):
    build = build_canonical_semantic_build(RAW)

    def fail_raw_rebuild(*_args, **_kwargs):
        raise AssertionError("canonical fallback attempted raw input rebuild")

    for module in [stable_service, section_service, role_service, validity_service]:
        monkeypatch.setattr(module, "build_experience_identities", fail_raw_rebuild, raising=False)
        monkeypatch.setattr(module, "build_experience_fact_ledger", fail_raw_rebuild, raising=False)

    request = schemas.GenerateRequest(
        anonymous_user_id="u", session_id="s", target_role="后端开发",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW,
    )
    build_stable_generation_fallback(request, analyze_long_input(RAW), semantic_build=build)
    fill_resume_sections(_payload([]), raw_input="RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build, write_log=False)
    resolve_resume_roles(
        _payload([]), "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, write_log=False,
    )
    ensure_resume_experience_validity(
        _payload([]), "RAW_INPUT_MUST_NOT_BE_READ", semantic_build=build,
        ownership_index=build.ownership_index, write_log=False,
    )


def test_canonical_fallback_log_excludes_user_text(tmp_path):
    build = build_canonical_semantic_build(RAW)
    stats = CanonicalFallbackRecoveryStats(local_fact_detail_recovered_count=2, missing_question_count=1)
    previous = state_service.FALLBACK_RECOVERY_LOG_PATH
    try:
        state_service.FALLBACK_RECOVERY_LOG_PATH = tmp_path / "canonical_fallback_recovery.jsonl"
        write_canonical_fallback_recovery_log(
            build.ownership_index, stats, stage="test", request_id="req_12345678", attempt_id="attempt_12345678",
        )
        entry = state_service.FALLBACK_RECOVERY_LOG_PATH.read_text(encoding="utf-8")
        assert RAW not in entry
        assert "智能客服系统" not in entry
        assert "FastAPI" not in entry
        assert "local_fact_detail_recovered_count" in entry
        assert json.loads(entry)["request_id"] == "req_12345678"
    finally:
        state_service.FALLBACK_RECOVERY_LOG_PATH = previous
