from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.paired_symbol_integrity_service import (  # noqa: E402
    ensure_paired_symbol_integrity, has_unbalanced_symbols,
)


def payload(detail):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{"name": "Resume Coach", "meta": "个人项目",
            "time": "2026", "intro": "项目简介", "role": "独立开发", "details": [detail]}]),
    )


def test_known_broken_quote_regression_is_rewritten():
    broken = "如何在“ ” “ 表达更强 和 面试能够真实承接”之间找到边界"
    result = ensure_paired_symbol_integrity(payload(broken), write_log=False)
    text = result.resume_sections.projects[0]["details"][0]
    assert text == "围绕“表达强度”与“面试可承接性”设计经历定位和风险判断机制"
    assert not has_unbalanced_symbols(text)


def test_empty_and_unmatched_quotes_are_removed_safely():
    result = ensure_paired_symbol_integrity(payload("建立“ ”规则并处理“异常文本"), write_log=False)
    text = result.resume_sections.projects[0]["details"][0]
    assert "“ ”" not in text
    assert not has_unbalanced_symbols(text)


def test_placeholder_and_valid_backticks_survive():
    result = ensure_paired_symbol_integrity(payload("时间为[待填写]，校验`resume_sections`结构"), write_log=False)
    text = result.resume_sections.projects[0]["details"][0]
    assert "[待填写]" in text and "`resume_sections`" in text


def test_mismatched_parenthesis_is_removed():
    result = ensure_paired_symbol_integrity(payload("完成业务校验（避免空白导出"), write_log=False)
    assert "（" not in result.resume_sections.projects[0]["details"][0]
