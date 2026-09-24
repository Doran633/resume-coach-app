"""Version completeness is checked before defaults, not inferred from saved text."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from app.services import generation_service as generation
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09162_model_output_evidence_contract import request
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import provider, deliver
from test_v09192_evidence_bounded_expression import expression_sample, THIN
from test_v09193_evidence_bounded_composition import review_reply


VERSIONS = {
    'normal_version': '使用Vue制作课程展示网站，制作页面并协助测试。',
    'bold_version': '围绕课程展示网站开展Vue页面制作与测试协助。',
    'boundary_version': '风险边界：测试协助不等于独立制定测试方案。',
    'recommended_version': '使用Vue制作课程展示网站，承担页面制作并协助测试。',
}


def sample():
    case, build, body, _ = expression_sample(THIN, rewrite=False)
    body.update(VERSIONS)
    return case, build, body


def receive(monkeypatch, replies, *, long=False):
    case, build, _ = sample()
    views = build_canonical_consumer_views(build)
    before = deepcopy(build), repr(views)
    sent = provider(monkeypatch, [(reply, 'stop') for reply in replies])
    try:
        result = generation.build_llm_generation(request(case),
            replace(build.long_input_context, long_input_mode=long), consumer_views=views)
        return result, sent
    finally:
        assert len(sent) <= 2
        assert (build, repr(views)) == before


@pytest.mark.parametrize('field', VERSIONS)
@pytest.mark.parametrize('kind', ['missing', 'empty', 'whitespace', 'null', 'array', 'object', 'duplicate'])
def test_raw_invalid_version_is_not_normalized_into_success(field, kind, monkeypatch, isolated):
    _, _, body = sample()
    if kind == 'missing':
        del body[field]
    elif kind != 'duplicate':
        body[field] = {'empty': '', 'whitespace': ' \n ', 'null': None, 'array': ['text'], 'object': {'text': 'text'}}[kind]
    text = json.dumps(body, ensure_ascii=False)
    if kind == 'duplicate':
        text = '{' + json.dumps(field) + ':"first",' + text[1:]
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, [text])
    assert caught.value.code == 'MODEL_OUTPUT_CONTRACT_INVALID'


@pytest.mark.parametrize('long', [False, True])
def test_actual_schema_and_corrected_retry_preserve_short_versions(long, monkeypatch, isolated):
    _, _, good = sample()
    bad = deepcopy(good)
    for key in VERSIONS:
        del bad[key]
    (payload, stats), sent = receive(monkeypatch, [json.dumps(bad), json.dumps(good)], long=long)
    assert len(sent) == stats['attempt'] == 2
    assert {k: getattr(payload, k) for k in VERSIONS} == VERSIONS
    for call in sent:
        text = call['messages'][1]['content']
        schema = text.split('JSON 顶层字段必须完整包含：', 1)[1].split('\n\n', 1)[0]
        assert all('- ' + key + ':' in schema for key in VERSIONS)


def test_missing_versions_never_save_or_fallback(monkeypatch, tmp_path, isolated):
    case, _, body = sample()
    for key in VERSIONS:
        del body[key]
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body), 'stop')])
    assert outcome['error'] == 'MODEL_OUTPUT_CONTRACT_INVALID'
    assert outcome['results'] == 0 and len(outcome['sent']) == 2
    assert not list(tmp_path.glob('*.docx'))


def test_short_valid_versions_are_not_replaced_by_old_derivations(monkeypatch, tmp_path, isolated):
    case, build, body = sample()
    before = deepcopy(body)
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome
    for field, expected in VERSIONS.items():
        assert outcome['saved'][field].rstrip('。') == expected.rstrip('。')
    serialized = json.dumps(outcome['saved'], ensure_ascii=False)
    assert '问题定位与交付质量保障' not in serialized
    assert body == before
    project = outcome['saved']['resume_sections']['projects'][0]
    assert set(project['source_fact_ids']) == {f.fact_id for f in build.ledger.facts}
    assert '我帮忙测试' in project['details']


def test_format_retry_leaves_no_third_call_for_rewrite_review(monkeypatch, isolated):
    _, _, good = sample()
    bad = deepcopy(good)
    del bad['normal_version']
    for item in good['resume_sections']['projects'][0]['expression_units']:
        if item['text'] == '我帮忙测试':
            item['text'] = '协助开展测试工作。'
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, [json.dumps(bad), json.dumps(good)])
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_BUDGET'


def test_missing_then_json_error_does_not_enter_parse_fallback(monkeypatch, isolated):
    _, _, body = sample()
    del body['recommended_version']
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, [json.dumps(body), 'not-json'])
    assert caught.value.code == 'MODEL_OUTPUT_CONTRACT_INVALID'


def test_short_versions_survive_reviewed_project_expression(monkeypatch, tmp_path, isolated):
    case, build, body = sample()
    fact = next(f for f in build.ledger.facts if f.resume_ready_text == '我帮忙测试')
    next(u for u in body['resume_sections']['projects'][0]['expression_units'] if u['fact_ids'] == [fact.fact_id])['text'] = '协助开展测试工作。'
    review = review_reply(build, body, {fact.fact_id: {
        'verdict': 'supported', 'source_fact_id': None, 'source_excerpt': None, 'candidate_excerpt': None,
    }})
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body), 'stop'), (json.dumps(review), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome and len(outcome['sent']) == 2
    assert {key: outcome['saved'][key].rstrip('。') for key in VERSIONS} == {
        key: value.rstrip('。') for key, value in VERSIONS.items()
    }
    project = outcome['saved']['resume_sections']['projects'][0]
    index = project['details'].index('协助开展测试工作')
    assert project['detail_fact_ids'][index] == [fact.fact_id]
    assert project['detail_claim_ids'][index] == [fact.claim_id]


def test_independent_legacy_receiver_keeps_default_and_duplicate_compatibility(monkeypatch, isolated):
    case, build, _ = sample()
    body = generation.build_mock_generation(request(case)).model_dump()
    body['normal_version'] = ''
    text = '{"normal_version":"first",' + json.dumps(body)[1:]
    sent = provider(monkeypatch, [(text, 'stop')])
    payload, stats = generation.build_llm_generation(request(case), build.long_input_context)
    assert payload.normal_version == '' and len(sent) == stats['attempt'] == 1
