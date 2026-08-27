from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.recruiter_facing_technical_language_service import (  # noqa: E402
    ensure_recruiter_facing_technical_language,
)


def payload(details: list[str]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80, confirmed_facts=[], missing_questions=[], normal_version="",
        bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[], resume_sections=schemas.ResumeSections(projects=[{
            "name": "Resume Coach", "meta": "个人项目", "time": "2026", "intro": "AI 简历工具",
            "role": "独立开发", "details": details, "source_experience_id": "EXP-001",
        }]))


def test_internal_observability_fields_become_engineering_language():
    result = ensure_recruiter_facing_technical_language(payload([
        "记录 retrieved_count、retrieval_score、confidence、no_answer、token_usage 和 answer_policy。",
    ]), write_log=False)
    text = result.resume_sections.projects[0]["details"][0]
    assert "检索召回" in text and "回答置信度" in text and "Token 消耗" in text
    assert "retrieved_count" not in text and "answer_policy" not in text


def test_fact_fields_are_summarized_without_losing_experience_boundary_meaning():
    result = ensure_recruiter_facing_technical_language(payload([
        "将长输入拆分为 EXP-001、EXP-002，提取 raw_text、experience_type、explicit_tech_terms、explicit_metrics。",
        "使用 RAG 和 Agent 构建应用。",
    ]), write_log=False)
    text = " ".join(result.resume_sections.projects[0]["details"])
    assert "技术、指标、证据和风险事实" in text
    assert "经历级事实边界" in text
    assert "RAG" in text and "Agent" in text
    assert "raw_text" not in text and "explicit_metrics" not in text


def test_pipeline_names_are_productized_and_debug_markers_removed():
    result = ensure_recruiter_facing_technical_language(payload([
        "执行 result_cleanup、fact_guard 和 resume_section_fallback。",
        "section summary chunk",
    ]), write_log=False)
    text = " ".join(result.resume_sections.projects[0]["details"])
    assert "生成结果清洗" in text and "事实校验" in text and "完整性兜底" in text
    assert "section summary chunk" not in text

