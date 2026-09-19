"""Real compilation and receiver; network returns are controls, not history."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app import models
from app.database import Base
from app.services import generation_service as generation
from app.services import experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.llm_service import LLMResult
from test_v09162_model_output_evidence_contract import CASES, controlled_return, request, real_receiver, reference_return
from test_v0916_canonical_model_evidence import evidence


KEYS = ('source_experience_id', 'fact_placements')


def references(data):
    return reference_return(data)


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv('LLM_MODE', 'openai')
    monkeypatch.setenv('MAX_LLM_CALLS_PER_ATTEMPT', '2')
    monkeypatch.setattr(generation.resource_protection, 'check_daily_budget', lambda: SimpleNamespace(allowed=True))
    monkeypatch.setattr(generation.resource_protection, 'record_llm_usage', lambda **kw: None)
    for module in tuple(sys.modules.values()):
        if getattr(module, '__name__', '').startswith('app.services.'):
            for key, value in list(vars(module).items()):
                if isinstance(value, Path) and (key == 'LOG_DIR' or key.endswith('LOG_PATH')):
                    monkeypatch.setattr(module, key, tmp_path if key == 'LOG_DIR' else tmp_path / value.name)


def receive(monkeypatch, case, replies, long_mode=False):
    build, _ = controlled_return(case)
    views = build_canonical_consumer_views(build)
    before, snapshot = deepcopy(build), repr(views)
    sent = []
    def network(prompt):
        reply = replies[min(len(sent), len(replies)-1)]
        sent.append(prompt)
        return LLMResult(finish_reason="stop", text=reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False), model='controlled', latency_ms=0)
    monkeypatch.setattr(generation, 'call_openai', network)
    try:
        output = generation.build_llm_generation(request(case), replace(build.long_input_context, long_input_mode=long_mode), consumer_views=views)
        return output, sent, build
    finally:
        assert build == before and repr(views) == snapshot
        if len(sent) == 2:
            assert evidence(sent[0]) == evidence(sent[1])


@pytest.mark.parametrize('case', CASES, ids=lambda c: str(c['result_id']))
@pytest.mark.parametrize('long_mode', [False, True])
def test_reference_return_preserves_every_fact_and_lineage(case, long_mode, monkeypatch, isolated):
    build, body = controlled_return(case)
    data = references(body)
    before = deepcopy(data)
    (payload, log), sent, _ = receive(monkeypatch, case, [data], long_mode)
    assert len(sent) == 1 and data == before
    for p in payload.resume_sections.projects:
        original = next(x for x in body['resume_sections']['projects'] if x['source_experience_id'] == p['source_experience_id'])
        for key in ('intro', 'role', 'details', 'intro_source_fact_ids', 'intro_source_claim_ids', 'role_source_fact_ids', 'role_source_claim_ids', 'detail_fact_ids', 'detail_claim_ids'):
            assert p[key] == original[key]
        assert set(p['source_fact_ids']) == {f.fact_id for f in build.ledger.for_experience(p['source_experience_id'])}
    contract = json.JSONDecoder().raw_decode(sent[0].split('<canonical_model_output_contract>\n', 1)[1])[0]
    assert set(contract['required_fields']) == set(KEYS)


@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'foreign', 'unknown', 'old_body', 'trust', 'header', 'claims', 'aggregate', 'extra', 'wrong_order', 'wrong_shape', 'duplicate_owner', 'missing_owner'])
def test_invalid_selection_never_enters_cleanup_or_save(kind, monkeypatch, isolated):
    case = CASES[0]
    _, body = controlled_return(case)
    data = references(body)
    p = data['resume_sections']['projects'][0]
    fid = next(iter(p['fact_placements']))
    if kind == 'missing': p['fact_placements'].popitem()
    elif kind == 'duplicate': data['resume_sections']['projects'].append(deepcopy(p))
    elif kind == 'foreign': p['fact_placements'][next(iter(data['resume_sections']['projects'][1]['fact_placements']))] = 'detail'
    elif kind == 'unknown': p['fact_placements']['EXP-999-F001'] = 'detail'
    elif kind == 'old_body': p['intro'] = '独立主导系统架构'
    elif kind == 'trust': p['source_binding_locked'] = True
    elif kind == 'header': p['name'] = '模型决定的名称'
    elif kind == 'claims': p['detail_claim_ids'] = body['resume_sections']['projects'][0]['detail_claim_ids']
    elif kind == 'aggregate': p['source_fact_ids'] = body['resume_sections']['projects'][0]['source_fact_ids']
    elif kind == 'extra': p['ignored'] = 'must reject'
    elif kind == 'wrong_order':
        # Model ordering is no longer a wire capability; old arrays are rejected.
        p['intro_source_fact_ids'] = list(reversed(p['fact_placements']))
    elif kind == 'wrong_shape': p['fact_placements'][fid] = ['intro','detail']
    elif kind == 'duplicate_owner': data['resume_sections']['projects'].append(deepcopy(p))
    elif kind == 'missing_owner': data['resume_sections']['projects'].pop()
    monkeypatch.setattr(generation, 'call_openai', lambda prompt: LLMResult(finish_reason="stop", text=json.dumps(data, ensure_ascii=False), model='controlled', latency_ms=0))
    calls = []
    for name in ('cleanup_generation_payload', 'plan_canonical_project_projections', 'build_stable_generation_fallback'):
        fn = getattr(generation, name)
        def spy(*args, _fn=fn, _name=name, **kwargs):
            calls.append(_name)
            return _fn(*args, **kwargs)
        monkeypatch.setattr(generation, name, spy)
    engine = create_engine('sqlite:///:memory:')
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            with pytest.raises(generation.GenerationServiceError, match='MODEL_EVIDENCE_'):
                generation.create_generation(db, request(case), request_id='req_selection_failure')
            assert db.scalar(select(func.count()).select_from(models.GenerationResult)) == 0
            assert calls == []
    finally:
        engine.dispose()


def test_combination_empty_rows_and_owner_order(monkeypatch, isolated):
    _, body = controlled_return(CASES[0])
    data = references(body)
    data['resume_sections']['projects'].reverse()
    for p in data['resume_sections']['projects']:
        p['fact_placements'] = {fid: dict(p['fact_placements'][fid], position='detail') for fid in reversed(p['fact_placements'])}
    (payload, _), _, build = receive(monkeypatch, CASES[0], [data])
    for p in payload.resume_sections.projects:
        facts = list(build.ledger.for_experience(p['source_experience_id']))
        assert p['intro'] == p['role'] == ''
        assert p['details'] == [f.resume_ready_text for f in facts]
        assert p['detail_fact_ids'] == [[f.fact_id] for f in facts]
        assert p['detail_claim_ids'] == [[f.claim_id] for f in facts]
        assert len(p['details']) == len(p['detail_fact_ids']) == len(p['detail_claim_ids'])


def test_retry_keeps_frozen_evidence_and_cannot_escape_via_json(monkeypatch, isolated):
    _, body = controlled_return(CASES[0])
    valid = references(body)
    bad = deepcopy(valid)
    bad['resume_sections']['projects'][0]['fact_placements'].popitem()
    (payload, log), sent, _ = receive(monkeypatch, CASES[0], [bad, valid])
    assert log['attempt'] == len(sent) == 2
    with pytest.raises(generation.GenerationServiceError, match='MODEL_EVIDENCE_'):
        receive(monkeypatch, CASES[0], [bad, 'not json'])


@pytest.mark.parametrize('rewrite', ['编写了18条', '独立主导系统架构', '删除职责限定'])
def test_old_free_text_protocol_is_not_silently_materialized(rewrite, monkeypatch, isolated):
    build, body = controlled_return(CASES[0])
    body['resume_sections']['projects'][0]['details'][1] = rewrite
    with pytest.raises(generation.GenerationServiceError, match='MODEL_EVIDENCE_FORMAT'):
        receive(monkeypatch, CASES[0], [body])
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.validate_model_project_evidence(body, build_canonical_consumer_views(build))


@pytest.mark.parametrize('kind', ['literal', 'format', 'particle', 'inflation', 'limitation'])
def test_existing_support_validator_is_not_relaxed(kind, isolated):
    build, body = controlled_return(CASES[0])
    p = body['resume_sections']['projects'][0]
    if kind == 'format': p['details'][1] += '。'
    elif kind == 'particle': p['details'][1] = p['details'][1].replace('编写18条', '编写了18条')
    elif kind == 'inflation': p['details'][1] += '，独立主导系统架构设计'
    elif kind == 'limitation': p['details'][0] = '我负责按照已有结构编写查询逻辑'
    views = build_canonical_consumer_views(build)
    if kind in ('literal', 'format'):
        assert slots.validate_model_project_evidence(body, views)['resume_sections']['projects']
    else:
        with pytest.raises(slots.ModelEvidenceContractError, match='MODEL_EVIDENCE_UNSUPPORTED'):
            slots.validate_model_project_evidence(body, views)


def test_same_claim_can_support_distinct_facts_and_composition_is_idempotent(isolated):
    build, body = controlled_return(CASES[0])
    views = build_canonical_consumer_views(build)
    data = references(body)
    before = deepcopy(data)
    first = slots.compose_model_fact_references(data, views)
    second = slots.compose_model_fact_references(data, views)
    assert first == second and data == before
    projects = first['resume_sections']['projects']
    p = next(p for p in projects if p['source_experience_id'] == 'EXP-002')
    assert p['intro_source_fact_ids'] != p['role_source_fact_ids']
    assert p['intro_source_claim_ids'] == p['role_source_claim_ids']
    # Internal materialized payloads cannot masquerade as a second model return.
    with pytest.raises(slots.ModelEvidenceContractError, match='MODEL_EVIDENCE_FORMAT'):
        slots.compose_model_fact_references(first, views)


@pytest.mark.parametrize('case', CASES, ids=lambda c: str(c['result_id']))
def test_frozen_headers_do_not_discard_verified_owners_before_projection(case, monkeypatch, tmp_path, isolated):
    build, body = controlled_return(case)
    changes = []
    body_keys = ('source_experience_id', 'intro', 'role', 'details', 'intro_source_fact_ids',
                 'intro_source_claim_ids', 'role_source_fact_ids', 'role_source_claim_ids',
                 'detail_fact_ids', 'detail_claim_ids')
    def snapshot(payload):
        return [{k: deepcopy(p.get(k)) for k in body_keys} for p in payload.resume_sections.projects]
    for name in ('ensure_packaging_gain', 'guard_experience_boundaries', 'sanitize_resume_body',
                 'reconcile_resume_projects', 'deduplicate_resume_facts', 'guard_fact_coverage',
                 'layer_resume_sections', 'ensure_resume_fact_increment', 'organize_adaptive_narrative',
                 'ensure_information_gain', 'ensure_dedup_quality', 'deduplicate_fact_clusters',
                 'guard_template_language', 'guard_resume_output', 'professionalize_resume_language',
                 'ensure_recruiter_facing_technical_language', 'ensure_recruiter_readability'):
        original = getattr(generation, name)
        def observe(*args, _fn=original, _name=name, **kwargs):
            before = snapshot(args[0])
            output = _fn(*args, **kwargs)
            after = snapshot(output)
            if before != after:
                changes.append({'writer': _name, 'stage': kwargs.get('stage'), 'before': before, 'after': after})
            return output
        monkeypatch.setattr(generation, name, observe)
    captured = real_receiver(case, references(body), monkeypatch, tmp_path, deliver=True)
    expected = {p['source_experience_id']: p for p in body['resume_sections']['projects']}
    checked = set()
    for name, payload in captured['stages']:
        if name in checked or name not in ('cleanup_generation_payload', 'guard_hard_facts', 'bind_projects_to_experience_slots', 'contain_ownerless_projects'):
            continue
        checked.add(name)
        actual = {p.get('source_experience_id'): p for p in payload.resume_sections.projects}
        assert set(actual) == set(expected), name
        for owner, p in actual.items():
            for key in ('intro', 'role', 'details', 'detail_fact_ids', 'detail_claim_ids'):
                assert p[key] == expected[owner][key], (name, owner, key)
    assert captured['saved'] and captured['docx']
    (tmp_path / 'downstream-changes.json').write_text(json.dumps({
        'input_fixture': case['result_id'], 'initial_owners': list(expected),
        'changes': changes, 'saved_projects': captured['saved']['resume_sections']['projects'],
    }, ensure_ascii=False, indent=2), encoding='utf-8')


@pytest.mark.parametrize('long_mode', [False, True])
def test_actual_prompt_has_no_competing_project_prose_task(long_mode, monkeypatch, isolated):
    _, body = controlled_return(CASES[0])
    _, sent, _ = receive(monkeypatch, CASES[0], [references(body)], long_mode)
    for forbidden in ('<!-- legacy-project -->', '每个 project.details 控制在 3-5 条',
                      '单段主要经历：details 建议 4-6 条', '项目专属表达规则：',
                      '每项包含 name、meta、time、intro、role、details',
                      '按段允许的自然承接知识也必须结合本段经历'):
        assert forbidden not in sent[0]
    assert 'normal_version' in sent[0] and 'knowledge_checklist' in sent[0]
    assert '全部 owner 提供的每个 eligible Fact 必须且只能分配一次' in sent[0]


def test_reference_log_distinguishes_materialization_from_text_validation(monkeypatch, isolated):
    _, body = controlled_return(CASES[0])
    receive(monkeypatch, CASES[0], [references(body)])
    rows = [json.loads(line) for line in slots.LOG_PATH.read_text(encoding='utf-8').splitlines()]
    composed = next(r for r in rows if r['stage'] == 'generation_model_expression_candidates_prepared')
    assert composed['required_fact_count'] == composed['assigned_fact_count'] == 12
    assert composed['reference_protocol'] == 'canonical_fact_expressions_v1'
    assert rows[-1]['stage'] == 'generation_model_evidence_received'
    assert rows[-1]['verified_field_count'] == 12 and rows[-1]['contract_passed'] is True
    text = slots.LOG_PATH.read_text(encoding='utf-8')
    assert not any(p['intro'] in text for p in body['resume_sections']['projects'])


@pytest.mark.parametrize('kind', ['valid', 'missing', 'foreign', 'rewrite', 'orphan'])
@pytest.mark.parametrize('pending_candidate', [False, True])
def test_binder_direct_owner_requires_complete_verified_fields(kind, pending_candidate, isolated):
    build, body = controlled_return(CASES[0])
    data = slots.compose_model_fact_references(references(body), build_canonical_consumer_views(build))
    p = data['resume_sections']['projects'][1]
    assert p['name'] == '项目：自习室预约平台'
    if pending_candidate:
        p['name'] = '项目：【待填写】'
    if kind == 'missing': p['detail_fact_ids'][0] = []
    elif kind == 'foreign': p['detail_fact_ids'][0] = body['resume_sections']['projects'][0]['detail_fact_ids'][0]
    elif kind == 'rewrite': p['details'][0] += '，独立主导百万用户服务'
    elif kind == 'orphan':
        p['details'].append('')
        p['detail_fact_ids'].append(p['intro_source_fact_ids'])
        p['detail_claim_ids'].append(p['intro_source_claim_ids'])
    payload = generation.schemas.GenerationPayload.model_validate(data)
    before = payload.model_copy(deep=True)
    result = slots.bind_projects_to_experience_slots(payload, CASES[0]['raw_input'], semantic_build=build, ownership_index=build.ownership_index)
    assert payload == before
    current = result.resume_sections.projects[1]
    if kind == 'valid':
        assert current['source_binding_origin'] == 'canonical_field_evidence'
        assert current['immutable_source_experience_id'] == 'EXP-002'
        assert current['details'] == p['details']
    else:
        assert current['source_binding_origin'] != 'canonical_field_evidence'
