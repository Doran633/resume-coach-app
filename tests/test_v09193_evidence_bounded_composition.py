"""Controlled network tests prove wiring, not probabilistic reviewer accuracy."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
from docx import Document

from app.services import generation_service as generation, experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09172_initial_evidence_preservation import detail_return, detail_input, project_input
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import provider, deliver
from test_v09162_model_output_evidence_contract import request

RAW = ('个人项目：课程资料检索助手\n2026年4月至6月，使用Python和FastAPI开发课程资料检索助手，实现文件上传、关键词检索和查询结果展示。'
       '整理45份课程资料，记录课程名称。项目仅用于小组课堂展示。\n\n'
       '课程项目：设备借用页面\n2026年3月，在三人小组中只负责使用Vue制作设备列表和登记表单。根据同学提供的接口完成页面联调。')


def composition_sample(raw=RAW, position='detail', combine=True):
    case, build, body = detail_return(raw)
    views = build_canonical_consumer_views(build)
    projects = []
    for owner in views.experience_ids:
        facts = sorted(views.facts_for_owner(owner), key=lambda f: f.source_span)
        units = [{'fact_ids': [f.fact_id], 'position': position, 'text': f.resume_ready_text} for f in facts]
        if combine and len(units) > 1:
            first, second = units[:2]
            first['fact_ids'] += second['fact_ids']
            first['text'] = first['text'].rstrip('。；;') + '；' + second['text'].rstrip('。；;')
            del units[1]
        projects.append({'source_experience_id': owner, 'expression_units': units})
    body['resume_sections']['projects'] = projects
    body['resume_sections']['summary'] = ['具备项目实践经历。']
    for key in ('normal_version', 'bold_version', 'boundary_version', 'recommended_version'):
        body[key] = '\n'.join(f.resume_ready_text for f in build.ledger.facts)
    return case, build, body


def decision(verdict='supported', source_fact_id=None, source=None, candidate=None):
    return {'verdict': verdict, 'source_fact_id': source_fact_id, 'source_excerpt': source, 'candidate_excerpt': candidate}


def coverage_reply(review, decisions):
    return {
        'decisions': decisions,
        'coverage': {
            fact_id: {'verdict': 'complete', 'unit_ids': unit_ids, 'source_excerpt': None}
            for fact_id, unit_ids in review.coverage_units().items()
        },
    }


def review_reply(build, body, decisions):
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    slots.compose_model_fact_references(body, views, expression_review=review)
    return coverage_reply(review, decisions)


def receive(monkeypatch, case, build, replies, long=False, review=None):
    views = build_canonical_consumer_views(build)
    before = deepcopy(build), repr(views), deepcopy(replies)
    sent = provider(monkeypatch, [(json.dumps(x, ensure_ascii=False) if not isinstance(x, str) else x, 'stop') for x in replies])
    try:
        payload, stats = generation.build_llm_generation(request(case), replace(build.long_input_context, long_input_mode=long),
            consumer_views=views, expression_review=review)
        return payload, stats, sent
    finally:
        assert (build, repr(views), replies) == before
        assert len(sent) <= 2


@pytest.mark.parametrize('position', ['intro', 'role', 'detail'])
@pytest.mark.parametrize('long', [False, True])
def test_literal_units_use_real_receiver_and_preserve_lineage(position, long, monkeypatch, isolated):
    case, build, body = composition_sample(position=position)
    payload, stats, sent = receive(monkeypatch, case, build, [body], long)
    assert stats['attempt'] == len(sent) == 1
    assert 'canonical_fact_compositions_v2' in sent[0]['messages'][1]['content']
    for project in payload.resume_sections.projects:
        facts = build.ledger.for_experience(project['source_experience_id'])
        assert set(project['source_fact_ids']) == {f.fact_id for f in facts}
        assert set(project['source_claim_ids']) == {f.claim_id for f in facts}
        if position == 'detail':
            assert len(project['detail_fact_ids'][0]) == 2


@pytest.mark.parametrize('position', ['intro', 'role', 'detail'])
def test_composed_expression_review_save_docx(position, monkeypatch, tmp_path, isolated):
    case, build, body = composition_sample(position=position)
    unit = body['resume_sections']['projects'][0]['expression_units'][0]
    unit['text'] = '2026年4月至6月，使用Python与FastAPI开发课程资料检索助手，实现文件上传、关键词检索及查询结果展示。'
    review = review_reply(build, body, {unit['fact_ids'][0]: decision()})
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop'), (json.dumps(review), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    project = outcome['saved']['resume_sections']['projects'][0]
    rows = [(project.get(p), project.get(p + '_source_fact_ids'), project.get(p + '_source_claim_ids')) for p in ('intro', 'role')]
    rows += list(zip(project['details'], project['detail_fact_ids'], project['detail_claim_ids']))
    text, ids, claims = next(row for row in rows if unit['text'].rstrip('。') in (row[0] or ''))
    assert set(unit['fact_ids']) <= set(ids)
    assert set(claims) == {f.claim_id for f in build.ledger.facts if f.fact_id in ids}
    assert unit['text'].rstrip('。') in '\n'.join(p.text for p in Document(next(tmp_path.glob('*.docx'))).paragraphs)


@pytest.mark.parametrize('kind', ['repeat_inside', 'repeat_unit', 'missing', 'unknown', 'foreign', 'noncontiguous', 'reverse', 'position', 'extra', 'old'])
def test_invalid_partition_rejected(kind, monkeypatch, isolated):
    case, build, body = composition_sample(combine=False)
    project = body['resume_sections']['projects'][0]
    units = project['expression_units']
    if kind == 'repeat_inside': units[0]['fact_ids'] *= 2
    elif kind == 'repeat_unit': units.append(deepcopy(units[0]))
    elif kind == 'missing': units.pop()
    elif kind == 'unknown': units[0]['fact_ids'] = ['EXP-999-F001']
    elif kind == 'foreign': units[0]['fact_ids'] = body['resume_sections']['projects'][1]['expression_units'][0]['fact_ids']
    elif kind == 'noncontiguous': units[0]['fact_ids'] += units.pop(2)['fact_ids']
    elif kind == 'reverse': units[0]['fact_ids'] = units.pop(1)['fact_ids'] + units[0]['fact_ids']
    elif kind == 'position': units[0]['position'] = 'summary'
    elif kind == 'extra': units[0]['trusted'] = True
    else: project['fact_placements'] = {u['fact_ids'][0]: {'position': u['position'], 'text': u['text']} for u in project.pop('expression_units')}
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, case, build, [body])
    assert caught.value.code.startswith('MODEL_EVIDENCE_')


@pytest.mark.parametrize('raw', [detail_input(9), project_input(6)])
def test_boundaries_preserved(raw, monkeypatch, tmp_path, isolated):
    case, build, body = composition_sample(raw, combine=False)
    body['resume_sections']['projects'].reverse()
    for p in body['resume_sections']['projects']: p['expression_units'].reverse()
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    refs = [fid for p in outcome['saved']['resume_sections']['projects'] for row in p['detail_fact_ids'] for fid in row]
    assert set(refs) == {f.fact_id for f in build.ledger.facts} and len(refs) == len(set(refs))


@pytest.mark.parametrize('verdict', ['added_claim', 'omitted_fact', 'changed_qualification', 'uncertain'])
def test_review_rejection_never_saves(verdict, monkeypatch, tmp_path, isolated):
    case, build, body = composition_sample()
    unit = body['resume_sections']['projects'][1]['expression_units'][0]
    unit['text'] = '独立负责整体系统并提升性能50%。'
    first = next(f for f in build.ledger.facts if f.fact_id == unit['fact_ids'][0])
    source = first.resume_ready_text if verdict in ('omitted_fact', 'changed_qualification') else None
    candidate = '独立负责整体系统' if verdict != 'omitted_fact' else None
    reply = review_reply(build, body, {unit['fact_ids'][0]: decision(verdict, first.fact_id if source else None, source, candidate)})
    result = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop'), (json.dumps(reply, ensure_ascii=False), 'stop')])
    assert result['error'] == ('MODEL_EXPRESSION_REVIEW_UNCERTAIN' if verdict == 'uncertain' else 'MODEL_EXPRESSION_REJECTED')
    assert result['results'] == 0 and not list(tmp_path.glob('*.docx'))
    assert len(result['sent']) == 2


@pytest.mark.parametrize('kind', ['missing', 'extra', 'foreign_source', 'source_without_excerpt', 'old', 'replacement', 'unknown'])
def test_invalid_review_mapping(kind, monkeypatch, isolated):
    case, build, body = composition_sample()
    unit = body['resume_sections']['projects'][0]['expression_units'][0]
    unit['text'] += '候选改写'
    key = unit['fact_ids'][0]
    reply = review_reply(build, body, {key: decision()})
    row = reply['decisions'][key]
    if kind == 'missing': reply['decisions'].clear()
    elif kind == 'extra': reply['decisions']['unknown'] = decision()
    elif kind == 'foreign_source': row.update(verdict='omitted_fact', source_fact_id='EXP-002-F001', source_excerpt='使用Vue')
    elif kind == 'source_without_excerpt': row['source_fact_id'] = key
    elif kind == 'old': del row['source_fact_id']
    elif kind == 'replacement': row['replacement_text'] = 'replacement'
    else: row['verdict'] = 'probably_supported'
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, case, build, [body, reply])
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'


@pytest.mark.parametrize('kind', ['text', 'position', 'partial', 'reordered', 'other_request'])
def test_receipt_cannot_authorize_changed_field(kind, monkeypatch, isolated):
    case, build, body = composition_sample(position='intro')
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    payload, _, _ = receive(monkeypatch, case, build, [body], review=review)
    changed = payload.model_copy(deep=True)
    p = changed.resume_sections.projects[0]
    if kind == 'text': p['intro'] += '提升性能50%'
    elif kind == 'position':
        for key in ('', '_source_fact_ids', '_source_claim_ids'):
            p['role' + key], p['intro' + key] = p['intro' + key], '' if not key else []
    elif kind == 'partial': p['intro_source_fact_ids'].pop(0)
    elif kind == 'reordered': p['intro_source_fact_ids'].reverse()
    else: views = build_canonical_consumer_views(deepcopy(build))
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.validate_model_project_evidence(changed, views, expression_review=review, require_complete=True, write_log=False)
    slots.validate_model_project_evidence(payload, build_canonical_consumer_views(build), expression_review=review, require_complete=True, write_log=False)


def test_review_receives_exact_cited_sources_and_budget_is_shared(monkeypatch, isolated):
    case, build, body = composition_sample()
    unit = body['resume_sections']['projects'][0]['expression_units'][0]
    unit['text'] = '2026年4月至6月，使用Python与FastAPI开发课程资料检索助手，实现文件上传、关键词检索及查询结果展示。'
    reply = review_reply(build, body, {unit['fact_ids'][0]: decision()})
    _, _, sent = receive(monkeypatch, case, build, [body, reply])
    text = sent[1]['messages'][1]['content']
    rows = json.JSONDecoder().raw_decode(text.split('<expression_review>\n')[1])[0]
    assert [f['fact_id'] for f in rows[unit['fact_ids'][0]]['sources']] == unit['fact_ids']
    assert 'canonical_expression_review_v6' in text
    bad = deepcopy(body)
    bad['resume_sections']['projects'][0]['expression_units'].pop()
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, case, build, [bad, body])
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_BUDGET'


@pytest.mark.parametrize('kind', ['units', 'ids', 'text', 'owner'])
def test_duplicate_json_fields_rejected(kind, monkeypatch, isolated):
    case, build, body = composition_sample()
    text = json.dumps(body, ensure_ascii=False)
    key, value = {'units': ('expression_units', '[]'), 'ids': ('fact_ids', '[]'),
                  'text': ('text', '"untrusted"'), 'owner': ('source_experience_id', '"EXP-999"')}[kind]
    text = text.replace('"' + key + '":', '"' + key + '":' + value + ',"' + key + '":', 1)
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, case, build, [text])
    assert caught.value.code.startswith('MODEL_EVIDENCE_')


def test_same_text_different_sources_not_merged(monkeypatch, isolated):
    raw = ('个人项目：页面工具\n2026年4月，使用Vue制作页面。我帮忙测试。\n\n'
           '课程项目：展示工具\n2026年5月，使用Vue制作页面。我帮忙测试。')
    case, build, body = composition_sample(raw, combine=False)
    payload, _, _ = receive(monkeypatch, case, build, [body])
    matching = [(p['source_experience_id'], ids) for p in payload.resume_sections.projects
                for text, ids in zip(p['details'], p['detail_fact_ids']) if text == '我帮忙测试']
    assert len(matching) == 2 and matching[0] != matching[1]


@pytest.mark.parametrize('kind', ['normal', 'thin', 'qualified', 'holdout'])
def test_stage_preservation_without_recovery(kind, monkeypatch, tmp_path, isolated):
    normal = json.loads((Path(__file__).parent / 'fixtures/v091811_normal_inputs.json').read_text(encoding='utf-8'))
    raw = {'normal': normal[0]['raw_input'] if isinstance(normal[0], dict) else normal[0],
           'thin': '个人项目：课程展示网站\n2026年5月，使用Vue制作课程展示网站。我做了页面。我帮忙测试。',
           'qualified': RAW,
           'holdout': '个人项目：馆藏记录检查工具\n2026年5月，协助使用Python检查馆藏记录，整理27条记录的编号。工具仅在本地运行。'}[kind]
    case, build, body = composition_sample(raw)
    expected = {f.fact_id: f for f in build.ledger.facts}
    stages = []
    def inspect(payload, name):
        if hasattr(payload, 'model_dump'): payload = payload.model_dump()
        projects = payload['resume_sections']['projects']
        assigned = []
        for p in projects:
            rows = [(p.get(k, ''), p.get(k + '_source_fact_ids', []), p.get(k + '_source_claim_ids', [])) for k in ('intro', 'role')]
            rows += list(zip(p['details'], p['detail_fact_ids'], p['detail_claim_ids'], strict=True))
            for text, ids, claims in rows:
                assert set(claims) == {expected[fid].claim_id for fid in ids}, name
                assert all(expected[fid].experience_id == p['source_experience_id'] for fid in ids), name
                assert all(expected[fid].resume_ready_text.rstrip('。；;') in text for fid in ids), name
                assigned.extend(ids)
        assert len(assigned) == len(set(assigned)) and set(assigned) == set(expected), name
        stages.append({'stage': name, 'projects': deepcopy(projects)})
    for name in ('compose_model_fact_references', 'normalize_llm_payload', 'cleanup_generation_payload',
                 'guard_hard_facts', 'bind_projects_to_experience_slots', 'append_canonical_project_projection_candidates',
                 'sanitize_resume_body', 'reconcile_resume_projects', 'organize_adaptive_narrative',
                 'deduplicate_resume_facts', 'guard_template_language', 'guard_resume_output',
                 'professionalize_resume_language', 'ensure_recruiter_readability', 'ensure_resume_whitespace_quality'):
        fn = getattr(generation, name)
        def observe(*args, _fn=fn, _name=name, **kwargs):
            result = _fn(*args, **kwargs)
            inspect(result[0] if isinstance(result, tuple) else result, _name)
            return result
        monkeypatch.setattr(generation, name, observe)
    before = deepcopy(build)
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    inspect(outcome['saved'], 'saved_revision')
    assert build == before and len(stages) >= 16
    (tmp_path / 'composition-stages.json').write_text(json.dumps(stages, ensure_ascii=False), encoding='utf-8')
