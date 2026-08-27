from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_skill_taxonomy_service import calibrate_resume_skill_taxonomy  # noqa: E402


def test_skills_use_recruiter_facing_canonical_categories():
    payload = schemas.GenerationPayload(
        completeness_score=80, confirmed_facts=[], missing_questions=[], normal_version="",
        bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[], resume_sections=schemas.ResumeSections(skills=[
            "后端技术：掌握 Python、FastAPI、SQLite",
            "前端技术：TypeScript、React",
            "工具：Nginx、systemd、Docker",
            "AI：RAG、Agent",
            "数据库：SQLite",
        ]),
    )
    result = calibrate_resume_skill_taxonomy(payload, write_log=False)
    text = "\n".join(result.resume_sections.skills)
    assert "编程语言：Python、TypeScript" in text
    assert "前端开发：React" in text
    assert "后端开发：FastAPI" in text
    assert "数据库与存储：SQLite" in text
    assert "工程化与部署：Docker、Nginx、systemd" in text
    assert "AI / 大模型应用：RAG、Agent" in text
    assert text.count("SQLite") == 1
    assert all(word not in text for word in ["掌握", "精通", "熟悉"])


def test_empty_categories_are_not_emitted():
    payload = schemas.GenerationPayload(
        completeness_score=80, confirmed_facts=[], missing_questions=[], normal_version="",
        bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[], resume_sections=schemas.ResumeSections(skills=["编程语言：Python"]),
    )
    result = calibrate_resume_skill_taxonomy(payload, write_log=False)
    assert result.resume_sections.skills == ["编程语言：Python"]

