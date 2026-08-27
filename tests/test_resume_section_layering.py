from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_fact_increment_service import ensure_resume_fact_increment  # noqa: E402
from app.services.resume_section_layering_service import layer_resume_sections  # noqa: E402


def payload(details: list[str]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80, confirmed_facts=[], missing_questions=[], normal_version="",
        bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[], resume_sections=schemas.ResumeSections(projects=[{
            "name": "RAG 助手", "meta": "个人项目", "time": "2026",
            "intro": "面向课程资料问答场景开发 RAG 学习助手。负责 RAG 链路实现。",
            "role": "独立开发，负责前后端设计、RAG 链路实现及部署。",
            "details": details,
            "detail_fact_ids": [[f"EXP-001-F{i:03d}"] for i in range(1, len(details) + 1)],
            "source_experience_id": "EXP-001",
        }]))


def test_intro_role_details_are_layered_without_losing_high_value_facts():
    source = payload([
        "独立开发并负责前后端设计、RAG 链路实现及部署。",
        "建立固定测试集，围绕 Top-K 和 Score Threshold 评估检索质量。",
        "通过 Nginx 与 systemd 完成公网部署并增加健康检查。",
        "将平均 Token 消耗从 1400 降低至 600 Token/次。",
    ])
    layered = layer_resume_sections(source, write_log=False)
    result = ensure_resume_fact_increment(layered)
    project = result.resume_sections.projects[0]
    assert "面向课程资料问答场景" in project["intro"]
    assert "独立开发" in project["role"]
    text = " ".join(project["details"])
    assert "测试集" in text and "健康检查" in text and "1400" in text and "600" in text
    assert len(project["details"]) >= 3


def test_generic_header_duplicate_without_provenance_is_removed():
    source = payload([
        "面向课程资料问答场景开发 RAG 学习助手。",
        "建立固定测试集并评估检索质量。",
        "完成公网部署。",
    ])
    source.resume_sections.projects[0]["detail_fact_ids"] = [[], ["EXP-001-F002"], ["EXP-001-F003"]]
    result = layer_resume_sections(source, write_log=False)
    assert result.resume_sections.projects[0]["details"][0] != "面向课程资料问答场景开发 RAG 学习助手。"

