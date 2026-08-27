from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_recruiter_readability_service import ensure_recruiter_readability  # noqa: E402


def test_removes_file_residue_and_intro_duplicate_but_keeps_architecture_value():
    intro = "面向求职者设计 AI 简历定位与面试承接平台。"
    payload = schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{"name": "Resume Coach", "meta": "个人项目",
            "time": "2026", "intro": intro, "role": "独立开发", "source_experience_id": "EXP-001",
            "details": [intro, "新增 resume_guard_service.py", "引入 Experience ID 和 Fact Ledger 建立经历级事实边界",
                "针对 Experience Dilution 设计分段生成和事实覆盖检查"]}]),
    )
    result = ensure_recruiter_readability(payload, write_log=False)
    text = "\n".join(result.resume_sections.projects[0]["details"])
    assert "resume_guard_service.py" not in text
    assert text.count(intro) == 0
    assert "Experience ID" in text and "Fact Ledger" in text and "Experience Dilution" in text
