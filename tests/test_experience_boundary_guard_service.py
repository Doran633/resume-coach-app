from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.experience_boundary_guard_service import guard_experience_boundaries  # noqa: E402
from app.services.project_specificity_guard_service import guard_project_specificity  # noqa: E402


RAW_INPUT = """项目一｜RAG 助手
使用 React、FastAPI、RAG 和 Docker 完成资料上传、检索问答，并通过公网域名部署，有 500 用户访问记录。

项目二｜课程后台
使用 Vue 完成后台页面、表单校验和接口联调。

科研经历｜课程知识图谱研究
参与论文阅读和实验结果整理。

竞赛经历｜创新创业比赛
负责答辩材料和方案展示，获得校级立项。
"""

RAG_TEMPLATE = "围绕文档解析、切块、Embedding、向量检索和回答生成梳理 RAG 应用链路"


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


def test_project_does_not_inherit_other_project_docker():
    payload = payload_with_projects(
        [
            {"name": "RAG 助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "负责 RAG", "details": ["使用 Docker 完成部署", "围绕 Top-K 和 Retrieval 进行检索评估"]},
            {"name": "课程后台", "meta": "项目经历", "time": "[待填写]", "intro": "课程后台", "role": "负责 Vue 页面", "details": ["使用 Vue 完成页面", "使用 Docker 管理服务"]},
        ]
    )

    guarded = guard_experience_boundaries(payload, RAW_INPUT)
    second = guarded.resume_sections.projects[1]

    assert "Docker" not in " ".join(second["details"])
    assert "Vue" in " ".join(second["details"])


def test_rag_project_keeps_supported_inference_terms():
    payload = payload_with_projects(
        [
            {"name": "RAG 助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "负责 RAG", "details": ["围绕 Top-K 和 Retrieval 进行检索评估"]},
            {"name": "课程后台", "meta": "项目经历", "time": "[待填写]", "intro": "课程后台", "role": "负责 Vue 页面", "details": ["使用 Vue 完成页面"]},
        ]
    )

    guarded = guard_experience_boundaries(payload, RAW_INPUT)
    first_text = " ".join(guarded.resume_sections.projects[0]["details"])

    assert "Top-K" in first_text
    assert "Retrieval" in first_text


def test_experience_does_not_inherit_metrics_or_awards():
    payload = payload_with_projects(
        [
            {"name": "RAG 助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "负责 RAG", "details": ["有 500 用户访问记录"]},
            {"name": "课程后台", "meta": "项目经历", "time": "[待填写]", "intro": "课程后台", "role": "负责 Vue 页面", "details": ["支持 500 用户访问", "使用 Vue 完成页面"]},
            {"name": "创新创业比赛", "meta": "竞赛经历", "time": "[待填写]", "intro": "竞赛", "role": "负责答辩", "details": ["获得校级立项", "完成论文实验结果分析"]},
        ]
    )

    guarded = guard_experience_boundaries(payload, RAW_INPUT)

    assert "500" not in " ".join(guarded.resume_sections.projects[1]["details"])
    assert "论文" not in " ".join(guarded.resume_sections.projects[2]["details"])
    assert "校级立项" in " ".join(guarded.resume_sections.projects[2]["details"])


def test_template_sentence_needs_specificity_guard():
    payload = payload_with_projects(
        [
            {"name": "RAG 助手", "meta": "项目经历", "time": "[待填写]", "intro": "RAG 项目", "role": "负责 RAG", "details": [RAG_TEMPLATE]},
            {"name": "课程后台", "meta": "项目经历", "time": "[待填写]", "intro": "课程后台", "role": "负责 Vue 页面", "details": [RAG_TEMPLATE, "使用 Vue 完成页面"]},
        ]
    )

    boundary_guarded = guard_experience_boundaries(payload, RAW_INPUT)
    specificity_guarded = guard_project_specificity(boundary_guarded, RAW_INPUT)

    combined = " ".join(" ".join(project["details"]) for project in specificity_guarded.resume_sections.projects)
    assert combined.count(RAG_TEMPLATE) == 1


if __name__ == "__main__":
    test_project_does_not_inherit_other_project_docker()
    test_rag_project_keeps_supported_inference_terms()
    test_experience_does_not_inherit_metrics_or_awards()
    test_template_sentence_needs_specificity_guard()
    print("experience boundary guard tests passed")
