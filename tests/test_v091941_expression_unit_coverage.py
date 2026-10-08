"""A reused compound Fact can be expressed across units without losing coverage."""

from copy import deepcopy
import json
from dataclasses import replace

import pytest

from app.services import experience_slot_service as slots
from app.services import generation_service as generation
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from scripts.run_public_smoke_test import SMOKE_CASES
from test_v09172_initial_evidence_preservation import detail_return
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import deliver, provider
from test_v09193_evidence_bounded_composition import composition_sample
from test_v09162_model_output_evidence_contract import request


def smoke_units():
    raw = SMOKE_CASES[1]["raw_input"]
    build = build_canonical_semantic_build(raw)
    views = build_canonical_consumer_views(build)
    assert views.experience_ids == ("EXP-001",)
    facts = views.facts_for_owner("EXP-001")
    assert len(facts) == 1 and facts[0].fact_id == "EXP-001-F001"
    fact = facts[0]
    units = [
        {"fact_ids": [fact.fact_id], "position": position, "text": text}
        for position, text in (
            ("intro", "独立开发校园活动管理项目"),
            ("detail", "使用 TypeScript、React 完成活动列表、报名表单"),
            ("detail", "完成状态展示"),
            ("detail", "根据同学试用反馈调整交互流程"),
        )
    ]
    body = {"resume_sections": {"projects": [
        {"source_experience_id": fact.experience_id, "expression_units": units}
    ]}}
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    composed = slots.compose_model_fact_references(body, views, expression_review=review)
    assert len(review.pending) == len(units) == 4
    return build, views, fact, body, review, composed


def complete_reply(review, fact_id):
    return {
        "decisions": {key: {
            "verdict": "supported", "source_fact_id": None,
            "source_excerpt": None, "candidate_excerpt": None,
        } for key in review.pending},
        "coverage": {fact_id: {
            "verdict": "complete", "unit_ids": list(review.candidates),
            "source_excerpt": None,
        }},
    }


def full_reply(review):
    return {
        "decisions": {key: {
            "verdict": "supported", "source_fact_id": None,
            "source_excerpt": None, "candidate_excerpt": None,
        } for key in review.pending},
        "coverage": {fact_id: {
            "verdict": "complete", "unit_ids": unit_ids,
            "source_excerpt": None,
        } for fact_id, unit_ids in review.coverage_units().items()},
    }


def test_compound_smoke_fact_can_be_complete_across_four_units(isolated):
    build, views, fact, _, review, composed = smoke_units()
    review.accept(complete_reply(review, fact.fact_id))
    checked = slots.validate_model_project_evidence(
        composed, views, expression_review=review, require_complete=True, write_log=False,
    )
    project = checked["resume_sections"]["projects"][0]
    assert project["intro_source_fact_ids"] == [fact.fact_id]
    assert project["detail_fact_ids"] == [[fact.fact_id]] * 3
    assert project["detail_claim_ids"] == [[fact.claim_id]] * 3
    assert project["source_fact_ids"] == [fact.fact_id]
    assert build.ledger.facts[0] == fact


def test_covering_fact_id_does_not_hide_missing_feedback(isolated):
    _, _, fact, _, review, _ = smoke_units()
    reply = complete_reply(review, fact.fact_id)
    reply["coverage"][fact.fact_id] = {
        "verdict": "omitted", "unit_ids": list(review.candidates),
        "source_excerpt": "根据同学试用反馈调整交互流程",
    }
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.code == "MODEL_EXPRESSION_REJECTED"


def test_covering_fact_id_does_not_hide_bad_unit_mapping(isolated):
    _, _, fact, _, review, _ = smoke_units()
    reply = complete_reply(review, fact.fact_id)
    reply["coverage"][fact.fact_id]["unit_ids"] = ["unrelated-unit"]
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.code == "MODEL_EXPRESSION_REVIEW_INVALID"


def test_deleting_one_reviewed_unit_invalidates_group_coverage(isolated):
    _, views, fact, _, review, composed = smoke_units()
    review.accept(complete_reply(review, fact.fact_id))
    changed = deepcopy(composed)
    project = changed["resume_sections"]["projects"][0]
    for field in ("details", "detail_fact_ids", "detail_claim_ids"):
        del project[field][1]
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.validate_model_project_evidence(
            changed, views, expression_review=review,
            require_complete=True, write_log=False,
        )


def test_synchronized_detail_reordering_preserves_coverage_but_misalignment_does_not(isolated):
    _, views, fact, _, review, composed = smoke_units()
    review.accept(complete_reply(review, fact.fact_id))
    reordered = deepcopy(composed)
    project = reordered["resume_sections"]["projects"][0]
    for field in ("details", "detail_fact_ids", "detail_claim_ids"):
        project[field].reverse()
    checked = slots.validate_model_project_evidence(
        reordered, views, expression_review=review,
        require_complete=True, write_log=False,
    )
    assert checked["resume_sections"]["projects"][0]["detail_fact_ids"] == [
        [fact.fact_id]
    ] * 3
    changed = deepcopy(reordered)
    changed["resume_sections"]["projects"][0]["detail_claim_ids"][0] = []
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.validate_model_project_evidence(
            changed, views, expression_review=review,
            require_complete=True, write_log=False,
        )


@pytest.mark.parametrize("missing", ["使用 TypeScript、React", "根据同学试用反馈调整交互流程"])
def test_group_omission_is_not_covered_by_repeat_references(missing, isolated):
    _, _, fact, _, review, _ = smoke_units()
    reply = complete_reply(review, fact.fact_id)
    reply["coverage"][fact.fact_id].update(verdict="omitted", source_excerpt=missing)
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.reason_counts == {"expression_review_coverage_omitted": 1}
    assert review.accepted == {} and review.coverage_accepted == {}
    assert review.review_issues[0]["source_span"] == [
        fact.resume_ready_text.index(missing), fact.resume_ready_text.index(missing) + len(missing),
    ]


def test_single_unit_overclaim_cannot_be_cured_by_complete_group(isolated):
    _, _, fact, _, review, _ = smoke_units()
    reply = complete_reply(review, fact.fact_id)
    key = next(iter(review.pending))
    review.candidates[key]["candidate"] = "独立主导全部业务系统开发"
    reply["decisions"][key] = {
        "verdict": "added_claim", "source_fact_id": None,
        "source_excerpt": None, "candidate_excerpt": "主导全部业务系统",
    }
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.code == "MODEL_EXPRESSION_REJECTED"
    assert review.accepted == {} and review.coverage_accepted == {}


def test_repeating_only_one_part_does_not_hide_group_omission(isolated):
    _, _, fact, _, review, _ = smoke_units()
    reply = complete_reply(review, fact.fact_id)
    reply["coverage"][fact.fact_id].update(
        verdict="omitted", source_excerpt="使用 TypeScript、React",
    )
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.reason_counts == {"expression_review_coverage_omitted": 1}


def test_multi_fact_and_shared_claim_keep_exact_field_lineage(isolated):
    _, build, body = composition_sample(combine=True)
    first = body["resume_sections"]["projects"][0]["expression_units"][0]
    first["text"] = first["text"].replace("和FastAPI", "与FastAPI")
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    composed = slots.compose_model_fact_references(body, views, expression_review=review)
    assert len(review.pending) == 1
    review.accept(full_reply(review))
    checked = slots.validate_model_project_evidence(
        composed, views, expression_review=review, require_complete=True, write_log=False,
    )
    project = checked["resume_sections"]["projects"][0]
    assert project["detail_fact_ids"][0] == first["fact_ids"]
    assert len(project["detail_claim_ids"][0]) == 1
    assert set(project["source_fact_ids"]) == {f.fact_id for f in views.facts_for_owner("EXP-001")}


def test_other_unit_cannot_cure_a_changed_responsibility(isolated):
    _, build, body = composition_sample(combine=False)
    second = body["resume_sections"]["projects"][1]["expression_units"][0]
    assert "只负责" in second["text"]
    second["text"] = second["text"].replace("只负责", "独立负责")
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    slots.compose_model_fact_references(body, views, expression_review=review)
    reply = full_reply(review)
    key = next(iter(review.pending))
    reply["decisions"][key] = {
        "verdict": "changed_qualification", "source_fact_id": second["fact_ids"][0],
        "source_excerpt": "只负责", "candidate_excerpt": "独立负责",
    }
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.code == "MODEL_EXPRESSION_REJECTED"


def test_duplicate_coverage_key_cannot_be_overwritten(isolated):
    _, _, fact, _, review, _ = smoke_units()
    reply = complete_reply(review, fact.fact_id)
    decisions = json.dumps(reply["decisions"], ensure_ascii=False)
    row = json.dumps(reply["coverage"][fact.fact_id], ensure_ascii=False)
    raw = ('{"decisions":' + decisions + ',"coverage":{"' + fact.fact_id
           + '":' + row + ',"' + fact.fact_id + '":' + row + '}}')
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(json.loads(raw, object_pairs_hook=slots.ModelJSONObject))
    assert caught.value.code == "MODEL_EXPRESSION_REVIEW_INVALID"


def test_v4_review_response_is_explicitly_invalid(isolated):
    _, _, fact, _, review, _ = smoke_units()
    old = complete_reply(review, fact.fact_id)
    old.pop("coverage")
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(old)
    assert caught.value.code == "MODEL_EXPRESSION_REVIEW_INVALID"


def test_full_smoke_compound_fact_can_reach_save_and_docx(monkeypatch, tmp_path, isolated):
    build, views, fact, body, review, _ = smoke_units()
    case, local_build, response = detail_return(SMOKE_CASES[1]["raw_input"])
    assert [f.resume_ready_text for f in local_build.ledger.facts] == [fact.resume_ready_text]
    response["resume_sections"]["projects"] = body["resume_sections"]["projects"]
    sent_review = complete_reply(review, fact.fact_id)
    outcome = deliver(monkeypatch, tmp_path, case, [
        (json.dumps(response, ensure_ascii=False), "stop"),
        (json.dumps(sent_review, ensure_ascii=False), "stop"),
    ])
    assert outcome["results"] == 1 and "docx" in outcome, outcome
    assert len(outcome["sent"]) == 2
    assert "<fact_coverage>" in outcome["sent"][1]["messages"][1]["content"]
    project = outcome["saved"]["resume_sections"]["projects"][0]
    assert project["intro_source_fact_ids"] == [fact.fact_id]
    assert project["detail_fact_ids"] == [[fact.fact_id]] * 3
    assert project["detail_claim_ids"] == [[fact.claim_id]] * 3


@pytest.mark.parametrize("long_mode", [False, True])
def test_normal_and_long_review_same_compound_fact_without_extra_calls(
    long_mode, monkeypatch, isolated,
):
    build, views, fact, body, review, _ = smoke_units()
    case, _, response = detail_return(SMOKE_CASES[1]["raw_input"])
    response["resume_sections"]["projects"] = body["resume_sections"]["projects"]
    sent = provider(monkeypatch, [
        (json.dumps(response, ensure_ascii=False), "stop"),
        (json.dumps(complete_reply(review, fact.fact_id), ensure_ascii=False), "stop"),
    ])
    payload, _ = generation.build_llm_generation(
        request(case), replace(build.long_input_context, long_input_mode=long_mode),
        consumer_views=views,
    )
    assert len(sent) == 2
    assert "canonical_fact_compositions_v2" in sent[0]["messages"][1]["content"]
    assert "canonical_expression_review_v6" in sent[1]["messages"][1]["content"]
    assert payload.resume_sections.projects[0]["detail_fact_ids"] == [[fact.fact_id]] * 3
