import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import canonical_display_name_service as name_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_project_projection_service import (  # noqa: E402
    NAME_PENDING_DISPLAY,
    append_canonical_project_projection_candidates,
    plan_canonical_project_projections,
)
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.experience_identity_service import ExperienceIdentity  # noqa: E402
from app.services.input_claim_resolution_service import resolve_experience_claims  # noqa: E402


def _payload():
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


def _views(raw: str):
    build = build_canonical_semantic_build(raw)
    return build, build_canonical_consumer_views(build)


def test_explicit_heading_name_is_qualified_without_becoming_a_new_fact():
    build, views = _views("项目二：论文阅读助手\n使用 FastAPI 实现论文检索与摘要阅读。")
    decision = build.display_name_qualifications[0]

    assert decision.qualified
    assert decision.display_name == "论文阅读助手"
    assert decision.candidate_source == "explicit_heading_name"
    assert decision.reason_codes == ("explicit_heading_name",)
    assert decision.source_span == build.identities[0].source_span
    assert views.planner_view.display_name_qualification_for_owner("EXP-001") is decision
    assert all("论文阅读助手" not in fact.resume_ready_text for fact in build.ledger.facts)


def test_structural_labels_instructions_and_negative_titles_are_pending_not_names():
    generic, _ = _views("项目经历\n完成数据导入和回归模型对比。")
    negative, _ = _views("没有开发 AI 系统\n参与需求讨论和资料整理。")
    instruction, _ = _views("请不要把这段说明写进简历\n完成资料整理。")

    assert not generic.display_name_qualifications[0].qualified
    assert "generic_structure_label" in generic.display_name_qualifications[0].reason_codes
    assert not negative.display_name_qualifications[0].qualified
    assert "constraint_statement_title" in negative.display_name_qualifications[0].reason_codes
    assert not instruction.display_name_qualifications[0].qualified


def test_legitimate_product_name_containing_negative_word_is_not_rejected_by_spelling():
    build, _ = _views("项目一：没有边界的检索工具\n完成文档检索和摘要阅读。")
    decision = build.display_name_qualifications[0]

    assert decision.qualified
    assert decision.display_name == "没有边界的检索工具"
    assert "negative_claim" not in decision.reason_codes


def test_explicit_heading_cannot_turn_a_negative_statement_into_a_project_name():
    build, _ = _views("项目一：没有开发 AI 系统\n参与需求讨论和资料整理。")
    decision = build.display_name_qualifications[0]

    assert not decision.qualified
    assert "constraint_statement_title" in decision.reason_codes


def test_canonical_name_title_and_alias_each_require_qualification():
    identity = ExperienceIdentity(
        experience_id="EXP-001",
        experience_type="项目经历",
        title="项目经历",
        raw_text="没有开发 AI 系统，参与需求讨论。",
        explicit_tech_terms=[],
        explicit_metrics=[],
        evidence_terms=[],
        risk_terms=[],
        supported_inference_terms=[],
        canonical_project_name="项目经历",
        project_aliases=["没有开发 AI 系统"],
        source_span=(40, 60),
    )
    resolution = resolve_experience_claims(
        identity.experience_id, identity.raw_text, identity.source_span[0]
    )
    decision = name_service.build_canonical_display_name_qualifications(
        (identity,), (resolution,)
    )[0]

    assert not decision.qualified
    assert decision.display_name == ""
    assert "generic_structure_label" in decision.reason_codes
    assert "constraint_statement_title" in decision.reason_codes
    assert decision.source_span == (40, 60)


def test_pending_name_keeps_owner_and_facts_and_adds_generic_missing_question():
    build, views = _views("项目经历\n完成数据导入和回归模型对比。")
    plan = plan_canonical_project_projections(_payload(), views.planner_view)
    updated = append_canonical_project_projection_candidates(_payload(), plan)
    candidate = updated.resume_sections.projects[0]

    assert candidate["name"] == NAME_PENDING_DISPLAY
    assert candidate["source_experience_id"] == "EXP-001"
    assert candidate["source_fact_ids"]
    assert plan.pending_name_owner_ids == ("EXP-001",)
    assert updated.missing_questions == ["请补充尚未明确命名的项目、实习、科研课题、竞赛或活动名称。"]
    assert [fact.fact_id for fact in build.ledger.facts] == [
        fact.fact_id for fact in build.ledger.facts
    ]


def test_each_owner_uses_its_own_qualified_name_without_cross_owner_borrowing():
    raw = """项目一：智能停车系统
完成车位状态采集和停车数据展示。

项目二：回归分析计算器
完成数据导入和回归模型对比。"""
    build, views = _views(raw)
    plan = plan_canonical_project_projections(_payload(), views.planner_view)

    assert [item["name"] for item in plan.candidates] == ["智能停车系统", "回归分析计算器"]
    assert [item["source_experience_id"] for item in plan.candidates] == ["EXP-001", "EXP-002"]
    assert len({item["source_experience_id"] for item in plan.candidates}) == 2
    assert len(build.display_name_qualifications) == 2


def test_projection_cannot_bypass_qualified_name_accessor(monkeypatch):
    build, views = _views("项目一：智能停车系统\n完成车位状态采集和停车数据展示。")

    def forbidden_identity_access(self, experience_id):
        raise AssertionError("projection must not read unqualified identity title")

    monkeypatch.setattr(type(views.planner_view), "identity_for_owner", forbidden_identity_access)
    plan = plan_canonical_project_projections(_payload(), views.planner_view)

    assert plan.candidates[0]["name"] == "智能停车系统"
    assert build.display_name_qualifications[0].qualified


def test_decisions_are_deterministic_and_do_not_change_claim_or_fact_contracts():
    raw = "项目一：论文阅读助手\n使用 FastAPI 实现论文检索与摘要阅读。"
    first, _ = _views(raw)
    second, _ = _views(raw)

    assert first.display_name_qualifications == second.display_name_qualifications
    assert [(claim.claim_id, claim.eligibility) for claim in first.ledger.claims] == [
        (claim.claim_id, claim.eligibility) for claim in second.ledger.claims
    ]
    assert [(fact.fact_id, fact.experience_id) for fact in first.ledger.facts] == [
        (fact.fact_id, fact.experience_id) for fact in second.ledger.facts
    ]


def test_qualification_log_is_aggregate_only(tmp_path, monkeypatch):
    raw = "项目一：论文阅读助手\n使用 FastAPI 实现论文检索与摘要阅读。"
    build, _ = _views(raw)
    monkeypatch.setattr(name_service, "LOG_PATH", tmp_path / "names.jsonl")

    name_service.write_canonical_display_name_qualification_log(
        build.display_name_qualifications,
        stage="test",
        request_id="req_v0988",
    )
    content = name_service.LOG_PATH.read_text(encoding="utf-8")
    row = json.loads(content)

    assert raw not in content
    assert "论文阅读助手" not in content
    assert "FastAPI" not in content
    assert row["qualified_name_count"] == 1
    assert row["candidate_source_counts"] == {"explicit_heading_name": 1}
