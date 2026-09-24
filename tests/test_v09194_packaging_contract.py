"""Packaging permission must not weaken frozen evidence or delivery checks."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.services import experience_slot_service as slots
from app.services import generation_service as generation
from app.services import prompt_service as prompts
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import deliver
from test_v09192_evidence_bounded_expression import THIN, expression_sample
from test_v09193_evidence_bounded_composition import composition_sample, decision, coverage_reply, review_reply
from test_v091741_canonical_project_task_cleanup import COURSE, run_receiver


def _review(build, body):
    views = build_canonical_consumer_views(build)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    composed = slots.compose_model_fact_references(body, views, expression_review=review)
    return views, review, composed


def _editorial(source_id, source, candidate):
    return {
        **decision('editorial_expansion', source_id, source, candidate),
        'checks': {
            'source_meaning_preserved': True,
            'owner_scope_preserved': True,
            'qualification_preserved': True,
            'no_new_concrete_action': True,
            'no_new_hard_claim': True,
        },
    }


def test_writer_and_reviewer_receive_the_same_packaging_boundary(isolated):
    case, build, _ = composition_sample(combine=False)
    views = build_canonical_consumer_views(build)
    scope = prompts._expression_scope()
    assert any('编辑性展开' in rule for rule in scope)
    assert any('重大冲突' in rule for rule in scope)
    assert not any('保留全部实质信息' in rule for rule in scope)
    from test_v09162_model_output_evidence_contract import request
    written = prompts.build_generation_prompt(request(case), consumer_views=views)
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    review.candidates['test'] = {
        'owner': views.experience_ids[0], 'sources': {}, 'candidate': '测试候选',
        'position': 'detail', 'field_ids': [], 'field_text': '测试候选',
        'unit_index': 0, 'literal': False, 'signature': 'test',
    }
    reviewed = prompts.build_expression_review_prompt(review, views)
    assert 'editorial_expansion' in reviewed
    assert json.loads(written.split('<canonical_model_output_contract>')[1].split('</canonical_model_output_contract>')[0])['expression_scope'] == json.loads(reviewed.split('<expression_scope>')[1].split('</expression_scope>')[0])


def test_editorial_expansion_receipt_preserves_full_source_and_expires_on_change(isolated):
    _, build, body = composition_sample(combine=False)
    unit = body['resume_sections']['projects'][0]['expression_units'][0]
    fact_id = unit['fact_ids'][0]
    source = unit['text']
    unit['text'] = source.rstrip('。') + '，形成清晰的资料查询流程。'
    views, review, composed = _review(build, body)
    assert fact_id in review.pending
    review.accept(coverage_reply(review, {fact_id: _editorial(fact_id, source, '形成清晰的资料查询流程')}))
    checked = slots.validate_model_project_evidence(composed, views, expression_review=review,
                                                    require_complete=True, write_log=False)
    project = checked['resume_sections']['projects'][0]
    assert project['detail_fact_ids'][0] == [fact_id]
    assert project['detail_claim_ids'][0]
    changed = deepcopy(checked)
    changed['resume_sections']['projects'][0]['details'][0] += '，提升效率50%'
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.validate_model_project_evidence(changed, views, expression_review=review,
                                              require_complete=True, write_log=False)


@pytest.mark.parametrize('position', ['intro', 'role', 'detail'])
def test_editorial_receipt_and_lineage_are_field_specific(position, isolated):
    _, build, body = composition_sample(position=position, combine=False)
    unit = body['resume_sections']['projects'][0]['expression_units'][0]
    fact_id = unit['fact_ids'][0]
    source = unit['text']
    unit['text'] = source.rstrip('。') + '，形成清晰的资料查询流程。'
    views, review, composed = _review(build, body)
    review.accept(coverage_reply(review, {fact_id: _editorial(fact_id, source, '形成清晰的资料查询流程')}))
    checked = slots.validate_model_project_evidence(composed, views, expression_review=review,
                                                    require_complete=True, write_log=False)
    project = checked['resume_sections']['projects'][0]
    ids = project['detail_fact_ids'][0] if position == 'detail' else project[f'{position}_source_fact_ids']
    claims = project['detail_claim_ids'][0] if position == 'detail' else project[f'{position}_source_claim_ids']
    assert fact_id in ids
    assert next(f.claim_id for f in build.ledger.facts if f.fact_id == fact_id) in claims
    assert review.editorial_accepted_count == 1


def test_editorial_expansion_reaches_save_and_docx(monkeypatch, tmp_path, isolated):
    case, build, body, _ = expression_sample(THIN, rewrite=False)
    fact = next(f for f in build.ledger.facts if f.resume_ready_text == '我帮忙测试')
    unit = next(u for u in body['resume_sections']['projects'][0]['expression_units']
                if u['fact_ids'] == [fact.fact_id])
    unit['text'] = '在项目中协助开展测试工作。'
    review = review_reply(build, body, {fact.fact_id: _editorial(fact.fact_id, '我帮忙测试', '在项目中协助开展测试工作')})
    log_dir = tmp_path / 'logs'
    log_dir.mkdir()
    monkeypatch.setattr(generation, 'LOG_DIR', log_dir)
    outcome = deliver(monkeypatch, tmp_path, case, [
        (json.dumps(body, ensure_ascii=False), 'stop'),
        (json.dumps(review, ensure_ascii=False), 'stop'),
    ])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    project = outcome['saved']['resume_sections']['projects'][0]
    index = next(i for i, detail in enumerate(project['details']) if '协助开展测试工作' in detail)
    assert project['detail_fact_ids'][index] == [fact.fact_id]
    assert project['detail_claim_ids'][index] == [fact.claim_id]
    logs = [json.loads(line) for line in (log_dir / 'llm_calls.jsonl').read_text(encoding='utf-8').splitlines()]
    accepted = next(row for row in logs if row.get('stage') == 'generation_expression_review_validated')
    assert accepted['editorial_accepted_count'] == 1
    assert '协助开展测试工作' not in json.dumps(accepted, ensure_ascii=False)


@pytest.mark.parametrize('candidate,verdict,source,candidate_excerpt', [
    ('独立负责整个系统架构。', 'added_claim', None, '独立负责整个系统架构'),
    ('使用Vue完成页面并使通过率提升50%。', 'added_claim', None, '通过率提升50%'),
    ('负责使用Vue制作设备列表和登记表单。', 'changed_qualification', '只负责', '负责'),
])
def test_hard_claims_and_qualification_changes_still_rejected(
    candidate, verdict, source, candidate_excerpt, isolated,
):
    _, build, body = composition_sample(combine=False)
    unit = body['resume_sections']['projects'][1]['expression_units'][0]
    unit['text'] = candidate
    _, review, _ = _review(build, body)
    key = unit['fact_ids'][0]
    replies = {fid: decision() for fid in review.pending}
    replies[key] = decision(verdict, key if source else None, source, candidate_excerpt)
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(coverage_reply(review, replies))
    assert caught.value.code == 'MODEL_EXPRESSION_REJECTED'


def test_unclaimed_owner_evidence_still_rejected(isolated):
    _, build, body = composition_sample(combine=False)
    unit = body['resume_sections']['projects'][0]['expression_units'][0]
    unit['text'] += '，并完成第二个项目的页面联调'
    _, review, _ = _review(build, body)
    replies = {fid: decision() for fid in review.pending}
    replies[unit['fact_ids'][0]] = decision('added_claim', candidate='第二个项目的页面联调')
    with pytest.raises(slots.ModelEvidenceContractError):
        review.accept(coverage_reply(review, replies))


@pytest.mark.parametrize('change', ['missing_checks', 'unconfirmed', 'foreign_source', 'wrong_excerpt'])
def test_editorial_verdict_requires_structured_current_owner_evidence(change, isolated):
    _, build, body = composition_sample(combine=False)
    unit = body['resume_sections']['projects'][0]['expression_units'][0]
    fact_id = unit['fact_ids'][0]
    source = unit['text']
    unit['text'] = source.rstrip('。') + '，形成清晰的资料查询流程。'
    _, review, _ = _review(build, body)
    verdict = _editorial(fact_id, source, '形成清晰的资料查询流程')
    if change == 'missing_checks':
        verdict.pop('checks')
    elif change == 'unconfirmed':
        verdict['checks']['qualification_preserved'] = False
    elif change == 'foreign_source':
        verdict['source_fact_id'] = 'EXP-002-F001'
    else:
        verdict['candidate_excerpt'] = '不存在的候选片段'
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(coverage_reply(review, {fact_id: verdict}))
    assert caught.value.code == 'MODEL_EXPRESSION_REVIEW_INVALID'
    assert not review.accepted


@pytest.mark.parametrize('long_mode', [False, True])
@pytest.mark.parametrize('kind', ['unique', 'retry_corrected'])
def test_actual_writer_task_uses_bounded_packaging_on_first_call_and_retry(
    long_mode, kind, monkeypatch, isolated,
):
    output, error, sent, build = run_receiver(COURSE, kind, long_mode, monkeypatch)
    assert output is not None and error is None
    assert len(sent) == (2 if kind == 'retry_corrected' else 1)
    for actual in sent:
        contract = json.loads(actual.split('<canonical_model_output_contract>')[1].split('</canonical_model_output_contract>')[0])
        scope = contract['expression_scope']
        assert any('编辑性展开' in rule for rule in scope)
        assert any('辅助性质' in rule for rule in scope)
        assert '全部 owner 提供的每个 eligible Fact 必须声明；同owner关联单元整体须有意义地表达' in actual
        assert '不得新增精确数字、技术、客户、上线、奖项、证书、职位' in actual
        evidence = json.loads(actual.split('<canonical_model_evidence>')[1].split('</canonical_model_evidence>')[0])
        assert {f['fact_id'] for owner in evidence['owners'] for f in owner['eligible_facts']} == {
            fact.fact_id for fact in build.ledger.facts
        }


def test_heldout_research_input_preserves_owner_and_source_with_editorial_review(
    monkeypatch, tmp_path, isolated,
):
    cases = json.loads((Path(__file__).parent / 'fixtures/v091811_normal_inputs.json').read_text(encoding='utf-8'))
    raw = next(row['raw_input'] for row in cases if row['case'] == 'research')
    case, build, body = composition_sample(raw, combine=False)
    project = body['resume_sections']['projects'][0]
    unit = project['expression_units'][0]
    fact_id = unit['fact_ids'][0]
    source = unit['text']
    unit['text'] = source.rstrip('。') + '，使实验资料的组织更加清晰。'
    reply = review_reply(build, body, {fact_id: _editorial(fact_id, source, '使实验资料的组织更加清晰')})
    outcome = deliver(monkeypatch, tmp_path, case, [
        (json.dumps(body, ensure_ascii=False), 'stop'),
        (json.dumps(reply, ensure_ascii=False), 'stop'),
    ])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    actual = outcome['saved']['resume_sections']['projects'][0]
    assert actual['source_experience_id'] == project['source_experience_id']
    assert fact_id in actual['source_fact_ids']
    assert actual['source_claim_ids']
