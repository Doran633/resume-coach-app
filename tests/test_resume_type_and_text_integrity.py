from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.experience_identity_service import build_experience_identity_context  # noqa: E402
from app.services.resume_project_reconciliation_service import reconcile_resume_projects  # noqa: E402
from app.services.resume_text_integrity_service import ensure_resume_text_integrity  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW_INPUT = """从零设计并持续迭代一套可公网使用的 AI RAG 助手，使用 React + TypeScript、FastAPI、SQLite 完成前后端与数据持久化，实现文件上传解析、文本切块、BAAI/bge-m3 Embedding、向量检索、RAG 问答、Citation、连续对话与会话恢复。围绕 chunk、Top-K、阈值及检索排序进行了多轮量化优化。

独立设计并开发 AI 简历定位与包装网站，核心目标是将用户真实经历转化为表达更强但面试可承接的简历内容。设计经历输入、完整度分析、岗位定位、Claim 检查、面试准备、简历生成和 DOCX 导出工作流；发现 LLM 虽满足 JSON Schema 但正式简历字段可能为空后，引入 Resume Section Fallback。

在自行者科技有限公司 AI Agent 开发岗位实习，参与企业级 Agent 助手开发，建立测试集并优化 RAG 模块，使相关度从 0.4315 提升到 0.7243，平均 token 消耗从 1400 降低到 600。"""


def _payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="",
        bold_version="", boundary_version="", recommended_version="", claims=[],
        interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=["具备 AI 应用开发与工程落地能力"],
            skills=["React、TypeScript、FastAPI、RAG"],
            projects=[
                {"name": "AI RAG 助手", "meta": "个人项目", "time": "[待填写]",
                 "intro": "设计并开发可公网使用的 AI RAG 助手", "role": "独立开发",
                 "details": ["完成前后端开发与 RAG 检索链路优化"], "source_experience_id": "EXP-001"},
                {"name": "AI 简历定位与包装网站", "meta": "实习经历", "time": "[待填写]",
                 "intro": "独立设计并开发 AI 简历定位与包装网站", "role": "独立设计、开发与迭代",
                 "details": ["发现 LLM 虽满足 JSON Schema 但正式简...（原文截断，需补充）"],
                 "source_experience_id": "EXP-002"},
                {"name": "Agent 助手 RAG 模块优化", "meta": "实习经历", "time": "[待填写]",
                 "intro": "在自行者科技有限公司参与 Agent 助手开发", "role": "AI Agent 开发实习生",
                 "details": ["将相关度从 0.4315 提升到 0.7243"], "source_experience_id": "EXP-003"},
            ],
            interview_preparation=["准备 RAG 优化过程和指标口径"],
        ),
    )


def _processed_payload() -> schemas.GenerationPayload:
    value = reconcile_resume_projects(_payload(), RAW_INPUT, write_log=False)
    return ensure_resume_text_integrity(value, RAW_INPUT, write_log=False)


def test_source_id_corrects_project_type_and_keeps_real_internship():
    result = _processed_payload()
    assert result.resume_sections.projects[1]["meta"] == "项目经历"
    assert result.resume_sections.projects[2]["meta"] == "实习经历"


def test_truncated_detail_is_recovered_without_internal_marker():
    detail = " ".join(_processed_payload().resume_sections.projects[1]["details"])
    assert "Resume Section Fallback" in detail
    assert "原文截断" not in detail and "需补充" not in detail and "..." not in detail


def test_internal_context_does_not_describe_source_as_missing():
    context = build_experience_identity_context(RAW_INPUT)
    assert "长度裁剪不代表用户原文缺失" in context
    assert "..." not in context


def test_docx_orders_internship_before_projects_and_hides_source_id():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s-test",
        target_role="AI / 大模型 / Agent", mode="full_resume", packaging_level="大胆",
        experience_type="综合经历", raw_input=RAW_INPUT))
    db.add(models.GenerationResult(id=601, experience_input_id=1, completeness_score=90,
        result_json=_payload().model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u-test", session_id="s-test", generation_result_id=601))
            text = "\n".join(p.text for p in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert text.index("技能与能力") < text.index("实习经历") < text.index("项目经历")
            assert "AI 简历定位与包装网站 | 项目经历" in text
            assert "source_experience_id" not in text and "原文截断" not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


if __name__ == "__main__":
    test_source_id_corrects_project_type_and_keeps_real_internship()
    test_truncated_detail_is_recovered_without_internal_marker()
    test_internal_context_does_not_describe_source_as_missing()
    test_docx_orders_internship_before_projects_and_hides_source_id()
    print("resume type and text integrity tests passed")
