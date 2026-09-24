"""Cross-field reuse must not turn a Fact ID into a reusable review receipt."""
from copy import deepcopy
import json

import pytest
from docx import Document

from app.services import experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09193_evidence_bounded_composition import composition_sample, decision, coverage_reply
from test_v09176_delivery_closure import deliver
from test_v09174_fact_reference_composition import isolated


def sample():
    _, build, body = composition_sample(position='detail', combine=False)
    project = body['resume_sections']['projects'][0]
    units = project['expression_units']
    project['expression_units'] = [
        {'fact_ids': units[0]['fact_ids'] + units[1]['fact_ids'],
         'position': 'intro',
         'text': units[0]['text'].rstrip('。；;') + '；' + units[1]['text'].rstrip('。；;')},
        *units,
    ]
    return build, body


def prepare(build, body):
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    composed = slots.compose_model_fact_references(body, views, expression_review=review)
    review.accept(coverage_reply(review, {key: decision() for key in review.pending}))
    return views, review, composed


def test_complete_cross_field_reuse_preserves_lineage():
    build, body = sample()
    views, review, composed = prepare(build, body)
    checked = slots.validate_model_project_evidence(
        composed, views, expression_review=review, require_complete=True, write_log=False)
    project = checked['resume_sections']['projects'][0]
    intro_ids = project['intro_source_fact_ids']
    assert intro_ids == [row[0] for row in project['detail_fact_ids'][:2]]
    assert project['intro_source_claim_ids'] == list(dict.fromkeys(
        row[0] for row in project['detail_claim_ids'][:2]))
    assert len(project['source_fact_ids']) == len(set(project['source_fact_ids']))


def test_reused_fact_requires_distinct_review_receipts():
    build, body = sample()
    project = body['resume_sections']['projects'][0]
    project['expression_units'][0]['text'] += '候选改写'
    project['expression_units'][1]['text'] += '另一个候选改写'
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    composed = slots.compose_model_fact_references(body, views, expression_review=review)
    assert len(review.pending) == 2
    assert len(set(review.pending)) == 2
    review.accept(coverage_reply(review, {key: decision() for key in review.pending}))
    slots.validate_model_project_evidence(composed, views, expression_review=review,
                                          require_complete=True, write_log=False)
    changed = deepcopy(composed)
    changed['resume_sections']['projects'][0]['details'][0] += '新增结果'
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.validate_model_project_evidence(changed, views, expression_review=review,
                                              require_complete=True, write_log=False)


def test_same_intro_overlap_rejected():
    build, body = sample()
    units = body['resume_sections']['projects'][0]['expression_units']
    units[1]['position'] = 'intro'
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.compose_model_fact_references(body, views, expression_review=review)


def test_cross_field_reuse_saves_with_exact_attachments(monkeypatch, tmp_path, isolated):
    case, build, _ = composition_sample(position='detail', combine=False)
    _, body = sample()
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    project = outcome['saved']['resume_sections']['projects'][0]
    facts = {fact.fact_id: fact for fact in build.ledger.facts}
    assert project['intro_source_fact_ids'] == [row[0] for row in project['detail_fact_ids'][:2]]
    for ids, claims in zip(project['detail_fact_ids'], project['detail_claim_ids'], strict=True):
        assert claims == list(dict.fromkeys(facts[fid].claim_id for fid in ids))
    assert all(fact.resume_ready_text.rstrip('。；;') in '\n'.join(
        paragraph.text for paragraph in Document(next(tmp_path.glob('*.docx'))).paragraphs)
        for fact in build.ledger.facts)


def test_reused_source_reviewed_independently_through_delivery(monkeypatch, tmp_path, isolated):
    case, build, _ = composition_sample(position='detail', combine=False)
    _, body = sample()
    units = body['resume_sections']['projects'][0]['expression_units']
    units[0]['text'] = units[0]['text'].replace('和FastAPI', '与FastAPI')
    units[1]['text'] = units[1]['text'].replace('和FastAPI', '及FastAPI')
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    slots.compose_model_fact_references(body, views, expression_review=review)
    assert len(review.pending) == 2
    reply = coverage_reply(review, {key: decision() for key in review.pending})
    outcome = deliver(monkeypatch, tmp_path, case, [
        (json.dumps(body, ensure_ascii=False), 'stop'), (json.dumps(reply), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    assert len(outcome['sent']) == 2
    project = outcome['saved']['resume_sections']['projects'][0]
    assert project['intro_source_fact_ids'][0] == project['detail_fact_ids'][0][0]


def test_review_mapping_cannot_reuse_one_decision_for_two_units():
    build, body = sample()
    units = body['resume_sections']['projects'][0]['expression_units']
    units[0]['text'] += '候选改写'
    units[1]['text'] += '另一候选改写'
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    slots.compose_model_fact_references(body, views, expression_review=review)
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(coverage_reply(review, {next(iter(review.pending)): decision()}))
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'


@pytest.mark.parametrize('kind', ['missing', 'foreign', 'unsupported', 'repeat_inside', 'old'])
def test_reuse_does_not_hide_invalid_evidence(kind):
    build, body = sample()
    units = body['resume_sections']['projects'][0]['expression_units']
    if kind == 'missing':
        body['resume_sections']['projects'][1]['expression_units'].pop()
    elif kind == 'foreign':
        units[0]['fact_ids'][0] = body['resume_sections']['projects'][1]['expression_units'][0]['fact_ids'][0]
    elif kind == 'unsupported':
        units[0]['text'] += '独立设计检索架构'
    elif kind == 'repeat_inside':
        units[0]['fact_ids'].append(units[0]['fact_ids'][0])
    else:
        body['resume_sections']['projects'][0]['fact_placements'] = {}
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    if kind == 'unsupported':
        composed = slots.compose_model_fact_references(body, views, expression_review=review)
        assert review.pending
        key = next(key for key, row in review.pending.items() if row['candidate'].endswith('独立设计检索架构'))
        with pytest.raises(slots.ModelEvidenceContractError) as caught:
            review.accept(coverage_reply(review, {k: decision('added_claim', candidate='独立设计检索架构')
                                         if k == key else decision() for k in review.pending}))
        assert caught.value.code == 'MODEL_EXPRESSION_REJECTED'
    else:
        with pytest.raises(slots.ModelEvidenceContractError):
            slots.compose_model_fact_references(body, views, expression_review=review)
