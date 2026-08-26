from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.experience_type_resolution_service import build_type_resolutions, resolve_project_types  # noqa: E402
from app.services.resume_section_routing_service import route_resume_projects  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """项目一｜AI RAG 助手
独立开发 AI RAG 助手，使用 React、FastAPI 完成文档检索与问答。

项目二｜Resume Coach
独立开发 AI 简历网站，实现经历分析、风险检查和 DOCX 导出。

实习经历｜自行者科技有限公司
担任 AI Agent 开发实习生，负责 RAG 测试集建设与检索参数优化。"""


def payload() -> schemas.GenerationPayload:
    projects = [
        {"name": "AI RAG 助手", "meta": "实习经历", "time": "[待填写]", "intro": "文档检索问答", "role": "独立开发", "details": ["完成 RAG 链路"], "source_experience_id": "EXP-001"},
        {"name": "Resume Coach", "meta": "实习经历", "time": "[待填写]", "intro": "AI 简历网站", "role": "独立开发", "details": ["实现 DOCX 导出"], "source_experience_id": "EXP-002"},
        {"name": "自行者科技", "meta": "项目经历", "time": "[待填写]", "intro": "AI Agent 实习", "role": "实习生", "details": ["建设测试集"], "source_experience_id": "EXP-003"},
    ]
    return schemas.GenerationPayload(completeness_score=80, confirmed_facts=[], missing_questions=[], normal_version="", bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[], resume_sections=schemas.ResumeSections(projects=projects))


def test_local_type_signals_override_globally_polluted_meta():
    result = resolve_project_types(payload(), RAW, write_log=False)
    assert [item["meta"] for item in result.resume_sections.projects] == ["项目经历", "项目经历", "实习经历"]


def test_type_resolution_is_local_and_routing_is_lossless():
    resolutions = build_type_resolutions(RAW)
    assert resolutions["EXP-001"].resolved_type == "项目经历"
    assert resolutions["EXP-002"].resolved_type == "项目经历"
    assert resolutions["EXP-003"].resolved_type == "实习经历"
    result = resolve_project_types(payload(), RAW, write_log=False)
    groups = route_resume_projects(result.resume_sections.projects)
    assert sum(len(items) for _, items in groups) == 3
    assert groups[0][0] == "实习经历"
    assert len(dict((item["source_experience_id"], heading) for heading, items in groups for item in items)) == 3


def test_no_internship_input_creates_no_internship_section():
    short_raw = RAW.split("实习经历｜")[0]
    short_payload = payload().model_copy(deep=True)
    short_payload.resume_sections.projects = short_payload.resume_sections.projects[:2]
    result = resolve_project_types(short_payload, short_raw, write_log=False)
    assert all(heading != "实习经历" for heading, _ in route_resume_projects(result.resume_sections.projects))


def test_long_input_docx_routes_real_internship_before_projects():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="AI / 大模型 / Agent",
        mode="full_resume", packaging_level="大胆", experience_type="综合经历", raw_input=RAW))
    db.add(models.GenerationResult(id=807, experience_input_id=1, completeness_score=80, result_json=payload().model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(anonymous_user_id="u", session_id="s", generation_result_id=807))
            text = "\n".join(p.text for p in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert text.index("实习经历") < text.index("项目经历")
            assert "AI RAG 助手" in text and "Resume Coach" in text and "自行者科技" in text
            assert "source_experience_id" not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


if __name__ == "__main__":
    test_local_type_signals_override_globally_polluted_meta()
    test_type_resolution_is_local_and_routing_is_lossless()
    test_no_internship_input_creates_no_internship_section()
    test_long_input_docx_routes_real_internship_before_projects()
    print("experience type resolution and routing tests passed")
