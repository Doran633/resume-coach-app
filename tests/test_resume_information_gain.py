from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_information_gain_service import ensure_information_gain  # noqa: E402


def payload(details, ids=None):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n",
        bold_version="b", boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{
            "name": "RAG 助手", "meta": "个人项目", "time": "2026",
            "intro": "构建支持文档问答的 RAG 助手。", "role": "独立负责系统设计与开发。",
            "details": details, "source_experience_id": "EXP-001",
            "detail_fact_ids": ids or [[] for _ in details],
        }]),
    )


def test_intro_and_detail_same_fact_is_not_repeated():
    result = ensure_information_gain(payload([
        "构建支持文档问答的 RAG 助手。", "实现文档解析、Embedding 与向量检索链路。",
    ]))
    assert result.resume_sections.projects[0]["details"] == ["实现文档解析、Embedding 与向量检索链路。"]


def test_same_fact_paraphrase_keeps_more_informative_version():
    result = ensure_information_gain(payload(
        ["建立检索测试集。", "建立固定检索测试集并记录 Groundedness 与 Retrieval 指标。"],
        [["EXP-001-F001"], ["EXP-001-F001"]],
    ))
    assert result.resume_sections.projects[0]["details"] == ["建立固定检索测试集并记录 Groundedness 与 Retrieval 指标。"]


def test_shared_rag_term_does_not_remove_independent_facts():
    details = [
        "实现 RAG 文档解析、Embedding 与向量检索链路。",
        "建立 RAG 固定测试集并使用 Groundedness 评估回答质量。",
        "围绕 RAG Top-K 与阈值开展参数实验。",
        "实现 Citation 来源展示。",
        "加入日志、健康检查与 Smoke Test。",
        "通过 Nginx 和 systemd 完成公网部署。",
    ]
    result = ensure_information_gain(payload(details))
    assert result.resume_sections.projects[0]["details"] == details


def test_short_project_is_not_padded():
    result = ensure_information_gain(payload(["实现 Citation 来源展示。", "完成 Nginx 部署。"])).resume_sections.projects[0]
    assert len(result["details"]) == 2

