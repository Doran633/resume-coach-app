"""Actual request inputs; controlled returns are NOT historical model snapshots."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import schemas, models
from app.database import Base
from app.services import generation_service as generation
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.experience_slot_service import bind_projects_to_experience_slots, validate_model_project_evidence, provenance_text_unchanged
from app.services.fact_guard_service import guard_hard_facts
from app.services import docx_service
from app.services.result_cleanup_service import cleanup_generation_payload
from app.services.llm_service import LLMResult
from app.services.resume_body_sanitizer_service import sanitize_resume_body

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "v09162_request_inputs.json").read_text(encoding="utf-8")
)["requests"]
ATTACHMENTS = (
    "source_fact_ids", "source_claim_ids", "intro_source_fact_ids", "intro_source_claim_ids",
    "role_source_fact_ids", "role_source_claim_ids", "detail_fact_ids", "detail_claim_ids",
)


def request(case):
    return schemas.GenerateRequest(
        anonymous_user_id="v09162", session_id="v09162", attempt_id="v09162-controlled",
        target_role=case["target_role"], mode=case["mode"], packaging_level=case["packaging_level"],
        experience_type="综合经历", raw_input=case["raw_input"],
    )


def controlled_return(case):
    build = build_canonical_semantic_build(case["raw_input"])
    data = generation.build_mock_generation(request(case)).model_dump()
    projects = []
    for identity in build.identities:
        facts = list(build.ledger.for_experience(identity.experience_id))
        projects.append({
            "name": identity.title, "meta": identity.experience_type, "time": "[待填写]",
            "source_experience_id": identity.experience_id,
            "intro": facts[0].resume_ready_text, "role": facts[1].resume_ready_text,
            "details": [fact.resume_ready_text for fact in facts[2:]],
            "source_fact_ids": [fact.fact_id for fact in facts],
            "source_claim_ids": list(dict.fromkeys(fact.claim_id for fact in facts)),
            "intro_source_fact_ids": [facts[0].fact_id],
            "intro_source_claim_ids": [facts[0].claim_id],
            "role_source_fact_ids": [facts[1].fact_id],
            "role_source_claim_ids": [facts[1].claim_id],
            "detail_fact_ids": [[fact.fact_id] for fact in facts[2:]],
            "detail_claim_ids": [[fact.claim_id] for fact in facts[2:]],
        })
    data["resume_sections"]["projects"] = projects
    return build, data


@pytest.mark.parametrize("case", CASES, ids=lambda x: str(x["result_id"]))
def test_normalization_retains_candidate_rows_but_never_model_freeze(case):
    _, data = controlled_return(case)
    data["resume_sections"]["projects"][0].update(
        immutable_source_experience_id="EXP-999", source_binding_locked=True,
        canonical_projection_candidate=True, type_locked=True,
    )
    before = deepcopy(data)
    result = generation.normalize_llm_payload(data)
    assert data == before
    for original, project in zip(before["resume_sections"]["projects"], result["resume_sections"]["projects"]):
        for key in ATTACHMENTS:
            assert project.get(key) == original[key]
        assert not project.get("source_binding_locked")
        assert not project.get("immutable_source_experience_id")
        assert not project.get("canonical_projection_candidate")
        assert not project.get("type_locked")


def test_normalization_filters_text_and_attachment_rows_by_original_index():
    _, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    project["details"].insert(0, "  ")
    project["detail_fact_ids"].insert(0, ["EXP-999-F001"])
    project["detail_claim_ids"].insert(0, ["EXP-999-C001"])
    before = deepcopy(project)
    output = generation.normalize_llm_payload(deepcopy(data))["resume_sections"]["projects"][0]
    assert output["details"] == before["details"][1:]
    assert output.get("detail_fact_ids") == before["detail_fact_ids"][1:]
    assert output.get("detail_claim_ids") == before["detail_claim_ids"][1:]


@pytest.mark.parametrize("case", CASES, ids=lambda x: str(x["result_id"]))
def test_hard_guard_keeps_unchanged_field_lineage(case):
    _, data = controlled_return(case)
    payload = schemas.GenerationPayload.model_validate(data)
    before = payload.model_copy(deep=True)
    result = guard_hard_facts(payload, case["raw_input"])
    assert payload == before
    for original, current in zip(before.resume_sections.projects, result.resume_sections.projects):
        for field, prefix in (("intro", "intro_source"), ("role", "role_source")):
            if current[field] == original[field]:
                for suffix in ("fact_ids", "claim_ids"):
                    assert current.get(f"{prefix}_{suffix}") == original[f"{prefix}_{suffix}"]
        if current["details"] == original["details"]:
            assert current.get("detail_fact_ids") == original["detail_fact_ids"]
            assert current.get("detail_claim_ids") == original["detail_claim_ids"]


class StopBeforeProjection(BaseException):
    pass


def real_receiver(case, data, monkeypatch, tmp_path, *, deliver=False):
    """Only the network, budget and log locations are replaced; binding is real."""
    monkeypatch.setenv("LLM_MODE", "openai")
    monkeypatch.setattr(generation.resource_protection, "check_daily_budget", lambda: SimpleNamespace(allowed=True))
    monkeypatch.setattr(generation.resource_protection, "record_llm_usage", lambda **kwargs: None)
    for module in tuple(sys.modules.values()):
        if not getattr(module, "__name__", "").startswith("app.services."):
            continue
        for key in ("LOG_DIR", "LOG_PATH", "OWNER_DELIVERY_CONTRACT_LOG_PATH"):
            value = getattr(module, key, None)
            if isinstance(value, Path):
                monkeypatch.setattr(module, key, tmp_path if key == "LOG_DIR" else tmp_path / value.name)
    captured = {"stages": []}
    output = json.dumps(data, ensure_ascii=False)
    monkeypatch.setattr(generation, "call_openai", lambda prompt: LLMResult(
        text=output, model="offline-controlled-return", latency_ms=0,
    ))
    for name in (
        "normalize_resume_section_schema", "cleanup_generation_payload", "guard_hard_facts",
        "fill_resume_sections", "ensure_resume_experience_validity", "bind_projects_to_experience_slots",
        "contain_ownerless_projects",
    ):
        original = getattr(generation, name)
        def record(*args, _original=original, _name=name, **kwargs):
            result = _original(*args, **kwargs)
            payload = result[0] if isinstance(result, tuple) else result
            captured["stages"].append((_name, payload.model_copy(deep=True)))
            return result
        monkeypatch.setattr(generation, name, record)
    actual_plan = generation.plan_canonical_project_projections
    def capture(payload, view):
        captured["payload"] = payload.model_copy(deep=True)
        captured["plan"] = actual_plan(payload, view)
        if deliver:
            return captured["plan"]
        raise StopBeforeProjection()
    monkeypatch.setattr(generation, "plan_canonical_project_projections", capture)
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            if deliver:
                response = generation.create_generation(db, request(case), request_id="req_v09162_controlled")
                captured["response"] = response
                row = db.get(models.GenerationResult, response.generation_result_id)
                captured["saved"] = json.loads(row.result_json)
                saved_before = row.result_json
                monkeypatch.setattr(docx_service, "OUTPUT_DIR", tmp_path)
                captured["docx"] = docx_service.create_docx(db, schemas.DocxCreate(
                    generation_result_id=row.id, anonymous_user_id="v09162", session_id="v09162",
                ))
                assert row.result_json == saved_before
            else:
                with pytest.raises(StopBeforeProjection):
                    generation.create_generation(db, request(case), request_id="req_v09162_controlled")
    finally:
        engine.dispose()
    return captured


@pytest.mark.parametrize("case", CASES, ids=lambda x: str(x["result_id"]))
def test_actual_receiver_preserves_legal_field_lineage(case, monkeypatch, tmp_path):
    build, data = controlled_return(case)
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    projects = {p.get("source_experience_id"): p for p in captured["payload"].resume_sections.projects}
    assert set(projects) == {i.experience_id for i in build.identities}
    for original in data["resume_sections"]["projects"]:
        current = projects[original["source_experience_id"]]
        for key in ATTACHMENTS:
            assert current.get(key) == original[key]
    assert not dict(captured["plan"].detail_skip_counts).get("ambiguous_field_provenance")


@pytest.mark.parametrize("reverse", [False, True])
def test_candidate_order_does_not_discard_complete_provenance(reverse):
    build, data = controlled_return(CASES[0])
    good = deepcopy(data["resume_sections"]["projects"][0])
    unknown = {key: deepcopy(value) for key, value in good.items() if key not in ATTACHMENTS}
    projects = [good, unknown] if reverse else [unknown, good]
    data["resume_sections"]["projects"] = projects
    result = bind_projects_to_experience_slots(
        schemas.GenerationPayload.model_validate(data), CASES[0]["raw_input"],
        semantic_build=build, write_log=False,
    )
    frozen = [p for p in result.resume_sections.projects if p.get("source_binding_locked")]
    assert len(frozen) == 1
    assert frozen[0].get("detail_fact_ids") == good["detail_fact_ids"]
    assert frozen[0].get("detail_claim_ids") == good["detail_claim_ids"]


@pytest.mark.parametrize("case", CASES, ids=lambda x: str(x["result_id"]))
def test_existing_sanitizer_preserves_exact_intro_attachment(case):
    _, data = controlled_return(case)
    payload = schemas.GenerationPayload.model_validate(data)
    result = sanitize_resume_body(payload, semantic_safe=True)
    for original, current in zip(payload.resume_sections.projects, result.resume_sections.projects):
        assert current["intro"] == original["intro"]
        assert current.get("intro_source_fact_ids") == original["intro_source_fact_ids"]
        assert current.get("intro_source_claim_ids") == original["intro_source_claim_ids"]


def test_existing_presentation_view_does_not_gain_intro_rewrite_authority():
    build, data = controlled_return(CASES[0])
    project = deepcopy(data["resume_sections"]["projects"][0])
    view = build_canonical_consumer_views(build).presentation_view
    # Reading candidate attachments must not expand downstream rewriting rights.
    assert view.fact_ids_for_field(project, "intro") == ()
    project.pop("intro_source_fact_ids")
    assert view.fact_ids_for_field(project, "intro") == ()


@pytest.mark.parametrize("kind", ["unknown_fact", "foreign_fact", "wrong_claim", "ineligible_claim", "unsupported_text"])
def test_candidate_binding_does_not_accept_invalid_field_evidence(kind):
    build, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    if kind == "unknown_fact":
        project["detail_fact_ids"][0] = ["EXP-001-F999"]
    elif kind == "foreign_fact":
        other = build.ledger.for_experience("EXP-002")[0]
        project["detail_fact_ids"][0] = [other.fact_id]
        project["detail_claim_ids"][0] = [other.claim_id]
    elif kind == "wrong_claim":
        project["detail_claim_ids"][0] = project["detail_claim_ids"][1][:]
    elif kind == "ineligible_claim":
        excluded = next(c for c in build.ledger.excluded_claims if c.source_experience_id == "EXP-001")
        project["detail_claim_ids"][0] = [excluded.claim_id]
    else:
        project["details"][0] = "独立主导整体数据库架构设计并负责生产部署"
    data["resume_sections"]["projects"] = [project]
    result = bind_projects_to_experience_slots(
        schemas.GenerationPayload.model_validate(data), CASES[0]["raw_input"],
        semantic_build=build, write_log=False,
    )
    current = result.resume_sections.projects[0]
    assert not (current.get("detail_fact_ids") or [[]])[0]
    assert not (current.get("detail_claim_ids") or [[]])[0]


def test_missing_source_is_not_inferred_from_exact_text_or_project_aggregate():
    build, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    for key in ATTACHMENTS:
        if key not in {"source_fact_ids", "source_claim_ids"}:
            project.pop(key)
    data["resume_sections"]["projects"] = [project]
    result = bind_projects_to_experience_slots(
        schemas.GenerationPayload.model_validate(data), CASES[0]["raw_input"],
        semantic_build=build, write_log=False,
    )
    current = result.resume_sections.projects[0]
    assert current["details"] == project["details"]
    assert not any(current.get("detail_fact_ids", []))
    assert not current.get("intro_source_fact_ids")
    assert not current.get("role_source_fact_ids")


def test_normalization_preserves_one_field_with_multiple_declared_facts():
    _, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    project["details"] = ["；".join(project["details"][:2])]
    project["detail_fact_ids"] = [sum(project["detail_fact_ids"][:2], [])]
    project["detail_claim_ids"] = [sum(project["detail_claim_ids"][:2], [])]
    before = deepcopy(project)
    output = generation.normalize_llm_payload(deepcopy(data))["resume_sections"]["projects"][0]
    assert output["details"] == before["details"]
    assert output.get("detail_fact_ids") == before["detail_fact_ids"]
    assert output.get("detail_claim_ids") == before["detail_claim_ids"]


@pytest.mark.parametrize("case", CASES, ids=lambda x: str(x["result_id"]))
def test_actual_generation_save_and_docx(case, monkeypatch, tmp_path):
    from docx import Document
    build, data = controlled_return(case)
    captured = real_receiver(case, data, monkeypatch, tmp_path, deliver=True)
    saved = captured["saved"]["resume_sections"]["projects"]
    assert {p["source_experience_id"] for p in saved} == {i.experience_id for i in build.identities}
    rendered = "\n".join(p.text for path in tmp_path.glob("*.docx") for p in Document(path).paragraphs)
    assert rendered and captured["docx"]
    for project in saved:
        assert project["name"] in rendered
        assert all(text in rendered for text in project["details"])
        facts = {f.fact_id: f for f in build.ledger.for_experience(project["source_experience_id"])}
        rows = [(project[field], project[f"{field}_source_fact_ids"], project[f"{field}_source_claim_ids"])
                for field in ("intro", "role")]
        rows += list(zip(project["details"], project["detail_fact_ids"], project["detail_claim_ids"]))
        retained = set()
        for text, ids, claims in rows:
            assert ids and all(fid in facts for fid in ids)
            assert set(claims) == {facts[fid].claim_id for fid in ids}
            original = "；".join(facts[fid].resume_ready_text for fid in ids)
            # Existing professionalization removes this first-person prefix;
            # the model reception validator itself does not allow this rewrite.
            expected = original[1:] if original.startswith("我负责") else original
            assert provenance_text_unchanged(text, expected)
            retained.update(ids)
        assert retained == set(facts)
    public = captured["response"].model_dump_json()
    assert "immutable_source_experience_id" not in public
    assert "source_binding_locked" not in public


def test_cleanup_original_indices_changed_fields_and_existing_limits():
    _, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    project["details"] = ["", "role: 改写标签", *[f"保留内容{i}" for i in range(9)]]
    project["detail_fact_ids"] = [[f"F{i}"] for i in range(11)]
    project["detail_claim_ids"] = [[f"C{i}"] for i in range(11)]
    project["source_fact_ids"] += [f"F{i}" for i in range(11)]
    project["source_claim_ids"] += [f"C{i}" for i in range(11)]
    before = deepcopy(data)
    result = cleanup_generation_payload(data)
    assert data == before
    current = result.resume_sections.projects[0]
    assert len(current["details"]) == 8
    assert current["detail_fact_ids"] == [[], *[[f"F{i}"] for i in range(2, 9)]]
    assert current["detail_claim_ids"] == [[], *[[f"C{i}"] for i in range(2, 9)]]
    assert not {"F0", "F1", "F9", "F10"} & set(current["source_fact_ids"])
    assert current["intro_source_fact_ids"] == project["intro_source_fact_ids"]
    assert cleanup_generation_payload(result) == result


@pytest.mark.parametrize("kind", ["missing", "invalid", "unsupported"])
def test_actual_receiver_does_not_upgrade_unknown_model_evidence(kind, monkeypatch, tmp_path):
    build, data = controlled_return(CASES[0])
    for project in data["resume_sections"]["projects"]:
        if kind == "missing":
            for key in ATTACHMENTS:
                project.pop(key)
        elif kind == "invalid":
            project["detail_fact_ids"][0] = ["EXP-999-F001"]
        else:
            project["details"][0] = "独立负责全部架构设计并提升性能300%"
    captured = real_receiver(CASES[0], data, monkeypatch, tmp_path)
    # Inspect the actual post-network payload before fallback can add its own candidates.
    received = captured["stages"][0][1]
    assert len(received.resume_sections.projects) == len(build.identities)
    for project in received.resume_sections.projects:
        if kind == "missing":
            assert not any(project["detail_fact_ids"])
            assert not project.get("intro_source_fact_ids")
            assert not project.get("role_source_fact_ids")
        else:
            assert project["detail_fact_ids"][0] == []
            assert project["detail_claim_ids"][0] == []


def test_validator_literal_composition_idempotence_immutability_and_log_privacy(monkeypatch, tmp_path):
    from app.services import experience_slot_service as slots
    build, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    project["details"] = ["；".join(text.rstrip("。；;") for text in project["details"][:2])]
    project["detail_fact_ids"] = [sum(project["detail_fact_ids"][:2], [])]
    project["detail_claim_ids"] = [sum(project["detail_claim_ids"][:2], [])]
    payload = schemas.GenerationPayload.model_validate(data)
    views = build_canonical_consumer_views(build)
    before, build_before = payload.model_copy(deep=True), deepcopy(build)
    monkeypatch.setattr(slots, "LOG_PATH", tmp_path / "slot.jsonl")
    output = validate_model_project_evidence(payload, views, attempt_id="test-privacy")
    assert output.resume_sections.projects[0]["detail_fact_ids"] == project["detail_fact_ids"]
    assert validate_model_project_evidence(output, views, write_log=False) == output
    assert payload == before and build == build_before
    log = slots.LOG_PATH.read_text(encoding="utf-8")
    assert "test-privacy" in log and "verified_field_count" in log
    for candidate in payload.resume_sections.projects:
        assert candidate["name"] not in log and candidate["intro"] not in log
    changed = output.model_copy(deep=True)
    changed.resume_sections.projects[0]["details"][0] += "，独立主导整体架构"
    rejected = validate_model_project_evidence(changed, views, write_log=False)
    assert rejected.resume_sections.projects[0]["detail_fact_ids"][0] == []


def test_owner_matching_cannot_move_validated_field_sources():
    build, data = controlled_return(CASES[0])
    first, second = data["resume_sections"]["projects"]
    first["name"] = second["name"]
    data["resume_sections"]["projects"] = [first]
    result = bind_projects_to_experience_slots(
        schemas.GenerationPayload.model_validate(data), CASES[0]["raw_input"], semantic_build=build, write_log=False,
    )
    assert result.resume_sections.projects[0].get("immutable_source_experience_id") != "EXP-002"


def test_hard_guard_rewrite_invalidates_only_changed_field_evidence():
    _, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    project["details"][0] = "获得三等奖"
    fact, claim = project["detail_fact_ids"][0][0], project["detail_claim_ids"][0][0]
    result = guard_hard_facts(schemas.GenerationPayload.model_validate(data), "使用Python整理资料，没有获奖")
    current = result.resume_sections.projects[0]
    assert current["details"][0] != project["details"][0]
    assert current["detail_fact_ids"][0] == [] and current["detail_claim_ids"][0] == []
    assert fact not in current["source_fact_ids"] and claim not in current["source_claim_ids"]
    assert current["detail_fact_ids"][1:] == project["detail_fact_ids"][1:]


@pytest.mark.parametrize("bad_value", ["EXP-001-F001", [None], [{"id": "EXP-001-F001"}], 12])
def test_malformed_reference_values_are_not_proofs(bad_value):
    build, data = controlled_return(CASES[0])
    data["resume_sections"]["projects"][0]["detail_fact_ids"][0] = bad_value
    result = validate_model_project_evidence(
        schemas.GenerationPayload.model_validate(generation.normalize_llm_payload(data)),
        build_canonical_consumer_views(build), write_log=False,
    )
    assert result.resume_sections.projects[0]["detail_fact_ids"][0] == []


def test_invalid_detail_does_not_discard_independent_valid_fields():
    build, data = controlled_return(CASES[0])
    project = data["resume_sections"]["projects"][0]
    project["detail_fact_ids"][0] = ["EXP-999-F001"]
    received = validate_model_project_evidence(
        schemas.GenerationPayload.model_validate(data), build_canonical_consumer_views(build), write_log=False,
    )
    bound = bind_projects_to_experience_slots(received, CASES[0]["raw_input"], semantic_build=build, write_log=False)
    current = bound.resume_sections.projects[0]
    assert current["detail_fact_ids"][0] == []
    assert current["intro_source_fact_ids"] == project["intro_source_fact_ids"]
    assert current["role_source_claim_ids"] == project["role_source_claim_ids"]


def test_binder_repeated_execution_does_not_mutate_input_or_build():
    build, data = controlled_return(CASES[0])
    payload = schemas.GenerationPayload.model_validate(data)
    before, build_before = payload.model_copy(deep=True), deepcopy(build)
    result = bind_projects_to_experience_slots(payload, CASES[0]["raw_input"], semantic_build=build, write_log=False)
    assert bind_projects_to_experience_slots(result, CASES[0]["raw_input"], semantic_build=build, write_log=False) == result
    assert payload == before and build == build_before
