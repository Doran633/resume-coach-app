from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.input_content_classification_service import classify_input_content  # noqa: E402
from app.services.resume_output_firewall_service import guard_resume_output  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = "我独立完成回归分析工具，使用 CodeBuddy 连接虚拟机，想投 AI Agent 开发，希望包装得更专业，但不要写成完全无法解释的内容。"


def payload(details: list[str]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=70, confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(summary=[], skills=[], projects=[{
            "name": "回归分析工具", "meta": "个人项目", "time": "[待填写]",
            "intro": "完成回归分析工具开发", "role": "独立开发", "details": details,
            "source_experience_id": "EXP-001",
        }]))


def project_text(result: schemas.GenerationPayload) -> str:
    project = result.resume_sections.projects[0]
    return "\n".join([project.get("intro", ""), project.get("role", ""), *project.get("details", [])])


def test_input_is_classified_without_losing_fact_content():
    result = classify_input_content(RAW)
    assert result.experience_facts
    assert result.target_intents
    assert result.packaging_instructions


def test_mixed_fact_and_instruction_keeps_only_fact():
    result = guard_resume_output(payload([
        "使用 CodeBuddy 连接虚拟机完成项目开发，希望包装得更适合 AI Agent 岗位，但不要写成完全无法解释的内容。"
    ]), RAW, write_log=False)
    text = project_text(result)
    assert "CodeBuddy" in text and "虚拟机" in text
    assert "希望包装" not in text and "无法解释" not in text and "不要写成" not in text
    assert not text.endswith("但")


def test_target_intent_and_template_residue_do_not_reach_resume():
    result = guard_resume_output(payload([
        "想投前端开发", "哪些地方想重点放大", "我匹配度，但不要写成完全无法解释的内容"
    ]), RAW, write_log=False)
    text = project_text(result)
    assert "想投" not in text
    assert "哪些地方想重点放大" not in text
    assert "我匹配度" not in text


def test_real_internship_job_title_is_not_removed():
    result = guard_resume_output(payload(["担任 AI Agent 开发实习生，参与检索模块测试。"]), RAW, write_log=False)
    assert "AI Agent 开发实习生" in project_text(result)


def test_historical_docx_removes_instruction_leakage():
    dirty = guard_resume_output(payload([
        "技术动作：我独立完成回归分析工具，希望包装得更适合 AI Agent 岗位，但不要写成无法解释的内容"
    ]), RAW, write_log=False)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="AI / 大模型 / Agent",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW))
    db.add(models.GenerationResult(id=806, experience_input_id=1, completeness_score=70,
        result_json=dirty.model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=806))
            text = "\n".join(p.text for p in Document(Path(tmpdir) / response.file_name).paragraphs)
            for phrase in ["技术动作", "希望包装", "不要写成", "无法解释"]:
                assert phrase not in text, f"DOCX still contains {phrase.encode('unicode_escape')}: {text.encode('unicode_escape')}"
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


if __name__ == "__main__":
    test_input_is_classified_without_losing_fact_content()
    test_mixed_fact_and_instruction_keeps_only_fact()
    test_target_intent_and_template_residue_do_not_reach_resume()
    test_real_internship_job_title_is_not_removed()
    test_historical_docx_removes_instruction_leakage()
    print("resume output firewall tests passed")
