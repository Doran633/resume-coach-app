from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_fact_cluster_dedup_service import evaluate_semantic_quality  # noqa: E402
from app.services.resume_information_gain_service import information_gain_components  # noqa: E402


def payload(details):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{
            "name": "项目", "meta": "个人项目", "time": "2026", "intro": "项目简介。", "role": "独立开发。",
            "details": details, "source_experience_id": "EXP-001", "detail_fact_ids": [[] for _ in details],
        }]),
    )


def test_information_components_separate_action_metric_and_evidence():
    components = information_gain_components("建立固定测试集，调整 Top-K，并将相关度提升至 0.72。")
    assert "建立" in components["tech_actions"]
    assert "Top-K" in components["decisions"]
    assert "0.72" in components["metrics_results"]
    assert "测试集" in components["evidence"]


def test_semantic_scores_penalize_dependency_and_duplicate_cluster():
    score = evaluate_semantic_quality(payload([
        "完成从本地 MVP 到公网部署闭环。",
        "项目已完成从本地 MVP 到公网部署闭环。",
        "针对该问题，引入检查。",
    ]))
    assert score["semantic_completeness_score"] < 100
    assert score["fact_cluster_uniqueness_score"] < 100


def test_eight_independent_engineering_facts_can_remain_dense():
    details = [
        "实现文档解析与切块。", "接入 BAAI/bge-m3 Embedding。", "实现向量检索与 RAG 问答。",
        "实现 Citation Source Cards。", "建立固定评测集。", "围绕 Top-K 开展参数实验。",
        "加入日志、健康检查与 Smoke Test。", "通过 Nginx 与 systemd 完成部署。",
    ]
    score = evaluate_semantic_quality(payload(details))
    assert score["fact_cluster_uniqueness_score"] == 100

