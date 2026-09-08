import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import fact_coverage_guard_service as coverage_service  # noqa: E402
from app.services import resume_quality_repair_router_service as router_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_projection_completeness_service import _project_fact_ids  # noqa: E402
from app.services.canonical_semantic_state_service import CanonicalFactOwnershipIndex, build_canonical_semantic_build  # noqa: E402
from app.services.experience_fact_ledger_service import ExperienceFact, ExperienceFactLedger  # noqa: E402
from app.services.experience_identity_service import ExperienceIdentity  # noqa: E402
from app.services.fact_coverage_guard_service import guard_fact_coverage  # noqa: E402
from app.services.resume_body_sanitizer_service import sanitize_resume_body  # noqa: E402
from app.services.resume_delivery_quality_gate_service import ResumeQualityIssue, validate_resume_delivery_quality  # noqa: E402
from app.services.resume_quality_repair_router_service import route_quality_repairs  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger  # noqa: E402


OWNER = "EXP-001"
FOREIGN_OWNER = "EXP-002"
LOCAL_FACT = "EXP-001-F001"
FOREIGN_FACT = "EXP-002-F001"
LOCAL_CLAIM = "EXP-001-C001"
FOREIGN_CLAIM = "EXP-002-C001"
RAW = """项目：资料检索工具
使用 FastAPI 实现资料检索接口，并完成日志记录与健康检查。"""


def _payload(project: dict) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=90,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[project]),
    )


def _project(**overrides) -> dict:
    project = {
        "name": "本地项目",
        "meta": "项目经历",
        "time": "2026.01",
        "intro": "本地项目概览",
        "role": "",
        "details": ["外部事实描述"],
        "source_experience_id": OWNER,
        "immutable_source_experience_id": OWNER,
        "source_binding_locked": True,
        "source_fact_ids": [LOCAL_FACT],
        "detail_fact_ids": [[LOCAL_FACT]],
        "source_claim_ids": [LOCAL_CLAIM],
        "detail_claim_ids": [[LOCAL_CLAIM]],
    }
    project.update(overrides)
    return project


def _fact(owner: str, fact_id: str, claim_id: str, text: str, *, importance: str = "medium") -> ExperienceFact:
    return ExperienceFact(
        experience_id=owner,
        fact_id=fact_id,
        fact_type="实现",
        fact_text=text,
        importance=importance,
        explicit=True,
        resume_ready_text=text,
        source_span=(0, len(text)),
        immutable_experience_id=owner,
        claim_id=claim_id,
    )


def _canonical_build(*, local_importance: str = "medium") -> SimpleNamespace:
    local = _fact(OWNER, LOCAL_FACT, LOCAL_CLAIM, "本地接口实现", importance=local_importance)
    foreign = _fact(FOREIGN_OWNER, FOREIGN_FACT, FOREIGN_CLAIM, "外部事实描述")
    identity = ExperienceIdentity(
        experience_id=OWNER,
        experience_type="项目经历",
        title="本地项目",
        raw_text="",
        explicit_tech_terms=[],
        explicit_metrics=[],
        evidence_terms=[],
        risk_terms=[],
        supported_inference_terms=[],
        immutable_experience_id=OWNER,
    )
    ownership = CanonicalFactOwnershipIndex(
        fact_owner_by_id={LOCAL_FACT: OWNER, FOREIGN_FACT: FOREIGN_OWNER},
        claim_owner_by_id={LOCAL_CLAIM: OWNER, FOREIGN_CLAIM: FOREIGN_OWNER},
        eligible_fact_ids_by_experience={OWNER: (LOCAL_FACT,), FOREIGN_OWNER: (FOREIGN_FACT,)},
        eligible_claim_ids_by_experience={OWNER: (LOCAL_CLAIM,), FOREIGN_OWNER: (FOREIGN_CLAIM,)},
        source_experience_ids=(OWNER, FOREIGN_OWNER),
        ownership_fingerprint="v0989",
    )
    return SimpleNamespace(
        ledger=ExperienceFactLedger(facts=[local, foreign]),
        identities=(identity,),
        ownership_index=ownership,
    )


def _cover(payload: schemas.GenerationPayload, build: SimpleNamespace, **kwargs) -> schemas.GenerationPayload:
    return guard_fact_coverage(
        payload,
        "",
        semantic_build=build,
        ownership_index=build.ownership_index,
        write_log=False,
        **kwargs,
    )


def test_canonical_coverage_never_queries_global_ledger_for_bound_detail(monkeypatch):
    build = _canonical_build()
    calls: list[tuple[str, ...]] = []
    original = coverage_service._best_fact

    def traced(text, facts):
        calls.append(tuple(fact.fact_id for fact in facts))
        return original(text, facts)

    monkeypatch.setattr(coverage_service, "_best_fact", traced)
    _cover(_payload(_project()), build)

    assert calls
    assert all(FOREIGN_FACT not in fact_ids for fact_ids in calls)


def test_router_skips_intro_role_repeat_when_role_has_no_field_binding():
    build = build_canonical_semantic_build(RAW)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    views = build_canonical_consumer_views(build, evidence)
    owner = build.identities[0].experience_id
    fact_id = views.owner_scopes[owner].repair_eligible_fact_ids[0]
    payload = _payload({
        "name": "资料检索工具",
        "meta": "项目经历",
        "time": "[待填写]",
        "intro": "实现资料检索接口。",
        "role": "实现资料检索接口。",
        "details": [],
        "source_experience_id": owner,
        "immutable_source_experience_id": owner,
        "source_binding_locked": True,
        "source_fact_ids": [fact_id],
    })
    issue = ResumeQualityIssue(
        issue_code="DUPLICATE_FACT",
        severity="critical",
        field_path="resume_sections.projects.0",
    )
    before = payload.model_dump(mode="json")

    result = route_quality_repairs(payload, [issue], views.repair_view, stage="test", write_log=False)

    assert payload.model_dump(mode="json") == before
    assert result.stats.applied_action_count == 0
    assert result.stats.insufficient_provenance_skip_count == 1


def test_removed_detail_does_not_leave_aggregate_attachment_as_coverage(monkeypatch, tmp_path):
    build = _canonical_build(local_importance="high")
    payload = _payload(_project(details=["通用描述"], detail_fact_ids=[[LOCAL_FACT]], detail_claim_ids=[[LOCAL_CLAIM]]))
    monkeypatch.setattr(coverage_service, "is_generic_detail", lambda _value: True)
    monkeypatch.setattr(coverage_service, "MAX_PROJECT_DETAILS", 0)
    monkeypatch.setattr(coverage_service, "LOG_PATH", tmp_path / "coverage.jsonl")

    result = guard_fact_coverage(
        sanitize_resume_body(payload),
        "",
        semantic_build=build,
        ownership_index=build.ownership_index,
        write_log=True,
    )
    project = result.resume_sections.projects[0]
    log = json.loads(coverage_service.LOG_PATH.read_text(encoding="utf-8"))

    assert project["details"] == []
    assert project["source_fact_ids"] == []
    assert _project_fact_ids(project) == ()
    assert log["coverage_by_experience_id"][OWNER] == 0.0
    assert LOCAL_FACT in log["missing_fact_ids"]


def test_router_removal_clears_role_fact_and_claim_rows():
    build = build_canonical_semantic_build(RAW)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    views = build_canonical_consumer_views(build, evidence)
    owner = build.identities[0].experience_id
    fact_id = views.owner_scopes[owner].repair_eligible_fact_ids[0]
    fact = next(fact for fact in build.ledger.facts if fact.fact_id == fact_id)
    payload = _payload({
        "name": "资料检索工具",
        "meta": "项目经历",
        "time": "[待填写]",
        "intro": "概览",
        "role": fact.resume_ready_text,
        "details": [fact.resume_ready_text],
        "source_experience_id": owner,
        "immutable_source_experience_id": owner,
        "source_binding_locked": True,
        "source_fact_ids": [fact_id],
        "role_source_fact_ids": [fact_id],
        "detail_fact_ids": [[fact_id]],
        "role_source_claim_ids": [fact.claim_id],
        "detail_claim_ids": [[fact.claim_id]],
    })
    issue = ResumeQualityIssue(
        issue_code="DUPLICATE_FACT",
        severity="critical",
        field_path="resume_sections.projects.0",
    )

    result = route_quality_repairs(payload, [issue], views.repair_view, stage="test", write_log=False)
    project = payload.resume_sections.projects[0]

    assert result.stats.applied_action_count == 1
    assert project["role"] == ""
    assert "role_source_fact_ids" not in project
    assert "role_source_claim_ids" not in project
    assert project["details"] == [fact.resume_ready_text]
    assert project["detail_fact_ids"] == [[fact_id]]
    assert project["detail_claim_ids"] == [[fact.claim_id]]


def test_gate_is_read_only_after_provenance_contract_cleanup():
    build = build_canonical_semantic_build(RAW)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    views = build_canonical_consumer_views(build, evidence)
    owner = build.identities[0].experience_id
    fact_id = views.owner_scopes[owner].repair_eligible_fact_ids[0]
    payload = _payload({
        "name": "资料检索工具",
        "meta": "项目经历",
        "time": "[待填写]",
        "intro": "实现资料检索接口。",
        "role": "",
        "details": [],
        "source_experience_id": owner,
        "immutable_source_experience_id": owner,
        "source_binding_locked": True,
        "source_fact_ids": [fact_id],
    })
    before = payload.model_dump(mode="json")

    validate_resume_delivery_quality(payload, consumer_views=views, skill_evidence=evidence, write_log=False)

    assert payload.model_dump(mode="json") == before
