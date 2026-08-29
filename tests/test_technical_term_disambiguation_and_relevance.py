from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services import resume_output_relevance_service as relevance_service  # noqa: E402
from app.services import technical_term_disambiguation_service as disambiguation_service  # noqa: E402
from app.services.resume_output_relevance_service import guard_resume_output_relevance  # noqa: E402
from app.services.resume_skill_evidence_guard_service import guard_resume_skill_evidence  # noqa: E402
from app.services.resume_skill_taxonomy_service import calibrate_resume_skill_taxonomy  # noqa: E402
from app.services.technical_term_disambiguation_service import (  # noqa: E402
    best_resolution,
    resolve_technical_terms,
    write_disambiguation_log,
)
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def _payload(skills: list[str], details: list[str] | None = None) -> schemas.GenerationPayload:
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
            summary=["具备 AI 应用优化实践能力。"],
            skills=skills,
            projects=[{
                "name": "Agent 优化实践",
                "meta": "项目经历",
                "time": "[待填写]",
                "intro": "围绕模型应用质量与成本开展优化。",
                "role": "负责测试集建设与调用成本优化。",
                "details": details or [],
                "source_experience_id": "EXP-001",
            }],
        ),
    )


def _skill_pipeline(payload: schemas.GenerationPayload, raw: str) -> schemas.GenerationPayload:
    payload = guard_resume_skill_evidence(payload, raw, write_log=False)
    payload = calibrate_resume_skill_taxonomy(payload, raw_input=raw, write_log=False)
    return guard_resume_output_relevance(payload, raw, write_log=False)


def test_token_cost_is_not_classified_as_security_and_metric_is_preserved():
    raw = "建立 RAG 测试集并优化调用成本，将平均 Token 消耗从 1400 降低到 600 Token/次。"
    metric = "将平均 Token 消耗从 1400 降低到 600 Token/次"
    result = _skill_pipeline(_payload(["安全机制：Token"], [metric]), raw)
    skills = "\n".join(result.resume_sections.skills)

    assert "安全机制：Token" not in skills
    assert "大模型工程与成本优化：Token 成本控制" in skills
    assert metric in result.resume_sections.projects[0]["details"]


def test_prompt_token_is_context_management_not_security():
    raw = "压缩 Prompt 上下文并控制输入 Token 用量，减少模型调用成本。"
    resolution = best_resolution(resolve_technical_terms(raw), "Token")

    assert resolution is not None
    assert resolution.meaning == "prompt_token_cost"
    assert resolution.category == "Prompt 工程与上下文管理"


def test_authentication_token_remains_security_mechanism():
    raw = "使用 JWT Token 完成接口鉴权，并通过 Bearer 传递登录态。"
    result = _skill_pipeline(_payload(["Token"]), raw)

    assert "安全机制：Token 鉴权" in result.resume_sections.skills


def test_isolated_token_is_removed_and_turned_into_clarification_question():
    raw = "项目中使用了 Token。"
    result = _skill_pipeline(_payload(["安全机制：Token"]), raw)

    assert all("Token" not in line for line in result.resume_sections.skills)
    assert any("模型调用消耗" in question and "接口鉴权令牌" in question for question in result.missing_questions)


def test_model_training_deployment_user_and_test_are_disambiguated_by_context():
    raw = (
        "使用线性回归模型比较拟合效果。\n"
        "使用 SFT 微调模型。\n"
        "通过 Nginx 和 systemd 完成公网部署。\n"
        "积累 500 名真实用户访问记录。\n"
        "建立 RAG 测试集并使用 Groundedness 评测回答质量。"
    )
    resolutions = resolve_technical_terms(raw)
    meanings = {item.meaning for item in resolutions}

    assert "statistical_model" in meanings
    assert "model_training" in meanings
    assert "service_deployment" in meanings
    assert "user_evidence" in meanings
    assert "ai_evaluation" in meanings


def test_docx_export_cleans_historical_security_token_misclassification():
    raw = "负责 Agent 成本优化，将平均 Token 消耗从 1400 降低到 600 Token/次。"
    payload = _payload(
        ["安全机制：Token"],
        ["将平均 Token 消耗从 1400 降低到 600 Token/次"],
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=671,
        anonymous_user_id=1,
        session_id="s",
        target_role="AI / 大模型 / Agent",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="项目经历",
        raw_input=raw,
    ))
    db.add(models.GenerationResult(
        id=671,
        experience_input_id=671,
        completeness_score=80,
        result_json=payload.model_dump_json(),
    ))
    db.commit()
    previous_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=671,
            ))
            text = "\n".join(
                paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs
            )
            assert "安全机制：Token" not in text
            assert "大模型工程与成本优化：Token 成本控制" in text
            assert "1400" in text and "600" in text
        finally:
            docx_service.OUTPUT_DIR = previous_output
            db.close()


def test_structured_logs_contain_bindings_but_not_source_text(tmp_path, monkeypatch):
    raw = "敏感项目原文：将平均 Token 消耗从 1400 降低到 600 Token/次。"
    term_log = tmp_path / "terms.jsonl"
    relevance_log = tmp_path / "relevance.jsonl"
    monkeypatch.setattr(disambiguation_service, "LOG_PATH", term_log)
    monkeypatch.setattr(relevance_service, "LOG_PATH", relevance_log)

    resolutions = resolve_technical_terms(raw)
    write_disambiguation_log(resolutions, stage="test", generation_result_id=67)
    guard_resume_output_relevance(
        _payload(["安全机制：Token"]), raw,
        stage="test", generation_result_id=67, write_log=True,
    )

    combined = term_log.read_text(encoding="utf-8") + relevance_log.read_text(encoding="utf-8")
    assert "敏感项目原文" not in combined
    assert "1400" not in combined and "600" not in combined
    assert "EXP-001" in combined and "fact_id" in combined
    assert "llm_token_cost" in combined
