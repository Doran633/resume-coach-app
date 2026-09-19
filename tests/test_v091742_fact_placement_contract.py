"""Placement protocol controls and saved real output, not historical replay."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from app.services import generation_service as generation
from app.services import experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.json_repair_service import parse_llm_json
from app.services.llm_service import LLMResult
from test_v09162_model_output_evidence_contract import CASES, controlled_return, request, real_receiver, reference_return
from test_v09174_fact_reference_composition import isolated
from test_v09172_initial_evidence_preservation import detail_return, detail_input, project_input

FIXTURES = Path(__file__).parent / 'fixtures'
COURSE = dict(CASES[0], raw_input=(FIXTURES/'v091741_course_projects_input.txt').read_text(encoding='utf-8').rstrip('\n'), target_role='AI应用开发实习')


def placements(body):
    return reference_return(body)


def receive(case, replies, monkeypatch, long_mode=False):
    from app.services.canonical_semantic_state_service import build_canonical_semantic_build
    build = build_canonical_semantic_build(case['raw_input'])
    views = build_canonical_consumer_views(build)
    before = deepcopy(build), repr(views), deepcopy(replies)
    sent = []
    def network(prompt):
        reply = replies[min(len(sent), len(replies)-1)]
        sent.append(prompt)
        return LLMResult(finish_reason="stop", text=reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False), model='placement-control', latency_ms=0)
    monkeypatch.setattr(generation, 'call_openai', network)
    try:
        output = generation.build_llm_generation(request(case), replace(build.long_input_context, long_input_mode=long_mode), consumer_views=views)
        return output, sent, build
    finally:
        assert (build, repr(views), replies) == before


def test_saved_real_response_reproduces_overlap_and_is_rejected(monkeypatch, isolated):
    text = (FIXTURES/'v091742_real_model_response.json').read_text(encoding='utf-8')
    data = json.loads(text)
    refs = [fid for p in data['resume_sections']['projects'] for row in [p['intro_source_fact_ids'], p['role_source_fact_ids'], *p['detail_fact_ids']] for fid in row]
    assert len(set(refs)) == 10 and len(refs) == 20
    with pytest.raises(generation.GenerationServiceError, match='MODEL_EVIDENCE_FORMAT'):
        receive(COURSE, [text], monkeypatch)


@pytest.mark.parametrize('case', [COURSE, *CASES], ids=lambda c: str(c.get('result_id')))
@pytest.mark.parametrize('long_mode', [False, True])
def test_actual_task_receiver_preserves_every_field(case, long_mode, monkeypatch, isolated):
    _, body = controlled_return(case)
    (output, _), sent, build = receive(case, [placements(body)], monkeypatch, long_mode)
    assert len(sent) == 1
    contract = json.JSONDecoder().raw_decode(sent[0].split('<canonical_model_output_contract>\n')[1])[0]
    assert set(contract['required_fields']) == {'source_experience_id', 'fact_placements'}
    for actual, expected in zip(output.resume_sections.projects, body['resume_sections']['projects']):
        for key in ('intro','role','details','intro_source_fact_ids','role_source_fact_ids','detail_fact_ids','intro_source_claim_ids','role_source_claim_ids','detail_claim_ids'):
            assert actual[key] == expected[key]
        assert set(actual['source_fact_ids']) == {f.fact_id for f in build.ledger.for_experience(actual['source_experience_id'])}


@pytest.mark.parametrize('kind', ['fact','escaped_fact','owner','placements','projects','sections'])
@pytest.mark.parametrize('wrapper', ['plain','fenced','repair'])
def test_duplicate_keys_rejected_before_overwrite(kind, wrapper, monkeypatch, isolated):
    _, body = controlled_return(COURSE)
    data = placements(body)
    p = data['resume_sections']['projects'][0]
    fid = next(iter(p['fact_placements']))
    text = json.dumps(data,ensure_ascii=False)
    if kind in ('fact','escaped_fact'):
        key = json.dumps(fid)
        duplicate = key if kind == 'fact' else '"\\u0045' + fid[1:] + '"'
        value = json.dumps(p['fact_placements'][fid], ensure_ascii=False)
        text = text.replace(key + ': ' + value, duplicate + ': ' + value + ', ' + key + ': ' + value, 1)
    elif kind == 'owner':
        text = text.replace('"source_experience_id":', '"source_experience_id": "EXP-999", "source_experience_id":',1)
    elif kind == 'placements':
        text = text.replace('"fact_placements":', '"fact_placements": {}, "fact_placements":',1)
    elif kind == 'projects':
        text = text.replace('"projects":', '"projects": [], "projects":',1)
    else:
        text = text.replace('"resume_sections":', '"resume_sections": {}, "resume_sections":',1)
    if wrapper == 'fenced': text = '```json\n' + text + '\n```'
    if wrapper == 'repair': text = text[:-1]
    with pytest.raises(generation.GenerationServiceError, match='duplicate_project_key'):
        receive(COURSE, [text], monkeypatch)


@pytest.mark.parametrize('kind', ['missing','unknown','foreign','position','position_list','map_list','extra','duplicate_owner','missing_owner','old'])
def test_illegal_placements_rejected(kind, monkeypatch, isolated):
    _, body = controlled_return(COURSE)
    data = placements(body)
    p = data['resume_sections']['projects'][0]
    fid = next(iter(p['fact_placements']))
    if kind == 'missing': p['fact_placements'].pop(fid)
    elif kind == 'unknown': p['fact_placements']['EXP-999-F001'] = 'detail'
    elif kind == 'foreign': p['fact_placements'][next(iter(data['resume_sections']['projects'][1]['fact_placements']))] = 'detail'
    elif kind == 'position': p['fact_placements'][fid] = 'summary'
    elif kind == 'position_list': p['fact_placements'][fid] = ['intro','detail']
    elif kind == 'map_list': p['fact_placements'] = []
    elif kind == 'extra': p['intro'] = 'untrusted'
    elif kind == 'duplicate_owner': data['resume_sections']['projects'].append(deepcopy(p))
    elif kind == 'missing_owner': data['resume_sections']['projects'].pop()
    else: data = body
    with pytest.raises(generation.GenerationServiceError, match='MODEL_EVIDENCE_'):
        receive(COURSE,[data],monkeypatch)


def test_retry_and_parse_failure_cannot_escape_contract(monkeypatch, isolated):
    _, body = controlled_return(COURSE)
    good = placements(body)
    bad = deepcopy(good)
    bad['resume_sections']['projects'][0]['fact_placements'].popitem()
    (payload, info), sent, _ = receive(COURSE,[bad,good],monkeypatch)
    assert info['attempt'] == len(sent) == 2
    assert sent[1].startswith(sent[0]) and payload.resume_sections.projects
    with pytest.raises(generation.GenerationServiceError, match='MODEL_EVIDENCE_'):
        receive(COURSE,[bad,'not json'],monkeypatch)


def test_non_project_duplicate_and_legacy_parser_unchanged(monkeypatch, isolated):
    assert parse_llm_json('{"value":1,"value":2}') == {'value':2}
    _, body = controlled_return(COURSE)
    text = json.dumps(placements(body),ensure_ascii=False)
    text = '{"normal_version":"ignored",' + text[1:]
    (payload, _), _, _ = receive(COURSE,[text],monkeypatch)
    assert payload.normal_version == body['normal_version']


@pytest.mark.parametrize('raw', [project_input(6),detail_input(9)])
def test_boundaries_empty_fields_and_source_order(raw, monkeypatch, isolated):
    case, _, body = detail_return(raw)
    data = placements(body)
    data['resume_sections']['projects'].reverse()
    for p in data['resume_sections']['projects']:
        p['fact_placements'] = dict(reversed(list(p['fact_placements'].items())))
    (payload,_),_,build = receive(case,[data],monkeypatch)
    for p in payload.resume_sections.projects:
        facts = sorted(build.ledger.for_experience(p['source_experience_id']),key=lambda f:f.source_span)
        assert p['intro'] == p['role'] == ''
        assert p['details'] == [f.resume_ready_text for f in facts]
        assert p['detail_fact_ids'] == [[f.fact_id] for f in facts]
        assert p['detail_claim_ids'] == [[f.claim_id] for f in facts]


def test_grouping_intro_uses_frozen_order_and_shared_claims(monkeypatch, isolated):
    _,body = controlled_return(CASES[0])
    data = placements(body)
    for p in data['resume_sections']['projects']:
        p['fact_placements'] = {fid: dict(p['fact_placements'][fid], position='intro') for fid in reversed(p['fact_placements'])}
    (payload,_),_,build = receive(CASES[0],[data],monkeypatch)
    for p in payload.resume_sections.projects:
        facts = sorted(build.ledger.for_experience(p['source_experience_id']),key=lambda f:f.source_span)
        assert p['intro'] == '；'.join(f.resume_ready_text.rstrip('。；;') for f in facts)
        assert p['intro_source_fact_ids'] == [f.fact_id for f in facts]
        assert p['intro_source_claim_ids'] == list(dict.fromkeys(f.claim_id for f in facts))
        assert p['role'] == '' and p['details'] == []


@pytest.mark.parametrize('case', CASES, ids=lambda c:str(c['result_id']))
def test_real_generation_save_docx_with_placements(case, monkeypatch, tmp_path, isolated):
    _,body = controlled_return(case)
    captured = real_receiver(case,placements(body),monkeypatch,tmp_path,deliver=True)
    cleaned = next(p for stage,p in captured['stages'] if stage=='cleanup_generation_payload')
    for actual,expected in zip(cleaned.resume_sections.projects,body['resume_sections']['projects']):
        for key in ('intro','role','details','detail_fact_ids','detail_claim_ids'):
            assert actual[key] == expected[key]


def test_duplicate_keys_cannot_reach_fallback_or_persistence(monkeypatch, isolated):
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import Session
    from app import models
    from app.database import Base
    _, body = controlled_return(COURSE)
    text = json.dumps(placements(body),ensure_ascii=False)
    text = text.replace('"fact_placements":', '"fact_placements": {}, "fact_placements":',1)
    replies = iter([text,'not json'])
    monkeypatch.setattr(generation,'call_openai',lambda prompt: LLMResult(finish_reason="stop", text=next(replies),model='control',latency_ms=0))
    touched = []
    for name in ('cleanup_generation_payload','build_stable_generation_fallback'):
        original = getattr(generation,name)
        def observe(*args,_fn=original,_name=name,**kwargs):
            touched.append(_name)
            return _fn(*args,**kwargs)
        monkeypatch.setattr(generation,name,observe)
    engine = create_engine('sqlite:///:memory:')
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            with pytest.raises(generation.GenerationServiceError,match='duplicate_project_key'):
                generation.create_generation(db,request(COURSE),request_id='local-duplicate-key')
            assert db.scalar(select(func.count()).select_from(models.GenerationResult)) == 0
            assert not touched
    finally:
        engine.dispose()


def test_decode_hook_is_optional_and_preserves_duplicate_metadata():
    for text in ('{"key":1,"key":2}', '{"key":1,"key":2'):
        decoded = parse_llm_json(text,object_pairs_hook=slots.ModelJSONObject)
        assert decoded.duplicate_keys == {'key'}
        assert parse_llm_json(text) == {'key':2}


def test_reserved_sample_after_implementation(monkeypatch, tmp_path, isolated):
    raw = (FIXTURES/'v091742_holdout_input.txt').read_text(encoding='utf-8').rstrip('\n')
    case, build, body = detail_return(raw)
    case['target_role'] = '测试开发实习'
    captured = real_receiver(case,placements(body),monkeypatch,tmp_path,deliver=True)
    assert len(build.identities) == 2
    initial = captured['payload'].resume_sections.projects
    assert {p['source_experience_id'] for p in initial} == {x.experience_id for x in build.identities}
    for p in initial:
        facts = sorted(build.ledger.for_experience(p['source_experience_id']),key=lambda f:f.source_span)
        assert p['details'] == [f.resume_ready_text for f in facts]
        assert p['detail_fact_ids'] == [[f.fact_id] for f in facts]
        assert p['detail_claim_ids'] == [[f.claim_id] for f in facts]
    assert captured['saved'] and captured['docx']
