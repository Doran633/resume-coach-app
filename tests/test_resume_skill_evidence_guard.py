from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_skill_evidence_guard_service import guard_resume_skill_evidence  # noqa: E402


def payload(skills, knowledge=None, details=None):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[],
        knowledge_checklist=knowledge or [], resume_sections=schemas.ResumeSections(
            skills=skills, projects=[{"name": "项目", "meta": "个人项目", "time": "2026",
                "intro": "项目简介", "role": "独立开发", "details": details or [],
                "source_experience_id": "EXP-001"}],
        ),
    )


def test_uncertain_docker_without_evidence_is_removed():
    result = guard_resume_skill_evidence(payload(["工具：Git、Docker（如掌握）"]), "使用 Git 管理代码。", write_log=False)
    assert "Docker" not in " ".join(result.resume_sections.skills)
    assert "Git" in " ".join(result.resume_sections.skills)


def test_explicit_docker_is_kept_without_uncertain_marker():
    result = guard_resume_skill_evidence(
        payload(["工具：Docker（如掌握）"], details=["使用 Docker 构建服务镜像"]),
        "使用 Docker 完成服务部署。", write_log=False,
    )
    assert result.resume_sections.skills == ["工具：Docker"]


def test_knowledge_checklist_does_not_prove_skill():
    result = guard_resume_skill_evidence(payload(["Docker"], knowledge=["学习 Docker 部署"]), "完成个人项目。", write_log=False)
    assert result.resume_sections.skills == []


def test_target_role_requirement_does_not_prove_redis():
    result = guard_resume_skill_evidence(payload(["Redis"]), "目标岗位需要 Redis，但本人项目使用 SQLite。", write_log=False)
    text = " ".join(result.resume_sections.skills)
    assert "Redis" not in text
    assert "SQLite" in text


def test_grounded_rag_react_fastapi_are_kept():
    raw = "使用 React 和 FastAPI 开发 RAG 应用。"
    result = guard_resume_skill_evidence(payload(["React", "FastAPI", "RAG"], details=[raw]), raw, write_log=False)
    text = " ".join(result.resume_sections.skills)
    assert all(term in text for term in ["React", "FastAPI", "RAG", "Python"])
