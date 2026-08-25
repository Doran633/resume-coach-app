from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.project_specificity_guard_service import guard_project_specificity  # noqa: E402


RAG_TEMPLATE = "围绕文档解析、切块、Embedding、向量检索和回答生成梳理 RAG 应用链路"


RAW_INPUT = """项目一｜AI RAG 智能助手
从零设计 AI RAG 助手，使用 React、FastAPI、SQLite、Embedding、向量检索、RAG 问答和 Citation，并通过 VPS、Nginx、systemd 部署上线。

项目二｜Resume Positioning Coach
开发 AI 简历定位工具，设计经历输入、三档包装、Claim 承接检查、面试准备和 DOCX 导出。

实习经历｜产品运营实习
参与用户访谈整理、需求记录、后台数据核对和活动复盘。

竞赛经历｜创新创业比赛
负责方案设计、材料整理、路演答辩和赛后复盘。
"""


def payload_with_projects(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=[],
            skills=[],
            projects=projects,
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            interview_preparation=[],
        ),
    )


def project_text(project: dict) -> str:
    return " ".join(
        [
            str(project.get("intro", "")),
            str(project.get("role", "")),
            " ".join(str(item) for item in project.get("details", []) or []),
        ]
    )


def test_exact_duplicate_detail_is_removed_from_later_project():
    payload = payload_with_projects(
        [
            {"name": "AI RAG 智能助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "独立开发", "details": [RAG_TEMPLATE, "实现 Citation 和会话恢复"]},
            {"name": "Resume Positioning Coach", "meta": "项目经历", "time": "[待填写]", "intro": "简历工具", "role": "独立开发", "details": [RAG_TEMPLATE, "实现 DOCX 导出和 Claim 承接检查"]},
        ]
    )

    guarded = guard_project_specificity(payload, RAW_INPUT)
    all_details = " ".join(project_text(project) for project in guarded.resume_sections.projects)

    assert all_details.count(RAG_TEMPLATE) == 1
    assert "DOCX 导出" in project_text(guarded.resume_sections.projects[1])


def test_rag_template_only_kept_on_relevant_rag_project():
    payload = payload_with_projects(
        [
            {"name": "AI RAG 智能助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "独立开发", "details": [RAG_TEMPLATE]},
            {"name": "Resume Positioning Coach", "meta": "项目经历", "time": "[待填写]", "intro": "简历工具", "role": "独立开发", "details": [RAG_TEMPLATE, "设计三档包装和风险承接"]},
        ]
    )

    guarded = guard_project_specificity(payload, RAW_INPUT)
    first_text = project_text(guarded.resume_sections.projects[0])
    second_text = project_text(guarded.resume_sections.projects[1])

    assert RAG_TEMPLATE in first_text
    assert RAG_TEMPLATE not in second_text
    assert "三档包装" in second_text


def test_internship_does_not_keep_project_rag_template():
    payload = payload_with_projects(
        [
            {"name": "AI RAG 智能助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "独立开发", "details": [RAG_TEMPLATE]},
            {"name": "产品运营实习", "meta": "实习经历", "time": "[待填写]", "intro": "运营实习", "role": "参与运营支持", "details": [RAG_TEMPLATE, "整理用户访谈和需求记录"]},
        ]
    )

    guarded = guard_project_specificity(payload, RAW_INPUT)
    internship_text = project_text(guarded.resume_sections.projects[1])

    assert RAG_TEMPLATE not in internship_text
    assert "用户访谈" in internship_text


def test_competition_does_not_keep_project_rag_template():
    payload = payload_with_projects(
        [
            {"name": "AI RAG 智能助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "独立开发", "details": [RAG_TEMPLATE]},
            {"name": "创新创业比赛", "meta": "竞赛经历", "time": "[待填写]", "intro": "比赛", "role": "负责答辩", "details": [RAG_TEMPLATE, "完成路演材料和赛后复盘"]},
        ]
    )

    guarded = guard_project_specificity(payload, RAW_INPUT)
    competition_text = project_text(guarded.resume_sections.projects[1])

    assert RAG_TEMPLATE not in competition_text
    assert "路演材料" in competition_text


def test_project_with_enough_details_deletes_duplicate_without_padding():
    payload = payload_with_projects(
        [
            {"name": "AI RAG 智能助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "独立开发", "details": [RAG_TEMPLATE, "实现 Citation"]},
            {"name": "Resume Positioning Coach", "meta": "项目经历", "time": "[待填写]", "intro": "简历工具", "role": "独立开发", "details": [RAG_TEMPLATE, "实现 DOCX 导出", "设计 Claim 承接检查"]},
        ]
    )

    guarded = guard_project_specificity(payload, RAW_INPUT)
    second_details = guarded.resume_sections.projects[1]["details"]

    assert RAG_TEMPLATE not in second_details
    assert len(second_details) == 2


def test_cleanup_keeps_at_least_one_detail():
    payload = payload_with_projects(
        [
            {"name": "AI RAG 智能助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "独立开发", "details": [RAG_TEMPLATE]},
            {"name": "创新创业比赛", "meta": "竞赛经历", "time": "[待填写]", "intro": "比赛", "role": "负责答辩", "details": [RAG_TEMPLATE]},
        ]
    )

    guarded = guard_project_specificity(payload, RAW_INPUT)
    second_details = guarded.resume_sections.projects[1]["details"]

    assert second_details
    assert RAG_TEMPLATE not in " ".join(second_details)


def test_two_rag_projects_can_keep_rag_with_different_focus():
    raw_input = """项目一｜RAG 应用开发
实现文档问答、Embedding、向量检索和 Citation。

项目二｜RAG 测试集评估
围绕 Top-K、Recall、Groundedness 和固定测试集做检索效果评估。
"""
    payload = payload_with_projects(
        [
            {"name": "RAG 应用开发", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 应用", "role": "独立开发", "details": [RAG_TEMPLATE]},
            {"name": "RAG 测试集评估", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 评测", "role": "负责测试", "details": [RAG_TEMPLATE]},
        ]
    )

    guarded = guard_project_specificity(payload, raw_input)
    first_text = project_text(guarded.resume_sections.projects[0])
    second_text = project_text(guarded.resume_sections.projects[1])
    combined = first_text + second_text

    assert combined.count(RAG_TEMPLATE) <= 1
    assert "RAG" in first_text
    assert "RAG" in second_text
    assert first_text != second_text
    assert "Groundedness" in second_text or "Recall" in second_text or "Top-K" in second_text


if __name__ == "__main__":
    test_exact_duplicate_detail_is_removed_from_later_project()
    test_rag_template_only_kept_on_relevant_rag_project()
    test_internship_does_not_keep_project_rag_template()
    test_competition_does_not_keep_project_rag_template()
    test_project_with_enough_details_deletes_duplicate_without_padding()
    test_cleanup_keeps_at_least_one_detail()
    test_two_rag_projects_can_keep_rag_with_different_focus()
    print("project specificity guard tests passed")
