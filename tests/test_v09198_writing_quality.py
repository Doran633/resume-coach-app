"""Human drafts and controlled provider replies test delivery, not model quality."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest
from docx import Document

from app.services import generation_service as generation, experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.experience_slot_service import provenance_text_unchanged
from test_v09162_model_output_evidence_contract import request
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import deliver, provider
from test_v09193_evidence_bounded_composition import composition_sample, coverage_reply, decision

CASES = json.loads((Path(__file__).parent / 'fixtures/v09198_writing_quality_cases.json').read_text(encoding='utf-8'))
HOLDOUT = json.loads((Path(__file__).parent / 'fixtures/v09198_writing_quality_holdout.json').read_text(encoding='utf-8'))


def target_sample(sample, position='detail'):
    case, build, body = composition_sample(sample['raw_input'], combine=False)
    case['target_role'] = sample['target_role']
    body['resume_sections']['summary'] = sample['summary'][:]
    projects = []
    for draft in sample['projects']:
        owner = draft['source_experience_id']
        facts = build.ledger.for_experience(owner)
        units = []
        for index, unit in enumerate(draft['units']):
            ids = []
            for source in unit['source_texts']:
                matches = [f for f in facts if f.resume_ready_text == source]
                assert len(matches) == 1, (source, matches)
                ids.append(matches[0].fact_id)
            units.append({'fact_ids': ids, 'position': position if index == 0 else 'detail', 'text': unit['text']})
        assert {fid for unit in units for fid in unit['fact_ids']} == {f.fact_id for f in facts}
        projects.append({'source_experience_id': owner, 'expression_units': units})
    body['resume_sections']['projects'] = projects
    # Offline editorial attribution is not a model trust flag or a new API field.
    for evidence in sample['summary_evidence']:
        facts = build.ledger.for_experience(evidence['source_experience_id'])
        assert all(sum(f.resume_ready_text == text for f in facts) == 1
                   for text in evidence['source_texts'])
    return case, build, body


def controlled_review(build, body):
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    slots.compose_model_fact_references(body, views, expression_review=review)
    # Provider judgments are deliberately controlled; the receiver itself is real.
    reply = coverage_reply(review, {key: decision() for key in review.pending})
    return views, review, reply


def rows(project):
    result = [(project.get(p, ''), project.get(p + '_source_fact_ids', []),
               project.get(p + '_source_claim_ids', [])) for p in ('intro', 'role')]
    return [row for row in result if row[0]] + list(zip(
        project['details'], project['detail_fact_ids'], project['detail_claim_ids']))


@pytest.mark.parametrize('sample', CASES, ids=lambda s: s['key'])
@pytest.mark.parametrize('long_mode', [False, True])
def test_actual_writer_task_has_one_shared_editorial_brief(sample, long_mode, monkeypatch, tmp_path, isolated):
    case, build, _ = target_sample(sample)
    _, _, literal = composition_sample(sample['raw_input'], combine=False)
    views = build_canonical_consumer_views(build)
    before = deepcopy(build), repr(views)
    monkeypatch.setenv('MAX_LLM_CALLS_PER_ATTEMPT', '3')
    sent = provider(monkeypatch, [('not json', 'stop'), (json.dumps(literal, ensure_ascii=False), 'stop')])
    generation.build_llm_generation(request(case), replace(build.long_input_context, long_input_mode=long_mode), consumer_views=views)
    assert len(sent) == 2
    for index, wire in enumerate(sent):
        text = wire['messages'][1]['content']
        (tmp_path / f'writer-{index}.txt').write_text(text, encoding='utf-8')
        assert text.count('<canonical_writing_brief>') == 1
        brief = text.split('<canonical_writing_brief>', 1)[1].split('</canonical_writing_brief>', 1)[0]
        assert all(section in brief for section in ('正文组织', '表头与正文', '个人优势', '完整对照', '非线上拒绝条件'))
        assert '实际参与关系' in brief and '辅助过程' in brief and '来源甲、乙' in brief
        assert '团队' in brief and '关键行动' in brief and '不借目标岗位补能力' in brief
        assert '每条建议 35-70 个中文字符' not in text
        evidence = json.JSONDecoder().raw_decode(text.split('<canonical_model_evidence>\n')[1])[0]
        actual_facts = [f for owner in evidence['owners'] for f in owner['eligible_facts']]
        assert {f['fact_id']: f['resume_ready_text'] for f in actual_facts} == {f.fact_id: f.resume_ready_text for f in build.ledger.facts}
        assert {f['fact_id']: f['source_claim_ids'] for f in actual_facts} == {f.fact_id: [f.claim_id] for f in build.ledger.facts}
    assert (build, repr(views)) == before


def assert_target_delivery(sample, position, monkeypatch, tmp_path):
    case, build, body = target_sample(sample, position)
    views, review, reply = controlled_review(build, body)
    before = deepcopy(build), repr(views), deepcopy(body)
    stages = []
    for name in ('bind_projects_to_experience_slots', 'guard_template_language',
                 'professionalize_resume_language', '_check_final_expression_evidence'):
        actual = getattr(generation, name)
        def observe(payload, *args, _actual=actual, _name=name, **kwargs):
            result = _actual(payload, *args, **kwargs)
            value = result[0] if isinstance(result, tuple) else result
            value = value if hasattr(value, 'resume_sections') else payload
            stages.append({'stage': _name, 'payload': value.model_dump()})
            return result
        monkeypatch.setattr(generation, name, observe)
    outcome = deliver(monkeypatch, tmp_path, case, [
        (json.dumps(body, ensure_ascii=False), 'stop'), (json.dumps(reply, ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome.get('error', outcome['gates'])
    assert len(outcome['sent']) == 2 and outcome['gates'][-1]['passed']
    docx_text = '\n'.join(p.text for p in Document(next(tmp_path.glob('*.docx'))).paragraphs)
    stages.append({'stage': 'saved', 'payload': outcome['saved']})
    (tmp_path / 'writing-stages.json').write_text(json.dumps(stages, ensure_ascii=False, indent=2), encoding='utf-8')
    for stage in stages:
        payload = stage['payload']
        for original, project in zip(body['resume_sections']['projects'], payload['resume_sections']['projects']):
            assert original['source_experience_id'] == project['source_experience_id']
            actual_rows = rows(project)
            for unit in original['expression_units']:
                matched = [r for r in actual_rows if provenance_text_unchanged(unit['text'], r[0])]
                assert len(matched) == 1, (stage['stage'], unit, actual_rows)
                _, ids, claims = matched[0]
                assert ids == unit['fact_ids']
                expected_claims = list(dict.fromkeys(next(f.claim_id for f in build.ledger.facts if f.fact_id == fid) for fid in ids))
                assert claims == expected_claims
            assert set(project['source_fact_ids']) == {f.fact_id for f in build.ledger.for_experience(project['source_experience_id'])}
        assert len(payload['resume_sections']['summary']) == len(body['resume_sections']['summary'])
        assert all(provenance_text_unchanged(a, b) for a, b in zip(body['resume_sections']['summary'], payload['resume_sections']['summary']))
    for project in outcome['saved']['resume_sections']['projects']:
        for text, _, _ in rows(project):
            assert text in docx_text and text in outcome['saved']['bold_version']
    assert all(text in docx_text for text in outcome['saved']['resume_sections']['summary'])
    assert (build, repr(views), body) == before
    assert reply['coverage'] and all(r['verdict'] == 'complete' for r in reply['coverage'].values())


@pytest.mark.parametrize('sample', CASES, ids=lambda s: s['key'])
@pytest.mark.parametrize('position', ['intro', 'role', 'detail'])
def test_human_editorial_target_survives_real_delivery(sample, position, monkeypatch, tmp_path, isolated):
    assert_target_delivery(sample, position, monkeypatch, tmp_path)


@pytest.mark.parametrize('position', ['intro', 'role', 'detail'])
def test_heldout_target_after_primary_implementation(position, monkeypatch, tmp_path, isolated):
    assert_target_delivery(HOLDOUT, position, monkeypatch, tmp_path)


@pytest.mark.parametrize('kind,verdict', [
    ('duties', 'changed_qualification'), ('action', 'added_claim'),
    ('outcome', 'added_claim'), ('uncertain', 'uncertain'), ('omission', 'omitted'),
])
def test_nearby_overreach_and_omission_still_fail(kind, verdict, monkeypatch, tmp_path, isolated):
    case, build, body = target_sample(CASES[1])
    units = body['resume_sections']['projects'][0]['expression_units']
    if kind == 'duties':
        units[0]['text'] = '与一位同学合作，独立主导活动报名系统整体开发并部署上线。'
    elif kind == 'action':
        units[0]['text'] += '设计接口并实现防抖处理。'
    elif kind == 'outcome':
        units[1]['text'] += '将报名转化率提升30%。'
    elif kind == 'omission':
        units[1]['text'] = '检查空输入时的页面提示，项目已在课堂演示。'
    views, review, reply = controlled_review(build, body)
    if kind == 'omission':
        fact = next(f for f in build.ledger.facts if '重复点击' in f.resume_ready_text)
        reply['coverage'][fact.fact_id].update(verdict='omitted', source_excerpt='重复点击')
    else:
        key = next(k for k, row in review.pending.items() if row['candidate'] == units[1 if kind == 'outcome' else 0]['text'])
        fid = units[0]['fact_ids'][1] if kind == 'duties' else None
        reply['decisions'][key] = decision(verdict, fid, '只负责' if fid else None, review.pending[key]['candidate'])
    outcome = deliver(monkeypatch, tmp_path, case, [
        (json.dumps(body, ensure_ascii=False), 'stop'), (json.dumps(reply, ensure_ascii=False), 'stop')])
    expected = 'MODEL_EXPRESSION_REVIEW_UNCERTAIN' if kind == 'uncertain' else 'MODEL_EXPRESSION_REJECTED'
    assert outcome['error'] == expected
    assert outcome['results'] == 0 and not list(tmp_path.glob('*.docx')) and len(outcome['sent']) == 2


@pytest.mark.parametrize('sample', CASES, ids=lambda s: s['key'])
def test_original_wording_is_still_compatible_not_a_quality_rejection(sample, monkeypatch, tmp_path, isolated):
    case, build, body = composition_sample(sample['raw_input'], combine=False)
    case['target_role'] = sample['target_role']
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome and len(outcome['sent']) == 1
    for original, project in zip(body['resume_sections']['projects'], outcome['saved']['resume_sections']['projects']):
        actual = rows(project)
        for unit in original['expression_units']:
            matched = [row for row in actual if provenance_text_unchanged(unit['text'], row[0])]
            assert len(matched) == 1 and matched[0][1] == unit['fact_ids']
