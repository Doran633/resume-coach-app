from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_dedup_quality_service import ensure_dedup_quality  # noqa: E402
from app.services.resume_fact_dedup_service import deduplicate_resume_facts  # noqa: E402
from app.services.resume_fact_cluster_dedup_service import deduplicate_fact_clusters  # noqa: E402


def payload(details, *, intro="构建面向多段经历的简历生成系统。", role="负责生成质量链路设计与实现。", detail_fact_ids=None):
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n",
        bold_version="b", boundary_version="x", recommended_version="r", claims=[],
        interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=["具备结构化 LLM 应用开发能力。"], skills=["Python、FastAPI、RAG"],
            projects=[{
                "name": "Resume Coach", "meta": "个人项目", "time": "2026",
                "intro": intro, "role": role, "details": details,
                "source_experience_id": "EXP-001",
                "detail_fact_ids": detail_fact_ids or [[] for _ in details],
            }],
        ),
    )


def run(value):
    value = deduplicate_resume_facts(value, stage="test", write_log=False)
    return ensure_dedup_quality(value, stage="test", write_log=False)


def cluster_run(value):
    return deduplicate_fact_clusters(value, stage="test", write_log=False)


def test_experience_dilution_paraphrase_keeps_more_informative_expression():
    result = run(payload([
        "发现 Experience Dilution 和事实串用问题。",
        "在多段经历输入中识别 Experience Dilution 与跨经历事实串用问题，并引入经历级事实边界。",
    ]))
    assert result.resume_sections.projects[0]["details"] == [
        "在多段经历输入中识别 Experience Dilution 与跨经历事实串用问题，并引入经历级事实边界。"
    ]


def test_same_fact_ids_merge_and_preserve_union():
    result = run(payload(
        ["建立固定检索测试集。", "围绕检索质量建立固定测试集并记录评测结果。"],
        detail_fact_ids=[["EXP-001-F001"], ["EXP-001-F001", "EXP-001-F002"]],
    ))
    project = result.resume_sections.projects[0]
    assert len(project["details"]) == 1
    assert project["detail_fact_ids"][0] == ["EXP-001-F001", "EXP-001-F002"]


def test_shared_fact_id_does_not_merge_distinct_metrics():
    result = run(payload(
        ["将相关度从 0.4315 提升到 0.7258。", "将平均 token 消耗从 1400 降低到 600。"],
        detail_fact_ids=[["EXP-001-F001"], ["EXP-001-F001"]],
    ))
    assert len(result.resume_sections.projects[0]["details"]) == 2


def test_intro_and_role_duplicates_do_not_repeat_in_details():
    result = run(payload(
        ["构建面向多段经历的简历生成系统。", "负责生成质量链路设计与实现。", "引入 Fact Ledger 追踪原子事实来源。"],
    ))
    assert result.resume_sections.projects[0]["details"] == ["引入 Fact Ledger 追踪原子事实来源。"]


def test_independent_rag_facets_are_all_preserved():
    details = [
        "实现文档解析、切块、Embedding、向量检索和回答生成链路。",
        "建立固定测试集并使用 Groundedness 与 Retrieval 指标评测检索质量。",
        "围绕 Top-K 和阈值开展参数实验。",
        "实现 Citation 来源展示与答案溯源。",
        "通过 VPS、Nginx 和 systemd 完成公网部署。",
        "加入日志、健康检查、Smoke Test 和 Debug Trace。",
        "实现匿名用户数据隔离与权限边界。",
        "定位并解决 CORS、端口冲突和 Embedding 配置问题。",
    ]
    result = run(payload(details))
    assert result.resume_sections.projects[0]["details"] == details


def test_quality_pass_does_not_pad_short_project_with_generic_sentences():
    result = run(payload(["实现 Citation 来源展示。", "完成 Nginx 部署。"], intro="RAG 助手。", role="独立开发。"))
    assert len(result.resume_sections.projects[0]["details"]) == 2


def test_citation_pipeline_and_source_cards_are_independent_clusters():
    details = [
        "实现文档解析、Embedding、向量检索、RAG 问答和 Citation 链路。",
        "实现 Citation Source Cards，展示来源文件、章节路径、Chunk 位置和内容预览。",
    ]
    result = cluster_run(payload(details))
    assert result.resume_sections.projects[0]["details"] == details


def test_duplicate_deployment_closure_is_kept_once():
    result = cluster_run(payload([
        "完成从本地 MVP 到公网部署的完整闭环。",
        "项目已完成从本地 MVP 到公网部署的完整闭环，可进行小范围用户试用。",
    ]))
    assert len(result.resume_sections.projects[0]["details"]) == 1
    assert "用户试用" in result.resume_sections.projects[0]["details"][0]


def test_experience_dilution_problem_and_experience_id_solution_both_remain():
    details = [
        "识别多段输入中的 Experience Dilution 与跨经历事实串用问题。",
        "将用户输入拆分为 EXP-001、EXP-002 等独立经历并建立事实边界。",
    ]
    result = cluster_run(payload(details))
    assert result.resume_sections.projects[0]["details"] == details


def test_distinct_metrics_in_same_outcome_cluster_are_preserved():
    details = ["将回答相关度从 0.4315 提升至 0.7243。", "将平均 Token 消耗从 1400 降低至 600。"]
    result = cluster_run(payload(details, detail_fact_ids=[["EXP-001-F001"], ["EXP-001-F001"]]))
    assert result.resume_sections.projects[0]["details"] == details
