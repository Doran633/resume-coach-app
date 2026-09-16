"""Current execution controls, not historical request reconstruction."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import Base
from app.services import generation_service as generation, llm_service as llm
from app.services import docx_service
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09162_model_output_evidence_contract import request, reference_return
from test_v09172_initial_evidence_preservation import detail_input, detail_return
from test_v09174_fact_reference_composition import isolated


def provider(monkeypatch, replies):
    sent = []
    monkeypatch.setenv('OPENAI_API_KEY', 'offline-only')
    monkeypatch.setenv('OPENAI_BASE_URL', 'https://offline.invalid/v1')
    class Response:
        def __init__(self, data): self.data = data
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return json.dumps(self.data).encode()
    def network(req, **kwargs):
        text, finish = replies[min(len(sent), len(replies) - 1)]
        sent.append(json.loads(req.data))
        choice = {'message': {'content': text}}
        if finish is not None:
            choice['finish_reason'] = finish
        return Response({'choices': [choice], 'usage': {'prompt_tokens': 20, 'completion_tokens': 30}})
    monkeypatch.setattr(llm.urllib.request, 'urlopen', network)
    return sent


def sample(raw=None):
    case, build, body = detail_return(raw or detail_input(3))
    return case, build, json.dumps(reference_return(body), ensure_ascii=False)


def receive(monkeypatch, replies, long=False):
    case, build, _ = sample()
    views = build_canonical_consumer_views(build)
    before = deepcopy(build), repr(views)
    sent = provider(monkeypatch, replies)
    try:
        return generation.build_llm_generation(request(case), replace(build.long_input_context, long_input_mode=long), consumer_views=views), sent
    finally:
        assert (build, repr(views)) == before


def deliver(monkeypatch, tmp_path, case, replies):
    sent = provider(monkeypatch, replies)
    gates = []
    actual = generation.validate_resume_delivery_quality
    def observe(*args, **kwargs):
        result = actual(*args, **kwargs)
        gates.append({'passed': result.stats.gate_passed, 'codes': [i.issue_code for i in result.issues], 'severities': [i.severity for i in result.issues]})
        if kwargs.get('stage') == 'after_final_owner_delivery_contract':
            checked[:] = [args[0].model_copy(deep=True)]
        return result
    checked = []
    monkeypatch.setattr(generation, 'validate_resume_delivery_quality', observe)
    monkeypatch.setattr(docx_service, 'OUTPUT_DIR', tmp_path)
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    outcome = {'gates': gates, 'sent': sent}
    try:
        with Session(engine) as db:
            try:
                response = generation.create_generation(db, request(case), request_id='req_v09176_control')
                row = db.get(models.GenerationResult, response.generation_result_id)
                outcome['saved'] = json.loads(row.result_json)
                from app.services.immutable_delivery_revision_service import _visible_projection
                assert _visible_projection(checked[0]) == _visible_projection(schemas.GenerationPayload.model_validate(outcome['saved']))
                try:
                    outcome['docx'] = docx_service.create_docx(db, schemas.DocxCreate(generation_result_id=row.id, anonymous_user_id='v09162', session_id='v09162'))
                except docx_service.DocxRenderSourceError:
                    outcome['docx_rejected'] = True
                assert json.loads(row.result_json) == outcome['saved']
            except generation.GenerationServiceError as exc:
                outcome['error'] = exc.code
            outcome['results'] = db.scalar(select(func.count()).select_from(models.GenerationResult))
            outcome['inputs'] = db.scalar(select(func.count()).select_from(models.ExperienceInput))
    finally:
        engine.dispose()
    (tmp_path/'closure-outcome.json').write_text(json.dumps({k: v for k, v in outcome.items() if k != 'docx'}, ensure_ascii=False, default=str), encoding='utf-8')
    return outcome


@pytest.mark.parametrize('finish', ['length', 'content_filter', 'tool_calls', 'unknown', None])
def test_nonstop_rejected_before_json_repair(finish, monkeypatch, isolated):
    _, _, text = sample()
    with pytest.raises(generation.GenerationServiceError) as caught:
        receive(monkeypatch, [(text, finish)])
    assert caught.value.code == ('MODEL_OUTPUT_TRUNCATED' if finish == 'length' else 'MODEL_FINISH_INVALID')


@pytest.mark.parametrize('long', [False, True])
def test_truncated_then_complete_retries_same_evidence(long, monkeypatch, isolated):
    _, _, text = sample()
    (payload, info), sent = receive(monkeypatch, [(text, 'length'), (text, 'stop')], long)
    assert len(sent) == info['attempt'] == 2
    assert payload.resume_sections.projects and info['finish_reason'] == 'stop'
    assert sent[0]['messages'] == sent[1]['messages']


def test_final_gate_failure_cannot_save(monkeypatch, tmp_path, isolated):
    case, _, text = sample('基本信息：本科在读。希望申请开发实习。\n技能：了解Python。')
    outcome = deliver(monkeypatch, tmp_path, case, [(text, 'stop')])
    assert outcome['gates'] and not outcome['gates'][-1]['passed'], outcome
    assert outcome.get('error') == 'DELIVERY_QUALITY_FAILED', outcome
    assert outcome['results'] == 0 and outcome['inputs'] == 1
    assert not list(tmp_path.glob('*.docx'))
    assert not (tmp_path/'immutable_delivery_revision.jsonl').exists()


def test_warning_success_and_docx(monkeypatch, tmp_path, isolated):
    case, _, text = sample()
    outcome = deliver(monkeypatch, tmp_path, case, [(text, 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome
    assert outcome['gates'][-1]['passed']
    assert 'warning' in outcome['gates'][-1]['severities'] or 'observe' in outcome['gates'][-1]['severities']


def test_intro_attachments_part_of_revision_comparison():
    from app.services.immutable_delivery_revision_service import build_immutable_delivery_revision, revision_preserves_visible_delivery
    _, _, body = detail_return(detail_input(3))
    p = body['resume_sections']['projects'][0]
    p['intro'], p['intro_source_fact_ids'], p['intro_source_claim_ids'] = p['details'][0], p['detail_fact_ids'][0], p['detail_claim_ids'][0]
    payload = schemas.GenerationPayload.model_validate(body)
    revision = build_immutable_delivery_revision(payload, gate_passed=True)
    payload.resume_sections.projects[0]['intro_source_fact_ids'] = ['WRONG']
    assert not revision_preserves_visible_delivery(payload, revision)


def test_intro_claim_change_also_breaks_revision_comparison():
    from app.services.immutable_delivery_revision_service import build_immutable_delivery_revision, revision_preserves_visible_delivery
    _, _, body = detail_return(detail_input(3))
    payload = schemas.GenerationPayload.model_validate(body)
    payload.resume_sections.projects[0]['intro_source_claim_ids'] = ['CLAIM-A']
    revision = build_immutable_delivery_revision(payload, gate_passed=True)
    payload.resume_sections.projects[0]['intro_source_claim_ids'] = ['CLAIM-B']
    assert not revision_preserves_visible_delivery(payload, revision)


@pytest.mark.parametrize('repair', [False, True])
def test_truncation_does_not_reach_parser(repair, monkeypatch, isolated):
    _, _, text = sample()
    provider(monkeypatch, [(text[:-1] if repair else text, 'length')])
    case, build, _ = sample()
    def forbidden(*args, **kwargs):
        raise AssertionError('Truncated completion reached parser')
    monkeypatch.setattr(generation, 'parse_llm_json', forbidden)
    with pytest.raises(generation.GenerationServiceError) as caught:
        generation.build_llm_generation(request(case), build.long_input_context, consumer_views=build_canonical_consumer_views(build))
    assert caught.value.code == 'MODEL_OUTPUT_TRUNCATED'


@pytest.mark.parametrize('finish', ['length', 'stop'])
def test_saved_truncated_real_response_not_complete(finish, monkeypatch, tmp_path, isolated):
    fixtures = Path(__file__).parent/'fixtures'
    raw = (fixtures/'v091741_course_projects_input.txt').read_text(encoding='utf-8').rstrip('\n')
    case, _, _ = sample(raw)
    text = (fixtures/'v09176_truncated_response.txt').read_text(encoding='utf-8')
    meta = json.loads((fixtures/'v09176_truncated_provider.json').read_text(encoding='utf-8'))
    assert meta['finish_reason'] == 'length' and meta['usage']['completion_tokens'] == 4096
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)
    outcome = deliver(monkeypatch, tmp_path, case, [(text, finish)])
    if finish == 'length':
        assert outcome['error'] == 'MODEL_OUTPUT_TRUNCATED'
        assert not outcome['gates'] and outcome['results'] == 0
        assert len(outcome['sent']) == 2
    else:
        # Counterfactual metadata control, NOT the provider's original result.
        assert outcome['results'] == 1 and outcome['gates'][-1]['passed']


@pytest.mark.parametrize('first', ['length', 'evidence'])
def test_parse_error_cannot_hide_prior_contract_failure(first, monkeypatch, tmp_path, isolated):
    case, _, text = sample()
    if first == 'evidence':
        bad = json.loads(text)
        bad['resume_sections']['projects'][0]['fact_placements'].popitem()
        text = json.dumps(bad)
    outcome = deliver(monkeypatch, tmp_path, case, [(text, 'length' if first == 'length' else 'stop'), ('not json', 'stop')])
    assert outcome['error'] == ('MODEL_OUTPUT_TRUNCATED' if first == 'length' else 'MODEL_EVIDENCE_MISSING')
    assert outcome['results'] == 0 and not outcome['gates']


def test_legacy_receiver_does_not_acquire_completion_requirement(monkeypatch, isolated):
    case, build, body = detail_return(detail_input(3))
    sent = provider(monkeypatch, [(json.dumps(body), None)])
    payload, info = generation.build_llm_generation(request(case), build.long_input_context)
    assert payload.resume_sections.projects and len(sent) == 1
    assert info['finish_reason'] is None


def test_completion_log_is_correlated_and_contains_no_body(monkeypatch, tmp_path, isolated):
    _, _, text = sample()
    with pytest.raises(generation.GenerationServiceError):
        receive(monkeypatch, [(text, 'unknown-private-provider-text')])
    log = (tmp_path/'llm_calls.jsonl').read_text(encoding='utf-8')
    rows = [json.loads(line) for line in log.splitlines()]
    assert len(rows) == 2
    assert all(row['error_code'] == 'MODEL_FINISH_INVALID' for row in rows)
    assert all(row['attempt_id'] == 'v09162-controlled' for row in rows)
    assert 'unknown-private-provider-text' not in log and '接口校验工具' not in log


@pytest.mark.parametrize('total', [9, 21])
def test_retired_nested_writers_stay_out_and_final_payload_is_unchanged(total, monkeypatch, tmp_path, isolated):
    import importlib
    from test_v09175_post_processing_evidence import WRITERS, multi_detail_input, assert_complete
    names = {
        'resume_section_layering_service': 'layer_resume_sections',
        'resume_fact_increment_service': 'ensure_resume_fact_increment',
        'resume_information_gain_service': 'ensure_information_gain',
        'resume_dedup_quality_service': 'ensure_dedup_quality',
        'resume_fact_cluster_dedup_service': 'deduplicate_fact_clusters',
    }
    closed = []
    def forbidden(*a, **kw):
        raise AssertionError('Retired Canonical writer reached')
    for module, name in names.items():
        monkeypatch.setattr(importlib.import_module('app.services.' + module), name, forbidden)
        monkeypatch.setattr(generation, name, forbidden)
    for name in WRITERS:
        actual = getattr(generation, name)
        def write(*a, _fn=actual, **kw):
            assert not closed, 'Presentation writer executed after final Gate'
            return _fn(*a, **kw)
        monkeypatch.setattr(generation, name, write)
    gate = generation.validate_resume_delivery_quality
    def check(*a, **kw):
        result = gate(*a, **kw)
        if kw.get('stage') == 'after_final_owner_delivery_contract':
            closed.append(True)
        return result
    monkeypatch.setattr(generation, 'validate_resume_delivery_quality', check)
    case, build, text = sample(detail_input(total) if total == 9 else multi_detail_input(total))
    outcome = deliver(monkeypatch, tmp_path, case, [(text, 'stop')])
    assert closed and outcome['results'] == 1 and outcome['docx']
    assert_complete(outcome['saved']['resume_sections']['projects'], build)


@pytest.mark.parametrize('kind', ['success', 'gate', 'truncated'])
def test_real_task_status_matches_delivery(kind, monkeypatch, tmp_path, isolated):
    from sqlalchemy.orm import sessionmaker
    from app.services import generation_task_service as tasks
    from types import SimpleNamespace
    raw = '基本信息：本科在读。\n技能：了解Python。' if kind == 'gate' else detail_input(3)
    case, _, text = sample(raw)
    provider(monkeypatch, [(text, 'length' if kind == 'truncated' else 'stop')])
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    monkeypatch.setattr(tasks, 'SessionLocal', sessionmaker(bind=engine))
    monkeypatch.setattr(tasks.resource_protection, '_redis', None)
    monkeypatch.setattr(tasks.resource_protection, 'promote', lambda _: SimpleNamespace(status='running'))
    monkeypatch.setattr(tasks.resource_protection, 'release', lambda _: None)
    logs = []
    monkeypatch.setattr(tasks, 'write_structured_log', lambda *a, **kw: logs.append((a, kw)))
    manager = tasks.GenerationTaskManager()
    req = request(case)
    manager._save(tasks.GenerationTaskState(attempt_id=req.attempt_id, owner_hash='control', status='queued', request_id='req_closure_queue'))
    try:
        manager._run(req, 'control')
        state = manager.get(req.attempt_id)
        with Session(engine) as db:
            count = db.scalar(select(func.count()).select_from(models.GenerationResult))
        if kind == 'success':
            assert state.status == 'succeeded' and count == 1 and state.generation_result_id
        else:
            assert state.status == 'failed' and count == 0 and state.generation_result_id is None
            assert state.error_code == ('DELIVERY_QUALITY_FAILED' if kind == 'gate' else 'MODEL_OUTPUT_TRUNCATED')
            assert not any(a[1] == 'generation_task_succeeded' for a, _ in logs)
    finally:
        manager._executor.shutdown(wait=True)
        engine.dispose()
