from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_language_professionalization_service import (  # noqa: E402
    professionalize_resume_language,
    professionalize_text,
)


def payload(details: list[str]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=70, confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(summary=[], skills=[], projects=[{
            "name": "项目", "meta": "项目经历", "time": "[待填写]", "intro": "我做过一个回归分析计算器",
            "role": "技术动作：我独立完成此项目", "details": details, "source_experience_id": "EXP-001",
        }]))


def test_colloquial_phrases_are_professionalized():
    result = professionalize_resume_language(payload([
        "我写了几个页面", "我调了一些接口", "我修了一些 bug", "我写了文档"
    ]), write_log=False)
    text = "\n".join([result.resume_sections.projects[0]["intro"], result.resume_sections.projects[0]["role"], *result.resume_sections.projects[0]["details"]])
    for phrase in ["我做过", "技术动作", "我写了", "我调了", "我修了"]:
        assert phrase not in text
    assert "页面开发" in text and "接口联调" in text and "定位并修复" in text and "沉淀项目说明" in text
    assert "主导" not in text and "企业级" not in text and "高并发" not in text


def test_direct_professionalization_preserves_explicit_facts():
    text, changed, _ = professionalize_text("技术动作：我独立完成此项目，使用 CodeBuddy 连接虚拟机")
    assert changed
    assert text.startswith("独立完成")
    assert "CodeBuddy" in text and "虚拟机" in text


def test_source_experience_id_is_preserved_internally():
    result = professionalize_resume_language(payload(["我负责数据分析"]), write_log=False)
    assert result.resume_sections.projects[0]["source_experience_id"] == "EXP-001"


if __name__ == "__main__":
    test_colloquial_phrases_are_professionalized()
    test_direct_professionalization_preserves_explicit_facts()
    test_source_experience_id_is_preserved_internally()
    print("resume language professionalization tests passed")
