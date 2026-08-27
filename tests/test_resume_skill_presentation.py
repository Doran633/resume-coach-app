from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_skill_evidence_guard_service import guard_resume_skill_evidence  # noqa: E402
from app.services.resume_skill_presentation_service import evaluate_skill_presentation, organize_resume_skills  # noqa: E402


def payload(skills, details=None):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=["学习 Docker"],
        resume_sections=schemas.ResumeSections(
            skills=skills, projects=[{"name": "项目", "meta": "个人项目", "time": "2026",
                "intro": "项目简介", "role": "独立开发", "details": details or [],
                "source_experience_id": "EXP-001"}],
        ),
    )


def test_flat_verified_skills_are_grouped_for_ai_role():
    raw = "使用 React、TypeScript、Python、FastAPI、SQLite、Nginx、systemd、RAG、Agent 和 Embedding 开发并部署应用。"
    guarded = guard_resume_skill_evidence(payload(
        ["React", "TypeScript", "Python", "FastAPI", "SQLite", "Nginx", "systemd", "RAG", "Agent", "Embedding"],
        [raw],
    ), raw, write_log=False)
    result = organize_resume_skills(guarded, "AI / 大模型 / Agent", write_log=False)
    assert result.resume_sections.skills == [
        "编程语言：TypeScript、Python",
        "AI / 大模型应用：RAG、Agent、Embedding",
        "后端技术：FastAPI",
        "数据库与存储：SQLite",
        "前端技术：React",
        "工程化与部署：Nginx、systemd",
    ]


def test_existing_category_is_preserved_and_duplicates_are_removed():
    result = organize_resume_skills(payload([
        "前端技术：React、TypeScript", "编程语言：TypeScript", "后端技术：FastAPI",
    ]), "前端开发", write_log=False)
    text = "\n".join(result.resume_sections.skills)
    assert "前端技术：React、TypeScript" in text
    assert text.count("TypeScript") == 1


def test_presentation_never_adds_unsupported_skills_or_checklist_terms():
    result = organize_resume_skills(payload(["Python", "RAG"]), "AI Agent", write_log=False)
    text = " ".join(result.resume_sections.skills)
    assert "Docker" not in text and "Redis" not in text and "LangGraph" not in text


def test_frontend_role_uses_frontend_first_after_language():
    result = organize_resume_skills(payload(["FastAPI", "React", "Python", "Nginx"]), "前端开发", write_log=False)
    assert result.resume_sections.skills[0].startswith("编程语言：")
    assert result.resume_sections.skills[1].startswith("前端技术：")


def test_flat_list_quality_warning_is_reported():
    score, warnings = evaluate_skill_presentation(payload(["React", "Python", "FastAPI"]))
    assert score < 100
    assert "FLAT_SKILL_LIST" in warnings and "SKILL_CATEGORY_LOSS" in warnings
