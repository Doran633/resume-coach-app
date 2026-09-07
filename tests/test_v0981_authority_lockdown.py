import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services import resume_delivery_quality_gate_service as gate_service  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.resume_delivery_quality_gate_service import (  # noqa: E402
    evaluate_canonical_delivery_quality_issues,
    validate_resume_delivery_quality,
)
from app.services.resume_skill_evidence_aggregation_service import (  # noqa: E402
    aggregate_skill_evidence_from_ledger,
)
from app.services.semantic_mutation_trace_service import (  # noqa: E402
    SemanticMutationTracer,
    build_semantic_commit_snapshot,
)
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """项目一：课程资料助手
独立完成课程资料助手，使用 FastAPI 和 SQLite 实现资料检索问答。
增加日志和健康检查，并完成测试环境部署。

项目二：迎新志愿活动
参与新生引导和物资搬运，没有担任负责人，也没有使用 Docker。
请不要把第一个项目的技术内容写入志愿活动。"""


def _payload(projects: list[dict] | None = None, *, skills: list[str] | None = None) -> schemas.GenerationPayload:
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
            personal_info={},
            education={},
            summary=["具备项目开发与协作实践。"],
            skills=[] if skills is None else skills,
            projects=[] if projects is None else projects,
            interview_preparation=[],
        ),
    )


def _bound_projects(raw_input: str = RAW) -> tuple[object, list[dict]]:
    build = build_canonical_semantic_build(raw_input)
    projects: list[dict] = []
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
    return build, projects


def test_result_165_shape_is_reported_without_project_recovery():
    build = build_canonical_semantic_build(RAW)
    payload = _payload([])
    before = payload.model_dump()

    evaluation = validate_resume_delivery_quality(
        payload,
        semantic_build=build,
        skill_evidence=aggregate_skill_evidence_from_ledger(build.ledger),
        write_log=False,
    )

    assert payload.model_dump() == before
    assert payload.resume_sections.projects == []
    assert evaluation.stats.projects_before == 0
    assert evaluation.stats.projects_after == 0
    assert evaluation.stats.facts_recovered_count == 0
    assert evaluation.stats.unprojected_eligible_fact_count == len(build.ledger.facts)
    assert "EMPTY_VISIBLE_SECTION" in {issue.issue_code for issue in evaluation.issues}
    assert "ELIGIBLE_FACT_UNPROJECTED" in {issue.issue_code for issue in evaluation.issues}


def test_canonical_gate_never_calls_semantic_rebuild_or_recovery(monkeypatch):
    build, projects = _bound_projects()
    payload = _payload(projects)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("canonical delivery validation called a legacy semantic or recovery path")

    for name in (
        "build_experience_identities",
        "build_experience_fact_ledger",
        "_recover_projects_when_empty",
        "_repair_strong_cross_experience_terms",
        "ensure_resume_summary_quality",
        "guard_resume_skill_evidence",
        "guard_fact_coverage",
    ):
        monkeypatch.setattr(gate_service, name, forbidden)

    before = payload.model_dump()
    validate_resume_delivery_quality(
        payload,
        semantic_build=build,
        skill_evidence=aggregate_skill_evidence_from_ledger(build.ledger),
        write_log=False,
    )
    assert payload.model_dump() == before


def test_owner_type_fact_and_claim_bindings_are_immutable():
    build, projects = _bound_projects()
    projects[0]["source_claim_ids"] = list(
        build.ownership_index.eligible_claim_ids_by_experience.get(projects[0]["immutable_source_experience_id"], ())
    )
    payload = _payload(projects)
    before = payload.model_dump()

    evaluation = validate_resume_delivery_quality(
        payload,
        semantic_build=build,
        skill_evidence=aggregate_skill_evidence_from_ledger(build.ledger),
        write_log=False,
    )

    assert payload.model_dump() == before
    assert evaluation.stats.payload_changed is False
    assert evaluation.stats.fact_binding_count_before == evaluation.stats.fact_binding_count_after
    assert evaluation.stats.semantic_rebuild_attempt_count == 0
    assert evaluation.stats.validation_only is True


def test_canonical_checks_find_claim_owner_and_skill_violations_without_repair():
    build, projects = _bound_projects()
    projects[0]["details"].append("使用 PyTorch 完成模型训练。")
    projects[0]["detail_fact_ids"].append([])
    projects[0]["source_fact_ids"].append("EXP-999-F001")
    payload = _payload(projects, skills=["模型开发：PyTorch"])
    before = payload.model_dump()

    issues, _, _ = evaluate_canonical_delivery_quality_issues(
        payload,
        semantic_build=build,
        skill_evidence=aggregate_skill_evidence_from_ledger(build.ledger),
    )

    codes = {issue.issue_code for issue in issues}
    assert "UNSUPPORTED_HARD_FACT" in codes
    assert "SKILL_WITHOUT_EVIDENCE" in codes
    assert payload.model_dump() == before


def test_canonical_checks_keep_instruction_negative_uncertain_and_owner_boundaries_visible():
    raw = """项目一：知识库助手
使用 FastAPI 实现检索接口。
没有使用 Docker。
框架可能是 Flask，我记不清。
请不要把这些不确定内容写进简历。

项目二：志愿活动
参与新生引导和物资整理。"""
    build, projects = _bound_projects(raw)
    first_owner = projects[0]["immutable_source_experience_id"]
    second_owner = projects[1]["immutable_source_experience_id"]
    foreign_fact_id = build.ownership_index.eligible_fact_ids_by_experience[second_owner][0]
    projects[0]["details"].extend([
        "使用 Docker 完成容器化部署。",
        "使用 Flask 搭建后端服务。",
        "请不要把这些不确定内容写进简历。",
    ])
    projects[0]["detail_fact_ids"].extend([[], [], [foreign_fact_id]])
    projects[0]["source_fact_ids"].append(foreign_fact_id)
    payload = _payload(projects)
    before = payload.model_dump()

    issues, _, _ = evaluate_canonical_delivery_quality_issues(
        payload,
        semantic_build=build,
        skill_evidence=aggregate_skill_evidence_from_ledger(build.ledger),
    )

    codes = {issue.issue_code for issue in issues}
    assert "USER_CONSTRAINT_RENDERED" in codes
    assert "DENIED_CLAIM_ASSERTED" in codes
    assert "UNCERTAIN_CLAIM_ASSERTED" in codes
    assert "PROVENANCE_CONFLICT" in codes
    assert first_owner != second_owner
    assert payload.model_dump() == before


def test_delivery_gate_trace_has_validation_only_checkpoints():
    build, projects = _bound_projects()
    payload = _payload(projects)
    stages: list[str] = []

    class Trace:
        def checkpoint(self, value, stage, *, parent_stage):
            assert value is payload
            assert parent_stage == "delivery_quality_gate"
            stages.append(stage)

    validate_resume_delivery_quality(
        payload,
        semantic_build=build,
        skill_evidence=aggregate_skill_evidence_from_ledger(build.ledger),
        write_log=False,
        mutation_tracer=Trace(),
    )
    assert stages == ["delivery_gate.enter", "delivery_gate.evaluated", "delivery_gate.exit"]


def test_delivery_gate_trace_creates_no_experience_or_owner_mutation():
    build, projects = _bound_projects()
    payload = _payload(projects)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    trace = SemanticMutationTracer(
        build=build,
        snapshot=build_semantic_commit_snapshot(build, evidence),
        request_id="req_v0981_trace",
        attempt_id="attempt_v0981_trace",
    )
    trace.checkpoint(payload, "before_delivery_gate", parent_stage="test")

    validate_resume_delivery_quality(
        payload,
        semantic_build=build,
        skill_evidence=evidence,
        write_log=False,
        mutation_tracer=trace,
    )

    gate_mutations = [
        event
        for event in trace.events
        if event.get("event_type") == "mutation"
        and str(event.get("stage", "")).startswith("delivery_gate.")
    ]
    assert not any(
        event.get("mutation_code") in {"NEW_EXPERIENCE", "OWNER_CHANGED", "FACT_BINDING_DROPPED"}
        for event in gate_mutations
    )


def test_canonical_gate_log_is_aggregate_only(tmp_path, monkeypatch):
    build, projects = _bound_projects()
    payload = _payload(projects)
    log_path = tmp_path / "delivery.jsonl"
    monkeypatch.setattr(gate_service, "LOG_PATH", log_path)

    validate_resume_delivery_quality(
        payload,
        semantic_build=build,
        skill_evidence=aggregate_skill_evidence_from_ledger(build.ledger),
        stage="test",
    )

    content = log_path.read_text(encoding="utf-8")
    record = json.loads(content)
    assert record["validation_only"] is True
    assert record["payload_changed"] is False
    assert record["semantic_rebuild_attempt_count"] == 0
    assert RAW not in content
    assert "课程资料助手" not in content
    assert "FastAPI" not in content
    assert "迎新志愿活动" not in content


def test_create_generation_uses_canonical_validation_not_legacy_gate(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    calls = {"canonical": 0}
    real_validate = generation_service.validate_resume_delivery_quality

    def canonical_validate(payload, **kwargs):
        before = payload.model_dump()
        result = real_validate(payload, write_log=False, **kwargs)
        assert payload.model_dump() == before
        calls["canonical"] += 1
        return result

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy delivery gate or semantic rebuild was reached")

    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(generation_service, "LOG_DIR", tmp_path)
    monkeypatch.setattr(generation_service, "validate_resume_delivery_quality", canonical_validate)
    monkeypatch.setattr(gate_service, "ensure_resume_delivery_quality", forbidden)
    monkeypatch.setattr(gate_service, "build_experience_identities", forbidden)
    monkeypatch.setattr(gate_service, "build_experience_fact_ledger", forbidden)
    try:
        response = generation_service.create_generation(
            db,
            schemas.GenerateRequest(
                anonymous_user_id="anon-v0981",
                session_id="session-v0981",
                target_role="后端开发",
                mode="full_resume",
                packaging_level="稳妥",
                experience_type="项目经历",
                raw_input="项目经历：资料检索工具\n使用 FastAPI 实现资料检索接口，并完成日志记录。",
                attempt_id="attempt_v0981_authority",
            ),
            request_id="req_v0981_authority",
        )
        stored = db.get(models.GenerationResult, response.generation_result_id)
        assert stored is not None
        assert calls["canonical"] == 2
    finally:
        db.close()
