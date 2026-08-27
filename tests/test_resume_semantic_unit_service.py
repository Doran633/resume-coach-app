from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.experience_fact_ledger_service import build_experience_fact_ledger, split_atomic_facts  # noqa: E402
from app.services.resume_semantic_unit_service import ensure_semantic_units, fragment_reasons  # noqa: E402


def payload(detail, fact_ids=None):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{
            "name": "项目", "meta": "个人项目", "time": "2026", "intro": "项目简介。", "role": "独立开发。",
            "details": [detail], "source_experience_id": "EXP-001", "detail_fact_ids": [fact_ids or []],
        }]),
    )


def test_dependency_fragments_are_detected():
    assert "trailing_dependency" in fragment_reasons("完成检索参数实验，并")
    assert "leading_dependency" in fragment_reasons("针对该问题，引入业务完整性检查。")
    assert "trailing_dependency" in fragment_reasons("主要包括：")


def test_semicolon_keeps_problem_and_solution_in_same_atomic_fact():
    text = "LLM 返回结构合法但核心字段为空；针对该问题引入 Resume Section Fallback。"
    assert split_atomic_facts(text) == [text.rstrip("。")]


def test_metrics_stay_with_optimization_object():
    text = "优化回答相关度，从 0.4315 提升至 0.7243，同时将 Token 从 1400 降至 600。"
    facts = build_experience_fact_ledger(text).facts
    assert len(facts) == 1
    assert "0.4315" in facts[0].fact_text and "600" in facts[0].fact_text


def test_fragment_recovers_from_same_experience_fact():
    raw = "负责检索优化，通过调整 Top-K 与阈值提升检索稳定性。"
    ledger = build_experience_fact_ledger(raw)
    result = ensure_semantic_units(payload("通过", [ledger.facts[0].fact_id]), raw)
    assert result.resume_sections.projects[0]["details"] == [ledger.facts[0].resume_ready_text]


def test_unrecoverable_trailing_fragment_is_removed():
    result = ensure_semantic_units(payload("围绕", []), "这是一个完整项目经历。")
    assert result.resume_sections.projects[0]["details"] == []

