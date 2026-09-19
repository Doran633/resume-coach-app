"""Inspect actual network-bound tasks; controlled responses are not model history."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import re

import pytest

from app.services import generation_service as generation
from app.services import prompt_service as prompts
from app.services import experience_slot_service as slots
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.llm_service import LLMResult
from test_v09162_model_output_evidence_contract import CASES, controlled_return, request
from test_v09174_fact_reference_composition import isolated, references


RAW = (Path(__file__).parent / 'fixtures/v091741_course_projects_input.txt').read_text(encoding='utf-8').rstrip('\n')
COURSE = {**CASES[0], 'result_id': 'new_course_control', 'raw_input': RAW, 'target_role': 'AI应用开发实习'}
INPUTS = [COURSE, *CASES]
LEGACY_HASHES = {
    False: '6dbf53d7ccd1f1868d3597c542ce0e22f8883474e15ad72c7824667b299b1319',
    True: '9972ac822e336a89982dc62af8f3d77f6372aad41607aa0ea53cb2dea8d0bc09',
}
CONTRACT_HASH = 'bbb9202793fd1b2404096de7204371cb28720f9ced68b1755600dbb202028baf'
# Filled after reviewing the entire captured static task, not generated at test runtime.
REVIEWED_TASK_HASHES = {
    False: '9697e04826403b8378de56cd9ec80ccdfcdf9d810761dae04fb5a71ab93bb38d',
    True: '0a861b761efdc89c3070b4d76f3669502fa23b5f212ea48b754524dcec59679d',
}
RETIRED = {
    False: (
        '只有系统明确提供合并关系时才能合并',
        '项目详情采用“动作 + 对象/技术 + 结果或目的”结构',
        'project.meta 必须服从后端基于 source_experience_id 提供的 resolved_type',
        '不得写进 resume_sections.summary 或 resume_sections.projects',
        '每个主要项目至少应体现项目定位、我的职责、技术动作、结果或证据、面试承接点',
        '每条项目 detail 应呈现问题、工程动作、机制或价值',
        'Resume Coach 类工程项目应突出真实用户需求、业务异常、解决方案、可观测性与架构演进',
        '事实较少但信息明确的项目，应优先从本段 experience_id 恢复目标、职责、功能、技术、结果和证据',
        'Fallback 和覆盖恢复只允许使用当前 Slot 的可输出事实',
        'summary、skills、intro、role 和 details 数组项直接写正文',
    ),
    True: (
        '不能原样写入 resume_sections.summary 或 projects',
        'project.meta 必须服从对应 source_experience_id 的后端 resolved_type',
        '每条 detail 必须包含新的问题、动作、机制、证据或结果',
        '不得进入 summary、skills、intro、role 或 details',
    ),
}


def digest(text):
    return sha256(re.sub(r'\s+', ' ', text).strip().encode()).hexdigest()


def reviewed_task(prompt):
    # Mask only known request data; all instructions and the full protocol remain.
    prompt = re.sub(r'<canonical_model_evidence>\n.*?\n</canonical_model_evidence>', '{FROZEN_EVIDENCE}', prompt, flags=re.S)
    prompt = re.sub(r'^- (目标岗位|生成模式|包装强度|经历类型)：[^\n]*', r'- \1：{REQUEST_VALUE}', prompt, flags=re.M)
    prompt = re.sub(r'(系统识别出的低置信度分段追问（只能加入 missing_questions，不得自行认定）：\n).*?(?=\n\n)', r'\1{QUESTIONS}', prompt, flags=re.S)
    return prompt


def run_receiver(case, kind, long_mode, monkeypatch):
    build, body = controlled_return(case)
    views = build_canonical_consumer_views(build)
    good = references(body)
    for p in good['resume_sections']['projects']:
        ids = [f.fact_id for f in views.facts_for_owner(p['source_experience_id'])]
        p['fact_placements'] = {fid: dict(p['fact_placements'][fid], position='detail') for fid in ids}
    wire = deepcopy(good)
    if kind in ('within_row','across_fields','overlap','retry_corrected'):
        # Old overlap fixtures remain negative controls after protocol retirement.
        wire['resume_sections']['projects'] = [dict(
            source_experience_id=p['source_experience_id'], intro_source_fact_ids=[],
            role_source_fact_ids=[], detail_fact_ids=[[fid] for fid in p['fact_placements']],
        ) for p in good['resume_sections']['projects']]
    p = wire['resume_sections']['projects'][0]
    ids = list(good['resume_sections']['projects'][0]['fact_placements'])
    if kind == 'within_row':
        p['detail_fact_ids'][0].append(ids[0])
    elif kind in ('across_fields', 'retry_corrected'):
        p['intro_source_fact_ids'] = [ids[0]]
    elif kind == 'overlap':
        p['detail_fact_ids'] = [ids[:2], ids[1:3]] + [[fid] for fid in ids[3:]]
    elif kind == 'combination':
        p['fact_placements'] = {fid: dict(p['fact_placements'][fid], position=('intro' if i < 2 else 'detail')) for i,fid in enumerate(ids)}
    before = deepcopy(build), repr(views), deepcopy(wire)
    sent = []
    def network(prompt):
        sent.append(prompt)
        response = good if kind == 'retry_corrected' and len(sent) == 2 else wire
        return LLMResult(finish_reason="stop", text=json.dumps(response, ensure_ascii=False), model='controlled-task-cleanup', latency_ms=0)
    monkeypatch.setattr(generation, 'call_openai', network)
    output = error = None
    try:
        output, _ = generation.build_llm_generation(request(case), replace(build.long_input_context, long_input_mode=long_mode), consumer_views=views)
    except generation.GenerationServiceError as exc:
        error = exc.code
    assert (build, repr(views), wire) == before
    return output, error, sent, build


@pytest.mark.parametrize('case', INPUTS, ids=lambda c:str(c['result_id']))
@pytest.mark.parametrize('long_mode', [False, True])
@pytest.mark.parametrize('kind', ['unique', 'retry_corrected'])
def test_entire_actual_task_and_retry(case, long_mode, kind, monkeypatch, tmp_path, isolated):
    output, error, sent, build = run_receiver(case, kind, long_mode, monkeypatch)
    assert error is None and output is not None
    assert len(sent) == (2 if kind == 'retry_corrected' else 1)
    for index, text in enumerate(sent):
        (tmp_path / f'actual-sent-{index+1}.txt').write_text(text, encoding='utf-8')
        leaked = [unit for unit in RETIRED[long_mode] if unit in text]
        assert not leaked, leaked
        assert '<!-- legacy-project -->' not in text
        evidence = json.JSONDecoder().raw_decode(text.split('<canonical_model_evidence>\n')[1])[0]
        for owner in evidence['owners']:
            facts = {f.fact_id:f for f in build.ledger.for_experience(owner['source_experience_id'])}
            for fact in owner['eligible_facts']:
                original = facts[fact['fact_id']]
                assert fact['resume_ready_text'] == original.resume_ready_text
                assert fact['source_span'] == list(original.source_span)
                assert fact['source_claim_ids'] == [original.claim_id]
        assert 'internal_constraints_not_resume_facts' in evidence
        assert 'non_experience_context_not_project_facts' in evidence
    assert digest(reviewed_task(sent[0])) == REVIEWED_TASK_HASHES[long_mode]
    assert sha256(prompts._canonical_output_contract().encode()).hexdigest() == CONTRACT_HASH
    if len(sent) == 2:
        suffix = '\n\n上次返回未满足内部来源契约：MODEL_EVIDENCE_FORMAT: format_fact_placements, format_forbidden_project_fields, missing_fact_assignment, missing_reference_fields。请按已有内部 JSON 字段协议重新输出完整对象；不得自报可信或冻结状态。'
        assert sent[1] == sent[0] + suffix
    expected = {f.fact_id for owner in build.identities for f in build.ledger.for_experience(owner.experience_id)}
    actual = [fid for p in output.resume_sections.projects for fid in p['source_fact_ids']]
    assert set(actual) == expected and len(actual) == len(expected)


@pytest.mark.parametrize('long_mode', [False, True])
@pytest.mark.parametrize('kind', ['within_row','across_fields','overlap','combination'])
def test_unchanged_duplicate_rejection_and_composition(kind, long_mode, monkeypatch, isolated):
    output, error, sent, _ = run_receiver(COURSE, kind, long_mode, monkeypatch)
    rows = [json.loads(line) for line in slots.LOG_PATH.read_text(encoding='utf-8').splitlines()]
    if kind == 'combination':
        assert output is not None and error is None and len(sent) == 1
        assert all(row['contract_passed'] for row in rows)
    else:
        assert output is None and error == 'MODEL_EVIDENCE_FORMAT' and len(sent) == 2
        assert len(rows) == 2
        for row in rows:
            assert row['required_fact_count'] == 10 and row['assigned_fact_count'] == 0
            assert row['evidence_reason_counts'] == {
                'format_fact_placements':2, 'format_forbidden_project_fields':2,
                'missing_reference_fields':2, 'missing_fact_assignment':1,
            }


@pytest.mark.parametrize('long_mode', [False, True])
def test_full_legacy_template_and_actual_legacy_receiver_unchanged(long_mode, monkeypatch, isolated):
    name = 'generate_resume_coach_result_long.md' if long_mode else 'generate_resume_coach_result.md'
    assert digest(prompts._generation_template(name)) == LEGACY_HASHES[long_mode]
    build, body = controlled_return(COURSE)
    sent = []
    def network(prompt):
        sent.append(prompt)
        return LLMResult(finish_reason="stop", text=json.dumps(body,ensure_ascii=False),model='legacy-control',latency_ms=0)
    monkeypatch.setattr(generation,'call_openai',network)
    output, _ = generation.build_llm_generation(request(COURSE), replace(build.long_input_context,long_input_mode=long_mode))
    assert output.resume_sections.projects and len(sent) == 1
    assert '<canonical_model_output_contract>' not in sent[0]
    assert all(unit in sent[0] for unit in RETIRED[long_mode])
