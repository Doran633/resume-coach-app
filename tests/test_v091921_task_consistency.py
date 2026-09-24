"""Task changes are inspected at the real receiver's controlled network boundary."""
from copy import deepcopy
import json

import pytest

from app.services import prompt_service as prompts
from test_v091741_canonical_project_task_cleanup import COURSE, INPUTS, run_receiver
from test_v09174_fact_reference_composition import isolated
from test_v09192_evidence_bounded_expression import expression_sample, THIN, LIMITED
from test_v091921_expression_scope import decision
from test_v09176_delivery_closure import deliver


CONFLICTS = {
    False: (
        '职责表达可适度拉高', '必须能被事实、知识或面试准备承接',
        '允许把参与核心流程、接口联调、问题排查表达为核心模块贡献',
        '普通版、 大胆版、边界版都要比用户原文更充实',
        '可以使用 compact_context 中标记为“可写入简历”的自然承接知识',
        '负责核心页面开发、交互状态流转与接口联调',
        '围绕核心接口链路完成联调、问题定位与稳定性优化',
        '不能与用户原始输入高度相似', '必须改写为可投递表达',
        '不能只复述“写了页面、调了接口、做了展示”',
    ),
    True: (
        '职责、技术动作、问题排查、结果表达可以更正式，但不能改变硬事实',
        '可以使用本段标记为“可写入简历”的自然承接知识',
        '但要突出需求理解、功能实现、协作沟通、材料沉淀、展示答辩和复盘能力',
        '禁止“我做过、我写了、我调了、技术动作、项目动作”等口语和内部标签',
    ),
}


@pytest.mark.parametrize('long_mode', [False, True])
@pytest.mark.parametrize('kind', ['unique', 'retry_corrected'])
@pytest.mark.parametrize('case', [*INPUTS, {**COURSE, 'raw_input': THIN}, {**COURSE, 'raw_input': LIMITED}])
def test_actual_tasks_retire_competing_permissions(case, long_mode, kind, monkeypatch, tmp_path, isolated):
    output, error, sent, build = run_receiver(case, kind, long_mode, monkeypatch)
    assert output is not None and error is None
    assert len(sent) == (2 if kind == 'retry_corrected' else 1)
    for i, text in enumerate(sent):
        (tmp_path / f'complete-sent-{i}.txt').write_text(text, encoding='utf-8')
        assert not [rule for rule in CONFLICTS[long_mode] if rule in text]
        assert text.count('<canonical_expression_tasks>') == 1
        task = text.split('<canonical_expression_tasks>')[1].split('</canonical_expression_tasks>')[0]
        assert 'resume_sections.projects' in task and 'expression_scope' in task
        assert all(field in task for field in ('normal_version', 'bold_version', 'recommended_version', 'boundary_version'))
        assert '四个必需的顶层字符串字段' in task
        assert '辅助性质' in task and '不以字数、相似度或必须改写' in task
        assert '不是新增行动或职责的授权' in task
        assert '不能作为正式项目的事实来源' in task
        assert 'interview_plan' in task and 'knowledge_checklist' in task
        evidence = json.loads(text.split('<canonical_model_evidence>')[1].split('</canonical_model_evidence>')[0])
        actual = {f['fact_id']: f['resume_ready_text'] for o in evidence['owners'] for f in o['eligible_facts']}
        assert actual == {f.fact_id: f.resume_ready_text for f in build.ledger.facts}


@pytest.mark.parametrize('long_mode', [False, True])
def test_legacy_retains_its_existing_expression_task(long_mode):
    name = 'generate_resume_coach_result_long.md' if long_mode else 'generate_resume_coach_result.md'
    text = prompts._generation_template(name)
    assert all(rule in text for rule in CONFLICTS[long_mode])
    assert '<canonical_expression_tasks>' not in text
    assert '<!-- legacy-expression -->' not in text


def test_assisting_role_control_saves_without_expanding_evidence(monkeypatch, tmp_path, isolated):
    case, build, body, _ = expression_sample(THIN, rewrite=False)
    before = deepcopy(build)
    fact = next(f for f in build.ledger.facts if f.resume_ready_text == '我帮忙测试')
    candidate = '协助开展测试工作。'
    next(u for u in body['resume_sections']['projects'][0]['expression_units'] if u['fact_ids'] == [fact.fact_id])['text'] = candidate
    reply = {'decisions': {fact.fact_id: decision()}}
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop'), (json.dumps(reply), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome
    project = outcome['saved']['resume_sections']['projects'][0]
    index = project['details'].index(candidate.rstrip('。'))
    assert project['detail_fact_ids'][index] == [fact.fact_id]
    assert project['detail_claim_ids'][index] == [fact.claim_id]
    assert build == before and len(outcome['sent']) == 2


@pytest.mark.parametrize('candidate,verdict,excerpt', [
    ('独立制定测试方案并定位问题。', 'added_claim', '独立制定测试方案并定位问题'),
    ('协助测试并使通过率提升50%。', 'added_claim', '使通过率提升50%'),
    ('协助使用Vue测试课程展示网站。', 'added_claim', '使用Vue测试课程展示网站'),
])
def test_controlled_review_rejection_remains_closed(candidate, verdict, excerpt, monkeypatch, tmp_path, isolated):
    case, build, body, _ = expression_sample(THIN, rewrite=False)
    fact = next(f for f in build.ledger.facts if f.resume_ready_text == '我帮忙测试')
    next(u for u in body['resume_sections']['projects'][0]['expression_units'] if u['fact_ids'] == [fact.fact_id])['text'] = candidate
    # Controlled verdicts validate wiring, not real reviewer discrimination.
    reply = {'decisions': {fact.fact_id: decision(verdict, None, excerpt)}}
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(body, ensure_ascii=False), 'stop'), (json.dumps(reply), 'stop')])
    assert outcome['error'] == 'MODEL_EXPRESSION_REJECTED'
    assert outcome['results'] == 0 and len(outcome['sent']) == 2
    assert not list(tmp_path.glob('*.docx'))


def test_unpaired_expression_branch_is_not_silently_used(monkeypatch):
    monkeypatch.setattr(prompts, 'load_prompt', lambda name: '<!-- legacy-expression -->task')
    with pytest.raises(ValueError, match='Unpaired template block'):
        prompts._generation_template('unused', canonical=True)
