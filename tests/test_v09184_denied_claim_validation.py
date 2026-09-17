"""Current-code controls; historical raw model responses are unavailable."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from app import schemas
from app.services import resume_delivery_quality_gate_service as gate
from app.services.experience_slot_service import bind_projects_to_experience_slots
from app.services.input_claim_resolution_service import assertion_surface_spans, surface_assertion_corresponds
from app.services.canonical_consumer_view_service import build_canonical_consumer_views, non_experience_context_for_build
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger
from test_v09162_model_output_evidence_contract import reference_return
from test_v09172_initial_evidence_preservation import detail_return
from test_v09174_fact_reference_composition import isolated
from test_v09176_delivery_closure import deliver


HISTORICAL_INPUT = """基本信息：
计算机科学与技术专业本科在读，预计2027年毕业。

科研经历：环境声音分类课题
2026年2月至2026年6月，在学校声学课题组参与环境声音分类研究，负责数据整理和实验记录。
使用Python检查240段音频的文件完整性，按照导师提供的规则整理类别标签。
按照课题组已有方案运行两组基线实验，记录参数设置和分类结果，没有提出新的模型结构，也没有发表论文。
为课题编写实验记录导出脚本，将运行参数和结果整理为CSV文件。
后续计划研究跨设备录音的适配问题，目前尚未开展相关实验。

个人项目：音频文件整理工具
2026年7月，使用Python开发音频文件整理工具，实现按文件格式归档和重复文件检查。
使用32个测试文件检查同名文件、空目录和不支持格式的处理情况。工具仅在本地运行。

技能：
能够使用Python和Git，了解基础音频数据处理。"""


def bound(raw):
    _, build, body = detail_return(raw)
    for key in ('normal_version', 'bold_version', 'boundary_version', 'recommended_version'):
        body[key] = ''
    body['resume_sections']['summary'] = ['具备项目实践经验。']
    body['resume_sections']['skills'] = []
    payload = bind_projects_to_experience_slots(schemas.GenerationPayload.model_validate(body), raw,
                                              semantic_build=build, write_log=False)
    return build, payload


def evaluate(build, payload, skill_evidence=()):
    before = deepcopy(build), payload.model_dump()
    views = build_canonical_consumer_views(build, skill_evidence)
    frozen = repr(views), deepcopy(skill_evidence)
    result = gate.validate_resume_delivery_quality(payload, consumer_views=views, skill_evidence=skill_evidence, write_log=False)
    assert (build, payload.model_dump()) == before
    repeated = gate.validate_resume_delivery_quality(payload, consumer_views=views, skill_evidence=skill_evidence, write_log=False)
    assert (repr(views), skill_evidence) == frozen
    assert result.issues == repeated.issues
    first_stats, repeated_stats = asdict(result.stats), asdict(repeated.stats)
    first_stats.pop('created_at')
    repeated_stats.pop('created_at')
    assert first_stats == repeated_stats
    return result


def denied(result):
    return [i for i in result.issues if i.issue_code == 'DENIED_CLAIM_ASSERTED']


def test_historical_input_current_legal_control_to_save_docx(monkeypatch, tmp_path, isolated):
    case, build, body = detail_return(HISTORICAL_INPUT)
    body['resume_sections']['summary'] = ['具备音频数据整理和实验记录实践。']
    for claim in build.ledger.claims:
        assert HISTORICAL_INPUT[slice(*claim.source_span)] == claim.text
    restrictions = [c for c in build.ledger.claims if c.certainty == 'denied']
    assert any('尚未开展' in c.text and not c.resume_eligible for c in restrictions)
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(reference_return(body), ensure_ascii=False), 'stop')])
    (tmp_path/'claim-evidence.json').write_text(json.dumps([asdict(c) for c in build.ledger.claims], ensure_ascii=False), encoding='utf-8')
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    assert all('DENIED_CLAIM_ASSERTED' not in row['codes'] for row in outcome['gates'])


@pytest.mark.parametrize('restriction,assertion', [
    ('我没有负责预测模型设计', '我负责预测模型设计'),
    ('团队尚未提交验收报告', '团队提交验收报告'),
    ('目前尚未开展相关实验', '目前开展相关实验'),
    ('没有提出新的模型结构，也没有发表论文', '发表论文'),
    ('没有使用 Docker', '使用 Docker 完成容器化部署'),
])
def test_direct_contradiction_has_exact_field_even_without_sources(restriction, assertion):
    build, payload = bound('项目一：记录整理工具\n使用Python整理记录。' + restriction + '。')
    project = payload.resume_sections.projects[0]
    index = len(project['details'])
    project['details'].append(assertion)
    project['detail_fact_ids'].append([])
    project['detail_claim_ids'].append([])
    issues = denied(evaluate(build, payload))
    assert issues and issues[0].severity == 'critical'
    assert issues[0].field_path == f'resume_sections.projects.0.details.{index}'
    assert issues[0].source_fact_ids == []


def test_field_boundary_cannot_create_a_denied_assertion():
    raw = '项目一：接口工具\n使用Python整理接口记录。了解Docker日志。没有使用Docker。'
    build, payload = bound(raw)
    p = payload.resume_sections.projects[0]
    p['role'], p['details'] = '检查命令使用', ['Docker日志格式分析']
    p['role_source_fact_ids'], p['role_source_claim_ids'] = [], []
    p['detail_fact_ids'], p['detail_claim_ids'] = [[]], [[]]
    assert not denied(evaluate(build, payload))


def test_negation_retained_is_not_an_affirmative_assertion():
    raw = '项目一：接口工具\n使用Python整理接口记录。没有使用Docker。'
    build, payload = bound(raw)
    p = payload.resume_sections.projects[0]
    p['details'].append('没有使用Docker')
    p['detail_fact_ids'].append([])
    p['detail_claim_ids'].append([])
    assert not denied(evaluate(build, payload))


@pytest.mark.parametrize('reverse', [False, True])
def test_other_owner_restriction_does_not_apply_to_a_local_limitation(reverse):
    parts = ['项目一：接口工具\n使用Python整理接口记录。没有使用Docker。',
             '项目二：日志工具\n使用Java处理日志。']
    raw = '\n\n'.join(reversed(parts) if reverse else parts)
    build, payload = bound(raw)
    project = next(p for p in payload.resume_sections.projects if any('Java' in d for d in p['details']))
    project['details'].append('没有使用Docker')
    project['detail_fact_ids'].append([])
    project['detail_claim_ids'].append([])
    assert not denied(evaluate(build, payload))


def test_global_direct_contradiction_is_not_silently_ignored():
    build, payload = bound('项目一：接口工具\n使用Python整理接口记录。没有使用Docker。')
    payload.resume_sections.summary = ['使用Docker完成容器化部署。']
    result = evaluate(build, payload)
    # No field owner is present: correspondence is not proof of applicability.
    assert not denied(result)
    issues = [i for i in result.issues if i.issue_code == 'DENIED_CLAIM_SCOPE_UNRESOLVED']
    assert issues and issues[0].field_path == 'resume_sections.summary.0'
    assert issues[0].source_experience_id == ''


def denial_checks(result):
    return [i for i in result.issues if i.issue_code in {'DENIED_CLAIM_ASSERTED', 'DENIED_CLAIM_SCOPE_UNRESOLVED'}]


@pytest.mark.parametrize('text', [
    '我没有负责预测模型设计', '团队尚未提交验收报告', '目前尚未开展相关实验',
    '目前我没有提交报告，也没有交付代码', '并非独立完成，只负责页面',
    '没有提出新模型，也没有发表论文', '我\r\n没有使用Docker',
])
def test_shared_access_preserves_original_ranges_and_qualifiers(text):
    rows = assertion_surface_spans(text)
    assert rows
    for row in rows:
        a, b = row['source_span']
        c, d = row['body_span']
        assert 0 <= a <= c <= d == b <= len(text)
        assert text[c:d].strip() == row['body']
    if '只负责页面' in text:
        assert '只负责页面' in rows[0]['body']
    if text.startswith('目前我'):
        assert len(rows) == 2
        assert {(r['time'], r['subject']) for r in rows} == {('目前', '我')}


@pytest.mark.parametrize('restriction,legal', [
    ('没有提出新的模型结构', '运行两组基线实验'),
    ('没有发表论文', '参与环境声音分类研究'),
    ('没有独立完成页面', '只负责页面'),
    ('没有负责页面', '可能负责页面'),
    ('没有使用Docker', 'Docker'),
    ('没有Docker', 'Docker'),
    ('没有使用Docker', '研究Docker日志格式'),
    ('没有使用Docker', '使用Docker完成容器化部署的计划'),
    ('没有使用Docker', '使用Docker完成容器化部署前检查配置'),
    ('目前没有使用Docker', '此前使用Docker'),
    ('团队没有提交验收报告', '我提交验收报告'),
    ('没有使用Docker', '没有使用Docker'),
    ('没有提出新模型，也没有发表论文', '没有提出新模型，也没有发表论文'),
])
def test_nearby_legal_project_statements_do_not_trigger_denial(restriction, legal):
    build, payload = bound('项目一：记录整理工具\n使用Python整理记录。' + restriction + '。')
    p = payload.resume_sections.projects[0]
    p['details'].append(legal)
    p['detail_fact_ids'].append([])
    p['detail_claim_ids'].append([])
    assert not denial_checks(evaluate(build, payload))


@pytest.mark.parametrize('field', ['intro', 'role', 'details'])
def test_real_fact_id_does_not_prove_rewritten_field(field):
    build, payload = bound('项目一：接口工具\n使用Python整理接口记录。没有使用Docker。')
    p = payload.resume_sections.projects[0]
    fid = p['detail_fact_ids'][0]
    cid = p['detail_claim_ids'][0]
    if field == 'details':
        p['details'][0] = '使用Docker'
    else:
        p[field] = '使用Docker'
        p[f'{field}_source_fact_ids'], p[f'{field}_source_claim_ids'] = fid, cid
    issues = denied(evaluate(build, payload))
    assert len(issues) == 1
    assert issues[0].field_path == 'resume_sections.projects.0.' + (field + '.0' if field == 'details' else field)
    assert issues[0].source_fact_ids == fid
    assert issues[0].source_claim_ids == [next(c.claim_id for c in build.ledger.claims if c.certainty == 'denied')]


def test_matching_body_with_unresolved_time_is_not_proven_contradiction():
    build, payload = bound('项目一：接口工具\n使用Python整理接口记录。目前没有使用Docker。')
    p = payload.resume_sections.projects[0]
    p['details'].append('使用Docker')
    p['detail_fact_ids'].append([])
    p['detail_claim_ids'].append([])
    issues = denial_checks(evaluate(build, payload))
    assert len(issues) == 1 and issues[0].issue_code == 'DENIED_CLAIM_SCOPE_UNRESOLVED'


@pytest.mark.parametrize('value', ['具备项目实践经验', '了解Docker', '运行基线实验', '没有使用Docker', 'Docker'])
def test_global_missing_sources_are_not_alone_a_denial_failure(value):
    build, payload = bound('项目一：接口工具\n使用Python整理接口记录。没有使用Docker。')
    payload.resume_sections.summary = [value]
    assert not denial_checks(evaluate(build, payload))


@pytest.mark.parametrize('reverse', [False, True])
def test_other_owner_literal_fact_is_valid_in_project_and_global_field(reverse):
    parts = ['项目一：接口工具\n使用Python整理接口记录。没有使用Docker。',
             '项目二：部署工具\n使用Java创建部署工具。使用Docker完成容器化部署。编写配置检查脚本。']
    build, payload = bound('\n\n'.join(reversed(parts) if reverse else parts))
    fact = next(f for f in build.ledger.facts if f.resume_ready_text == '使用Docker完成容器化部署')
    payload.resume_sections.summary = [fact.resume_ready_text]
    assert not denial_checks(evaluate(build, payload))


def test_background_skill_is_not_denied_by_project_non_usage():
    raw = '项目一：接口工具\n使用Python整理接口记录。没有使用Docker。\n技能：使用Docker。'
    build, payload = bound(raw)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger, non_experience_context=non_experience_context_for_build(build, raw))
    payload.resume_sections.skills = ['使用Docker']
    assert any(d['display_text'] == '使用Docker' for row in evidence for d in row.declarations)
    assert not denial_checks(evaluate(build, payload, evidence))
    payload.resume_sections.skills = ['使用Docker完成容器化部署']
    issues = denial_checks(evaluate(build, payload, evidence))
    assert len(issues) == 1 and issues[0].issue_code == 'DENIED_CLAIM_SCOPE_UNRESOLVED'


@pytest.mark.parametrize('prefix', ['', '工程化与部署：'])
def test_skill_display_label_does_not_bypass_scope_check(prefix):
    raw = '项目一：接口工具\n使用Python整理接口记录。没有使用Docker。\n技能：使用Docker。'
    build, payload = bound(raw)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger, non_experience_context=non_experience_context_for_build(build, raw))
    payload.resume_sections.skills = [prefix + '使用Docker']
    assert not denial_checks(evaluate(build, payload, evidence))
    payload.resume_sections.skills = [prefix + '使用Docker完成容器化部署']
    issues = denial_checks(evaluate(build, payload, evidence))
    assert len(issues) == 1 and issues[0].field_path == 'resume_sections.skills.0'
    assert issues[0].issue_code == 'DENIED_CLAIM_SCOPE_UNRESOLVED'


def test_shared_accessor_is_not_a_new_claim_build_path(monkeypatch):
    from app.services import input_claim_resolution_service as claims
    before, _ = bound(HISTORICAL_INPUT)
    def forbidden(*args, **kwargs):
        raise AssertionError('Shared comparison accessor entered semantic compilation')
    monkeypatch.setattr(claims, 'assertion_surface_spans', forbidden)
    after, _ = bound(HISTORICAL_INPUT)
    assert before == after


def test_legacy_denial_check_is_not_redirected_to_new_contract():
    build, payload = bound('项目一：接口工具\n使用Python整理接口记录。没有使用Docker。')
    payload.resume_sections.projects[0]['details'].append('没有使用Docker')
    assert any(i.issue_code == 'DENIED_CLAIM_ASSERTED' for i in gate._semantic_role_leaks_from_ledger(payload, build.ledger))
    assert not denial_checks(evaluate(build, payload))


def test_unseen_paraphrase_is_outside_literal_proof_not_a_trusted_assertion():
    build, payload = bound('项目一：接口工具\n使用Python整理接口记录。没有使用Docker。')
    payload.resume_sections.summary = ['具备容器技术落地经验。']
    assert not denial_checks(evaluate(build, payload))


def test_global_failure_reaches_real_final_gate_and_does_not_save(monkeypatch, tmp_path, isolated):
    case, _, body = detail_return(HISTORICAL_INPUT)
    body['resume_sections']['summary'] = ['发表论文']
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(reference_return(body), ensure_ascii=False), 'stop')])
    assert outcome.get('error') == 'DELIVERY_QUALITY_FAILED', outcome
    assert 'DENIED_CLAIM_SCOPE_UNRESOLVED' in outcome['gates'][-1]['codes']
    assert outcome['results'] == 0 and 'docx' not in outcome
    assert not list(tmp_path.glob('*.docx'))


def test_illegal_project_body_is_rejected_by_receiver_before_gate(monkeypatch, tmp_path, isolated):
    case, _, body = detail_return(HISTORICAL_INPUT)
    returned = reference_return(body)
    returned['resume_sections']['projects'][0]['intro'] = '发表论文'
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(returned, ensure_ascii=False), 'stop')])
    assert outcome['error'].startswith('MODEL_EVIDENCE_'), outcome
    assert outcome['results'] == 0 and not outcome['gates'] and 'docx' not in outcome


@pytest.mark.parametrize('index', range(3))
def test_healthy_full_inputs_save_and_export(index, monkeypatch, tmp_path, isolated):
    cases = json.loads((Path(__file__).parent/'fixtures/v091811_normal_inputs.json').read_text(encoding='utf-8'))
    case, _, body = detail_return(cases[index]['raw_input'])
    body['resume_sections']['summary'] = ['具备项目实践经验。']
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(reference_return(body), ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome


def test_denial_log_has_identifiers_and_reason_but_no_original_text(tmp_path, monkeypatch):
    build, payload = bound('项目一：接口工具\n使用Python整理接口记录。没有使用Docker。')
    payload.resume_sections.summary = ['使用Docker']
    path = tmp_path/'gate.jsonl'
    monkeypatch.setattr(gate, 'LOG_PATH', path)
    gate.validate_resume_delivery_quality(payload, semantic_build=build)
    text = path.read_text(encoding='utf-8')
    data = json.loads(text)
    issue = next(i for i in data['issues'] if i['issue_code'] == 'DENIED_CLAIM_SCOPE_UNRESOLVED')
    assert issue['source_claim_ids'] and issue['reason_category'] == 'assertion_scope_unresolved'
    assert all(value not in text for value in ('Docker', '没有使用', '接口工具'))


HOLDOUT_INPUT = '''个人项目：排班导出工具
2026年4月至2026年5月，使用Python开发排班导出工具。
整理18条班次记录，编写CSV导出和空值检查脚本。
目前团队没有提交验收附件，也没有交付运行手册。
技能：了解Python和Git。'''


@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_holdout_operations_sample_after_implementation(newline, monkeypatch, tmp_path, isolated):
    raw = HOLDOUT_INPUT.replace('\n', newline)
    case, _, body = detail_return(raw)
    body['resume_sections']['summary'] = ['具备数据整理与脚本开发实践。']
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(reference_return(body), ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    build, payload = bound(raw)
    project = payload.resume_sections.projects[0]
    project['details'].append('目前团队交付运行手册')
    project['detail_fact_ids'].append([])
    project['detail_claim_ids'].append([])
    issues = denied(evaluate(build, payload))
    assert len(issues) == 1 and issues[0].field_path.endswith(f"details.{len(project['details']) - 1}")
    project['details'][-1] = '目前团队整理运行手册目录'
    assert not denial_checks(evaluate(build, payload))
