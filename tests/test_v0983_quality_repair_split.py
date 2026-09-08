import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import resume_quality_repair_router_service as router_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.resume_delivery_quality_gate_service import (  # noqa: E402
    ResumeQualityIssue,
    validate_resume_delivery_quality,
)
from app.services.resume_quality_repair_router_service import route_quality_repairs  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import (  # noqa: E402
    aggregate_skill_evidence_from_ledger,
)


RAW = """项目一：资料检索工具
使用 FastAPI 实现资料检索接口。
完成日志记录与健康检查。
没有使用 Docker。
框架可能是 Flask，我记不清。

项目二：迎新志愿活动
参与新生引导和物资整理。"""


def _build_views():
    build = build_canonical_semantic_build(RAW)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    return build, evidence, build_canonical_consumer_views(build, evidence)


def _payload(projects):
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
            personal_info={}, education={}, summary=["具备项目实践能力。"],
            skills=[], projects=projects, interview_preparation=[],
        ),
    )


def _bound_project(owner, fact_ids, *, intro="实现资料检索接口。", role="实现资料检索接口。", details=None):
    return {
        "name": "资料检索工具",
        "meta": "项目经历",
        "time": "[待填写]",
        "intro": intro,
        "role": role,
        "details": list(details or ["实现资料检索接口。"]),
        "source_experience_id": owner,
        "immutable_source_experience_id": owner,
        "source_binding_locked": True,
        "source_fact_ids": list(fact_ids),
        "role_source_fact_ids": list(fact_ids),
        "detail_fact_ids": [list(fact_ids)],
    }


def _duplicate_issue(project_index=0):
    return ResumeQualityIssue(
        issue_code="DUPLICATE_FACT",
        severity="critical",
        field_path=f"resume_sections.projects.{project_index}",
    )


def test_same_owner_same_fact_duplicate_fields_keep_one_visible_fact():
    build, evidence, views = _build_views()
    owner = build.identities[0].experience_id
    fact_id = views.owner_scopes[owner].repair_eligible_fact_ids[0]
    payload = _payload([_bound_project(owner, (fact_id,))])
    gate_before = payload.model_dump(mode="json")
    evaluation = validate_resume_delivery_quality(
        payload, consumer_views=views, skill_evidence=evidence, write_log=False,
    )
    assert payload.model_dump(mode="json") == gate_before

    result = route_quality_repairs(
        payload, evaluation.issues, views.repair_view,
        stage="test", write_log=False,
    )

    project = payload.resume_sections.projects[0]
    assert project["intro"] == "实现资料检索接口。"
    assert project["role"] == ""
    # The project aggregate cannot prove that intro and detail carry the same
    # fact. Only role has field-local evidence, so the detail remains.
    assert project["details"] == ["实现资料检索接口。"]
    assert project["immutable_source_experience_id"] == owner
    assert project["source_fact_ids"] == [fact_id]
    assert result.stats.applied_action_count == 1
    assert result.stats.high_value_fact_count_after >= result.stats.high_value_fact_count_before
    assert "DUPLICATE_FACT" in {issue.issue_code for issue in evaluation.issues}
    assert gate_before != payload.model_dump(mode="json")


def test_same_text_with_different_fact_bindings_is_not_removed():
    build, _, views = _build_views()
    owner = build.identities[0].experience_id
    fact_ids = views.owner_scopes[owner].repair_eligible_fact_ids
    assert len(fact_ids) >= 2
    project = _bound_project(
        owner,
        (fact_ids[0],),
        role="实现资料检索接口。",
        details=["完成日志记录与健康检查。"],
    )
    project["role_source_fact_ids"] = [fact_ids[1]]
    project["detail_fact_ids"] = [[fact_ids[1]]]
    payload = _payload([project])

    result = route_quality_repairs(
        payload, [_duplicate_issue()], views.repair_view,
        stage="test", write_log=False,
    )

    assert payload.resume_sections.projects[0]["role"] == "实现资料检索接口。"
    assert result.stats.applied_action_count == 0


def test_cross_owner_duplicate_is_not_repaired_or_rebound():
    build, _, views = _build_views()
    first, second = (identity.experience_id for identity in build.identities)
    local_fact_id = views.owner_scopes[first].repair_eligible_fact_ids[0]
    foreign_fact_id = views.owner_scopes[second].repair_eligible_fact_ids[0]
    project = _bound_project(
        first,
        (local_fact_id,),
        details=["完成日志记录与健康检查。"],
    )
    project["role_source_fact_ids"] = [foreign_fact_id]
    project["detail_fact_ids"] = [[local_fact_id]]
    payload = _payload([project])
    before = payload.model_dump(mode="json")

    result = route_quality_repairs(
        payload, [_duplicate_issue()], views.repair_view,
        stage="test", write_log=False,
    )

    assert payload.model_dump(mode="json") == before
    assert result.stats.applied_action_count == 0


def test_withheld_uncertain_and_negative_claims_never_enter_repair_scope():
    build, _, views = _build_views()
    owner = build.identities[0].experience_id
    scope = views.owner_scopes[owner]
    withheld_claim_ids = set(scope.withheld_claim_ids) | set(scope.excluded_claim_ids)

    assert withheld_claim_ids
    assert all(not views.repair_view.permits_claim(owner, claim_id) for claim_id in withheld_claim_ids)
    assert all(
        fact.claim_id not in withheld_claim_ids
        for fact in views.repair_view.eligible_facts(owner)
    )


def test_router_is_idempotent_and_delivery_gate_remains_validation_only():
    build, evidence, views = _build_views()
    owner = build.identities[0].experience_id
    fact_id = views.owner_scopes[owner].repair_eligible_fact_ids[0]
    payload = _payload([_bound_project(owner, (fact_id,))])

    before_gate = payload.model_dump(mode="json")
    evaluation = validate_resume_delivery_quality(
        payload, consumer_views=views, skill_evidence=evidence, write_log=False,
    )
    assert payload.model_dump(mode="json") == before_gate

    first = route_quality_repairs(
        payload, evaluation.issues, views.repair_view, stage="test", write_log=False,
    )
    after_first = payload.model_dump(mode="json")
    second = route_quality_repairs(
        payload, evaluation.issues, views.repair_view, stage="test", write_log=False,
    )

    assert first.stats.changed is True
    assert second.stats.changed is False
    assert payload.model_dump(mode="json") == after_first


def test_router_log_is_aggregate_only(tmp_path, monkeypatch):
    build, _, views = _build_views()
    owner = build.identities[0].experience_id
    fact_id = views.owner_scopes[owner].repair_eligible_fact_ids[0]
    payload = _payload([_bound_project(owner, (fact_id,))])
    monkeypatch.setattr(router_service, "LOG_PATH", tmp_path / "repair.jsonl")

    route_quality_repairs(
        payload, [_duplicate_issue()], views.repair_view,
        stage="test", request_id="req_v0983", attempt_id="attempt_v0983",
    )
    content = router_service.LOG_PATH.read_text(encoding="utf-8")
    row = json.loads(content)
    assert row["applied_action_count"] == 1
    assert RAW not in content
    assert "资料检索工具" not in content
    assert "FastAPI" not in content
