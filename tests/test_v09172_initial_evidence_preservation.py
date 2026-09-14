"""Current-code experiments with controlled returns, not historical snapshots."""
from copy import deepcopy
import json

import pytest

from test_v09162_model_output_evidence_contract import (
    ATTACHMENTS, CASES, controlled_return, real_receiver, request,
)
from app.services import generation_service as generation
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services import result_cleanup_service as cleanup
from app.services.fact_guard_service import guard_hard_facts
from app.services.prompt_service import _canonical_evidence_context
from test_v09171_trusted_initial_presentation import altered, network, isolated


AWARD = "竞赛经历：数据分析竞赛\n团队获得三等奖。使用Python整理调查结果。"
NO_AWARD = "项目经历：课程练习工具\n使用Java开发查询页面，没有获奖。"


def detail_return(raw):
    case = dict(CASES[0], raw_input=raw)
    build = build_canonical_semantic_build(raw)
    data = generation.build_mock_generation(request(case)).model_dump()
    projects = []
    for identity in build.identities:
        facts = list(build.ledger.for_experience(identity.experience_id))
        assert facts
        projects.append({
            "name": identity.title, "meta": identity.experience_type, "time": "",
            "source_experience_id": identity.experience_id,
            "intro": "", "role": "", "details": [f.resume_ready_text for f in facts],
            "intro_source_fact_ids": [], "intro_source_claim_ids": [],
            "role_source_fact_ids": [], "role_source_claim_ids": [],
            "detail_fact_ids": [[f.fact_id] for f in facts],
            "detail_claim_ids": [[f.claim_id] for f in facts],
            "source_fact_ids": [f.fact_id for f in facts],
            "source_claim_ids": list(dict.fromkeys(f.claim_id for f in facts)),
        })
    data["resume_sections"]["projects"] = projects
    return case, build, data


def stage(captured, name):
    return next(payload for fn, payload in captured["stages"] if fn == name)


def assert_evidence_equal(actual, expected):
    assert [p["source_experience_id"] for p in actual] == [p["source_experience_id"] for p in expected]
    for current, before in zip(actual, expected):
        for key in ("intro", "role", "details", *ATTACHMENTS):
            assert current.get(key) == before.get(key), key


def project_input(count):
    return "\n".join(
        f"项目{number}：接口测试工具{number}\n使用Python编写{index + 10}条接口测试用例。"
        for index, number in enumerate("一二三四五六"[:count])
    )


def detail_input(count):
    return "项目一：接口校验工具\n" + "。".join(
        f"使用Python编写第{index}组接口测试用例并记录{index + 10}条结果"
        for index in range(1, count + 1)
    ) + "。"


def test_empty_body_fields_remain_empty_through_initial_cleanup(monkeypatch, tmp_path):
    case, build, data = detail_return(detail_input(2))
    before = deepcopy(data)
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    for name in ("cleanup_generation_payload", "guard_hard_facts"):
        assert_evidence_equal(stage(captured, name).resume_sections.projects, before["resume_sections"]["projects"])
    assert data == before


@pytest.mark.parametrize("count", [5, 6])
def test_verified_projects_are_not_truncated_before_candidate_recovery(count, monkeypatch, tmp_path):
    case, build, data = detail_return(project_input(count))
    assert len(build.identities) == count
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    cleaned = stage(captured, "cleanup_generation_payload").resume_sections.projects
    assert len(cleaned) == count
    assert_evidence_equal(cleaned, data["resume_sections"]["projects"])
    assert {p["source_experience_id"] for p in captured["payload"].resume_sections.projects} == {
        identity.experience_id for identity in build.identities
    }


@pytest.mark.parametrize("count", [8, 9])
def test_verified_detail_rows_are_not_truncated(count, monkeypatch, tmp_path):
    case, build, data = detail_return(detail_input(count))
    expected = data["resume_sections"]["projects"]
    assert len(expected[0]["details"]) == count
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    cleaned = stage(captured, "cleanup_generation_payload").resume_sections.projects
    assert len(cleaned[0]["details"]) == count
    assert_evidence_equal(cleaned, expected)
    assert_evidence_equal(captured["payload"].resume_sections.projects, expected)


@pytest.mark.parametrize("reverse", [False, True])
def test_other_owner_negation_cannot_rewrite_verified_award(reverse, monkeypatch, tmp_path):
    raw = "\n".join([NO_AWARD, AWARD] if reverse else [AWARD, NO_AWARD])
    case, build, data = detail_return(raw)
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    guarded = stage(captured, "guard_hard_facts").resume_sections.projects
    expected = data["resume_sections"]["projects"]
    # Check the independently compiled award, not the incidental owner number.
    owner = next(p["source_experience_id"] for p in expected if "团队获得三等奖" in p["details"])
    actual = next(p for p in guarded if p["source_experience_id"] == owner)
    original = next(p for p in expected if p["source_experience_id"] == owner)
    assert actual["details"] == original["details"]
    assert actual["detail_fact_ids"] == original["detail_fact_ids"]
    assert actual["detail_claim_ids"] == original["detail_claim_ids"]


@pytest.mark.parametrize("case", CASES, ids=lambda c: str(c["result_id"]))
def test_exact_input_supported_returns_preserve_initial_evidence(case, monkeypatch, tmp_path):
    build, data = controlled_return(case)
    before_build, before = deepcopy(build), deepcopy(data)
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    for name in ("cleanup_generation_payload", "guard_hard_facts"):
        assert_evidence_equal(stage(captured, name).resume_sections.projects, data["resume_sections"]["projects"])
    assert data == before and build == before_build


@pytest.mark.parametrize("reverse", [False, True])
def test_online_fact_and_other_owner_limitation_remain_separate(reverse, monkeypatch, tmp_path):
    parts = [
        "项目一：资料检索工具\n使用FastAPI实现查询接口，已部署上线。",
        "项目二：练习管理工具\n使用Java开发管理页面，没有上线。",
    ]
    case, build, data = detail_return("\n".join(reversed(parts) if reverse else parts))
    before = deepcopy(build)
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    assert_evidence_equal(stage(captured, "guard_hard_facts").resume_sections.projects,
                          data["resume_sections"]["projects"])
    assert build == before


def test_same_owner_fact_and_responsibility_limit_survive(monkeypatch, tmp_path):
    raw = "竞赛经历：数据分析竞赛\n团队获得三等奖，我没有负责预测模型设计。使用Python整理调查结果。"
    case, build, data = detail_return(raw)
    before = deepcopy(build)
    assert any("没有负责" in c.text for c in build.ledger.excluded_claims)
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    assert_evidence_equal(stage(captured, "guard_hard_facts").resume_sections.projects,
                          data["resume_sections"]["projects"])
    assert any("没有负责" in c.text for c in build.ledger.excluded_claims)
    assert build == before


@pytest.mark.parametrize("blank_index", [0, 1])
def test_blank_rows_use_original_indexes_through_receiver(blank_index, monkeypatch, tmp_path):
    case, build, data = detail_return(detail_input(3))
    expected = deepcopy(data["resume_sections"]["projects"])
    project = data["resume_sections"]["projects"][0]
    project["details"].insert(blank_index, " \n ")
    project["detail_fact_ids"].insert(blank_index, [])
    project["detail_claim_ids"].insert(blank_index, [])
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    for name in ("cleanup_generation_payload", "guard_hard_facts"):
        assert_evidence_equal(stage(captured, name).resume_sections.projects, expected)


def test_empty_details_and_nonempty_bound_headers_are_preserved(monkeypatch, tmp_path):
    case, build, data = detail_return(detail_input(2))
    project = data["resume_sections"]["projects"][0]
    for index, field in enumerate(("intro", "role")):
        project[field] = project["details"][index]
        project[f"{field}_source_fact_ids"] = project["detail_fact_ids"][index]
        project[f"{field}_source_claim_ids"] = project["detail_claim_ids"][index]
    project["details"], project["detail_fact_ids"], project["detail_claim_ids"] = [], [], []
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    for name in ("cleanup_generation_payload", "guard_hard_facts"):
        assert_evidence_equal(stage(captured, name).resume_sections.projects, [project])


def test_same_text_different_owner_sources_are_not_merged(monkeypatch, tmp_path):
    raw = "项目一：资料管理工具\n使用Python编写接口测试用例。\n项目二：订单管理工具\n使用Python编写接口测试用例。"
    case, build, data = detail_return(raw)
    projects = data["resume_sections"]["projects"]
    assert len(projects) == 2 and projects[0]["details"] == projects[1]["details"]
    assert projects[0]["detail_fact_ids"] != projects[1]["detail_fact_ids"]
    captured = real_receiver(case, data, monkeypatch, tmp_path)
    assert_evidence_equal(stage(captured, "cleanup_generation_payload").resume_sections.projects, projects)


def test_canonical_cleanup_is_idempotent_and_does_not_guess_aggregate_bindings(monkeypatch, tmp_path):
    monkeypatch.setattr(cleanup, "LOG_PATH", tmp_path / "cleanup.jsonl")
    monkeypatch.setattr(cleanup, "LOG_DIR", tmp_path)
    _, build, data = detail_return(detail_input(2))
    project = data["resume_sections"]["projects"][0]
    project["intro"] = project["details"][0]
    project.pop("intro_source_fact_ids")
    project.pop("intro_source_claim_ids")
    before = deepcopy(data)
    first = cleanup.cleanup_generation_payload(data, canonical_mode=True)
    second = cleanup.cleanup_generation_payload(first, canonical_mode=True)
    assert first == second and data == before
    assert "intro_source_fact_ids" not in first.resume_sections.projects[0]
    assert first.resume_sections.projects[0]["source_fact_ids"] == project["source_fact_ids"]
    guarded = guard_hard_facts(first, NO_AWARD, canonical_mode=True)
    assert guarded.resume_sections.projects == first.resume_sections.projects
    assert guard_hard_facts(guarded, NO_AWARD, canonical_mode=True) == guarded
    logs = (tmp_path / "cleanup.jsonl").read_text(encoding="utf-8")
    assert not any(text in logs for text in project["details"])


def test_cleaned_text_cannot_retain_stale_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(cleanup, "LOG_DIR", tmp_path)
    monkeypatch.setattr(cleanup, "LOG_PATH", tmp_path / "cleanup.jsonl")
    _, _, data = detail_return(detail_input(2))
    p = data["resume_sections"]["projects"][0]
    p["details"][0] = "details: " + p["details"][0]
    before = deepcopy(data)
    result = cleanup.cleanup_generation_payload(data, canonical_mode=True)
    current = result.resume_sections.projects[0]
    assert current["details"][0] != p["details"][0]
    assert current["detail_fact_ids"][0] == current["detail_claim_ids"][0] == []
    assert current["detail_fact_ids"][1] == p["detail_fact_ids"][1]
    assert p["detail_fact_ids"][0][0] not in current["source_fact_ids"]
    assert data == before


def test_default_legacy_limits_and_global_guard_stay_compatible(monkeypatch, tmp_path):
    monkeypatch.setattr(cleanup, "LOG_DIR", tmp_path)
    monkeypatch.setattr(cleanup, "LOG_PATH", tmp_path / "cleanup.jsonl")
    _, _, data = detail_return(project_input(6))
    legacy = cleanup.cleanup_generation_payload(data)
    assert len(legacy.resume_sections.projects) == 5
    assert legacy.resume_sections.projects[0]["intro"] == cleanup.DEFAULT_TEXT
    _, _, data = detail_return(detail_input(9))
    assert len(cleanup.cleanup_generation_payload(data).resume_sections.projects[0]["details"]) == 8
    _, _, award = detail_return(AWARD)
    assert guard_hard_facts(award, NO_AWARD).resume_sections.projects[0]["details"][0] != "团队获得三等奖"
    canonical = guard_hard_facts(award, NO_AWARD, canonical_mode=True)
    legacy = guard_hard_facts(award, NO_AWARD)
    for key, value in canonical.model_dump().items():
        if key != "resume_sections":
            assert value == legacy.model_dump()[key]
    for key, value in canonical.resume_sections.model_dump().items():
        if key != "projects":
            assert value == legacy.resume_sections.model_dump()[key]


@pytest.mark.parametrize("kind", ["missing", "foreign_owner", "bad_id", "bad_lineage", "rewrite"])
def test_invalid_model_evidence_still_stops_before_cleanup(kind, monkeypatch, tmp_path, isolated):
    _, data = controlled_return(CASES[0])
    with pytest.raises(generation.GenerationServiceError, match="MODEL_EVIDENCE_"):
        real_receiver(CASES[0], altered(data, kind), monkeypatch, tmp_path)


@pytest.mark.parametrize("long_mode", [False, True])
def test_retry_reuses_frozen_views_without_semantic_rebuild(long_mode, monkeypatch, isolated):
    from dataclasses import replace
    build, data = controlled_return(CASES[0])
    views = build_canonical_consumer_views(build)
    before = deepcopy(build)
    evidence_before = _canonical_evidence_context(request(CASES[0]), views)
    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected semantic rebuild")
    monkeypatch.setattr(generation, "build_canonical_semantic_build", forbidden)
    sent = network(monkeypatch, [altered(data, "missing"), data])
    result, _ = generation.build_llm_generation(
        request(CASES[0]), replace(build.long_input_context, long_input_mode=long_mode),
        consumer_views=views,
    )
    assert len(sent) == 2 and build == before
    assert _canonical_evidence_context(request(CASES[0]), views) == evidence_before
    assert_evidence_equal(result.resume_sections.projects, data["resume_sections"]["projects"])


@pytest.mark.parametrize("case", CASES, ids=lambda c: str(c["result_id"]))
def test_real_save_and_docx_record_downstream_changes_separately(case, monkeypatch, tmp_path):
    build, data = controlled_return(case)
    before = deepcopy(data)
    captured = real_receiver(case, data, monkeypatch, tmp_path, deliver=True)
    assert_evidence_equal(stage(captured, "guard_hard_facts").resume_sections.projects,
                          data["resume_sections"]["projects"])
    assert data == before
    assert captured["saved"] and captured["docx"]


def test_initial_preservation_does_not_hide_later_detail_loss(monkeypatch, tmp_path):
    case, build, data = detail_return(detail_input(9))
    changes, gates = [], []
    names = ("reconcile_resume_projects", "layer_resume_sections", "ensure_resume_fact_increment",
             "ensure_information_gain", "ensure_resume_experience_validity", "guard_resume_output")
    for name in names:
        original = getattr(generation, name)
        def observe(*args, _original=original, _name=name, **kwargs):
            before = deepcopy(args[0].resume_sections.projects)
            output = _original(*args, **kwargs)
            if before != output.resume_sections.projects:
                after = output.resume_sections.projects
                change = {"writer": _name, "stage": kwargs.get("stage"),
                          "before_details": sum(len(p.get("details", [])) for p in before),
                          "after_details": sum(len(p.get("details", [])) for p in after)}
                for suffix in ("fact_ids", "claim_ids"):
                    old_ids = {item for p in before for row in p.get(f"detail_{suffix}", []) for item in row}
                    new_ids = {item for p in after for row in p.get(f"detail_{suffix}", []) for item in row}
                    change[f"removed_{suffix}"] = sorted(old_ids - new_ids)
                changes.append(change)
            return output
        monkeypatch.setattr(generation, name, observe)
    actual_gate = generation.validate_resume_delivery_quality
    def observe_gate(*args, **kwargs):
        result = actual_gate(*args, **kwargs)
        gates.append({"passed": result.stats.gate_passed,
                      "issues": [i.issue_code for i in result.issues]})
        return result
    monkeypatch.setattr(generation, "validate_resume_delivery_quality", observe_gate)
    captured = real_receiver(case, data, monkeypatch, tmp_path, deliver=True)
    assert_evidence_equal(captured["payload"].resume_sections.projects, data["resume_sections"]["projects"])
    # Downstream limits are observed, not redefined as this release's success criterion.
    report = {"initial_details": 9, "downstream_changes": changes, "gates": gates,
              "saved_details": sum(len(p.get("details", [])) for p in captured["saved"]["resume_sections"]["projects"])}
    (tmp_path / "stage-evidence.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert gates and captured["docx"]


def test_pure_json_failure_keeps_existing_fallback_and_canonical_cleanup(monkeypatch, isolated):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.database import Base
    calls = []
    original_fallback = generation.build_stable_generation_fallback
    original_cleanup = generation.cleanup_generation_payload
    def fallback(*args, **kwargs):
        calls.append("fallback")
        return original_fallback(*args, **kwargs)
    def clean(*args, **kwargs):
        assert kwargs.get("canonical_mode") is True
        calls.append("cleanup")
        return original_cleanup(*args, **kwargs)
    monkeypatch.setattr(generation, "build_stable_generation_fallback", fallback)
    monkeypatch.setattr(generation, "cleanup_generation_payload", clean)
    sent = network(monkeypatch, ["not a JSON response"])
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            response = generation.create_generation(db, request(CASES[0]), request_id="req_v09172_parse")
            assert response.generation_result_id
    finally:
        engine.dispose()
    assert len(sent) == 2 and calls == ["fallback", "cleanup"]


@pytest.mark.parametrize("sample", ["ecommerce", "competition_campus"])
def test_reserved_full_samples_after_business_changes(sample, monkeypatch, tmp_path):
    """Held out from this release's implementation/debugging examples."""
    from test_v0916_canonical_model_evidence import FULL, MULTI_TYPE
    raw = FULL if sample == "ecommerce" else MULTI_TYPE[sample]
    case, build, data = detail_return(raw)
    expected = deepcopy(data["resume_sections"]["projects"])
    captured = real_receiver(case, data, monkeypatch, tmp_path, deliver=True)
    for name in ("cleanup_generation_payload", "guard_hard_facts"):
        assert_evidence_equal(stage(captured, name).resume_sections.projects, expected)
    facts = {f.fact_id: f for f in build.ledger.facts}
    for project in captured["payload"].resume_sections.projects:
        for text, ids, claims in zip(project["details"], project["detail_fact_ids"], project["detail_claim_ids"]):
            assert len(ids) == len(claims) == 1
            fact = facts[ids[0]]
            assert fact.experience_id == project["source_experience_id"]
            assert fact.claim_id == claims[0] and fact.resume_ready_text == text
    assert captured["saved"] and captured["docx"]
