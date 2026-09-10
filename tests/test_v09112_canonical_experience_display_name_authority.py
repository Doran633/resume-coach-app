"""Regression coverage for Canonical Experience Display Name Authority.

These are fixed current-code replays, not historical snapshots of result 177.
"""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import canonical_display_name_service as name_service  # noqa: E402
from app.services import resume_title_format_service as title_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_project_projection_service import (  # noqa: E402
    NAME_PENDING_DISPLAY,
    append_canonical_project_projection_candidates,
    plan_canonical_project_projections,
)
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402


RESULT_177_EQUIVALENT = (
    "项目名称明确为大学生消费行为数据分析。"
    "对数据分析的基本流程和 Python 数据处理工具进行了学习，完成数据清洗与可视化。"
)


def _empty_payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=0,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(),
    )


def _attachment_payload(build, name: str) -> schemas.GenerationPayload:
    fact = build.ledger.facts[0]
    return schemas.GenerationPayload(
        completeness_score=0,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{
            "name": name,
            "meta": "项目经历",
            "time": "[待填写]",
            "intro": fact.resume_ready_text,
            "role": "",
            "details": [],
            "source_experience_id": fact.experience_id,
            "immutable_source_experience_id": fact.experience_id,
            "source_binding_locked": True,
            "source_fact_ids": [fact.fact_id],
            "role_source_fact_ids": [],
            "detail_fact_ids": [],
            "source_claim_ids": [fact.claim_id],
            "role_source_claim_ids": [],
            "detail_claim_ids": [],
        }]),
    )


def _attachments(project: dict) -> dict:
    return {
        key: project.get(key)
        for key in (
            "source_fact_ids", "role_source_fact_ids", "detail_fact_ids",
            "source_claim_ids", "role_source_claim_ids", "detail_claim_ids",
        )
    }


def test_result_177_equivalent_uses_explicit_name_not_summary_identity_title():
    build = build_canonical_semantic_build(RESULT_177_EQUIVALENT)
    qualification = build.display_name_qualifications[0]

    assert len(build.identities) == 1
    assert build.identities[0].title == "对数据分析的基本流程和 Python 数据处理工具"
    assert qualification.qualified
    assert qualification.display_name == "大学生消费行为数据分析"
    assert qualification.candidate_source == "local_name_declaration"
    assert qualification.source_span == build.identities[0].source_span
    assert qualification.display_name != build.identities[0].title


def test_summary_skill_role_result_and_github_phrases_cannot_self_qualify_as_names():
    samples = (
        "对数据分析的基本流程和 Python 数据处理工具进行了学习。",
        "使用 Python、Pandas 和 Matplotlib 完成数据处理。",
        "负责清洗数据并制作图表，准确率提升 10%。",
        "将代码上传 GitHub 并完成上线。",
    )

    for raw in samples:
        build = build_canonical_semantic_build(raw)
        assert len(build.identities) == 1
        assert not build.display_name_qualifications[0].qualified


def test_named_product_entity_and_names_containing_negative_word_remain_eligible():
    product = build_canonical_semantic_build("开发图书借阅管理系统，完成借阅登记与库存查询。")
    negative_word = build_canonical_semantic_build("项目一：没有边界的检索工具\n完成文档检索和摘要阅读。")

    assert product.display_name_qualifications[0].display_name == "图书借阅管理系统"
    assert product.display_name_qualifications[0].qualified
    assert negative_word.display_name_qualifications[0].display_name == "没有边界的检索工具"
    assert negative_word.display_name_qualifications[0].qualified


def test_unknown_name_keeps_owner_facts_and_generic_missing_question():
    build = build_canonical_semantic_build("完成数据导入和回归模型对比。")
    views = build_canonical_consumer_views(build)
    plan = plan_canonical_project_projections(_empty_payload(), views.planner_view)
    projected = append_canonical_project_projection_candidates(_empty_payload(), plan)

    assert len(projected.resume_sections.projects) == 1
    assert projected.resume_sections.projects[0]["name"] == NAME_PENDING_DISPLAY
    assert projected.resume_sections.projects[0]["source_experience_id"] == "EXP-001"
    assert projected.resume_sections.projects[0]["source_fact_ids"]
    assert projected.missing_questions == ["请补充尚未明确命名的项目、实习、科研课题、竞赛或活动名称。"]


def test_canonical_title_consumer_cannot_keep_an_unqualified_existing_project_name():
    build = build_canonical_semantic_build(RESULT_177_EQUIVALENT)
    views = build_canonical_consumer_views(build)
    payload = _attachment_payload(build, "对数据分析的基本流程和 Python 数据处理工具")
    before = _attachments(payload.resume_sections.projects[0])

    resolved = title_service.resolve_canonical_resume_titles(payload, views.planner_view)
    project = resolved.resume_sections.projects[0]

    assert project["name"] == "大学生消费行为数据分析"
    assert _attachments(project) == before
    assert payload.resume_sections.projects[0]["name"] != project["name"]


def test_names_are_owner_scoped_and_log_remains_aggregate_only(tmp_path, monkeypatch):
    raw = """项目一：智能停车系统
完成车位状态采集。

项目二：图书借阅管理系统
完成借阅登记。"""
    build = build_canonical_semantic_build(raw)
    views = build_canonical_consumer_views(build)
    plan = plan_canonical_project_projections(_empty_payload(), views.planner_view)
    monkeypatch.setattr(name_service, "LOG_PATH", tmp_path / "qualification.jsonl")
    name_service.write_canonical_display_name_qualification_log(
        build.display_name_qualifications,
        stage="test",
        request_id="req_v09112",
    )
    row = json.loads(name_service.LOG_PATH.read_text(encoding="utf-8"))

    assert [item["name"] for item in plan.candidates] == ["智能停车系统", "图书借阅管理系统"]
    assert [item["source_experience_id"] for item in plan.candidates] == ["EXP-001", "EXP-002"]
    assert "智能停车系统" not in json.dumps(row, ensure_ascii=False)
    assert "图书借阅管理系统" not in json.dumps(row, ensure_ascii=False)
    assert row["qualified_source_counts"] == {"explicit_heading_name": 2}


def test_qualification_is_deterministic_and_does_not_change_fact_or_claim_attachments():
    first = build_canonical_semantic_build(RESULT_177_EQUIVALENT)
    second = build_canonical_semantic_build(RESULT_177_EQUIVALENT)

    assert first.display_name_qualifications == second.display_name_qualifications
    assert [(fact.fact_id, fact.claim_id, fact.experience_id) for fact in first.ledger.facts] == [
        (fact.fact_id, fact.claim_id, fact.experience_id) for fact in second.ledger.facts
    ]
