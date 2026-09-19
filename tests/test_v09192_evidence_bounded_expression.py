"""Network controls validate wiring, not the accuracy of a real semantic reviewer."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from docx import Document

from app import schemas
from app.services import generation_service as generation, experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09174_fact_reference_composition import isolated
from test_v09172_initial_evidence_preservation import detail_return
from test_v09162_model_output_evidence_contract import request
from test_v09176_delivery_closure import provider, deliver
from test_v0916_canonical_model_evidence import evidence
from test_v091851_semantic_unit_boundary import RAW_INPUT

THIN = '个人项目：课程展示网站\n2026年5月，使用Vue制作课程展示网站。我做了页面。我帮忙测试。'
LIMITED = '课程项目：设备登记系统\n2026年4月，在三人小组中只负责前端页面。使用Vue实现设备列表和登记表单。系统仅在本地演示，没有真实用户。'


def expression_sample(raw=THIN, *, rewrite=True, position='detail'):
    case, build, data = detail_return(raw)
    projects = []
    changed = {}
    for owner in build_canonical_consumer_views(build).experience_ids:
        placements = {}
        for f in build.ledger.for_experience(owner):
            text = f.resume_ready_text
            if rewrite:
                candidate = text.replace('我帮忙测试', '参与测试工作').replace('只负责', '仅负责').replace('协助排查', '协助定位与排查')
                if candidate != text:
                    changed[f.fact_id] = 'supported'
                    text = candidate
            placements[f.fact_id] = {'position': position, 'text': text}
        projects.append({'source_experience_id': owner, 'fact_placements': placements})
    data['resume_sections']['projects'] = projects
    data['resume_sections']['summary'] = ['具备项目实践经历。']
    for key in ('normal_version', 'bold_version', 'boundary_version', 'recommended_version'):
        data[key] = ''
    return case, build, data, {'decisions': changed}


def receive(monkeypatch, case, build, replies, *, long=False, review=None):
    views = build_canonical_consumer_views(build)
    before = deepcopy(build), repr(views)
    sent = provider(monkeypatch, [(json.dumps(r, ensure_ascii=False) if not isinstance(r, str) else r, 'stop') for r in replies])
    kwargs = {'expression_review': review} if review is not None else {}
    try:
        payload, stats = generation.build_llm_generation(request(case), replace(build.long_input_context, long_input_mode=long), consumer_views=views, **kwargs)
        return payload, stats, sent
    finally:
        assert (build, repr(views)) == before


@pytest.mark.parametrize('raw', [RAW_INPUT, THIN, LIMITED], ids=['normal', 'thin', 'limited'])
@pytest.mark.parametrize('position', ['intro', 'role', 'detail'])
def test_reviewed_expression_keeps_lineage_and_frozen_evidence(raw, position, monkeypatch, isolated):
    case, build, data, review = expression_sample(raw, position=position)
    payload, stats, sent = receive(monkeypatch, case, build, [data, review])
    assert len(sent) == stats['attempt'] == 2
    assert 'canonical_fact_expressions_v1' in sent[0]['messages'][1]['content']
    assert 'expression_review' in sent[1]['messages'][1]['content']
    for f in build.ledger.facts:
        p = next(p for p in payload.resume_sections.projects if p['source_experience_id'] == f.experience_id)
        assert f.fact_id in p['source_fact_ids'] and f.claim_id in p['source_claim_ids']
        text = data['resume_sections']['projects'][int(f.experience_id.split('-')[1])-1]['fact_placements'][f.fact_id]['text']
        assert text.rstrip('。；;') in json.dumps(p, ensure_ascii=False)


@pytest.mark.parametrize('long', [False, True])
def test_literal_echo_needs_only_writer(long, monkeypatch, isolated):
    case, build, data, _ = expression_sample(rewrite=False)
    _, stats, sent = receive(monkeypatch, case, build, [data], long=long)
    assert len(sent) == stats['attempt'] == 1


@pytest.mark.parametrize('verdict', ['added_claim', 'omitted_fact', 'changed_qualification', 'uncertain', 'invalid'])
def test_reviewer_rejection_is_not_rewritten_or_downgraded(verdict, monkeypatch, isolated):
    case, build, data, review = expression_sample()
    for fid in review['decisions']:
        review['decisions'][fid] = verdict
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, case, build, [data, review])
    assert caught.value.code.startswith('MODEL_')


def test_format_retry_cannot_create_third_review_call(monkeypatch, isolated):
    case, build, data, _ = expression_sample()
    bad = deepcopy(data)
    bad['resume_sections']['projects'][0]['fact_placements'].popitem()
    sent = provider(monkeypatch, [(json.dumps(bad, ensure_ascii=False), 'stop'), (json.dumps(data, ensure_ascii=False), 'stop')])
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert len(sent) == 2
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_BUDGET'
    assert evidence(sent[0]['messages'][1]['content']) == evidence(sent[1]['messages'][1]['content'])


def test_thin_reviewed_body_survives_to_docx_without_old_expansion(monkeypatch, tmp_path, isolated):
    case, build, data, review = expression_sample()
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(data, ensure_ascii=False), 'stop'), (json.dumps(review), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    text = json.dumps(outcome['saved']['resume_sections']['projects'], ensure_ascii=False)
    assert '参与测试工作' in text and '我做了页面' in text
    assert '问题定位' not in text and '交付质量保障' not in text
    rows = [p.text for p in Document(next(tmp_path.glob('*.docx'))).paragraphs]
    assert any('参与测试工作' in row for row in rows)


def test_legacy_placement_strings_are_rejected(monkeypatch, isolated):
    case, build, data, _ = expression_sample(rewrite=False)
    for p in data['resume_sections']['projects']:
        p['fact_placements'] = {fid: v['position'] for fid, v in p['fact_placements'].items()}
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, case, build, [data])
    assert caught.value.code == 'MODEL_EVIDENCE_FORMAT'


@pytest.mark.parametrize('kind', ['missing', 'extra', 'duplicate', 'replacement', 'wrong_shape', 'invalid_json'])
def test_review_mapping_must_be_exact(kind, monkeypatch, isolated):
    case, build, data, review = expression_sample()
    fid = next(iter(review['decisions']))
    if kind == 'missing':
        review['decisions'].pop(fid)
    elif kind == 'extra':
        review['decisions']['EXP-999-F001'] = 'supported'
    elif kind == 'replacement':
        review['text'] = '替代正文'
    elif kind == 'wrong_shape':
        review['decisions'][fid] = {'verdict': 'supported'}
    elif kind == 'invalid_json':
        review = json.dumps(review)[:-1]
    else:
        review = '{"decisions":{"%s":"supported","%s":"added_claim"}}' % (fid, fid)
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, case, build, [data, review])
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'


@pytest.mark.parametrize('finish', ['length', None, 'unknown'])
def test_review_abnormal_finish_never_repairs_or_retries(finish, monkeypatch, isolated):
    case, build, data, review = expression_sample()
    sent = provider(monkeypatch, [(json.dumps(data), 'stop'), (json.dumps(review), finish)])
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert len(sent) == 2
    assert caught.value.code in ('MODEL_OUTPUT_TRUNCATED', 'MODEL_FINISH_INVALID')


def test_supported_receipt_is_request_and_text_bound(monkeypatch, isolated):
    case, build, data, reply = expression_sample()
    views = build_canonical_consumer_views(build)
    receipt = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    payload, _, _ = receive(monkeypatch, case, build, [data, reply], review=receipt)
    original = payload.model_dump()
    verified = slots.validate_model_project_evidence(payload, views, expression_review=receipt, require_complete=True)
    assert verified.resume_sections.projects == original['resume_sections']['projects']
    _, another_build, _, _ = expression_sample()
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.validate_model_project_evidence(payload, build_canonical_consumer_views(another_build), expression_review=receipt, require_complete=True)
    modified = payload.model_copy(deep=True)
    modified.resume_sections.projects[0]['details'][-1] += '，独立负责系统架构'
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation._check_final_expression_evidence(modified, views, receipt, 'test')
    assert caught.value.code == 'DELIVERY_EXPRESSION_CHANGED'
    assert payload.model_dump() == original


@pytest.mark.parametrize('candidate,verdict', [
    ('独立负责整体系统设计与实现', 'added_claim'),
    ('在三人小组中负责前端页面', 'changed_qualification'),
    ('具备系统开发能力', 'omitted_fact'),
])
def test_controlled_review_rejection_prevents_save(candidate, verdict, monkeypatch, tmp_path, isolated):
    case, build, data, reply = expression_sample(LIMITED, rewrite=False)
    project = data['resume_sections']['projects'][0]
    fid = next(f.fact_id for f in build.ledger.facts if '只负责' in f.resume_ready_text)
    project['fact_placements'][fid]['text'] = candidate
    reply = {'decisions': {fid: verdict}}
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(data), 'stop'), (json.dumps(reply), 'stop')])
    assert outcome['results'] == 0 and 'docx' not in outcome
    assert outcome['error'] == 'MODEL_EXPRESSION_REJECTED'
    assert len(outcome['sent']) == 2


def test_retry_with_literal_body_uses_two_calls_no_review(monkeypatch, isolated):
    case, build, data, _ = expression_sample(rewrite=False)
    bad = deepcopy(data)
    bad['resume_sections']['projects'][0]['fact_placements'].popitem()
    _, stats, sent = receive(monkeypatch, case, build, [bad, data])
    assert len(sent) == stats['attempt'] == 2


@pytest.mark.parametrize('kind', ['text_key', 'position_key', 'fact_key'])
def test_duplicate_expression_keys_rejected_before_overwrite(kind, monkeypatch, isolated):
    case, build, data, _ = expression_sample(rewrite=False)
    encoded = json.dumps(data, ensure_ascii=False)
    if kind == 'text_key':
        encoded = encoded.replace('"text":', '"text":"伪造正文","text":', 1)
    elif kind == 'position_key':
        encoded = encoded.replace('"position":', '"position":"intro","position":', 1)
    else:
        fid = next(iter(data['resume_sections']['projects'][0]['fact_placements']))
        encoded = encoded.replace('"'+fid+'":', '"'+fid+'":{"position":"detail","text":"伪造正文"},"'+fid+'":', 1)
    with pytest.raises(generation.GenerationServiceError):
        receive(monkeypatch, case, build, [encoded])


@pytest.mark.parametrize('raw', [RAW_INPUT, LIMITED])
def test_normal_and_qualified_reviewed_payload_save_docx(raw, monkeypatch, tmp_path, isolated):
    case, build, data, reply = expression_sample(raw)
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(data), 'stop'), (json.dumps(reply), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome.get('error')
    all_ids = {fid for p in outcome['saved']['resume_sections']['projects'] for fid in p['source_fact_ids']}
    assert all_ids == set(build_canonical_consumer_views(build).eligible_fact_ids)
    if raw == LIMITED:
        text = json.dumps(outcome['saved']['resume_sections']['projects'], ensure_ascii=False)
        assert '仅负责' in text and '本地' in text


def test_holdout_full_pipeline_preserves_team_scope(monkeypatch, tmp_path, isolated):
    raw = ('个人项目：阅读进度记录工具\n2026年3月，和同学一起使用Python制作阅读进度记录工具。'
           '我协助整理书目文件，按照同学提供的格式登记阅读日期。工具仅供两人使用。')
    case, build, data, reply = expression_sample(raw, rewrite=False)
    fid = next(f.fact_id for f in build.ledger.facts if '我协助整理' in f.resume_ready_text)
    value = data['resume_sections']['projects'][0]['fact_placements'][fid]
    value['text'] = value['text'].replace('我协助整理', '协助整理')
    reply = {'decisions': {fid: 'supported'}}
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(data), 'stop'), (json.dumps(reply), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome.get('error')
    text = json.dumps(outcome['saved']['resume_sections']['projects'], ensure_ascii=False)
    assert '仅供两人使用' in text and '协助整理' in text and '独立' not in text


@pytest.mark.parametrize('count', [1, 6])
def test_all_fact_keys_retained_with_nine_details(count, monkeypatch, isolated):
    raw = '\n\n'.join(
        f'个人项目：资料归档工具{n}\n2026年3月，使用Python制作资料归档工具{n}。'
        + ''.join(f'编写第{i}类文件的校验脚本，记录{i+2}条检查结果。' for i in range(1, 10))
        for n in range(1, count+1))
    case, build, data, _ = expression_sample(raw, rewrite=False)
    payload, _, _ = receive(monkeypatch, case, build, [data])
    assert len(payload.resume_sections.projects) == count
    for project in payload.resume_sections.projects:
        facts = build.ledger.for_experience(project['source_experience_id'])
        assert len(project['details']) >= 9
        assert project['detail_fact_ids'] == [[f.fact_id] for f in sorted(facts, key=lambda f: f.source_span)]
        assert project['detail_claim_ids'] == [[f.claim_id] for f in sorted(facts, key=lambda f: f.source_span)]


def test_single_call_budget_does_not_release_unreviewed_expression(monkeypatch, isolated):
    monkeypatch.setenv('MAX_LLM_CALLS_PER_ATTEMPT', '1')
    case, build, data, reply = expression_sample()
    sent = provider(monkeypatch, [(json.dumps(data), 'stop'), (json.dumps(reply), 'stop')])
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_BUDGET'
    assert len(sent) == 1


def test_review_timeout_does_not_retry_or_fallback(monkeypatch, isolated):
    import urllib.request
    case, build, data, reply = expression_sample()
    sent = provider(monkeypatch, [(json.dumps(data), 'stop')])
    real_control = urllib.request.urlopen
    calls = []

    def timeout_second(req, **kwargs):
        calls.append(req)
        if len(calls) == 2:
            raise TimeoutError('controlled review timeout')
        return real_control(req, **kwargs)

    monkeypatch.setattr(urllib.request, 'urlopen', timeout_second)
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_FAILED'
    assert len(calls) == 2 and len(sent) == 1


def test_invalid_schema_after_review_cannot_use_third_call(monkeypatch, isolated):
    case, build, data, reply = expression_sample()
    data['completeness_score'] = 'not-an-integer'
    sent = provider(monkeypatch, [(json.dumps(data), 'stop'), (json.dumps(reply), 'stop')])
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert len(sent) == 2
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'


def test_same_expression_in_different_owners_needs_separate_reviews(monkeypatch, isolated):
    raw = ('个人项目：课程展示网站\n2026年5月，使用Vue制作课程展示网站。我帮忙测试。\n\n'
           '课程项目：阅读进度网站\n2026年6月，使用Vue制作阅读进度网站。我帮忙测试。')
    case, build, data, reply = expression_sample(raw)
    assert len(reply['decisions']) == 2
    payload, _, _ = receive(monkeypatch, case, build, [data, reply])
    for project in payload.resume_sections.projects:
        facts = build.ledger.for_experience(project['source_experience_id'])
        assert set(project['source_fact_ids']) == {f.fact_id for f in facts}
        assert '参与测试工作' in project['details']
    reply['decisions'].popitem()
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, case, build, [data, reply])
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'
