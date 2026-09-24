"""Actual wire evidence and controlled verdicts; neither proves reviewer accuracy."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.services import generation_service as generation, prompt_service as prompts
from app.services import experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09174_fact_reference_composition import isolated
from test_v09192_evidence_bounded_expression import expression_sample, THIN, unit_for
from test_v09162_model_output_evidence_contract import request
from test_v09176_delivery_closure import provider, deliver

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/v091921_real_expression_returns.json').read_text(encoding='utf-8'))
RAW = FIXTURE['parameters']['raw_input']


def decision(verdict='supported', source=None, candidate=None):
    return {'verdict': verdict, 'source_fact_id': 'EXP-001-F006' if source is not None else None,
            'source_excerpt': source, 'candidate_excerpt': candidate}


def context():
    case, build, body, _ = expression_sample(RAW, rewrite=False)
    case['target_role'] = 'AI应用开发实习'
    views = build_canonical_consumer_views(build)
    receipt = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    unit_for(body['resume_sections']['projects'][0], 'EXP-001-F006')['text'] = '项目用于小组课堂展示。'
    slots.compose_model_fact_references(body, views, expression_review=receipt)
    return case, build, views, body, receipt


def evidence(text, tag):
    return json.loads(text.split('<' + tag + '>')[1].split('</' + tag + '>')[0])


def test_role_qualified_context_is_shared_without_recompilation(isolated, monkeypatch):
    case, build, views, body, receipt = context()
    before = deepcopy(build), repr(views)
    for name in ('build_experience_identities', 'build_experience_fact_ledger', 'split_experience_segments'):
        monkeypatch.setattr(prompts, name, lambda *a, **k: pytest.fail('semantic rebuild'))
    written = evidence(prompts.build_generation_prompt(request(case), consumer_views=views), 'canonical_model_evidence')
    reviewed = evidence(prompts.build_expression_review_prompt(receipt, views), 'expression_review')
    constraints = written['internal_constraints_not_resume_facts']
    assert constraints and all(c['semantic_role'] != 'STRUCTURE_MARKER' for c in constraints)
    assert written['structural_context_not_resume_facts']
    row = reviewed['EXP-001-F006']
    assert row['constraints'] == [c for c in constraints if c['source_experience_id'] == 'EXP-001']
    assert row['sources'][0]['source_span'] == [164, 175]
    assert row['owner_context']['source_experience_id'] == 'EXP-001'
    assert 'eligible_facts' not in row['owner_context']
    assert (build, repr(views)) == before


def test_rejection_has_exact_redacted_ranges_and_no_receipt(isolated):
    _, _, _, _, receipt = context()
    reply = {'decisions': {'EXP-001-F006': decision('changed_qualification', '只用于', '用于')}}
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        receipt.accept(reply)
    assert caught.value.code == 'MODEL_EXPRESSION_REJECTED'
    assert receipt.review_issues == [{
        'fact_id': 'EXP-001-F006', 'source_experience_id': 'EXP-001',
        'source_fact_id': 'EXP-001-F006', 'source_fact_ids': ['EXP-001-F006'],
        'verdict': 'changed_qualification', 'source_span': [2, 5], 'candidate_span': [2, 4],
    }]
    assert not receipt.accepted
    assert '用于' not in json.dumps(receipt.review_issues, ensure_ascii=False)


@pytest.mark.parametrize('reply', [
    {'verdict': 'supported', 'source_excerpt': '只', 'candidate_excerpt': None},
    {'verdict': 'added_claim', 'source_excerpt': None, 'candidate_excerpt': '不存在的片段'},
    {'verdict': 'changed_qualification', 'source_excerpt': '只', 'candidate_excerpt': None},
    {'verdict': 'uncertain', 'source_excerpt': None, 'candidate_excerpt': None},
    {'verdict': 'omitted_fact', 'source_excerpt': '', 'candidate_excerpt': None},
    {'verdict': 'omitted_fact', 'source_excerpt': 2, 'candidate_excerpt': None},
    {'verdict': 'supported', 'source_excerpt': None, 'candidate_excerpt': None, 'text': 'replacement'},
    'supported',
])
def test_invalid_or_unlocalized_review_fails_closed(reply, isolated):
    _, _, _, _, receipt = context()
    if isinstance(reply, dict):
        reply = dict(reply, source_fact_id='EXP-001-F006' if reply.get('source_excerpt') is not None else None)
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        receipt.accept({'decisions': {'EXP-001-F006': reply}})
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'
    assert not receipt.accepted


@pytest.mark.parametrize('long', [False, True])
def test_sent_contract_shares_expression_scope_and_retries_evidence(long, isolated, monkeypatch):
    case, build, views, body, receipt = context()
    literal = expression_sample(RAW, rewrite=False)[2]
    bad = deepcopy(literal)
    bad['resume_sections']['projects'][0]['expression_units'].pop()
    sent = provider(monkeypatch, [(json.dumps(bad), 'stop'), (json.dumps(literal), 'stop')])
    generation.build_llm_generation(request(case), replace(build.long_input_context, long_input_mode=long), consumer_views=views)
    assert len(sent) == 2
    for tag in ('canonical_model_evidence', 'canonical_model_output_contract'):
        assert evidence(sent[0]['messages'][1]['content'], tag) == evidence(sent[1]['messages'][1]['content'], tag)
    scope = evidence(sent[0]['messages'][1]['content'], 'canonical_model_output_contract')['expression_scope']
    review_scope = evidence(prompts.build_expression_review_prompt(receipt, views), 'expression_scope')
    assert scope == review_scope


def test_preserving_rewrite_saves_with_real_pipeline_controlled_review(isolated, monkeypatch, tmp_path):
    case, build, views, body, receipt = context()
    p = body['resume_sections']['projects'][0]
    unit_for(p, 'EXP-001-F006')['text'] = '该项目的使用范围限于小组课堂展示。'
    unit_for(p, 'EXP-001-F005')['text'] = '围绕12个常见问题，逐项记录回答与资料内容是否一致，将发现的不一致情况反馈给负责检索部分的同学。'
    slots.compose_model_fact_references(body, views, expression_review=receipt)
    reply = {'decisions': {fid: decision() for fid in receipt.pending}}
    before = deepcopy(build), repr(views)
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop'), (json.dumps(reply), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome
    text = json.dumps(outcome['saved']['resume_sections']['projects'], ensure_ascii=False)
    assert '使用范围限于小组课堂展示' in text and '12个常见问题' in text
    assert (build, repr(views)) == before


@pytest.mark.parametrize('run', [0, 1])
def test_recorded_legacy_review_is_not_guessed_as_new_protocol(run, isolated, monkeypatch, tmp_path):
    case = FIXTURE['parameters']
    outcome = deliver(monkeypatch, tmp_path, case, [(FIXTURE['writer_returns'][run], 'stop'), (FIXTURE['review_returns'][run], 'stop')])
    # The untouched historical writer now fails before its old reviewer is consumed.
    assert outcome.get('error') == 'MODEL_OUTPUT_CONTRACT_INVALID'
    assert outcome['results'] == 0 and not list(tmp_path.glob('*.docx'))


@pytest.mark.parametrize('verdict,source,candidate,code', [
    ('omitted_fact', '只用于', None, 'MODEL_EXPRESSION_REJECTED'),
    ('added_claim', None, '项目用于小组课堂展示', 'MODEL_EXPRESSION_REJECTED'),
    ('changed_qualification', '只用于', '用于', 'MODEL_EXPRESSION_REJECTED'),
    ('uncertain', '只用于', None, 'MODEL_EXPRESSION_REVIEW_UNCERTAIN'),
])
def test_real_receiving_failure_logs_locations_not_text(verdict, source, candidate, code, isolated, monkeypatch, tmp_path):
    case, _, _, body, _ = context()
    log_dir = tmp_path / 'logs'
    log_dir.mkdir()
    monkeypatch.setattr(generation, 'LOG_DIR', log_dir)
    reply = {'decisions': {'EXP-001-F006': decision(verdict, source, candidate)}}
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body), 'stop'), (json.dumps(reply), 'stop')])
    assert outcome['error'] == code and outcome['results'] == 0
    rows = [json.loads(line) for line in (log_dir / 'llm_calls.jsonl').read_text(encoding='utf-8').splitlines()]
    row = next(r for r in rows if r.get('stage') == 'generation_expression_review_validated')
    assert row['review_protocol'] == 'canonical_expression_review_v4'
    assert row['review_issues'][0]['fact_id'] == 'EXP-001-F006'
    assert row['review_issues'][0]['verdict'] == verdict
    assert row['request_id'] and row['attempt_id']
    assert '课堂' not in json.dumps(row, ensure_ascii=False)
    assert len(outcome['sent']) == 2 and not list(tmp_path.glob('*.docx'))


@pytest.mark.parametrize('field', ['verdict', 'source_excerpt', 'candidate_excerpt'])
def test_duplicate_review_object_keys_rejected(field, isolated):
    _, _, _, _, receipt = context()
    wire = json.dumps({'decisions': {'EXP-001-F006': decision()}})
    wire = wire.replace('"' + field + '":', '"' + field + '":null,"' + field + '":', 1)
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        receipt.accept(json.loads(wire, object_pairs_hook=slots.ModelJSONObject))
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'
    assert not receipt.accepted


def test_ambiguous_anchor_not_resolved_by_first_occurrence(isolated):
    _, _, _, _, receipt = context()
    receipt.candidates['EXP-001-F006']['candidate'] = '课堂展示，课堂展示'
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        receipt.accept({'decisions': {'EXP-001-F006': decision('added_claim', None, '课堂展示')}})
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'


def test_new_failed_assessment_invalidates_old_receipt(isolated):
    _, _, _, _, receipt = context()
    receipt.accept({'decisions': {'EXP-001-F006': decision()}})
    assert receipt.accepted
    with pytest.raises(slots.ModelEvidenceContractError):
        receipt.accept({'decisions': {'EXP-001-F006': 'supported'}})
    assert not receipt.accepted and not receipt.review_issues


@pytest.mark.parametrize('position', ['intro', 'role', 'detail'])
def test_broad_rewrite_keeps_field_lineage(position, isolated, monkeypatch):
    case, build, body, _ = expression_sample(THIN, rewrite=False, position=position)
    views = build_canonical_consumer_views(build)
    receipt = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    project = body['resume_sections']['projects'][0]
    fact = next(f for f in build.ledger.facts if f.resume_ready_text == '我帮忙测试')
    unit_for(project, fact.fact_id)['text'] = '参与项目的测试工作。'
    reply = {'decisions': {fact.fact_id: decision()}}
    sent = provider(monkeypatch, [(json.dumps(body), 'stop'), (json.dumps(reply), 'stop')])
    before = deepcopy(build), repr(views)
    payload, _ = generation.build_llm_generation(request(case), build.long_input_context, consumer_views=views, expression_review=receipt)
    validated = slots.validate_model_project_evidence(payload, views, expression_review=receipt, require_complete=True)
    p = validated.resume_sections.projects[0]
    if position == 'detail':
        index = p['details'].index('参与项目的测试工作。')
        assert p['detail_fact_ids'][index] == [fact.fact_id]
        assert p['detail_claim_ids'][index] == [fact.claim_id]
    else:
        assert '参与项目的测试工作' in p[position]
        assert fact.fact_id in p[position + '_source_fact_ids']
        assert fact.claim_id in p[position + '_source_claim_ids']
    assert len(sent) == 2 and (build, repr(views)) == before


@pytest.mark.parametrize('case_key,start,expected', [
    ('complex', 0, 'MODEL_OUTPUT_TRUNCATED'),
    ('thin', 2, 'MODEL_OUTPUT_CONTRACT_INVALID'),
])
def test_actual_acceptance_returns_remain_release_blockers(case_key, start, expected, isolated, monkeypatch, tmp_path):
    # Replaying actual responses establishes behavior, not correctness of model judgments.
    captured = json.loads((Path(__file__).parent / 'fixtures/v091921_acceptance_returns.json').read_text(encoding='utf-8'))
    replies = [(r['content'], r['finish_reason']) for r in captured['responses'][start:start + 2]]
    outcome = deliver(monkeypatch, tmp_path, captured[case_key], replies)
    assert outcome['error'] == expected
    assert outcome['results'] == 0 and not list(tmp_path.glob('*.docx'))
    assert len(outcome['sent']) == 2 and not outcome['gates']
    if case_key == 'thin':
        parsed = json.loads(replies[1][0])
        assert parsed['decisions']['EXP-001-F002'] == {k: v for k, v in decision('added_claim', None, '负责网站页面的开发与实现。').items() if k != 'source_fact_id'}
        assert parsed['decisions']['EXP-001-F003'] == {k: v for k, v in decision('changed_qualification', '我帮忙测试', '参与项目功能测试工作。').items() if k != 'source_fact_id'}
