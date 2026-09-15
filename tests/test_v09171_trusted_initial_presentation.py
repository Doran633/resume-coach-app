"""Actual inputs and controlled returns, not historical response snapshots."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from test_v09162_model_output_evidence_contract import CASES, ATTACHMENTS, controlled_return, real_receiver, request, reference_return
from app import models
from app.database import Base
from app.services import generation_service as generation
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.llm_service import LLMResult
from app import schemas
from app.services import prompt_service
from app.services import experience_slot_service as slots
from test_v0916_canonical_model_evidence import evidence, declared_network_return, SAMPLES, FULL, ECOMMERCE, MULTI_TYPE


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_MODE", "openai")
    monkeypatch.setenv("MAX_LLM_CALLS_PER_ATTEMPT", "2")
    monkeypatch.setattr(generation.resource_protection, "check_daily_budget", lambda: SimpleNamespace(allowed=True))
    monkeypatch.setattr(generation.resource_protection, "record_llm_usage", lambda **kw: None)
    for module in tuple(sys.modules.values()):
        if not getattr(module, "__name__", "").startswith("app.services."):
            continue
        for key in ("LOG_DIR", "LOG_PATH", "OWNER_DELIVERY_CONTRACT_LOG_PATH"):
            value = getattr(module, key, None)
            if isinstance(value, Path):
                monkeypatch.setattr(module, key, tmp_path if key == "LOG_DIR" else tmp_path / value.name)
    return tmp_path


def network(monkeypatch, replies):
    sent = []
    def call(prompt):
        reply = replies[min(len(sent), len(replies) - 1)]
        sent.append(prompt)
        return LLMResult(text=reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False), model="controlled", latency_ms=0)
    monkeypatch.setattr(generation, "call_openai", call)
    return sent


def altered(data, kind):
    data = deepcopy(data)
    project = data["resume_sections"]["projects"][0]
    if kind == "missing":
        for item in data["resume_sections"]["projects"]:
            for key in ATTACHMENTS:
                item.pop(key, None)
    elif kind == "missing_owner":
        project.pop("source_experience_id")
    elif kind == "foreign_owner":
        project["source_experience_id"] = "EXP-999"
    elif kind == "bad_id":
        project["detail_fact_ids"][0] = ["EXP-999-F001"]
    elif kind == "bad_lineage":
        project["detail_claim_ids"][0] = project["intro_source_claim_ids"]
    elif kind == "rewrite":
        project["details"][0] = "Independently designed all databases and deployed production"
    elif kind == "empty_projects":
        data["resume_sections"]["projects"] = []
    elif kind == "missing_body":
        project.pop("intro")
    elif kind == "wrong_body_type":
        project["details"][0] = {"text": project["details"][0]}
    elif kind == "extra_source_row":
        project["detail_fact_ids"].append(project["intro_source_fact_ids"])
        project["detail_claim_ids"].append(project["intro_source_claim_ids"])
    elif kind == "blank_row_bad_reference":
        project["details"].insert(0, " ")
        project["detail_fact_ids"].insert(0, ["EXP-999-F001"])
        project["detail_claim_ids"].insert(0, ["EXP-999-C001"])
    else:
        raise AssertionError(kind)
    return data


@pytest.mark.parametrize("case", CASES, ids=lambda c: str(c["result_id"]))
@pytest.mark.parametrize("kind", ["missing", "missing_owner", "foreign_owner", "bad_id", "bad_lineage", "rewrite", "empty_projects", "missing_body", "wrong_body_type", "extra_source_row", "blank_row_bad_reference"])
def test_contract_failure_is_not_success_or_json_fallback(case, kind, monkeypatch, isolated):
    build, data = controlled_return(case)
    views = build_canonical_consumer_views(build)
    before_build = deepcopy(build)
    bad = altered(data, kind)
    before = deepcopy(bad)
    sent = network(monkeypatch, [bad])
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=views)
    assert caught.value.code.startswith("MODEL_EVIDENCE_")
    assert "JSON validation failed" not in str(caught.value)
    assert len(sent) == 2
    assert bad == before
    assert build == before_build


@pytest.mark.parametrize("case", CASES, ids=lambda c: str(c["result_id"]))
def test_failure_never_reaches_projection_or_persistence(case, monkeypatch, isolated):
    _, data = controlled_return(case)
    network(monkeypatch, [altered(data, "missing")])
    calls = []
    for name in ("build_stable_generation_fallback", "bind_projects_to_experience_slots", "plan_canonical_project_projections"):
        original = getattr(generation, name)
        def spy(*a, _fn=original, _name=name, **kw):
            calls.append(_name)
            return _fn(*a, **kw)
        monkeypatch.setattr(generation, name, spy)
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            with pytest.raises(generation.GenerationServiceError):
                generation.create_generation(db, request(case), request_id="req_v09171_failed")
            assert db.scalar(select(func.count()).select_from(models.GenerationResult)) == 0
            assert calls == []
    finally:
        engine.dispose()


@pytest.mark.parametrize("case", CASES, ids=lambda c: str(c["result_id"]))
def test_supported_response_reaches_real_save_and_docx(case, monkeypatch, tmp_path, isolated):
    build, data = controlled_return(case)
    before = deepcopy(data)
    captured = real_receiver(case, reference_return(data), monkeypatch, tmp_path, deliver=True)
    expected = {p["source_experience_id"]: p for p in data["resume_sections"]["projects"]}
    for project in captured["payload"].resume_sections.projects:
        original = expected[project["source_experience_id"]]
        for key in ATTACHMENTS:
            assert project.get(key) == original[key]
    assert len(captured["saved"]["resume_sections"]["projects"]) == len(build.identities)
    assert data == before
    assert not captured["plan"].detail_skip_counts


def output_contract(prompt):
    return json.JSONDecoder().raw_decode(prompt.split("<canonical_model_output_contract>\n", 1)[1])[0]


@pytest.mark.parametrize("long_mode", [False, True])
@pytest.mark.parametrize("case", CASES, ids=lambda c: str(c["result_id"]))
def test_retry_uses_identical_evidence_protocol_and_one_preparation(case, long_mode, monkeypatch, isolated):
    build, data = controlled_return(case)
    before = deepcopy(build)
    views = build_canonical_consumer_views(build)
    def forbidden(*a, **kw):
        raise AssertionError("Semantic rebuild during model preparation")
    for name in ("build_experience_identities", "split_experience_segments", "build_experience_fact_ledger",
                 "build_segmentation_questions", "build_experience_context", "build_experience_identity_context",
                 "build_fact_ledger_context"):
        monkeypatch.setattr(prompt_service, name, forbidden)
    monkeypatch.setattr(generation, "build_canonical_semantic_build", forbidden)
    original = generation.build_generation_prompt
    prepared = []
    def prepare(*a, **kw):
        prepared.append(1)
        return original(*a, **kw)
    monkeypatch.setattr(generation, "build_generation_prompt", prepare)
    sent = network(monkeypatch, [altered(data, "missing"), reference_return(data)])
    payload, log = generation.build_llm_generation(
        request(case), replace(build.long_input_context, long_input_mode=long_mode), consumer_views=views,
        request_id="req_v09171_retry",
    )
    assert log["attempt"] == len(sent) == 2 and len(prepared) == 1
    assert evidence(sent[0]) == evidence(sent[1])
    assert output_contract(sent[0]) == output_contract(sent[1])
    assert output_contract(sent[0])["field_references"] == {
        "intro": ["intro_source_fact_ids"],
        "role": ["role_source_fact_ids"],
        "details": ["detail_fact_ids"],
    }
    assert build == before
    assert payload.resume_sections.projects[0]["detail_fact_ids"] == data["resume_sections"]["projects"][0]["detail_fact_ids"]


@pytest.mark.parametrize("first,last", [("missing", "not json"), ("rewrite", "not json"), ("missing", "missing")])
def test_contract_failure_cannot_escape_through_later_parse_failure(first, last, monkeypatch, isolated):
    build, data = controlled_return(CASES[0])
    sent = network(monkeypatch, [altered(data, first), last if last == "not json" else altered(data, last)])
    with pytest.raises(generation.GenerationServiceError, match="MODEL_EVIDENCE_"):
        generation.build_llm_generation(request(CASES[0]), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert len(sent) == 2


@pytest.mark.parametrize("kind", ["bad_id", "bad_lineage", "rewrite"])
def test_invalid_evidence_is_not_hidden_by_an_unrelated_schema_error(kind, monkeypatch, isolated):
    build, data = controlled_return(CASES[0])
    data = altered(data, kind)
    data["completeness_score"] = "invalid-integer"
    network(monkeypatch, [data])
    with pytest.raises(generation.GenerationServiceError, match="MODEL_EVIDENCE_"):
        generation.build_llm_generation(request(CASES[0]), build.long_input_context, consumer_views=build_canonical_consumer_views(build))


def test_legacy_optional_sources_and_parse_failure_compatibility(monkeypatch, isolated):
    build, data = controlled_return(CASES[0])
    sent = network(monkeypatch, [altered(data, "missing")])
    payload, _ = generation.build_llm_generation(request(CASES[0]), build.long_input_context)
    assert payload.resume_sections.projects and len(sent) == 1
    network(monkeypatch, ["not json"])
    with pytest.raises(generation.GenerationServiceError, match="JSON validation failed"):
        generation.build_llm_generation(request(CASES[0]), build.long_input_context, consumer_views=build_canonical_consumer_views(build))


@pytest.mark.parametrize("limit", [1, 2, 9])
def test_contract_retries_respect_existing_call_limit(limit, monkeypatch, isolated):
    build, data = controlled_return(CASES[0])
    monkeypatch.setenv("MAX_LLM_CALLS_PER_ATTEMPT", str(limit))
    sent = network(monkeypatch, [altered(data, "missing")])
    with pytest.raises(generation.GenerationServiceError):
        generation.build_llm_generation(request(CASES[0]), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert len(sent) == min(limit, 2)


def test_blank_rows_and_multifact_rows_preserve_exact_lineage(monkeypatch, isolated):
    build, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    project["details"][0:2] = ["；".join(text.rstrip("。；;") for text in project["details"][:2])]
    for key in ("detail_fact_ids", "detail_claim_ids"):
        project[key][0:2] = [list(dict.fromkeys(sum(project[key][:2], [])))]
    expected = deepcopy(project)
    project["details"].insert(0, " \n")
    project["detail_fact_ids"].insert(0, [])
    project["detail_claim_ids"].insert(0, [])
    before = deepcopy(data)
    network(monkeypatch, [reference_return(data)])
    payload, _ = generation.build_llm_generation(request(CASES[0]), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    current = payload.resume_sections.projects[0]
    for key in ("details", "detail_fact_ids", "detail_claim_ids"):
        assert current[key] == expected[key]
    assert data == before


@pytest.mark.parametrize("kind", ["forged", "cross_owner", "excluded", "same_text_other_fact", "same_numbers", "aggregate_only"])
def test_declarations_are_not_backend_proof(kind, monkeypatch, isolated):
    build, data = controlled_return(CASES[0])
    project, other = data["resume_sections"]["projects"]
    if kind == "forged":
        for key in ATTACHMENTS:
            project.pop(key, None)
        project.update(source_binding_locked=True, immutable_source_experience_id="EXP-001", source_binding_origin="canonical")
    elif kind == "cross_owner":
        project["detail_fact_ids"][0] = other["detail_fact_ids"][0]
        project["detail_claim_ids"][0] = other["detail_claim_ids"][0]
        project["details"][0] = other["details"][0]
    elif kind == "excluded":
        claim = next(c for c in build.ledger.excluded_claims if c.source_experience_id == "EXP-001")
        project["detail_claim_ids"][0] = [claim.claim_id]
        project["details"][0] = claim.text
    elif kind == "same_text_other_fact":
        project["detail_fact_ids"][0] = project["intro_source_fact_ids"]
        project["detail_claim_ids"][0] = project["intro_source_claim_ids"]
    elif kind == "same_numbers":
        project["details"][0] += "，独立主导整体生产架构"
    else:
        project.pop("intro_source_fact_ids")
        project.pop("intro_source_claim_ids")
    network(monkeypatch, [data])
    with pytest.raises(generation.GenerationServiceError, match="MODEL_EVIDENCE_"):
        generation.build_llm_generation(request(CASES[0]), build.long_input_context, consumer_views=build_canonical_consumer_views(build))


def test_partial_invalid_return_preserves_valid_fields_without_cross_attempt_merge(monkeypatch, isolated):
    build, data = controlled_return(CASES[0])
    bad = altered(data, "rewrite")
    before = deepcopy(bad)
    payload = schemas.GenerationPayload.model_validate(bad)
    views = build_canonical_consumer_views(build)
    retained = slots.validate_model_project_evidence(payload, views, write_log=False)
    original = data["resume_sections"]["projects"][0]
    assert retained.resume_sections.projects[0]["intro_source_fact_ids"] == original["intro_source_fact_ids"]
    assert retained.resume_sections.projects[0]["role_source_fact_ids"] == original["role_source_fact_ids"]
    assert retained.resume_sections.projects[0]["details"] == bad["resume_sections"]["projects"][0]["details"]
    sent = network(monkeypatch, [bad, reference_return(data)])
    result, _ = generation.build_llm_generation(request(CASES[0]), build.long_input_context, consumer_views=views)
    assert len(sent) == 2 and bad == before
    assert result.resume_sections.projects[0]["details"] == original["details"]


def test_contract_failure_logs_only_codes_counts_and_request_correlation(monkeypatch, isolated):
    build, data = controlled_return(CASES[0])
    data["resume_sections"]["projects"][0]["details"][0] = "Private-return-body-must-never-be-logged"
    sent = network(monkeypatch, [data])
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(CASES[0]), build.long_input_context,
                                        consumer_views=build_canonical_consumer_views(build), request_id="req_v09171_private")
    # Free-text projects now fail format validation before body verification.
    assert caught.value.code == "MODEL_EVIDENCE_FORMAT"
    text = slots.LOG_PATH.read_text(encoding="utf-8")
    rows = [json.loads(line) for line in text.splitlines()]
    assert len(rows) == 2
    assert {r["model_attempt"] for r in rows} == {1, 2}
    assert all(r["request_id"] == "req_v09171_private" and r["attempt_id"] == request(CASES[0]).attempt_id for r in rows)
    assert all(r["contract_passed"] is False and r["verified_field_count"] == 0 for r in rows)
    assert all("format_forbidden_project_fields" in r["evidence_reason_counts"] for r in rows)
    for project in data["resume_sections"]["projects"]:
        for value in [project["name"], project["intro"], project["role"], *project["details"]]:
            assert value not in text
    assert "Private-return-body" not in sent[-1]
    assert "Private-return-body" not in str(caught.value)


@pytest.mark.parametrize("raw", [*SAMPLES.values(), FULL, *ECOMMERCE.values(), *MULTI_TYPE.values()])
def test_full_inputs_use_actual_sent_evidence_for_controlled_response(raw, monkeypatch, isolated):
    from app.services.canonical_semantic_state_service import build_canonical_semantic_build
    build = build_canonical_semantic_build(raw)
    before = deepcopy(build)
    case = dict(CASES[0], raw_input=raw)
    sent = []
    def call(prompt):
        sent.append(prompt)
        return LLMResult(text=declared_network_return(request(case), prompt), model="controlled-protocol", latency_ms=0)
    monkeypatch.setattr(generation, "call_openai", call)
    result, _ = generation.build_llm_generation(request(case), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert len(sent) == 1 and build == before
    for project in result.resume_sections.projects:
        facts = {f.fact_id: f for f in build.ledger.for_experience(project["source_experience_id"])}
        assert set(project["source_fact_ids"]) == set(facts)
        assert set(project["source_claim_ids"]) == {f.claim_id for f in facts.values()}
