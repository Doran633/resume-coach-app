from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.enhancement_guard_service import ensure_packaging_gain  # noqa: E402
from app.services.fact_guard_service import guard_hard_facts  # noqa: E402


RAW_INPUT = "我做了一个 Vue 后台管理系统，主要写了几个页面，调了一些接口，修 bug，写文档。项目是课程项目，没有上线。我想投前端开发。"


def build_plain_payload():
    return {
        "completeness_score": 70,
        "confirmed_facts": ["做了 Vue 后台管理系统"],
        "missing_questions": [],
        "normal_version": RAW_INPUT,
        "bold_version": RAW_INPUT,
        "boundary_version": "不要写成企业级生产系统。",
        "recommended_version": RAW_INPUT,
        "claims": [],
        "interview_plan": [],
        "knowledge_checklist": ["Vue"],
        "resume_sections": {
            "personal_info": {"姓名": "[待填写]", "求职意向": "前端开发"},
            "summary": ["做过项目"],
            "skills": ["Vue"],
            "projects": [
                {
                    "name": "Vue 后台管理系统",
                    "meta": "课程项目",
                    "time": "[待填写]",
                    "intro": RAW_INPUT,
                    "role": "",
                    "details": [RAW_INPUT],
                }
            ],
            "education": {"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            "interview_preparation": [],
        },
    }


def test_enhancement_rewrites_recommended_version_when_too_similar():
    enhanced = ensure_packaging_gain(build_plain_payload(), RAW_INPUT, "前端开发")

    assert enhanced.recommended_version != RAW_INPUT
    assert "推荐版本" in enhanced.recommended_version
    assert "项目目标" in enhanced.recommended_version or "项目定位" in enhanced.recommended_version


def test_enhancement_upgrades_soft_facts_without_adding_hard_facts():
    enhanced = ensure_packaging_gain(build_plain_payload(), RAW_INPUT, "前端开发")
    guarded = guard_hard_facts(enhanced, RAW_INPUT)
    text = guarded.model_dump_json()

    assert "负责核心页面开发、交互状态流转与接口联调" in text
    assert "围绕核心接口链路完成联调、异常定位与数据流转校验" in text
    assert "定位并修复关键流程异常，提升功能稳定性" in text
    assert "沉淀项目说明、使用文档和复盘材料，提升项目可维护性" in text
    assert "企业级生产系统" not in text
    assert "高并发" not in text
    assert "计算机相关专业" not in text


def test_project_details_are_not_only_raw_input_copy():
    enhanced = ensure_packaging_gain(build_plain_payload(), RAW_INPUT, "前端开发")
    details = enhanced.resume_sections.projects[0]["details"]

    assert RAW_INPUT not in details
    assert len(details) >= 5
    assert any("技术动作" in item or "负责核心页面" in item for item in details)


if __name__ == "__main__":
    test_enhancement_rewrites_recommended_version_when_too_similar()
    test_enhancement_upgrades_soft_facts_without_adding_hard_facts()
    test_project_details_are_not_only_raw_input_copy()
    print("enhancement guard tests passed")
