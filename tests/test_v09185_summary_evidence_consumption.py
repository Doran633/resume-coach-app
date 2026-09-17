"""Current controlled returns, not reconstructed historical model responses."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sys

import pytest
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app import schemas
from app.services import generation_service as generation, prompt_service
from app.services import resume_summary_quality_service as summary_quality
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.fact_guard_service import guard_hard_facts
from app.services.resume_body_sanitizer_service import sanitize_resume_body
from app.services.resume_output_firewall_service import guard_resume_output
from app.services.input_content_classification_service import strip_non_fact_fragments, classify_input_content
from test_v0916_canonical_model_evidence import evidence
from test_v09162_model_output_evidence_contract import reference_return, request
from test_v09172_initial_evidence_preservation import detail_return
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import deliver, provider


FIXTURES = Path(__file__).parent / 'fixtures'
NORMAL = json.loads((FIXTURES / 'v091811_normal_inputs.json').read_text(encoding='utf-8'))
SUMMARIES = [
    '参与前端页面开发、接口联调和问题修复。',
    '负责课程项目后端接口开发；团队获得校赛二等奖。',
    '具备音频数据整理和实验记录实践，接触过PyTorch。',
]
AWARD = '竞赛经历：数据分析竞赛\n团队获得三等奖。使用Python整理调查结果。'
NO_AWARD = '项目经历：课程练习工具\n使用Java开发查询页面，没有获奖。'
LIMITED = '个人项目：日志整理工具\n使用Python整理日志，工具仅在本地运行，没有上线。'
WRITERS = (
    'normalize_resume_section_schema', 'cleanup_generation_payload', 'guard_hard_facts',
    'fill_resume_sections', 'ensure_packaging_gain', 'sanitize_resume_body',
    'reconcile_resume_projects', 'organize_adaptive_narrative', 'deduplicate_resume_facts',
    'guard_template_language', 'guard_resume_output', 'professionalize_resume_language',
    'guard_resume_output_relevance', 'ensure_recruiter_facing_technical_language',
    'ensure_recruiter_readability', 'ensure_paired_symbol_integrity',
    'ensure_resume_section_integrity', 'ensure_resume_whitespace_quality',
    'ensure_typography_quality',
)


def control(raw, summary):
    case, build, data = detail_return(raw)
    data['resume_sections']['summary'] = list(summary)
    for key in ('normal_version', 'bold_version', 'boundary_version', 'recommended_version'):
        data[key] = ''
    return case, build, data


def trace_delivery(raw, summary, monkeypatch, tmp_path):
    case, build, data = control(raw, summary)
    unchanged = deepcopy(build)
    stages = []
    observed_builds, observed_views = [], []
    actual_build = generation.build_canonical_semantic_build
    actual_views = generation.build_canonical_consumer_views
    actual_receive = generation.build_llm_generation
    consumption_builds = []
    def record_build(*args, **kwargs):
        result = actual_build(*args, **kwargs)
        observed_builds.append((result, deepcopy(result)))
        return result
    def record_views(*args, **kwargs):
        result = actual_views(*args, **kwargs)
        observed_views.append((result, repr(result)))
        return result
    def record_receive(*args, **kwargs):
        # The existing shadow projection attaches experience_input_id before
        # model consumption. Check immutability from that consumer boundary.
        live_build = observed_builds[0][0]
        consumption_builds.append((live_build, deepcopy(live_build)))
        return actual_receive(*args, **kwargs)
    monkeypatch.setattr(generation, 'build_canonical_semantic_build', record_build)
    monkeypatch.setattr(generation, 'build_canonical_consumer_views', record_views)
    monkeypatch.setattr(generation, 'build_llm_generation', record_receive)
    for name in WRITERS:
        fn = getattr(generation, name)
        def record(*args, _fn=fn, _name=name, **kwargs):
            before = args[0].model_dump()
            out = _fn(*args, **kwargs)
            payload = out[0] if isinstance(out, tuple) else out
            stages.append((_name, before, payload.model_dump()))
            return out
        monkeypatch.setattr(generation, name, record)
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(reference_return(data), ensure_ascii=False), 'stop')])
    assert build == unchanged
    assert len(observed_builds) == len(observed_views) == 1
    for value, snapshot in observed_builds:
        assert replace(value, state=snapshot.state) == snapshot
        for key in ('experiences', 'claims', 'facts', 'validation'):
            assert getattr(value.state, key) == getattr(snapshot.state, key)
    assert consumption_builds and all(value == snapshot for value, snapshot in consumption_builds)
    assert all(repr(value) == snapshot for value, snapshot in observed_views)
    # Diagnostic payloads are local test artifacts, not production log additions.
    (tmp_path / 'summary-stages.json').write_text(json.dumps(stages, ensure_ascii=False, indent=2), encoding='utf-8')
    return build, stages, outcome


def surface(value):
    # Only tolerate the existing presentation trim, never remove limitations.
    return value.strip(' 。')


@pytest.mark.parametrize('reverse', [False, True])
def test_full_chain_award_is_not_replaced_by_foreign_denial(reverse, monkeypatch, tmp_path, isolated):
    raw = '\n\n'.join([NO_AWARD, AWARD] if reverse else [AWARD, NO_AWARD])
    summary = ['团队获得三等奖，承担调查结果整理工作。']
    _, stages, _ = trace_delivery(raw, summary, monkeypatch, tmp_path)
    guard = next(row for row in stages if row[0] == 'guard_hard_facts')
    assert guard[1]['resume_sections']['summary'] == summary
    assert guard[2]['resume_sections']['summary'] == summary
    for _, _, after in stages:
        assert [surface(s) for s in after['resume_sections']['summary']] == [surface(s) for s in summary]


@pytest.mark.parametrize('raw,summary', [
    (LIMITED, '使用Python整理日志，工具没有上线，仅在本地运行。'),
    ('技能：接触过Python，对异步编程不太熟。\n个人项目：日志整理工具\n使用Python整理日志。',
     '接触过Python，对异步编程不太熟。'),
])
def test_full_chain_preserves_local_limitations(raw, summary, monkeypatch, tmp_path, isolated):
    _, stages, _ = trace_delivery(raw, [summary], monkeypatch, tmp_path)
    for _, _, after in stages:
        assert [surface(s) for s in after['resume_sections']['summary']] == [surface(summary)]


@pytest.mark.parametrize('index', range(3))
@pytest.mark.parametrize('long_mode', [False, True])
def test_sent_complete_evidence_and_retry_without_rebuild(index, long_mode, monkeypatch, isolated):
    case, build, data = control(NORMAL[index]['raw_input'], [SUMMARIES[index]])
    views = build_canonical_consumer_views(build)
    before = deepcopy(build), repr(views), deepcopy(case)
    wire = json.dumps(reference_return(data), ensure_ascii=False)
    sent = provider(monkeypatch, [(wire, 'length'), (wire, 'stop')])
    def forbidden(*args, **kwargs):
        raise AssertionError('Prompt must consume existing evidence, not rebuild or invent summary')
    for name in ('build_experience_identities', 'build_experience_fact_ledger',
                 'split_experience_segments', 'build_semantic_role_context'):
        monkeypatch.setattr(prompt_service, name, forbidden)
    monkeypatch.setattr(summary_quality, 'build_grounded_summary_candidates', forbidden)
    payload, info = generation.build_llm_generation(
        request(case), replace(build.long_input_context, long_input_mode=long_mode), consumer_views=views,
    )
    assert len(sent) == info['attempt'] == 2
    assert sent[0]['messages'] == sent[1]['messages']
    prompt = '\n'.join(m['content'] for m in sent[0]['messages'])
    actual = evidence(prompt)
    sent_facts = [f for owner in actual['owners'] for f in owner['eligible_facts']]
    facts = [f for owner in views.experience_ids for f in views.facts_for_owner(owner)]
    assert [(f['fact_id'], f['resume_ready_text'], tuple(f['source_span'])) for f in sent_facts] == [
        (f.fact_id, f.resume_ready_text, tuple(f.source_span)) for f in facts]
    claims = {c.claim_id: c for owner in views.experience_ids for c in views.claims_for_owner(owner)}
    for f in sent_facts:
        assert f['source_claim_text'] == claims[f['source_claim_ids'][0]].text
    allowed = {cid for owner in views.experience_ids for cid in views.scope_for_owner(owner).eligible_claim_ids}
    assert {c['claim_id']: c['text'] for c in actual['internal_constraints_not_resume_facts']} == {
        cid: c.text for cid, c in claims.items() if cid not in allowed}
    assert [(tuple(c['source_span']), c['text']) for c in actual['non_experience_context_not_project_facts']] == list(views.non_experience_context(case['raw_input']))
    assert payload.resume_sections.summary == data['resume_sections']['summary']
    assert (build, repr(views), case) == before


@pytest.mark.parametrize('index', range(3))
def test_normal_inputs_summary_survives_save_docx(index, monkeypatch, tmp_path, isolated):
    build, stages, outcome = trace_delivery(NORMAL[index]['raw_input'], [SUMMARIES[index]], monkeypatch, tmp_path)
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    expected = surface(SUMMARIES[index])
    assert [surface(s) for s in outcome['saved']['resume_sections']['summary']] == [expected]
    files = list(tmp_path.glob('*.docx'))
    assert files
    assert expected in '\n'.join(p.text for p in Document(files[0]).paragraphs)
    for name, before, after in stages:
        if name in {'guard_hard_facts', 'sanitize_resume_body'}:
            expected_projects = deepcopy(before['resume_sections']['projects'])
            if name == 'sanitize_resume_body':
                # Existing empty-role cleanup removes empty keys, not evidence.
                for p in expected_projects:
                    if not p['role']:
                        for key in ('role_source_fact_ids', 'role_source_claim_ids'):
                            assert not p.get(key)
                            p.pop(key, None)
            assert expected_projects == after['resume_sections']['projects']


def test_wrong_model_ability_is_not_falsely_claimed_as_fixed(monkeypatch, tmp_path, isolated):
    raw = NORMAL[0]['raw_input']
    summary = ['独立主导企业整体技术架构。']
    _, stages, outcome = trace_delivery(raw, summary, monkeypatch, tmp_path)
    assert stages[0][1]['resume_sections']['summary'] == summary
    assert [surface(s) for s in stages[-1][2]['resume_sections']['summary']] == [surface(summary[0])]
    # This records the boundary, not an assertion that arbitrary prose is supported.
    (tmp_path / 'model-expression-boundary.json').write_text(json.dumps({
        'controlled_model_text_already_overstates': True, 'saved': outcome['results'],
        'gates': outcome['gates'],
    }, ensure_ascii=False), encoding='utf-8')


def test_empty_summary_remains_an_explicit_failure(monkeypatch, tmp_path, isolated):
    _, stages, outcome = trace_delivery(NORMAL[0]['raw_input'], [], monkeypatch, tmp_path)
    assert all(not after['resume_sections']['summary'] for _, _, after in stages)
    assert outcome['error'] == 'DELIVERY_QUALITY_FAILED' and outcome['results'] == 0
    assert not list(tmp_path.glob('*.docx'))


@pytest.mark.parametrize('summary', [
    ['使用Python整理日志，工具没有上线。'],
    ['接触过Python，对异步编程不太熟。'],
    ['团队获得三等奖。'],
])
def test_narrow_changes_are_immutable_idempotent_and_keep_legacy(summary):
    _, build, data = control(LIMITED, summary)
    payload = schemas.GenerationPayload.model_validate(data)
    before = payload.model_dump(), deepcopy(build)
    guarded = guard_hard_facts(payload, LIMITED, canonical_mode=True)
    assert guarded.resume_sections.summary == summary
    cleaned = sanitize_resume_body(guarded, semantic_safe=True)
    assert cleaned == sanitize_resume_body(cleaned, semantic_safe=True)
    assert [surface(s) for s in cleaned.resume_sections.summary] == [surface(s) for s in summary]
    assert (payload.model_dump(), build) == before
    # Independent legacy calls keep their existing behavior.
    legacy = guard_hard_facts(payload, LIMITED)
    if '三等奖' in summary[0]:
        assert '竞赛参与' in legacy.resume_sections.summary[0]
    legacy = sanitize_resume_body(payload)
    assert '没有上线' not in ''.join(legacy.resume_sections.summary)
    assert '不太熟' not in ''.join(legacy.resume_sections.summary)


def test_firewall_keeps_summary_limits_but_still_removes_instruction_and_template(isolated):
    _, _, data = control(LIMITED, [
        'summary: 使用Python整理日志，工具没有上线。希望包装得更专业。',
        '接触过Python，对异步编程不太熟。',
    ])
    original = schemas.GenerationPayload.model_validate(data)
    before = original.model_dump()
    canonical = guard_resume_output(original, canonical_mode=True, write_log=False)
    legacy = guard_resume_output(original, write_log=False)
    assert canonical.resume_sections.summary == ['使用Python整理日志，工具没有上线', '接触过Python，对异步编程不太熟']
    assert '没有上线' not in ''.join(legacy.resume_sections.summary)
    assert canonical == guard_resume_output(canonical, canonical_mode=True, write_log=False)
    actual, expected = canonical.model_dump(), legacy.model_dump()
    actual['resume_sections'].pop('summary')
    expected['resume_sections'].pop('summary')
    assert actual == expected and original.model_dump() == before


def test_shared_cleaner_default_and_classification_unchanged():
    text = '使用Python整理日志，没有上线。不太熟异步编程。希望包装得更专业。'
    classification = classify_input_content(text)
    old, removed = strip_non_fact_fragments(text)
    kept, kept_removed = strip_non_fact_fragments(text, preserve_limits=True)
    assert '没有上线' not in old and '不太熟' not in old
    assert '没有上线' in kept and '不太熟' in kept
    assert '希望包装' not in kept and any('希望包装' in x for x in kept_removed)
    assert len(removed) > len(kept_removed)
    assert classify_input_content(text) == classification


def test_holdout_maintenance_summary_to_save_docx(monkeypatch, tmp_path, isolated):
    # Held out until the two failing writer branches were implemented.
    raw = ('基本信息：信息管理专业本科在读，预计2028年毕业。\n'
           '技能：了解SQL，会使用Excel。\n'
           '个人项目：借阅记录检查工具\n'
           '2026年4月，使用Python开发借阅记录检查工具。我负责检查日期和重复编号。'
           '使用18条记录验证检查结果，将异常编号输出到CSV。')
    summary = ['使用Python完成借阅记录检查，负责日期与重复编号核对；了解SQL。']
    _, stages, outcome = trace_delivery(raw, summary, monkeypatch, tmp_path)
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    assert all([surface(s) for s in after['resume_sections']['summary']] == [surface(summary[0])]
               for _, _, after in stages)


def test_existing_gate_still_rejects_explicit_conflict_after_cleaners(monkeypatch, tmp_path, isolated):
    raw = ('个人项目：接口校验工具\n使用Python开发接口校验工具，编写12条接口测试。'
           '没有使用Docker。')
    _, _, outcome = trace_delivery(raw, ['使用Docker完成容器化部署。'], monkeypatch, tmp_path)
    assert outcome['error'] == 'DELIVERY_QUALITY_FAILED' and outcome['results'] == 0
    assert 'DENIED_CLAIM_SCOPE_UNRESOLVED' in outcome['gates'][-1]['codes']
    assert not list(tmp_path.glob('*.docx'))
