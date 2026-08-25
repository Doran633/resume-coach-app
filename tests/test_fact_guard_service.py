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


RAW_WITHOUT_MAJOR = "我做了一个 AI RAG 智能助手，使用 React、TypeScript、FastAPI、SQLite 和 RAG，实现文件上传、向量检索和问答。项目通过 VPS + Nginx + systemd 部署到独立域名。"


def build_hallucinated_payload():
    return {
        "completeness_score": 80,
        "confirmed_facts": ["计算机相关专业，具备科班背景", "已完成企业级生产系统"],
        "missing_questions": [],
        "normal_version": "计算机相关专业学生，具备科班背景和企业级实战经验。",
        "bold_version": "具备模型训练经验，掌握 SFT、RLHF、LoRA，并负责企业级生产系统。",
        "boundary_version": "不要写高并发和企业级生产系统。",
        "recommended_version": "计算机相关专业背景，独立完成 RAG 项目并上线运行，但不要写高并发。",
        "claims": [
            {
                "claim": "企业级生产系统与高并发",
                "risk_level": "yellow",
                "evidence": "已部署上线",
                "risk_reason": "公司级项目和高并发缺少证据",
                "interview_questions": ["你如何证明高并发？"],
                "knowledge_to_prepare": ["SFT", "RLHF", "RAG"],
                "downgrade_wording": "可公网访问的个人项目",
            }
        ],
        "interview_plan": ["准备解释模型训练经验和 SFT。"],
        "knowledge_checklist": ["RAG", "React", "FastAPI", "SFT", "LoRA"],
        "resume_sections": {
            "personal_info": {"姓名": "[待填写]", "求职意向": "AI / 大模型 / Agent"},
            "summary": ["计算机相关专业，科班背景扎实，具备企业级实战经验。"],
            "skills": ["React", "FastAPI", "RAG", "SFT"],
            "projects": [
                {
                    "name": "AI RAG 智能助手",
                    "meta": "企业级生产系统",
                    "time": "[待填写]",
                    "intro": "生产级业务系统，支持高并发访问。",
                    "role": "负责模型训练和微调模型。",
                    "details": ["使用 RAG、React、FastAPI。", "完成 SFT 和 LoRA。"],
                }
            ],
            "education": {"学校": "某大学", "专业": "计算机相关专业", "学历": "本科", "时间": "2024-2028"},
            "interview_preparation": ["准备 SFT、RLHF、LoRA 训练细节。"],
        },
    }


def all_text(payload: schemas.GenerationPayload) -> str:
    return payload.model_dump_json()


def test_fact_guard_removes_missing_major_and_implicit_school_facts():
    guarded = guard_hard_facts(build_hallucinated_payload(), RAW_WITHOUT_MAJOR)
    text = all_text(guarded)

    assert "计算机相关专业" not in text
    assert "科班背景" not in text
    assert guarded.resume_sections.education["学校"] == "[待填写]"
    assert guarded.resume_sections.education["专业"] == "[待填写]"
    assert guarded.resume_sections.education["学历"] == "[待填写]"


def test_fact_guard_removes_training_and_concurrency_hallucination_but_keeps_rag():
    guarded = guard_hard_facts(build_hallucinated_payload(), RAW_WITHOUT_MAJOR)
    text = all_text(guarded)

    assert "模型训练经验" not in text
    assert "微调模型" not in text
    assert "高并发" not in text
    assert "企业级生产系统" not in text
    assert "RAG" in text
    assert "React" in text
    assert "FastAPI" in text


def test_fact_guard_keeps_online_when_user_provides_deployment_evidence():
    guarded = guard_hard_facts(build_hallucinated_payload(), RAW_WITHOUT_MAJOR)

    assert "上线运行" in guarded.recommended_version or "已部署上线" in guarded.recommended_version
    assert "企业级生产系统" not in all_text(guarded)


def test_docx_export_runs_fact_guard_for_historical_hallucinated_result():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    input_row = models.ExperienceInput(
        id=1,
        anonymous_user_id=None,
        session_id="s-test",
        target_role="AI / 大模型 / Agent",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="项目经历",
        raw_input=RAW_WITHOUT_MAJOR,
    )
    payload = schemas.GenerationPayload.model_validate(build_hallucinated_payload())
    result_row = models.GenerationResult(
        id=41,
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
                schemas.DocxCreate(anonymous_user_id="u-test", session_id="s-test", generation_result_id=41),
            )
            assert response is not None
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert "计算机相关专业" not in text
            assert "科班背景" not in text
            assert "学校：[待填写]" in text
            assert "专业：[待填写]" in text
        finally:
            docx_service.OUTPUT_DIR = original_output_dir
            resume_section_fallback_service.LOG_PATH = original_log_path
            resume_section_fallback_service.LOG_DIR = original_log_dir
    db.close()


if __name__ == "__main__":
    test_fact_guard_removes_missing_major_and_implicit_school_facts()
    test_fact_guard_removes_training_and_concurrency_hallucination_but_keeps_rag()
    test_fact_guard_keeps_online_when_user_provides_deployment_evidence()
    test_docx_export_runs_fact_guard_for_historical_hallucinated_result()
    print("fact guard tests passed")
