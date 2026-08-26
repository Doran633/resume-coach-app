from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.docx_delivery_readiness_service import prepare_docx_delivery  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = "独立开发 RAG 知识助手，使用 React 和 FastAPI，实现文档检索与问答。"


def payload():
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[RAW],
        missing_questions=["项目如何评估检索效果？"],
        normal_version="正式项目表达",
        bold_version="正式项目表达",
        boundary_version="边界参考",
        recommended_version="正式项目表达",
        claims=[schemas.ClaimResult(
            claim="负责 RAG 检索链路",
            risk_level="yellow",
            evidence="准备项目仓库与测试记录",
            risk_reason="需要说明检索评估方法",
            interview_questions=["Top-K 如何选择？"],
            knowledge_to_prepare=["Chunk、Embedding 和 Top-K"],
            downgrade_wording="参与 RAG 检索功能实现",
        )],
        interview_plan=["如果被问到，请说明检索链路"],
        knowledge_checklist=["需要学习 RAG 评估方法"],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]", "手机号": "[待填写]", "邮箱": "[待填写]"},
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            summary=["具备独立项目开发与交付能力。", "如果被问到项目细节，建议补充证据。"],
            skills=["React、FastAPI、RAG"],
            projects=[{
                "name": "RAG 知识助手", "meta": "个人项目", "time": "[待填写]",
                "intro": "面向文档问答场景构建 RAG 知识助手。",
                "role": "负责前后端功能开发。",
                "details": ["实现文档检索与问答链路。"],
            }],
            interview_preparation=["面试准备清单：解释 Chunk 和 Top-K"],
        ),
    )


def test_delivery_readiness_filters_coaching_from_formal_sections_only():
    result = prepare_docx_delivery(payload(), generation_result_id=901)
    assert result.resume_sections.summary == ["具备独立项目开发与交付能力。"]
    assert result.interview_plan and result.knowledge_checklist
    assert result.resume_sections.interview_preparation


def test_historical_docx_excludes_all_interview_delivery_content():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="AI / 大模型 / Agent",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW))
    db.add(models.GenerationResult(id=901, experience_input_id=1, completeness_score=80, result_json=payload().model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=901))
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            for forbidden in ["面试准备清单", "Top-K 如何选择", "需要学习 RAG", "参与 RAG 检索功能实现"]:
                assert forbidden not in text
            assert "个人优势" in text and "技能与能力" in text and "RAG 知识助手" in text
            assert "[待填写]" in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


if __name__ == "__main__":
    test_delivery_readiness_filters_coaching_from_formal_sections_only()
    test_historical_docx_excludes_all_interview_delivery_content()
    print("docx delivery readiness tests passed")
