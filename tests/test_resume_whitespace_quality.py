from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.experience_fact_ledger_service import build_experience_fact_ledger  # noqa: E402
from app.services.resume_whitespace_quality_service import (  # noqa: E402
    ensure_resume_whitespace_quality, normalize_resume_whitespace,
)
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def payload(details=None, intro="项目 简介"):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]"}, education={"学校": "[待填写]"},
            projects=[{"name": "AI Agent 项目", "meta": "个人项目", "time": "2026",
                "intro": intro, "role": "独立 开发", "details": details or [],
                "source_experience_id": "EXP-001", "source_fact_ids": ["EXP-001-F001"]}],
        ),
    )


def test_chinese_internal_and_punctuation_spaces_are_cleaned():
    assert normalize_resume_whitespace("项目 经验") == "项目经验"
    assert normalize_resume_whitespace("完成部署 ， 并上线") == "完成部署，并上线"
    assert normalize_resume_whitespace("业务 完整性检查") == "业务完整性检查"
    assert normalize_resume_whitespace("建立 经历级事实边界") == "建立经历级事实边界"


def test_quote_and_parenthesis_inner_spaces_are_cleaned():
    assert normalize_resume_whitespace("“ 表达强度 ”") == "“表达强度”"
    assert normalize_resume_whitespace("（ 如掌握 ）") == "（如掌握）"


def test_special_and_repeated_spaces_are_normalized():
    assert normalize_resume_whitespace("完成\u00a0\u00a0项目") == "完成项目"
    assert normalize_resume_whitespace("完成\u3000项目") == "完成项目"
    assert normalize_resume_whitespace("完成\u200b项目") == "完成项目"
    assert normalize_resume_whitespace("AI\u200bAgent") == "AI Agent"
    assert normalize_resume_whitespace("使用   React") == "使用 React"


def test_protected_technical_phrases_and_units_remain_natural():
    phrases = [
        "AI Agent", "JSON Schema", "Resume Section Fallback", "Citation Source Cards",
        "Experience Fact Ledger", "Smoke Test", "React 18", "500 名用户", "1400 Token/次",
        "https://resume.example.com", "resume_guard_service.py", "[待填写]",
    ]
    for phrase in phrases:
        assert normalize_resume_whitespace(phrase) == phrase
    assert normalize_resume_whitespace("AIAgent") == "AI Agent"
    assert normalize_resume_whitespace("JSONSchema") == "JSON Schema"


def test_payload_cleanup_preserves_internal_ids_and_experience_boundaries():
    source = payload(["完成 业务 校验 ，支持 AI Agent"])
    cleaned = ensure_resume_whitespace_quality(source, write_log=False)
    project = cleaned.resume_sections.projects[0]
    assert project["details"] == ["完成业务校验，支持 AI Agent"]
    assert project["source_experience_id"] == "EXP-001"
    assert project["source_fact_ids"] == ["EXP-001-F001"]


def test_fact_ledger_source_spans_are_not_changed_by_output_cleanup():
    raw = "独立开发 AI Agent，完成项目 部署。"
    before = [(fact.fact_id, fact.source_span) for fact in build_experience_fact_ledger(raw).facts]
    ensure_resume_whitespace_quality(payload([raw]), write_log=False)
    after = [(fact.fact_id, fact.source_span) for fact in build_experience_fact_ledger(raw).facts]
    assert before == after


def test_historical_docx_cleans_spaces_without_breaking_technical_phrases():
    raw = "独立开发 AI Agent，使用 JSON Schema 校验输出，并设计 Resume Section Fallback。"
    stored = payload([
        "独立 开发 AI Agent ，使用 JSON Schema 校验输出",
        "设计 Resume Section Fallback ，避免空白 导出",
    ])
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="AI Agent",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=raw))
    db.add(models.GenerationResult(id=954, experience_input_id=1, completeness_score=90,
        result_json=stored.model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=954))
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert "独立 开发" not in text and "空白 导出" not in text
            assert "AIAgent" not in text and "JSONSchema" not in text
            assert "AI Agent" in text and "JSON Schema" in text and "Resume Section Fallback" in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()
