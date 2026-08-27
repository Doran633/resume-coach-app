from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_output_quality_gate_service import evaluate_resume_output_quality  # noqa: E402


RAW = "项目经历｜RAG 助手\n独立使用 FastAPI 构建 RAG 助手，实现 Citation，并通过 Nginx 部署。"


def payload(details, intro="面向文档问答场景构建 RAG 助手。"):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n",
        bold_version="b", boundary_version="x", recommended_version="r", claims=[],
        interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=["具备独立项目交付能力。"], skills=["FastAPI、RAG、Nginx"],
            projects=[{
                "name": "RAG 助手", "meta": "个人项目", "time": "2026", "intro": intro,
                "role": "独立负责核心链路设计与实现。", "details": details,
                "source_experience_id": "EXP-001",
            }],
        ),
    )


def score(value):
    return evaluate_resume_output_quality(value, RAW, stage="test", write_log=False)


def test_clean_payload_scores_high_and_gate_does_not_mutate_payload():
    value = payload(["使用 FastAPI 构建 RAG 问答链路。", "实现 Citation 来源展示。", "通过 Nginx 完成部署。"])
    before = value.model_dump_json()
    result = score(value)
    assert result.overall_quality_score >= 85
    assert result.typography_score == 100
    assert value.model_dump_json() == before


def test_duplicate_typography_and_internal_markers_lower_scores():
    duplicate = payload(["发现 Experience Dilution 问题。", "进一步发现 Experience Dilution 问题。"])
    punctuation = payload(["标题感知切块、、Query Intent"])
    internal = payload(["section summary chunk source_experience_id"])
    assert score(duplicate).duplicate_score < 100
    assert score(punctuation).typography_score < 100
    assert score(internal).internal_marker_score < 100
