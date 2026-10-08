"""Real receiver controls for call scheduling and noncompeting coverage proofs."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from app.services import generation_service as generation
from app.services import experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import provider, deliver
from test_v091941_expression_unit_coverage import full_reply
from test_v091942_header_aware_expression_coverage import RAW, prepared
from test_v09172_initial_evidence_preservation import detail_return
from test_v09162_model_output_evidence_contract import request


def sample():
    build, views, facts, review, composed = prepared()
    case, _, body = detail_return(RAW)
    body['resume_sections']['projects'] = [{
        'source_experience_id': 'EXP-001',
        'expression_units': [dict(fact_ids=list(row['sources']), position=row['position'],
                                  text=row['candidate']) for row in review.candidates.values()],
    }]
    return case, build, views, facts, review, body


def test_literal_fact_does_not_need_probabilistic_coverage(isolated):
    _, views, facts, review, composed = prepared()
    assert facts[3].fact_id not in review.coverage_units()
    before = deepcopy(composed)
    review.accept(full_reply(review))
    checked = slots.validate_model_project_evidence(
        composed, views, expression_review=review, require_complete=True, write_log=False,
    )
    assert checked == before
    assert checked['resume_sections']['projects'][0]['detail_fact_ids'][-1] == [facts[3].fact_id]


def test_partial_fact_still_needs_coverage_and_cannot_use_literal_proof(isolated):
    _, _, _, facts, _, body = sample()
    body['resume_sections']['projects'][0]['expression_units'][-1]['text'] = '项目用于课程结课展示'
    build = generation.build_canonical_semantic_build(RAW)
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    slots.compose_model_fact_references(body, views, expression_review=review)
    assert facts[3].fact_id in review.coverage_units()
    reply = full_reply(review)
    reply['coverage'][facts[3].fact_id].update(verdict='omitted', source_excerpt='展示后没有继续运营')
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.reason_counts == {'expression_review_coverage_omitted': 1}


@pytest.mark.parametrize('long_mode', [False, True])
def test_second_writer_keeps_one_call_for_review(long_mode, monkeypatch, isolated):
    monkeypatch.delenv('MAX_LLM_CALLS_PER_ATTEMPT', raising=False)
    case, build, views, _, review, body = sample()
    sent = provider(monkeypatch, [('not json', 'stop'),
        (json.dumps(body, ensure_ascii=False), 'stop'),
        (json.dumps(full_reply(review), ensure_ascii=False), 'stop')])
    before = deepcopy(build)
    payload, info = generation.build_llm_generation(
        request(case), replace(build.long_input_context, long_input_mode=long_mode),
        consumer_views=views,
    )
    assert info['attempt'] == len(sent) == 3
    assert [row['max_tokens'] for row in sent] == [8192, 8192, 4096]
    assert payload.resume_sections.projects[0]['detail_fact_ids'][-1] == ['EXP-001-F004']
    assert build == before


def test_explicit_two_call_cap_still_refuses_unreviewed_expression(monkeypatch, isolated):
    case, build, views, _, _, body = sample()
    sent = provider(monkeypatch, [('not json', 'stop'), (json.dumps(body), 'stop')])
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=views)
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_BUDGET'
    assert len(sent) == 2


def test_three_call_limit_never_authorizes_third_writer(monkeypatch, isolated):
    monkeypatch.setenv('MAX_LLM_CALLS_PER_ATTEMPT', '3')
    case, build, views, _, _, _ = sample()
    sent = provider(monkeypatch, [('not json', 'stop')])
    with pytest.raises(generation.GenerationServiceError):
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=views)
    assert len(sent) == 2


def test_literal_proof_does_not_protect_an_overclaiming_second_unit(isolated):
    _, build, views, facts, _, body = sample()
    units = body['resume_sections']['projects'][0]['expression_units']
    units.append(dict(fact_ids=[facts[3].fact_id], position='detail', text='正式上线并服务商业客户'))
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    slots.compose_model_fact_references(body, views, expression_review=review)
    assert facts[3].fact_id not in review.coverage_units()
    reply = full_reply(review)
    key = next(key for key, row in review.pending.items() if '商业客户' in row['candidate'])
    reply['decisions'][key].update(verdict='added_claim', candidate_excerpt='服务商业客户')
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.reason_counts == {'expression_review_added_claim': 1}


def test_retry_review_can_reach_save_and_docx(monkeypatch, tmp_path, isolated):
    monkeypatch.setenv('MAX_LLM_CALLS_PER_ATTEMPT', '3')
    case, _, _, _, review, body = sample()
    outcome = deliver(monkeypatch, tmp_path, case, [('not json', 'stop'),
        (json.dumps(body, ensure_ascii=False), 'stop'),
        (json.dumps(full_reply(review), ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    assert len(outcome['sent']) == 3
    assert outcome['gates'][-1]['passed']
    project = outcome['saved']['resume_sections']['projects'][0]
    assert project['detail_fact_ids'][-1] == ['EXP-001-F004']
    assert project['detail_claim_ids'][-1] == ['EXP-001-C005']


def test_truncated_first_writer_is_not_repaired_and_can_retry(monkeypatch, isolated):
    monkeypatch.setenv('MAX_LLM_CALLS_PER_ATTEMPT', '3')
    case, build, views, _, review, body = sample()
    sent = provider(monkeypatch, [(json.dumps(body), 'length'),
        (json.dumps(body), 'stop'), (json.dumps(full_reply(review)), 'stop')])
    _, info = generation.build_llm_generation(request(case), build.long_input_context,
                                               consumer_views=views)
    assert info['attempt'] == len(sent) == 3
    assert [row['max_tokens'] for row in sent] == [8192, 8192, 4096]


@pytest.mark.parametrize('uncertain', [False, True])
def test_editorial_observation_does_not_release_major_uncertainty(uncertain, isolated):
    from test_v09194_packaging_contract import _editorial
    _, _, _, _, review, _ = sample()
    key = next(iter(review.pending))
    row = review.pending[key]
    source_id = next(iter(row['sources']))
    reply = full_reply(review)
    decision = _editorial(source_id, row['sources'][source_id], row['candidate'])
    decision['verdict'] = 'editorial_observe'
    if uncertain:
        decision['verdict'] = 'uncertain'
        decision.pop('checks')
    reply['decisions'][key] = decision
    if uncertain:
        with pytest.raises(slots.ModelEvidenceContractError) as caught:
            review.accept(reply)
        assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_UNCERTAIN'
        assert not review.accepted
    else:
        review.accept(reply)
        assert review.editorial_observed_count == 1
        assert review.review_issues[0]['verdict'] == 'editorial_observe'
        assert 'source_excerpt' not in review.review_issues[0]


def test_stale_literal_coverage_is_not_silently_accepted(isolated):
    _, _, facts, review, _ = prepared()
    reply = full_reply(review)
    reply['coverage'][facts[3].fact_id] = dict(verdict='complete', unit_ids=[facts[3].fact_id],
                                             source_excerpt=None)
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'


def test_role_caps_are_separate_and_legacy_cap_is_preserved(monkeypatch, isolated):
    from app.services import llm_service
    sent = provider(monkeypatch, [('{}', 'stop')])
    monkeypatch.setenv('LLM_MAX_TOKENS', '1234')
    monkeypatch.setenv('LLM_WRITER_MAX_TOKENS', '8192')
    monkeypatch.setenv('LLM_REVIEW_MAX_TOKENS', '4096')
    llm_service.call_openai('legacy')
    llm_service.call_openai('writer', role='writer')
    llm_service.call_openai('review', role='reviewer')
    assert [row['max_tokens'] for row in sent] == [1234, 8192, 4096]
    with pytest.raises(llm_service.LLMServiceError):
        llm_service.call_openai('unknown', role='unknown')
    assert len(sent) == 3
