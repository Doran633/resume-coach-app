from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_adaptive_narrative_service import organize_adaptive_narrative  # noqa: E402
from app.services.resume_narrative_coherence_service import evaluate_narrative_quality  # noqa: E402


def payload(meta: str, details: list[str]):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n",
        bold_version="b", boundary_version="x", recommended_version="r", claims=[],
        interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{
            "name": "经历", "meta": meta, "time": "[待填写]", "intro": "解决目标场景中的具体问题。",
            "role": "负责核心任务交付。", "details": details, "source_experience_id": "EXP-001",
            "detail_fact_ids": [[f"EXP-001-F{i:03d}"] for i in range(1, len(details) + 1)],
        }]),
    )


def test_project_facts_are_ordered_by_available_dimensions_without_padding():
    value = payload("个人项目", [
        "通过 VPS、Nginx 和 systemd 完成公网部署。",
        "实现文档解析、Embedding 与向量检索链路。",
        "围绕 Top-K 和阈值开展参数实验并优化检索效果。",
    ])
    result = organize_adaptive_narrative(value)
    assert result.resume_sections.projects[0]["details"] == [
        "实现文档解析、Embedding 与向量检索链路。",
        "围绕 Top-K 和阈值开展参数实验并优化检索效果。",
        "通过 VPS、Nginx 和 systemd 完成公网部署。",
    ]
    assert len(result.resume_sections.projects[0]["details"]) == 3


def test_internship_uses_ownership_before_delivery_result():
    result = organize_adaptive_narrative(payload("实习经历", [
        "将回答相关度从 0.43 提升至 0.72。",
        "负责 RAG 测试集建设与检索参数优化。",
        "建立固定测试集并完成结果分析。",
    ]))
    details = result.resume_sections.projects[0]["details"]
    assert details[0].startswith("负责")
    assert details[-1].startswith("将回答相关度")


def test_internal_dimensions_never_enter_project_payload():
    result = organize_adaptive_narrative(payload("科研经历", ["设计实验并分析结果。"])).model_dump()
    assert "narrative_dimension" not in str(result)


def test_quality_evaluation_reports_coherent_sequence():
    value = organize_adaptive_narrative(payload("个人项目", [
        "实现检索链路。", "定位检索偏差并调整 Top-K。", "完成 Nginx 部署。",
    ]))
    score = evaluate_narrative_quality(value, stage="test", write_log=False)
    assert score.narrative_coherence_score == 100

