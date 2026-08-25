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
from app.services import docx_service, resume_section_fallback_service  # noqa: E402
from app.services.resume_body_sanitizer_service import sanitize_resume_body  # noqa: E402


RAW = "我没有实习经历，课程项目没有上线，没有真实用户；参加过比赛但没有获奖，只是课程作业，写了几个页面，调了一些接口。"


def payload_with_negative_body() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=60,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="没有实习经历，只是课程作业。",
        bold_version="简单小项目，写了几个页面。",
        boundary_version="没有上线，不能写成上线项目。",
        recommended_version="没有实习经历，但写了几个页面，调了一些接口。",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={},
            summary=["没有实习经历，没什么奖项。", "只是课程作业。"],
            skills=[],
            projects=[
                {
                    "name": "简单小项目",
                    "meta": "项目经历",
                    "time": "[待填写]",
                    "intro": "没有上线，没有真实用户，只是课程作业。",
                    "role": "写了几个页面，调了一些接口。",
                    "details": ["没有获奖。", "写了几个页面。", "调了一些接口。"],
                }
            ],
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            interview_preparation=["没有实习经历时要解释。"],
        ),
    )


def all_resume_body_text(payload: schemas.GenerationPayload) -> str:
    sections = payload.resume_sections
    projects = []
    for project in sections.projects:
        projects.append(" ".join([str(project.get("name", "")), str(project.get("meta", "")), str(project.get("intro", "")), str(project.get("role", "")), " ".join(project.get("details", []) or [])]))
    return " ".join(sections.summary + projects + sections.interview_preparation)


def test_negative_phrases_are_removed_from_summary_and_projects():
    cleaned = sanitize_resume_body(payload_with_negative_body(), RAW)
    text = all_resume_body_text(cleaned)

    for phrase in ["没有实习", "没有上线", "没有真实用户", "没有获奖", "没什么奖项"]:
        assert phrase not in text


def test_self_deprecating_phrases_are_rewritten():
    cleaned = sanitize_resume_body(payload_with_negative_body(), RAW)
    text = all_resume_body_text(cleaned)

    assert "课程项目" in text
    assert "个人项目实践" in text
    assert "参与核心页面开发与交互流程实现" in text
    assert "完成接口联调与数据流转校验" in text
    assert "只是课程作业" not in text
    assert "简单小项目" not in text


def test_interview_plan_keeps_boundary_without_negative_resume_body():
    cleaned = sanitize_resume_body(payload_with_negative_body(), RAW)

    assert any("课程项目" in item and "学习迁移能力" in item for item in cleaned.interview_plan)
    assert any("上线情况" in item for item in cleaned.interview_plan)
    assert "没有实习" not in all_resume_body_text(cleaned)


def test_docx_export_sanitizes_historical_negative_body():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    input_row = models.ExperienceInput(
        id=1,
        anonymous_user_id=None,
        session_id="s-test",
        target_role="前端开发",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="项目经历",
        raw_input=RAW,
    )
    payload = payload_with_negative_body()
    result_row = models.GenerationResult(id=71, experience_input_id=1, completeness_score=payload.completeness_score, result_json=payload.model_dump_json())
    db.add(input_row)
    db.add(result_row)
    db.commit()

    original_output_dir = docx_service.OUTPUT_DIR
    original_log_path = resume_section_fallback_service.LOG_PATH
    original_log_dir = resume_section_fallback_service.LOG_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            resume_section_fallback_service.LOG_DIR = Path(tmpdir)
            resume_section_fallback_service.LOG_PATH = Path(tmpdir) / "resume_section_fallback.jsonl"
            response = docx_service.create_docx(db, schemas.DocxCreate(anonymous_user_id="u-test", session_id="s-test", generation_result_id=71))
            assert response is not None
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            for phrase in ["没有实习", "没有上线", "没有真实用户", "没有获奖", "只是课程作业", "简单小项目"]:
                assert phrase not in text
        finally:
            docx_service.OUTPUT_DIR = original_output_dir
            resume_section_fallback_service.LOG_PATH = original_log_path
            resume_section_fallback_service.LOG_DIR = original_log_dir
    db.close()


if __name__ == "__main__":
    test_negative_phrases_are_removed_from_summary_and_projects()
    test_self_deprecating_phrases_are_rewritten()
    test_interview_plan_keeps_boundary_without_negative_resume_body()
    test_docx_export_sanitizes_historical_negative_body()
    print("resume body sanitizer tests passed")
