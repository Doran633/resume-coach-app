from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.experience_boundary_guard_service import guard_experience_boundaries  # noqa: E402
from app.services.long_input_service import analyze_long_input  # noqa: E402
from app.services.resume_output_firewall_service import guard_resume_output  # noqa: E402
from app.services.resume_role_resolution_service import resolve_resume_roles  # noqa: E402
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402
from app.services.stable_generation_fallback_service import build_stable_generation_fallback  # noqa: E402


DIRTY_ROLE = "围绕该段经历完成相关任务，具体职责以用户原文提供的信息为准。"
FORBIDDEN = ["以用户原文为准", "以用户提供的信息为准", "围绕该段经历完成相关任务", "根据用户原文", "待用户确认"]


def payload(projects, missing=None):
    return schemas.GenerationPayload(
        completeness_score=80, confirmed_facts=[], missing_questions=missing or [], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(summary=["具备项目实践能力"], skills=[], projects=projects),
    )


def project(name="项目", role=DIRTY_ROLE, details=None, source_id="EXP-001"):
    return {"name": name, "meta": "个人项目", "time": "2026", "intro": "完成项目功能开发",
        "role": role, "details": details or ["完成项目功能开发"], "source_experience_id": source_id}


def test_internal_fallback_role_is_removed_when_no_fact_supports_it():
    raw = "项目经历：完成一个课程展示。"
    result = resolve_resume_roles(payload([project()]), raw, write_log=False)
    assert result.resume_sections.projects[0]["role"] == ""
    assert "你在这段经历中具体负责哪些工作？" in result.missing_questions


def test_explicit_rag_responsibility_is_recovered_from_same_experience():
    raw = "项目经历：我负责 RAG 测试集建设，对检索效果进行评估和优化。"
    result = resolve_resume_roles(payload([project(details=[])]), raw, write_log=False)
    role = result.resume_sections.projects[0]["role"]
    assert "RAG" in role and "测试集" in role
    assert all(marker not in role for marker in FORBIDDEN)


def test_page_and_api_work_is_professionalized_without_new_hard_fact():
    raw = "项目经历：我写了几个 Vue 页面，也调了一些后端接口。"
    result = resolve_resume_roles(payload([project(details=[])]), raw, write_log=False)
    role = result.resume_sections.projects[0]["role"]
    assert "页面开发" in role and "接口联调" in role
    assert "主导" not in role and "owner" not in role.lower()


def test_role_resolution_does_not_borrow_from_other_experience():
    raw = "项目一：我负责 RAG 测试集建设。\n\n项目二：完成课程展示。"
    result = resolve_resume_roles(payload([
        project("RAG 项目", source_id="EXP-001"), project("课程展示", source_id="EXP-002"),
    ]), raw, write_log=False)
    assert "RAG" in result.resume_sections.projects[0]["role"]
    assert "RAG" not in result.resume_sections.projects[1]["role"]


def test_firewall_drops_pure_internal_role_and_preserves_real_prefix():
    dirty = payload([
        project("纯污染", DIRTY_ROLE),
        project("混合文本", "负责 RAG 测试集建设，具体职责以用户原文提供的信息为准。"),
    ])
    result = guard_resume_output(dirty, write_log=False)
    assert result.resume_sections.projects[0]["role"] == ""
    assert result.resume_sections.projects[1]["role"] == "负责 RAG 测试集建设"


def test_boundary_guard_never_writes_internal_fallback_role():
    raw = "项目一：使用 React 完成页面开发。\n\n项目二：负责 RAG 测试集建设。"
    guarded = guard_experience_boundaries(payload([
        project("前端项目", "负责 RAG 测试集建设", source_id="EXP-001"),
        project("RAG 项目", "负责 RAG 测试集建设", source_id="EXP-002"),
    ]), raw, write_log=False)
    assert DIRTY_ROLE not in guarded.model_dump_json()
    assert all("以用户原文" not in str(item.get("role")) for item in guarded.resume_sections.projects)


def test_section_and_stable_fallback_do_not_emit_internal_role_notes():
    raw = "项目经历：我负责 RAG 测试集建设，并优化检索效果。"
    empty = payload([])
    filled = fill_resume_sections(empty, raw_input=raw, write_log=False)
    assert all(marker not in filled.model_dump_json() for marker in FORBIDDEN)
    request = schemas.GenerateRequest(anonymous_user_id="u", session_id="s", target_role="AI Agent",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=raw)
    stable = build_stable_generation_fallback(request, analyze_long_input(raw))
    assert all(marker not in stable.model_dump_json() for marker in FORBIDDEN)


def test_section_fallback_cleans_historical_internal_role():
    raw = "项目经历：我负责 RAG 测试集建设。"
    dirty = payload([project(role=DIRTY_ROLE)])
    result = fill_resume_sections(dirty, raw_input=raw, write_log=False)
    assert DIRTY_ROLE not in result.model_dump_json()
    assert "RAG" in result.resume_sections.projects[0]["role"]


def test_historical_docx_removes_internal_role_or_omits_empty_role_line():
    raw = "项目经历：完成课程展示。"
    dirty = payload([project()])
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="前端开发",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=raw))
    db.add(models.GenerationResult(id=956, experience_input_id=1, completeness_score=80, result_json=dirty.model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=956))
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert all(marker not in text for marker in FORBIDDEN)
            assert "具体职责以" not in text and "相关任务" not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()
