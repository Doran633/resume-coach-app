from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.recruiter_language_service import ensure_recruiter_language  # noqa: E402


def payload(details):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{"name": "Resume Coach", "meta": "个人项目",
            "time": "2026", "intro": "简历定位平台", "role": "独立开发", "details": details}]),
    )


def test_internal_field_enumeration_becomes_recruiter_language():
    source = "将用户输入拆分为 EXP-001、EXP-002、EXP-003，并提取 raw_text、experience_type、explicit_tech_terms、explicit_metrics、evidence_terms、risk_terms 和 supported_inference_terms。"
    result = ensure_recruiter_language(payload([source]), write_log=False)
    text = result.resume_sections.projects[0]["details"][0]
    assert "技术、指标、证据和风险事实" in text
    assert "建立经历级事实边界" in text
    assert "raw_text" not in text and "explicit_metrics" not in text


def test_claim_flow_is_converted_without_losing_risk_value():
    source = "缺乏事实依据的内容进入 missing_questions、claims 或 interview_preparation。"
    result = ensure_recruiter_language(payload([source]), write_log=False)
    text = result.resume_sections.projects[0]["details"][0]
    assert "风险分级" in text and "补充证据" in text
    assert "missing_questions" not in text


def test_schema_and_pydantic_are_preserved():
    source = "LLM 输出满足 JSON Schema 和 Pydantic 校验，但 resume_sections 核心字段可能为空。"
    result = ensure_recruiter_language(payload([source]), write_log=False)
    text = result.resume_sections.projects[0]["details"][0]
    assert "JSON Schema" in text and "Pydantic" in text
    assert "业务完整性" in text
