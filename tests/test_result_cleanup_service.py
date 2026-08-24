from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.result_cleanup_service import cleanup_generation_payload  # noqa: E402


def build_dirty_payload():
    claims = [
        {
            "claim": "",
            "risk_level": "blue",
            "evidence": "details: 有日志",
            "risk_reason": "",
            "interview_questions": "question: 怎么证明？",
            "knowledge_to_prepare": "RAG",
            "downgrade_wording": "",
        }
    ]
    claims.extend(
        {
            "claim": f"claim: 表达 {index}",
            "risk_level": "yellow",
            "evidence": "evidence",
            "risk_reason": "reason",
            "interview_questions": [],
            "knowledge_to_prepare": [],
            "downgrade_wording": "downgrade",
        }
        for index in range(20)
    )

    projects = []
    for index in range(5):
        projects.append(
            {
                "name": f"name: 项目 {index}",
                "meta": "meta: 个人项目",
                "time": "time: 2026",
                "intro": "intro: 项目简介",
                "role": "role: 独立开发",
                "details": [f"details: 技术细节 {item}" for item in range(10)],
            }
        )

    return {
        "completeness_score": 80,
        "confirmed_facts": [f"fact {index}" for index in range(10)],
        "missing_questions": [f"question: 问题 {index}" for index in range(10)],
        "normal_version": "summary: 内容 skills: React projects: 项目",
        "bold_version": '"project": AI 复习系统，my_role = 独立开发，tech_details: React + FastAPI + RAG',
        "boundary_version": "- project: 项目经历 summary：过度表达 skills = LangGraph",
        "recommended_version": "details: 技术细节 intro: 项目简介 project_name: AI 复习辅助系统",
        "claims": claims,
        "interview_plan": [f"question: 面试 {index} answer_points: 要点" for index in range(12)],
        "knowledge_checklist": [f"skills: 技术 {index}" for index in range(14)],
        "resume_sections": {
            "personal_info": {"name": ""},
            "summary": ["summary: 优势"],
            "skills": ["skills: React"],
            "projects": projects,
            "education": {"degree": "本科", "school": "[待填写]", "major": "[待填写]"},
            "interview_preparation": ["question: 准备"],
        },
    }


def test_cleanup_replaces_internal_field_names():
    cleaned = cleanup_generation_payload(build_dirty_payload(), source="test")

    assert "summary:" not in cleaned.normal_version
    assert "skills:" not in cleaned.normal_version
    assert "projects:" not in cleaned.normal_version
    assert "project" not in cleaned.bold_version.lower()
    assert "my_role" not in cleaned.bold_version
    assert "tech_details" not in cleaned.bold_version
    assert "answer_points:" not in cleaned.bold_version
    assert "summary" not in cleaned.boundary_version.lower()
    assert "skills" not in cleaned.boundary_version.lower()
    assert "project_name" not in cleaned.recommended_version
    assert "details:" not in cleaned.recommended_version
    assert "intro:" not in cleaned.recommended_version
    assert "role:" not in cleaned.boundary_version
    assert "question:" not in cleaned.interview_plan[0]
    assert "回答要点：" in cleaned.interview_plan[0]
    assert "我的职责" in cleaned.bold_version
    assert "项目经历" in cleaned.bold_version
    assert "项目名称" in cleaned.recommended_version


def test_cleanup_fallback_and_risk_level():
    cleaned = cleanup_generation_payload(build_dirty_payload(), source="test")
    first_claim = cleaned.claims[0]

    assert first_claim.risk_level == "yellow"
    assert first_claim.claim == "待确认表达"
    assert first_claim.risk_reason == "该表达需要结合事实证据和面试准备判断使用强度。"
    assert first_claim.downgrade_wording == "准备不足时建议降低职责强度，改为参与或协助相关工作。"
    assert first_claim.interview_questions == []
    assert first_claim.knowledge_to_prepare == []
    assert first_claim.risk_level == "yellow"


def test_cleanup_keeps_empty_arrays_and_limits_counts():
    cleaned = cleanup_generation_payload(build_dirty_payload(), source="test")

    assert len(cleaned.confirmed_facts) == 8
    assert len(cleaned.missing_questions) == 8
    assert len(cleaned.claims) == 16
    assert len(cleaned.interview_plan) == 12
    assert len(cleaned.knowledge_checklist) == 14
    assert len(cleaned.resume_sections.projects) == 5
    assert len(cleaned.resume_sections.projects[0]["details"]) == 8


def test_cleanup_localizes_education_keys():
    cleaned = cleanup_generation_payload(build_dirty_payload(), source="test")

    assert "学历" in cleaned.resume_sections.education
    assert "学校" in cleaned.resume_sections.education
    assert "专业" in cleaned.resume_sections.education


def test_cleanup_keeps_technical_terms():
    cleaned = cleanup_generation_payload(build_dirty_payload(), source="test")

    assert "RAG" in cleaned.bold_version
    assert "React" in cleaned.bold_version
    assert "FastAPI" in cleaned.bold_version
    assert "LangGraph" in cleaned.boundary_version


if __name__ == "__main__":
    test_cleanup_replaces_internal_field_names()
    test_cleanup_fallback_and_risk_level()
    test_cleanup_keeps_empty_arrays_and_limits_counts()
    test_cleanup_localizes_education_keys()
    test_cleanup_keeps_technical_terms()
    print("result cleanup tests passed")
