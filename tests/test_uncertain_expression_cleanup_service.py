from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.uncertain_expression_cleanup_service import cleanup_uncertain_expressions  # noqa: E402


def make_payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="熟悉 Docker（如有）和 RAG 应用开发。",
        bold_version="集成 LangGraph 编排流程。",
        boundary_version="",
        recommended_version="围绕 Top-K / Retrieval 做检索评估。",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=["具备 RAG 和 Docker（如有）实践。"],
            skills=["RAG", "Docker（如有）", "LangGraph（建议掌握）"],
            projects=[
                {
                    "name": "RAG 测试集",
                    "meta": "项目经历",
                    "time": "[待填写]",
                    "intro": "围绕 RAG 测试集做检索效果评估。",
                    "role": "负责 Top-K / Retrieval 测试设计。",
                    "details": ["使用 Redis（可补充）优化缓存", "围绕 Top-K / Retrieval 进行评估", "接入 Rerank 提升检索排序"],
                }
            ],
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            interview_preparation=[],
        ),
    )


def test_uncertain_terms_removed_from_resume_body_and_moved_to_preparation():
    cleaned = cleanup_uncertain_expressions(make_payload(), "我做了 RAG 测试集和检索效果评估。")
    body = cleaned.model_dump_json()

    assert "Docker（如有）" not in body
    assert "Redis（可补充）" not in body
    assert "LangGraph（建议掌握）" not in body
    assert "接入 Rerank" not in body
    assert "如有" not in body
    assert "可补充" not in body
    assert "建议掌握" not in body
    assert "Docker" in cleaned.knowledge_checklist
    assert "Redis" in cleaned.knowledge_checklist
    assert "LangGraph" in cleaned.knowledge_checklist
    assert "Rerank" in cleaned.knowledge_checklist


def test_supported_rag_inference_terms_are_kept():
    cleaned = cleanup_uncertain_expressions(make_payload(), "我做了 RAG 测试集和检索效果评估。")
    project_text = " ".join(cleaned.resume_sections.projects[0]["details"])

    assert "Top-K" in project_text
    assert "Retrieval" in project_text


def test_explicit_technology_without_uncertain_marker_is_kept():
    payload = make_payload()
    payload.resume_sections.skills = ["Docker", "RAG"]
    payload.resume_sections.projects[0]["details"] = ["使用 Docker 完成服务部署"]

    cleaned = cleanup_uncertain_expressions(payload, "使用 Docker 完成 RAG 服务部署。")
    body = cleaned.model_dump_json()

    assert "Docker" in body
    assert "Docker（如有）" not in body


if __name__ == "__main__":
    test_uncertain_terms_removed_from_resume_body_and_moved_to_preparation()
    test_supported_rag_inference_terms_are_kept()
    test_explicit_technology_without_uncertain_marker_is_kept()
    print("uncertain expression cleanup tests passed")
