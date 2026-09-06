import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services import canonical_consumer_view_service as view_service  # noqa: E402
from app.services.canonical_consumer_view_service import (  # noqa: E402
    CanonicalConsumerViewAccessStats,
    build_canonical_consumer_views,
)
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.resume_delivery_quality_gate_service import (  # noqa: E402
    evaluate_canonical_delivery_quality_issues,
    validate_resume_delivery_quality,
)
from app.services.resume_skill_evidence_aggregation_service import (  # noqa: E402
    aggregate_skill_evidence_from_ledger,
)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """项目一：课程资料助手
使用 FastAPI 实现资料检索接口，并完成日志记录。
没有使用 Docker。
框架可能是 Flask，我记不清。
请不要把不确定内容写进简历。

项目二：迎新志愿活动
参与新生引导和物资整理。"""


def _build_and_views():
    build = build_canonical_semantic_build(RAW)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    return build, evidence, build_canonical_consumer_views(build, evidence)


def _payload(build):
    projects = []
    for identity in build.identities:
        facts = list(build.ledger.for_experience(identity.experience_id))
        details = [fact.resume_ready_text for fact in facts if fact.resume_ready_text]
        fact_ids = [fact.fact_id for fact in facts if fact.resume_ready_text]
        projects.append({
            "name": identity.title,
            "meta": build.canonical_type_by_experience_id[identity.experience_id].canonical_experience_type,
            "time": "[待填写]",
            "intro": details[0] if details else "参与对应经历。",
            "role": "",
            "details": details,
            "source_experience_id": identity.experience_id,
            "immutable_source_experience_id": identity.experience_id,
            "source_binding_locked": True,
            "source_fact_ids": fact_ids,
            "detail_fact_ids": [[fact_id] for fact_id in fact_ids],
        })
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


def test_views_share_one_build_and_fingerprint_without_mutating_it():
    build, evidence, first = _build_and_views()
    second = build_canonical_consumer_views(build, evidence)
    before = (
        tuple(build.ownership_index.fact_owner_by_id.items()),
        tuple(build.ownership_index.claim_owner_by_id.items()),
    )

    assert first.build_fingerprint == second.build_fingerprint
    assert first.planner_view.fingerprint == first.guard_view.fingerprint == first.repair_view.fingerprint
    assert first._build is build
    assert first.planner_view.canonical_identity(build.identities[0].experience_id) == build.identities[0].experience_id
    assert first.planner_view.verified_skill_evidence_keys == first.verified_skill_evidence_keys
    assert before == (
        tuple(build.ownership_index.fact_owner_by_id.items()),
        tuple(build.ownership_index.claim_owner_by_id.items()),
    )


def test_owner_scopes_reject_cross_owner_fact_and_claim_access():
    build, _, views = _build_and_views()
    first, second = (identity.experience_id for identity in build.identities)
    foreign_fact_id = views.owner_scopes[second].eligible_fact_ids[0]
    foreign_claim_id = views.owner_scopes[second].eligible_claim_ids[0]
    stats = CanonicalConsumerViewAccessStats()

    assert views.guard_view.eligible_facts(first)
    assert all(fact.experience_id == first for fact in views.guard_view.eligible_facts(first))
    assert not views.guard_view.permits_fact(first, foreign_fact_id, access_stats=stats)
    assert not views.guard_view.permits_claim(first, foreign_claim_id, access_stats=stats)
    assert stats.rejected_cross_owner_access_count == 2
    assert foreign_fact_id in views.guard_view.unprojected_eligible_fact_ids(set())


def test_repair_scope_excludes_withheld_negative_uncertain_and_planned_claims():
    build, _, views = _build_and_views()
    first_owner = build.identities[0].experience_id
    scope = views.owner_scopes[first_owner]
    repair_facts = views.repair_view.eligible_facts(first_owner)

    assert scope.withheld_claim_ids or scope.excluded_claim_ids
    assert set(scope.repair_eligible_fact_ids).issubset(scope.eligible_fact_ids)
    assert {fact.fact_id for fact in repair_facts} == set(scope.repair_eligible_fact_ids)
    assert all(
        fact.claim_id not in set(scope.withheld_claim_ids) | set(scope.excluded_claim_ids)
        for fact in repair_facts
    )


def test_view_public_projection_and_log_do_not_expose_resume_text(tmp_path, monkeypatch):
    _, _, views = _build_and_views()
    monkeypatch.setattr(view_service, "LOG_PATH", tmp_path / "views.jsonl")

    view_service.write_canonical_consumer_views_log(
        views,
        stage="test",
        request_id="req_v0982_test",
        attempt_id="attempt_v0982_test",
    )
    content = view_service.LOG_PATH.read_text(encoding="utf-8")
    assert RAW not in repr(views)
    assert "课程资料助手" not in repr(views)
    assert "FastAPI" not in content
    assert "迎新志愿活动" not in content
    row = json.loads(content)
    assert row["experience_count"] == 2
    assert row["eligible_fact_count"] >= 1


def test_guard_view_preserves_validation_only_delivery_gate_behavior():
    build, evidence, views = _build_and_views()
    payload = _payload(build)
    before = payload.model_dump(mode="json")
    issues_from_view, coverage_from_view, _ = evaluate_canonical_delivery_quality_issues(
        payload,
        consumer_views=views,
        skill_evidence=evidence,
    )
    issues_from_legacy, coverage_from_legacy, _ = evaluate_canonical_delivery_quality_issues(
        payload,
        semantic_build=build,
        skill_evidence=evidence,
    )
    evaluation = validate_resume_delivery_quality(
        payload,
        consumer_views=views,
        skill_evidence=evidence,
        write_log=False,
    )

    assert payload.model_dump(mode="json") == before
    assert coverage_from_view == coverage_from_legacy
    assert {issue.issue_code for issue in issues_from_view} == {
        issue.issue_code for issue in issues_from_legacy
    }
    assert evaluation.stats.validation_only is True
    assert evaluation.stats.payload_changed is False


def test_generation_builds_one_consumer_view_and_passes_it_to_delivery_gate(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    calls = {"views": 0, "gate_views": 0}
    real_build_views = generation_service.build_canonical_consumer_views
    real_validate = generation_service.validate_resume_delivery_quality

    def capture_views(*args, **kwargs):
        calls["views"] += 1
        return real_build_views(*args, **kwargs)

    def capture_gate(payload, **kwargs):
        assert kwargs.get("consumer_views") is not None
        calls["gate_views"] += 1
        return real_validate(payload, write_log=False, **kwargs)

    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(generation_service, "LOG_DIR", tmp_path)
    monkeypatch.setattr(generation_service, "build_canonical_consumer_views", capture_views)
    monkeypatch.setattr(generation_service, "validate_resume_delivery_quality", capture_gate)
    try:
        response = generation_service.create_generation(
            db,
            schemas.GenerateRequest(
                anonymous_user_id="anon-v0982",
                session_id="session-v0982",
                target_role="后端开发",
                mode="full_resume",
                packaging_level="稳妥",
                experience_type="项目经历",
                raw_input="项目经历：资料检索工具\n使用 FastAPI 实现资料检索接口，并完成日志记录。",
                attempt_id="attempt_v0982_view",
            ),
            request_id="req_v0982_view",
        )
        assert db.get(models.GenerationResult, response.generation_result_id) is not None
        assert calls == {"views": 1, "gate_views": 1}
    finally:
        db.close()
