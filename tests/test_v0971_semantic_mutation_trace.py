import json

from app import schemas
from app.database import Base
from app.services import generation_service
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger
from app.services.resume_delivery_quality_gate_service import ensure_resume_delivery_quality
from app.services.semantic_mutation_trace_service import (
    SemanticMutationTracer,
    build_semantic_commit_snapshot,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


RAW = """项目一：知识库问答系统\n使用 FastAPI 开发问答接口，完成 120 条测试集验证。\n\n项目二：校园志愿活动\n参与迎新引导，不涉及技术开发。\n请不要为了让简历更丰富给项目二编技术内容。"""


def payload():
    return schemas.GenerationPayload.model_validate({
        "completeness_score": 80,
        "confirmed_facts": [], "missing_questions": [],
        "normal_version": "", "bold_version": "", "boundary_version": "", "recommended_version": "",
        "claims": [], "interview_plan": [], "knowledge_checklist": [],
        "resume_sections": {"summary": ["项目开发经历"], "skills": ["技能证据：FastAPI"], "projects": [
            {"name": "知识库问答系统", "meta": "项目经历", "source_experience_id": "EXP-001",
             "source_fact_ids": ["EXP-001-F001"], "details": ["使用 FastAPI 开发问答接口"],
             "detail_fact_ids": [["EXP-001-F001"]]},
        ]},
    })


def tracer():
    build = build_canonical_semantic_build(RAW)
    snapshot = build_semantic_commit_snapshot(build, aggregate_skill_evidence_from_ledger(build.ledger))
    return SemanticMutationTracer(build=build, snapshot=snapshot, request_id="req_trace_test", attempt_id="attempt_trace_test")


def mutation_codes(trace):
    return {event["mutation_code"] for event in trace.events if event["event_type"] == "mutation"}


def test_trace_observes_without_changing_payload():
    value = payload()
    before = value.model_dump_json()
    trace = tracer()
    trace.checkpoint(value, "after_owner_freeze")
    assert value.model_dump_json() == before
    assert trace.events


def test_trace_detects_owner_foreign_fact_skill_and_instruction():
    value = payload()
    project = value.resume_sections.projects[0]
    project["source_experience_id"] = "EXP-002"
    project["detail_fact_ids"] = [["EXP-001-F001"]]
    project["details"] = ["请不要为了让简历更丰富给项目二编技术内容。"]
    value.resume_sections.skills = ["技能证据：Docker"]
    trace = tracer()
    trace.checkpoint(value, "after_delivery_gate")
    codes = mutation_codes(trace)
    assert "FOREIGN_FACT_VISIBLE" in codes
    assert "WITHHELD_OR_NEGATIVE_CLAIM_VISIBLE" in codes
    assert "SKILL_WITHOUT_CANONICAL_EVIDENCE" in codes


def test_trace_detects_owner_change_after_commit():
    value = payload()
    trace = tracer()
    trace.checkpoint(value, "after_owner_freeze")
    value.resume_sections.projects[0]["source_experience_id"] = "EXP-002"
    trace.checkpoint(value, "after_reconciliation")
    assert "OWNER_CHANGED" in mutation_codes(trace)


def test_same_owner_rewrite_is_observe_only():
    value = payload()
    trace = tracer()
    trace.checkpoint(value, "after_owner_freeze")
    value.resume_sections.projects[0]["details"] = ["完成 FastAPI 问答接口开发"]
    trace.checkpoint(value, "after_professionalization")
    codes = mutation_codes(trace)
    assert "SUPPORTED_PRESENTATION_REWRITE" in codes
    assert "FOREIGN_FACT_VISIBLE" not in codes


def test_trace_log_contains_no_visible_text(tmp_path, monkeypatch):
    from app.services import semantic_mutation_trace_service as service

    monkeypatch.setattr(service, "LOG_PATH", tmp_path / "trace.jsonl")
    trace = tracer()
    trace.checkpoint(payload(), "after_owner_freeze")
    trace.flush(99)
    text = service.LOG_PATH.read_text(encoding="utf-8")
    assert "FastAPI" not in text
    assert "知识库" not in text
    assert "请不要" not in text
    assert json.loads(text.splitlines()[0])["generation_result_id"] == 99


def test_delivery_gate_emits_internal_trace_checkpoints():
    stages = []

    class Trace:
        def checkpoint(self, value, stage, *, parent_stage):
            assert isinstance(value, schemas.GenerationPayload)
            assert parent_stage == "delivery_quality_gate"
            stages.append(stage)

    ensure_resume_delivery_quality(payload(), RAW, stage="test", write_log=False, mutation_tracer=Trace())
    assert stages == [
        "delivery_gate.enter",
        "delivery_gate.after_semantic_role_cleanup",
        "delivery_gate.after_hard_fact_guard",
        "delivery_gate.after_cross_experience_repair",
        "delivery_gate.after_validity_check",
        "delivery_gate.after_project_recovery",
        "delivery_gate.after_summary_recovery",
        "delivery_gate.after_skill_recovery",
        "delivery_gate.after_coverage_recovery",
        "delivery_gate.exit",
    ]


def test_generation_payload_is_identical_when_observer_is_replaced(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(generation_service, "LOG_DIR", tmp_path)
    request = schemas.GenerateRequest(
        anonymous_user_id="anon-v0971", session_id="session-v0971", target_role="后端开发",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW,
        attempt_id="attempt_v0971_observer",
    )
    observed = generation_service.create_generation(db, request, request_id="req_v0971_observer")

    class NoopTracer:
        def __init__(self, **_kwargs):
            pass

        def checkpoint(self, *_args, **_kwargs):
            pass

        def flush(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(generation_service, "SemanticMutationTracer", NoopTracer)
    baseline = generation_service.create_generation(db, request, request_id="req_v0971_baseline")
    assert observed.result.model_dump() == baseline.result.model_dump()
    db.close()
