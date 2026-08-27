from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_template_language_guard_service import guard_template_language  # noqa: E402


def payload(details):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n",
        bold_version="b", boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{
            "name": "项目", "meta": "个人项目", "time": "2026", "intro": "围绕项目目标，解决复习效率问题。",
            "role": "负责核心功能开发。", "details": details,
        }]),
    )


def test_colloquial_and_internal_prefixes_are_cleaned_without_new_facts():
    result = guard_template_language(payload([
        "我做过一个 RAG 助手。", "技术动作：建立固定测试集。", "然后优化 Top-K 参数。",
    ])).resume_sections.projects[0]
    assert result["details"] == ["设计并完成 RAG 助手。", "建立固定测试集。", "优化 Top-K 参数。"]
    assert result["intro"] == "解决复习效率问题。"


def test_technical_terms_are_preserved():
    result = guard_template_language(payload(["我做了 BAAI/bge-m3 Embedding 与 FastAPI 接入。"]))
    text = result.resume_sections.projects[0]["details"][0]
    assert "BAAI/bge-m3" in text and "FastAPI" in text

