from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.weak_profile_strategy_service import detect_weak_profile, strengthen_weak_profile_payload  # noqa: E402


def payload_with_projects(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=55,
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
            personal_info={},
            summary=[],
            skills=[],
            projects=projects,
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            interview_preparation=[],
        ),
    )


def all_resume_text(payload: schemas.GenerationPayload) -> str:
    sections = payload.resume_sections
    project_text = []
    for project in sections.projects:
        project_text.append(" ".join([str(project.get("name", "")), str(project.get("meta", "")), str(project.get("intro", "")), str(project.get("role", "")), " ".join(project.get("details", []) or [])]))
    return " ".join(sections.summary + sections.skills + project_text + sections.interview_preparation)


def test_course_assignment_is_detected_as_weak_profile():
    raw = "我做过一个课程大作业，写了几个 Vue 页面，调了一些接口，最后做了课堂展示。"
    payload = payload_with_projects(
        [{"name": "课程大作业", "meta": "项目经历", "time": "[待填写]", "intro": "课程项目", "role": "写页面", "details": ["写页面", "调接口"]}]
    )

    assert detect_weak_profile(raw, payload) is True


def test_no_internship_is_not_fabricated():
    raw = "我做过一个课程大作业，写了几个页面，调接口。"
    payload = strengthen_weak_profile_payload(payload_with_projects([]), raw, "前端开发")
    text = all_resume_text(payload)

    assert "实习经历" not in text
    assert "公司" not in text
    assert "企业" not in text


def test_course_project_is_not_written_as_enterprise_project():
    raw = "课程项目：做了一个图书管理系统，负责页面、接口联调和展示。"
    payload = payload_with_projects(
        [{"name": "图书管理系统", "meta": "企业项目", "time": "[待填写]", "intro": "课程项目", "role": "负责展示", "details": ["写页面"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "后端开发")
    text = all_resume_text(strengthened)

    assert strengthened.resume_sections.projects[0]["meta"] == "课程项目"
    assert "企业项目" not in text
    assert "生产级" not in text


def test_simple_page_and_api_work_is_strengthened():
    raw = "我做过一个小项目，写页面，调接口，写文档。"
    payload = payload_with_projects(
        [{"name": "小项目", "meta": "项目经历", "time": "[待填写]", "intro": "简单小项目", "role": "写页面", "details": ["写页面"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "前端开发")
    details = " ".join(strengthened.resume_sections.projects[0]["details"])

    assert "页面开发与交互流程实现" in details
    assert "接口联调与数据流转校验" in details
    assert "项目说明" in details or "复盘文档" in details


def test_student_work_becomes_coordination_and_delivery():
    raw = "学生工作：我在学生会参与活动组织，做材料整理和现场执行。"
    payload = payload_with_projects(
        [{"name": "学生会活动", "meta": "校园经历", "time": "[待填写]", "intro": "学生工作", "role": "整理材料", "details": ["现场执行"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "产品 / 运营")
    text = all_resume_text(strengthened)

    assert "组织协调" in text
    assert "沟通推进" in text or "执行复盘" in text
    assert "材料沉淀" in text


def test_competition_participation_does_not_fabricate_award():
    raw = "比赛经历：参加创新创业比赛，负责方案设计、材料整理和路演答辩。"
    payload = payload_with_projects(
        [{"name": "创新创业比赛", "meta": "竞赛经历", "time": "[待填写]", "intro": "比赛参与", "role": "负责答辩", "details": ["方案设计"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "泛互联网岗位")
    text = all_resume_text(strengthened)

    assert "方案设计" in text
    assert "展示答辩" in text or "路演" in text
    assert "一等奖" not in text
    assert "二等奖" not in text
    assert "获奖" not in text


def test_summary_and_details_are_filled_enough():
    raw = "课设：做了一个后台系统，写页面、调接口、做展示。"
    payload = payload_with_projects(
        [{"name": "后台系统", "meta": "项目经历", "time": "[待填写]", "intro": "课设", "role": "开发", "details": ["写页面"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "前端开发")

    assert 1 <= len(strengthened.resume_sections.summary) <= 2
    assert len(strengthened.resume_sections.projects[0]["details"]) >= 3


def test_no_missing_hard_facts_are_added_to_resume_sections():
    raw = "我做过一个课程大作业，写了几个页面，调接口。"
    payload = payload_with_projects(
        [{"name": "课程大作业", "meta": "项目经历", "time": "[待填写]", "intro": "课程项目", "role": "写页面", "details": ["调接口"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "前端开发")
    text = all_resume_text(strengthened)

    for forbidden in ["上线", "用户数", "star", "公司", "专业", "高并发"]:
        assert forbidden not in text


def test_weak_profile_does_not_put_no_internship_in_resume_body():
    raw = "我没有实习经历，只做过一个课程大作业，写了几个页面。"
    payload = payload_with_projects(
        [{"name": "课程大作业", "meta": "项目经历", "time": "[待填写]", "intro": "没有实习经历", "role": "写页面", "details": ["写了几个页面"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "前端开发")
    text = all_resume_text(strengthened)

    assert "没有实习" not in text
    assert "实习经历" not in text


def test_weak_profile_does_not_put_no_online_in_projects():
    raw = "课程项目没有上线，主要做了页面开发和课堂展示。"
    payload = payload_with_projects(
        [{"name": "课程项目", "meta": "课程项目", "time": "[待填写]", "intro": "没有上线", "role": "课堂展示", "details": ["没有上线", "写了几个页面"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "前端开发")
    text = all_resume_text(strengthened)

    assert "没有上线" not in text
    assert "未上线" not in text


def test_weak_profile_competition_without_award_stays_positive():
    raw = "参加过一次创新创业比赛，没有获奖，主要负责方案文档和答辩 PPT。"
    payload = payload_with_projects(
        [{"name": "创新创业比赛", "meta": "竞赛经历", "time": "[待填写]", "intro": "没有获奖", "role": "答辩 PPT", "details": ["没有获奖", "方案文档"]}]
    )

    strengthened = strengthen_weak_profile_payload(payload, raw, "泛互联网岗位")
    text = all_resume_text(strengthened)

    assert "没有获奖" not in text
    assert "获奖" not in text
    assert "方案文档" in text
    assert "竞赛经历" in text


def test_weak_profile_never_creates_internship_module_without_fact():
    raw = "没有实习，只有课程项目和学生工作。"
    strengthened = strengthen_weak_profile_payload(payload_with_projects([]), raw, "泛互联网岗位")

    assert all("实习" not in str(project.get("meta", "")) for project in strengthened.resume_sections.projects)


if __name__ == "__main__":
    test_course_assignment_is_detected_as_weak_profile()
    test_no_internship_is_not_fabricated()
    test_course_project_is_not_written_as_enterprise_project()
    test_simple_page_and_api_work_is_strengthened()
    test_student_work_becomes_coordination_and_delivery()
    test_competition_participation_does_not_fabricate_award()
    test_summary_and_details_are_filled_enough()
    test_no_missing_hard_facts_are_added_to_resume_sections()
    test_weak_profile_does_not_put_no_internship_in_resume_body()
    test_weak_profile_does_not_put_no_online_in_projects()
    test_weak_profile_competition_without_award_stays_positive()
    test_weak_profile_never_creates_internship_module_without_fact()
    print("weak profile strategy tests passed")
