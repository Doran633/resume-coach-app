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
from app.services.experience_identity_service import build_experience_identities  # noqa: E402
from app.services.long_input_service import analyze_long_input  # noqa: E402
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402
from app.services.stable_generation_fallback_service import build_stable_generation_fallback  # noqa: E402


RAW_INPUT = """项目一｜AI RAG 智能助手
使用 React、FastAPI、RAG、Embedding 实现资料上传、向量检索和问答，通过公网域名部署，有 500 用户访问记录。

项目二｜课程后台管理系统
使用 Vue 完成商品列表、详情页、发布页面、登录页面、表单校验和接口联调。
"""


def request() -> schemas.GenerateRequest:
    return schemas.GenerateRequest(
        anonymous_user_id="u-test",
        session_id="s-test",
        target_role="AI / 大模型 / Agent",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="综合经历",
        raw_input=RAW_INPUT,
    )


def payload_with_projects(projects: list[dict]) -> schemas.GenerationPayload:
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
        resume_sections=schemas.ResumeSections(
            summary=[],
            skills=[],
            projects=projects,
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            interview_preparation=[],
        ),
    )


def test_two_experiences_get_distinct_experience_ids():
    identities = build_experience_identities(RAW_INPUT)

    assert [item.experience_id for item in identities] == ["EXP-001", "EXP-002"]
    assert identities[0].title == "AI RAG 智能助手"
    assert identities[1].title == "课程后台管理系统"


def test_source_id_cleans_tech_contamination():
    payload = payload_with_projects(
        [
            {
                "name": "AI RAG 智能助手",
                "meta": "项目经历",
                "time": "[待填写]",
                "intro": "RAG 项目",
                "role": "负责 RAG",
                "details": ["使用 React 和 FastAPI 完成 RAG 问答", "有 500 用户访问记录"],
                "source_experience_id": "EXP-001",
            },
            {
                "name": "课程后台管理系统",
                "meta": "项目经历",
                "time": "[待填写]",
                "intro": "Vue 后台项目",
                "role": "负责 Vue 页面",
                "details": ["使用 Vue 完成页面", "接入 RAG 和 Embedding 检索链路"],
                "source_experience_id": "EXP-002",
            },
        ]
    )

    guarded = guard_experience_boundaries(payload, RAW_INPUT, write_log=False)
    second_text = " ".join(guarded.resume_sections.projects[1]["details"])

    assert "Vue" in second_text
    assert "RAG" not in second_text
    assert "Embedding" not in second_text


def test_source_id_cleans_metric_contamination():
    payload = payload_with_projects(
        [
            {
                "name": "AI RAG 智能助手",
                "meta": "项目经历",
                "time": "[待填写]",
                "intro": "RAG 项目",
                "role": "负责 RAG",
                "details": ["有 500 用户访问记录"],
                "source_experience_id": "EXP-001",
            },
            {
                "name": "课程后台管理系统",
                "meta": "项目经历",
                "time": "[待填写]",
                "intro": "Vue 后台项目",
                "role": "负责 Vue 页面",
                "details": ["支持 500 用户访问", "使用 Vue 完成页面"],
                "source_experience_id": "EXP-002",
            },
        ]
    )

    guarded = guard_experience_boundaries(payload, RAW_INPUT, write_log=False)
    second_text = " ".join(guarded.resume_sections.projects[1]["details"])

    assert "500" not in second_text
    assert "Vue" in second_text


def test_missing_source_id_can_be_back_matched():
    payload = payload_with_projects(
        [
            {"name": "AI RAG 智能助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "负责 RAG", "details": ["使用 RAG 完成问答"]},
            {"name": "课程后台管理系统", "meta": "项目经历", "time": "[待填写]", "intro": "Vue 后台项目", "role": "负责 Vue 页面", "details": ["使用 Vue 完成页面"]},
        ]
    )

    guarded = guard_experience_boundaries(payload, RAW_INPUT, write_log=False)

    assert guarded.resume_sections.projects[0]["source_experience_id"] == "EXP-001"
    assert guarded.resume_sections.projects[1]["source_experience_id"] == "EXP-002"


def test_fallback_generates_projects_by_experience_id():
    payload = schemas.GenerationPayload(
        completeness_score=70,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[]),
    )

    filled = fill_resume_sections(payload, raw_input=RAW_INPUT, write_log=False)

    assert len(filled.resume_sections.projects) >= 2
    assert filled.resume_sections.projects[0]["source_experience_id"] == "EXP-001"
    assert filled.resume_sections.projects[1]["source_experience_id"] == "EXP-002"


def test_fallback_replaces_single_comprehensive_project_when_multiple_experiences_exist():
    payload = payload_with_projects(
        [
            {
                "name": "综合经历项目",
                "meta": "综合经历",
                "time": "[待填写]",
                "intro": "笼统整理用户经历",
                "role": "整理相关内容",
                "details": ["混合描述"],
            }
        ]
    )

    filled = fill_resume_sections(payload, raw_input=RAW_INPUT, write_log=False)

    assert len(filled.resume_sections.projects) >= 2
    assert all("综合经历" not in project["name"] for project in filled.resume_sections.projects)
    assert {project["source_experience_id"] for project in filled.resume_sections.projects} >= {"EXP-001", "EXP-002"}


def test_unmatched_project_is_not_forced_to_first_experience():
    payload = payload_with_projects(
        [
            {
                "name": "无法确认来源的经历",
                "meta": "其他经历",
                "time": "[待填写]",
                "intro": "缺少可匹配信息",
                "role": "[待确认]",
                "details": ["需要继续追问"],
            }
        ]
    )

    guarded = guard_experience_boundaries(payload, RAW_INPUT, write_log=False)

    assert "source_experience_id" not in guarded.resume_sections.projects[0]


def test_stable_fallback_uses_experience_ids():
    payload = build_stable_generation_fallback(request(), analyze_long_input(RAW_INPUT))

    assert payload.resume_sections.projects[0]["source_experience_id"] == "EXP-001"
    assert payload.resume_sections.projects[1]["source_experience_id"] == "EXP-002"


def test_docx_does_not_show_source_experience_id():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    experience = models.ExperienceInput(
        id=1,
        anonymous_user_id=1,
        session_id="s-test",
        target_role="AI / 大模型 / Agent",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="综合经历",
        raw_input=RAW_INPUT,
    )
    payload = payload_with_projects(
        [
            {
                "name": "AI RAG 智能助手",
                "meta": "项目经历",
                "time": "[待填写]",
                "intro": "RAG 项目",
                "role": "独立开发",
                "details": ["使用 React、FastAPI 和 RAG 完成问答"],
                "source_experience_id": "EXP-001",
            }
        ]
    )
    row = models.GenerationResult(id=401, experience_input_id=1, completeness_score=80, result_json=payload.model_dump_json())
    db.add(experience)
    db.add(row)
    db.commit()

    original_output_dir = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(
                db,
                schemas.DocxCreate(anonymous_user_id="u-test", session_id="s-test", generation_result_id=401),
            )
            assert response is not None
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert "AI RAG 智能助手" in text
            assert "source_experience_id" not in text
            assert "EXP-001" not in text
        finally:
            docx_service.OUTPUT_DIR = original_output_dir
    db.close()


if __name__ == "__main__":
    test_two_experiences_get_distinct_experience_ids()
    test_source_id_cleans_tech_contamination()
    test_source_id_cleans_metric_contamination()
    test_missing_source_id_can_be_back_matched()
    test_fallback_generates_projects_by_experience_id()
    test_fallback_replaces_single_comprehensive_project_when_multiple_experiences_exist()
    test_unmatched_project_is_not_forced_to_first_experience()
    test_stable_fallback_uses_experience_ids()
    test_docx_does_not_show_source_experience_id()
    print("experience identity boundary tests passed")
