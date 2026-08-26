from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_fact_dedup_service import deduplicate_resume_facts, similarity  # noqa: E402


def payload(details: list[str], second_project: bool = False) -> schemas.GenerationPayload:
    projects = [{"name": "Resume Coach", "meta": "项目经历", "time": "[待填写]", "intro": "开发 AI 简历定位平台", "role": "独立开发", "details": details, "source_experience_id": "EXP-001"}]
    if second_project:
        projects.append({"name": "RAG 助手", "meta": "项目经历", "time": "[待填写]", "intro": "开发文档问答工具", "role": "独立开发", "details": ["使用 RAG 完成文档检索与上下文构建"], "source_experience_id": "EXP-002"})
    return schemas.GenerationPayload(completeness_score=80, confirmed_facts=[], missing_questions=[], normal_version="", bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[], resume_sections=schemas.ResumeSections(projects=projects))


def test_experience_dilution_duplicate_is_merged_with_progress_retained():
    result = deduplicate_resume_facts(payload([
        "发现 Experience Dilution 和事实串用问题",
        "之后在多段经历输入中进一步发现 Experience Dilution 和事实串用问题，并推进经历级拆分",
    ]), write_log=False)
    details = result.resume_sections.projects[0]["details"]
    assert len(details) == 1
    assert "推进经历级拆分" in details[0]


def test_different_project_usage_is_not_cross_project_deduplicated():
    result = deduplicate_resume_facts(payload(["使用 RAG 进行简历事实承接检查"], second_project=True), write_log=False)
    assert len(result.resume_sections.projects) == 2
    assert result.resume_sections.projects[0]["details"]
    assert result.resume_sections.projects[1]["details"]


def test_medium_similarity_is_retained_for_precision():
    assert similarity("完成检索测试集建设", "完成检索参数优化并记录评测结果") < 0.88


if __name__ == "__main__":
    test_experience_dilution_duplicate_is_merged_with_progress_retained()
    test_different_project_usage_is_not_cross_project_deduplicated()
    test_medium_similarity_is_retained_for_precision()
    print("resume fact dedup tests passed")
