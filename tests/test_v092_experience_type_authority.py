import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import canonical_semantic_state_service as state_service  # noqa: E402
from app.services import experience_type_resolution_service as type_service  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.experience_type_resolution_service import resolve_project_types  # noqa: E402
from app.services.resume_section_routing_service import route_resume_projects  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


PAPER_PROJECT = """项目二：论文阅读助手
独立开发论文阅读助手，完成论文解析、检索和问答。"""
RESEARCH = """科研经历：论文阅读课题
在实验室参与课题研究，完成论文投稿。"""
MULTI_EXPERIENCE = """项目经历：论文阅读助手
独立开发论文阅读助手，完成论文解析和检索问答。

实习经历：星河科技有限公司
担任后端开发实习生，参与接口开发和联调。

竞赛经历：数学建模比赛
参加数学建模比赛，完成赛题分析和答辩。

校园经历：迎新志愿活动
参与迎新志愿活动，负责新生引导和物资搬运。"""


def _payload(projects: list[dict]) -> schemas.GenerationPayload:
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
        resume_sections=schemas.ResumeSections(projects=projects),
    )


def test_explicit_project_label_freezes_paper_assistant_as_project():
    build = build_canonical_semantic_build(PAPER_PROJECT)
    decision = build.canonical_type_by_experience_id["EXP-001"]

    assert decision.canonical_experience_type == "项目经历"
    assert decision.type_source == "declared_experience_type"
    assert decision.explicit is True
    assert decision.confidence == 1.0


def test_explicit_research_label_stays_research():
    build = build_canonical_semantic_build(RESEARCH)

    assert build.canonical_type_by_experience_id["EXP-001"].canonical_experience_type == "科研经历"


def test_canonical_authority_corrects_llm_type_without_reading_raw_input(monkeypatch):
    build = build_canonical_semantic_build(PAPER_PROJECT)
    payload = _payload([
        {"name": "论文阅读助手", "meta": "科研经历", "details": ["完成论文解析"], "source_experience_id": "EXP-001"},
    ])

    def fail_legacy_resolution(_raw_input):
        raise AssertionError("canonical authority must not rebuild types from raw_input")

    monkeypatch.setattr(type_service, "build_type_resolutions", fail_legacy_resolution)
    resolved = resolve_project_types(
        payload,
        canonical_type_decisions=build.canonical_type_by_experience_id,
        write_log=False,
    )

    project = resolved.resume_sections.projects[0]
    assert project["meta"] == "项目经历"
    assert project["resolved_experience_type"] == "项目经历"
    assert project["type_locked"] is True


def test_missing_owner_never_receives_a_guessed_canonical_type(tmp_path, monkeypatch):
    build = build_canonical_semantic_build(PAPER_PROJECT)
    payload = _payload([
        {"name": "无归属项目", "meta": "科研经历", "details": ["完成展示"], "source_experience_id": ""},
    ])
    old_path = type_service.LOG_PATH
    try:
        type_service.LOG_PATH = tmp_path / "type-resolution.jsonl"
        resolved = resolve_project_types(
            payload,
            canonical_type_decisions=build.canonical_type_by_experience_id,
            stage="test",
        )
        entry = json.loads(type_service.LOG_PATH.read_text(encoding="utf-8").strip())
        assert resolved.resume_sections.projects[0]["meta"] == "科研经历"
        assert "resolved_experience_type" not in resolved.resume_sections.projects[0]
        assert entry["canonical_mapping_found"] is False
        assert PAPER_PROJECT not in json.dumps(entry, ensure_ascii=False)
        assert "论文阅读助手" not in json.dumps(entry, ensure_ascii=False)
    finally:
        type_service.LOG_PATH = old_path


def test_before_save_canonical_check_is_read_only(tmp_path):
    build = build_canonical_semantic_build(PAPER_PROJECT)
    payload = _payload([
        {"name": "论文阅读助手", "meta": "科研经历", "details": ["完成论文解析"], "source_experience_id": "EXP-001"},
    ])
    frozen = resolve_project_types(
        payload,
        canonical_type_decisions=build.canonical_type_by_experience_id,
        write_log=False,
    )
    frozen.resume_sections.projects[0]["meta"] = "科研经历"
    old_path = type_service.LOG_PATH
    try:
        type_service.LOG_PATH = tmp_path / "type-resolution.jsonl"
        checked = resolve_project_types(
            frozen,
            canonical_type_decisions=build.canonical_type_by_experience_id,
            apply_canonical_types=False,
            stage="before_save_type_validation",
        )
        entry = json.loads(type_service.LOG_PATH.read_text(encoding="utf-8").strip())
        assert checked.resume_sections.projects[0]["meta"] == "科研经历"
        assert entry["write_mode"] == "validate"
        assert entry["correction_applied"] is False
        assert entry["conflict_detected"] is True
    finally:
        type_service.LOG_PATH = old_path


def test_canonical_types_route_independent_experiences_without_cross_contamination():
    build = build_canonical_semantic_build(MULTI_EXPERIENCE)
    payload = _payload([
        {"name": "论文阅读助手", "meta": "科研经历", "details": ["解析论文"], "source_experience_id": "EXP-001"},
        {"name": "星河科技", "meta": "项目经历", "details": ["接口联调"], "source_experience_id": "EXP-002"},
        {"name": "数学建模比赛", "meta": "项目经历", "details": ["完成答辩"], "source_experience_id": "EXP-003"},
        {"name": "迎新志愿活动", "meta": "项目经历", "details": ["引导新生"], "source_experience_id": "EXP-004"},
    ])

    resolved = resolve_project_types(
        payload,
        canonical_type_decisions=build.canonical_type_by_experience_id,
        write_log=False,
    )
    routes = {project["source_experience_id"]: heading for heading, items in route_resume_projects(resolved.resume_sections.projects) for project in items}

    assert routes == {
        "EXP-001": "项目经历",
        "EXP-002": "实习经历",
        "EXP-003": "竞赛经历",
        "EXP-004": "校园 / 社团经历",
    }


def test_canonical_type_logs_keep_only_safe_type_metadata(tmp_path):
    build = build_canonical_semantic_build(PAPER_PROJECT)
    payload = _payload([
        {"name": "论文阅读助手", "meta": "科研经历", "details": ["完成论文解析"], "source_experience_id": "EXP-001"},
    ])
    old_path = type_service.LOG_PATH
    try:
        type_service.LOG_PATH = tmp_path / "type-resolution.jsonl"
        resolve_project_types(payload, canonical_type_decisions=build.canonical_type_by_experience_id, stage="test")
        entry = type_service.LOG_PATH.read_text(encoding="utf-8")
        assert PAPER_PROJECT not in entry
        assert "论文阅读助手" not in entry
        assert '"canonical_type_source": "declared_experience_type"' in entry
        assert '"canonical_type_explicit": true' in entry
    finally:
        type_service.LOG_PATH = old_path


def test_generation_applies_type_freeze_once_then_only_validates(tmp_path, monkeypatch):
    original_mode = os.environ.get("LLM_MODE")
    original_log_dir = generation_service.LOG_DIR
    original_state_log = state_service.LOG_PATH
    original_resolver = generation_service.resolve_project_types
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    calls: list[dict] = []
    try:
        monkeypatch.setenv("LLM_MODE", "mock")
        generation_service.LOG_DIR = tmp_path
        state_service.LOG_PATH = tmp_path / "canonical-state.jsonl"

        def capture_resolver(payload, raw_input=None, **kwargs):
            calls.append({
                "raw_input": raw_input,
                "stage": kwargs.get("stage"),
                "apply": kwargs.get("apply_canonical_types", True),
                "has_canonical_types": bool(kwargs.get("canonical_type_decisions")),
            })
            return original_resolver(payload, raw_input, **kwargs)

        monkeypatch.setattr(generation_service, "resolve_project_types", capture_resolver)
        request = schemas.GenerateRequest(
            anonymous_user_id="anon-v092",
            session_id="session-v092",
            target_role="后端开发",
            mode="full_resume",
            packaging_level="大胆",
            experience_type="综合经历",
            raw_input=PAPER_PROJECT,
            attempt_id="attempt_v092_type_freeze",
        )
        response = generation_service.create_generation(db, request, request_id="req_v092_type_freeze")

        assert [(item["stage"], item["apply"]) for item in calls] == [
            ("generation_type_freeze", True),
            ("before_save_type_validation", False),
        ]
        assert all(item["raw_input"] is None for item in calls)
        assert all(item["has_canonical_types"] for item in calls)
        assert "canonical_experience_type" not in response.result.model_dump_json()
    finally:
        generation_service.LOG_DIR = original_log_dir
        state_service.LOG_PATH = original_state_log
        db.close()
        if original_mode is None:
            os.environ.pop("LLM_MODE", None)
        else:
            os.environ["LLM_MODE"] = original_mode
