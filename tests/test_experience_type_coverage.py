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
from app.services import resume_section_fallback_service  # noqa: E402
from app.services.fact_guard_service import guard_hard_facts  # noqa: E402
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402


INTERNSHIP_RAW = """实习经历｜字节跳动前端开发实习
参与内部运营后台页面开发，负责活动配置页面、表单校验、接口联调和缺陷修复，配合团队完成需求验收。"""

RESEARCH_RAW = """科研经历｜工业工程排程优化研究
参与课程科研课题，围绕生产排程问题整理文献、构建约束条件、设计启发式求解思路，并完成实验记录和报告撰写。"""

COMPETITION_RAW = """竞赛经历｜大学生创新创业训练项目
负责项目方案设计、需求分析、原型展示和答辩材料整理，最终完成校级立项展示。"""

MIXED_RAW = f"""项目经历｜AI RAG 智能助手
使用 React、FastAPI 和 RAG 实现资料上传、向量检索和问答。

{INTERNSHIP_RAW}

{COMPETITION_RAW}
"""


def base_payload():
    return {
        "completeness_score": 75,
        "confirmed_facts": ["用户提供了多类经历"],
        "missing_questions": [],
        "normal_version": "用户具备项目、实习或竞赛经历。",
        "bold_version": "用户具备项目、实习或竞赛经历。",
        "boundary_version": "不要写成不存在的企业级生产系统。",
        "recommended_version": "用户具备项目、实习或竞赛经历。",
        "claims": [],
        "interview_plan": ["准备介绍各段经历的职责边界。"],
        "knowledge_checklist": ["React", "FastAPI", "RAG"],
        "resume_sections": {
            "personal_info": {"姓名": "[待填写]", "求职意向": "前端开发"},
            "summary": ["具备多类实践经历。"],
            "skills": ["React", "FastAPI", "RAG"],
            "projects": [],
            "education": {"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            "interview_preparation": [],
        },
    }


def metas(payload: schemas.GenerationPayload) -> list[str]:
    return [project["meta"] for project in payload.resume_sections.projects]


def names(payload: schemas.GenerationPayload) -> list[str]:
    return [project["name"] for project in payload.resume_sections.projects]


def test_internship_experience_is_kept_as_internship_meta():
    payload = fill_resume_sections(base_payload(), raw_input=INTERNSHIP_RAW, write_log=False)

    assert "实习经历" in metas(payload)
    assert "字节跳动前端开发实习" in names(payload)


def test_research_experience_is_kept_as_research_meta():
    payload = fill_resume_sections(base_payload(), raw_input=RESEARCH_RAW, write_log=False)

    assert "科研经历" in metas(payload)
    assert "工业工程排程优化研究" in names(payload)


def test_competition_experience_is_kept_as_competition_meta():
    payload = fill_resume_sections(base_payload(), raw_input=COMPETITION_RAW, write_log=False)

    assert "竞赛经历" in metas(payload)
    assert "大学生创新创业训练项目" in names(payload)


def test_mixed_project_internship_competition_keeps_three_entries():
    data = base_payload()
    data["resume_sections"]["projects"] = [
        {
            "name": "AI RAG 智能助手",
            "meta": "项目经历",
            "time": "[待填写]",
            "intro": "使用 React、FastAPI 和 RAG 实现资料上传、向量检索和问答。",
            "role": "负责核心功能设计与实现。",
            "details": ["实现资料上传、向量检索和问答链路。"],
        }
    ]
    payload = fill_resume_sections(data, raw_input=MIXED_RAW, write_log=False)

    assert len(payload.resume_sections.projects) >= 3
    assert "项目经历" in metas(payload)
    assert "实习经历" in metas(payload)
    assert "竞赛经历" in metas(payload)


def test_fact_guard_keeps_real_internship_experience():
    data = base_payload()
    data["resume_sections"]["projects"] = [
        {
            "name": "字节跳动前端开发实习",
            "meta": "实习经历",
            "time": "[待填写]",
            "intro": "参与内部运营后台页面开发。",
            "role": "负责页面开发和接口联调。",
            "details": ["参与真实业务团队协作，完成需求验收。"],
        }
    ]
    guarded = guard_hard_facts(data, INTERNSHIP_RAW)
    text = guarded.model_dump_json()

    assert "实习经历" in text
    assert "字节跳动前端开发实习" in text
    assert "真实业务团队协作" in text


def test_docx_contains_separated_experience_headings_and_non_project_content():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    input_row = models.ExperienceInput(
        id=1,
        anonymous_user_id=None,
        session_id="s-test",
        target_role="前端开发",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="综合经历",
        raw_input=MIXED_RAW,
    )
    # DOCX receives the persisted, post-fallback snapshot. Export must not
    # reconstruct missing sections from the linked raw input.
    payload = fill_resume_sections(base_payload(), raw_input=MIXED_RAW, write_log=False)
    result_row = models.GenerationResult(
        id=51,
        experience_input_id=1,
        completeness_score=payload.completeness_score,
        result_json=payload.model_dump_json(),
    )
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
            response = docx_service.create_docx(
                db,
                schemas.DocxCreate(anonymous_user_id="u-test", session_id="s-test", generation_result_id=51),
            )
            assert response is not None
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert "项目经历" in text
            assert "实习经历" in text
            assert "竞赛经历" in text
            assert "字节跳动前端开发实习" in text
            assert "大学生创新创业训练项目" in text
        finally:
            docx_service.OUTPUT_DIR = original_output_dir
            resume_section_fallback_service.LOG_PATH = original_log_path
            resume_section_fallback_service.LOG_DIR = original_log_dir
    db.close()


if __name__ == "__main__":
    test_internship_experience_is_kept_as_internship_meta()
    test_research_experience_is_kept_as_research_meta()
    test_competition_experience_is_kept_as_competition_meta()
    test_mixed_project_internship_competition_keeps_three_entries()
    test_fact_guard_keeps_real_internship_experience()
    test_docx_contains_separated_experience_headings_and_non_project_content()
    print("experience type coverage tests passed")
