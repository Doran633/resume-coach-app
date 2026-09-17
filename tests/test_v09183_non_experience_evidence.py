"""Current-code controls, not historical request or model-response snapshots."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from app import schemas
from app.services import generation_service as generation
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.canonical_consumer_view_service import non_experience_context_for_build
from app.services.fact_guard_service import education_from_context, guard_hard_facts
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger
from app.services.resume_skill_evidence_guard_service import guard_resume_skill_evidence
from app.services.resume_skill_taxonomy_service import calibrate_resume_skill_taxonomy
from app.services.resume_output_relevance_service import guard_resume_output_relevance, TOKEN_QUESTION
from app.services.llm_service import LLMResult
from app.services import prompt_service
from test_v0916_canonical_model_evidence import evidence as sent_evidence
from test_v09162_model_output_evidence_contract import real_receiver, reference_return
from test_v09172_initial_evidence_preservation import detail_return
from test_v09174_fact_reference_composition import isolated
from test_v091811_experience_admission import assert_saved_evidence

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'tests/fixtures/v091811_normal_inputs.json').read_text(encoding='utf-8'))
TARGETS = ['前端开发实习', 'Java后端开发实习', 'AI应用开发实习']
SKILLS = [
    ['Vue', 'JavaScript', 'HTML', 'CSS', 'Git', 'Element Plus', 'Supabase'],
    ['Java', 'Spring Boot', 'MySQL', 'Redis', 'Postman'],
    ['Python', 'PyTorch', 'Pandas', 'FastAPI', 'Git'],
]


def delivery(raw, target, monkeypatch, tmp_path, *, returned_skills=None, returned_education=None):
    case, build, body = detail_return(raw)
    case['target_role'] = target
    body['resume_sections']['personal_info']['求职意向'] = '模型擅自改成的岗位'
    body['resume_sections']['education'] = returned_education or {}
    body['resume_sections']['skills'] = returned_skills or []
    body['resume_sections']['summary'] = ['具备项目实践经验。']
    snapshots = []
    for name in ('guard_resume_skill_evidence', 'calibrate_resume_skill_taxonomy',
                 'guard_resume_output_relevance', 'ensure_recruiter_facing_technical_language',
                 'ensure_recruiter_readability', 'ensure_resume_section_integrity'):
        fn = getattr(generation, name)
        def record(*args, _fn=fn, _name=name, **kwargs):
            output = _fn(*args, **kwargs)
            snapshots.append((_name, output.model_dump()))
            return output
        monkeypatch.setattr(generation, name, record)
    captured = real_receiver(case, reference_return(body), monkeypatch, tmp_path, deliver=True)
    (tmp_path / 'non-experience-stages.json').write_text(json.dumps({
        'initial': body, 'stages': snapshots, 'saved': captured['saved'],
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    return build, captured, snapshots


@pytest.mark.parametrize('index', range(3))
def test_full_inputs_keep_background_evidence_through_save_and_docx(index, monkeypatch, tmp_path, isolated):
    case = CASES[index]
    before = build_canonical_semantic_build(case['raw_input'])
    build, captured, snapshots = delivery(case['raw_input'], TARGETS[index], monkeypatch, tmp_path)
    sections = captured['saved']['resume_sections']
    assert sections['personal_info']['求职意向'] == TARGETS[index]
    assert sections['education']['时间'] == '预计2027年毕业'
    assert sections['education']['学历'] == ('[待填写]' if index == 0 else '本科')
    skill_text = '\n'.join(sections['skills'])
    for term in SKILLS[index]:
        assert term in skill_text, (term, skill_text)
    if index == 2:
        assert '接触过PyTorch' in skill_text
    for name, stage in snapshots:
        if name in {'calibrate_resume_skill_taxonomy', 'guard_resume_output_relevance'}:
            assert stage['resume_sections']['skills'] == sections['skills']
        assert_saved_evidence(stage['resume_sections']['projects'], build)
    assert_saved_evidence(sections['projects'], build)
    assert asdict(before) == asdict(build_canonical_semantic_build(case['raw_input']))
    rendered = ''.join(node.text or '' for path in tmp_path.glob('*.docx')
                       for node in Document(path).element.xpath('.//w:t'))
    assert TARGETS[index] in ''.join(rendered.split()) and '预计2027年毕业' in rendered


def test_classification_does_not_drop_verified_unlisted_skill_or_qualification():
    from app.services.resume_skill_evidence_aggregation_service import AggregatedSkillEvidence
    payload = schemas.GenerationPayload.model_validate({
        **generation.build_mock_generation(schemas.GenerateRequest(
            anonymous_user_id='test', session_id='test', target_role='开发',
            experience_type='项目经历', raw_input='使用Python开发工具。',
        )).model_dump(),
    })
    payload.resume_sections.skills = ['接触过PyTorch', '会使用Postman']
    evidence = [AggregatedSkillEvidence('PyTorch', 'explicit', 1), AggregatedSkillEvidence('Postman', 'explicit', 1)]
    for row, label in zip(evidence, payload.resume_sections.skills):
        row.declarations.append({'display_text': label, 'qualified': True})
    result = calibrate_resume_skill_taxonomy(payload, aggregated_evidence=evidence, write_log=False)
    assert any('接触过PyTorch' in line for line in result.resume_sections.skills)
    assert any('Postman' in line for line in result.resume_sections.skills)


PROJECT = '\n\n个人项目：记录检索工具\n使用Python开发记录查询功能。编写18条测试检查空数据。'


def compile_background(text):
    raw = '基本信息：\n' + text + PROJECT
    build = build_canonical_semantic_build(raw)
    original = deepcopy(build)
    context = non_experience_context_for_build(build, raw)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger, non_experience_context=context)
    assert build == original
    return raw, build, context, evidence


@pytest.mark.parametrize('text,expected', [
    ('熟悉Java基础，会使用Postman测试接口。', ['熟悉Java基础', '会使用Postman测试接口']),
    ('了解PyTorch，接触过Pandas和FastAPI。', ['了解PyTorch', '接触过Pandas', '接触过FastAPI']),
    ('会使用QuillPad，了解基础Linux命令和Nginx配置。', ['会使用QuillPad', '了解基础Linux命令', '了解Nginx配置']),
    ('熟悉Java，但不熟悉Rust。', ['熟悉Java']),
    ('会用Git提交代码，计划学习Docker。', ['会用Git提交代码']),
    ('技能：Java、HTML和CSS。', ['Java', 'HTML', 'CSS']),
    ('了解.NET、Node.js和C++。', ['了解.NET', '了解Node.js', '了解C++']),
    ('会使用Python，Java，但仅用于课程练习。', ['会使用Python，但仅用于课程练习', '会使用Java，但仅用于课程练习']),
    ('了解数据可视化。', ['了解数据可视化']),
    ('技能\n了解QuillPad和Java基础。', ['了解QuillPad', '了解Java基础']),
])
def test_declaration_scope_and_exact_source_spans(text, expected):
    raw, build, context, evidence = compile_background(text)
    displays = [d['display_text'] for row in evidence for d in row.declarations]
    assert displays == expected
    for row in evidence:
        for proof in row.declarations:
            assert raw[slice(*proof['term_span'])] == row.term
            assert proof['source_kind'] == 'background_declaration'
            assert any(start <= proof['source_span'][0] < proof['source_span'][1] <= end for (start, end), _ in context)
        if not row.source_fact_ids:
            assert row.declarations and row.source_experience_ids == [] and row.inferred_from == []


@pytest.mark.parametrize('text', [
    '计划学习Rust。', '希望掌握Rust。', '岗位要求熟悉Rust。', '建议学习Rust。',
    '没有使用Rust。', '不熟悉Rust。', '可能熟悉Rust。', '如果熟悉Rust可以申请。',
    '请把Rust写进技能。', '熟悉Rust的同学负责测试。', '熟悉Rust或者Go，记不清了。',
])
def test_intent_instructions_negation_and_conditions_do_not_prove_skill(text):
    _, _, _, evidence = compile_background(text)
    assert not any(row.term in {'Rust', 'Go'} for row in evidence)


def test_duplicate_sources_preserve_distinct_qualifications_and_restrictions():
    raw, build, context, evidence = compile_background('了解Python，仅会用Python完成基础汇总。不熟悉Python的异步编程。')
    row = next(row for row in evidence if row.term == 'Python')
    assert row.source_fact_ids and row.source_experience_ids == ['EXP-001']
    assert len(row.declarations) == 3
    assert [d['qualified'] for d in row.declarations] == [True, True, False]
    _, _, body = detail_return(raw)
    payload = schemas.GenerationPayload.model_validate(body)
    before = payload.model_copy(deep=True)
    guarded = guard_resume_skill_evidence(payload, aggregated_evidence=evidence, canonical_evidence=True, write_log=False)
    assert any('不熟悉Python的异步编程' in line for line in guarded.resume_sections.skills)
    assert any('仅会用Python完成基础汇总' in line for line in guarded.resume_sections.skills)
    assert any('Python' in q for q in guarded.missing_questions)
    assert payload == before
    assert guarded == guard_resume_skill_evidence(guarded, aggregated_evidence=evidence, canonical_evidence=True, write_log=False)


@pytest.mark.parametrize('text,expected', [
    ('我目前是计算机科学与技术专业本科生，预计2027年毕业。', {'专业': '计算机科学与技术', '学历': '本科', '时间': '预计2027年毕业'}),
    ('我是软件工程专业大三学生，预计2027年毕业。', {'专业': '软件工程', '学历': '[待填写]', '时间': '预计2027年毕业'}),
    ('学校：海岚大学，专业：工业工程，学历：本科，就读时间：2023年9月至2027年6月。', {'学校': '海岚大学', '专业': '工业工程', '学历': '本科', '时间': '2023年9月至2027年6月'}),
    ('我就读于海岚大学，专业是统计学，目前本科在读。', {'学校': '海岚大学', '专业': '统计学', '学历': '本科'}),
    ('我在企业实习，项目合作方是海岚大学。', {'学校': '[待填写]'}),
    ('希望申请海岚大学硕士，预计2027年毕业。', {'学校': '[待填写]', '学历': '[待填写]', '时间': '预计2027年毕业'}),
])
def test_education_fields_have_local_proof_not_model_or_project_dates(text, expected):
    # Direct consumer controls keep partition differences outside this field test.
    context = (((0, len(text)), text),)
    values, proofs, questions = education_from_context(context)
    assert {k: values[k] for k in expected} == expected
    for key, rows in proofs.items():
        for value, span in rows:
            assert value == ''.join(text[slice(*span)].split())


@pytest.mark.parametrize('text', [
    '学校：海岚大学，专业：统计学。学校：云帆学院，专业：软件工程。',
    '学历：本科。学历：硕士。',
    '预计2027年毕业。预计2028年毕业。',
])
def test_conflicting_education_cannot_create_a_combined_record(text):
    values, _, questions = education_from_context((((0, len(text)), text),))
    assert set(values.values()) == {'[待填写]'} and questions


def test_confirmed_background_accessor_rejects_another_request_and_does_not_repartition():
    raw, build, context, _ = compile_background('本科在读，了解Java基础。')
    views = build_canonical_consumer_views(build)
    assert context == views.non_experience_context(raw)
    with pytest.raises(ValueError):
        non_experience_context_for_build(build, raw + '新增内容')


@pytest.mark.parametrize('style', ['lf', 'crlf', 'blank', 'sentence'])
@pytest.mark.parametrize('index', range(3))
def test_format_variants_preserve_background_evidence_and_original_offsets(index, style):
    raw = CASES[index]['raw_input']
    if style == 'crlf': raw = raw.replace('\n', '\r\n')
    elif style == 'blank': raw = raw.replace('\n', '\n\n')
    elif style == 'sentence': raw = raw.replace('。', '。\n')
    build = build_canonical_semantic_build(raw)
    context = non_experience_context_for_build(build, raw)
    rows = aggregate_skill_evidence_from_ledger(build.ledger, non_experience_context=context)
    assert all(term in {row.term for row in rows} for term in SKILLS[index])
    assert education_from_context(context)[0]['时间'] == '预计2027年毕业'
    for row in rows:
        for proof in row.declarations:
            assert raw[slice(*proof['term_span'])] == row.term
    assert len(build.identities) == 2


@pytest.mark.parametrize('background,conflict', [
    ('本科在读，希望申请Python开发实习。了解Java基础。', False),
    ('本科在读，希望申请Java后端实习。了解Java基础。', True),
    ('', False),
])
def test_request_target_is_applied_without_borrowing_model_or_education(background, conflict, monkeypatch, tmp_path, isolated):
    raw = ('基本信息：' + background if background else '') + PROJECT
    build, captured, _ = delivery(raw, 'Python开发实习', monkeypatch, tmp_path,
                                returned_education={'学校': '模型虚构大学', '学历': '博士', '时间': '2020-2024'})
    saved = captured['saved']
    assert saved['resume_sections']['personal_info']['求职意向'] == 'Python开发实习'
    assert any('表单目标岗位' in q for q in saved['missing_questions']) == conflict
    assert saved['resume_sections']['education']['学校'] == '[待填写]'
    assert saved['resume_sections']['education']['时间'] == '[待填写]'
    assert len(build.identities) == 1
    assert_saved_evidence(saved['resume_sections']['projects'], build)


@pytest.mark.parametrize('long', [False, True])
def test_actual_prompt_and_retry_reuse_build_views_and_background(monkeypatch, tmp_path, isolated, long):
    raw = CASES[1]['raw_input']
    if long:
        raw += '\n技能：\n' + '了解Java基础。' * 240
    case, build, body = detail_return(raw)
    context = non_experience_context_for_build(build, raw)
    rows = aggregate_skill_evidence_from_ledger(build.ledger, non_experience_context=context)
    views = build_canonical_consumer_views(build, rows)
    before_build = deepcopy(build)
    before_views = build_canonical_consumer_views(before_build, deepcopy(rows))
    assert build.long_input_context.long_input_mode == long
    good = reference_return(body)
    bad = deepcopy(good)
    bad['resume_sections']['projects'][0]['fact_placements'] = {}
    prompts = []
    def network(prompt):
        prompts.append(prompt)
        return LLMResult(text=json.dumps(bad if len(prompts) == 1 else good, ensure_ascii=False),
                         finish_reason='stop', model='offline-control', latency_ms=0)
    def forbidden(*args, **kwargs):
        raise AssertionError('Prompt consumer must not rebuild semantics')
    for name in ('build_experience_identity_map', 'build_experience_fact_ledger', 'analyze_long_input'):
        if hasattr(prompt_service, name):
            monkeypatch.setattr(prompt_service, name, forbidden)
    monkeypatch.setattr(generation, 'call_openai', network)
    monkeypatch.setattr(generation.resource_protection, 'check_daily_budget', lambda: SimpleNamespace(allowed=True))
    monkeypatch.setattr(generation.resource_protection, 'record_llm_usage', lambda **kw: None)
    request = schemas.GenerateRequest(anonymous_user_id='test', session_id='test',
                                     target_role=TARGETS[1], experience_type='综合经历', raw_input=raw)
    generation.build_llm_generation(request, build.long_input_context, consumer_views=views)
    assert len(prompts) == 2 and prompts[1].startswith(prompts[0])
    assert sent_evidence(prompts[0]) == sent_evidence(prompts[1])
    sent = sent_evidence(prompts[0])
    assert [(tuple(row['source_span']), row['text']) for row in sent['non_experience_context_not_project_facts']] == list(context)
    assert [(f['fact_id'], f['resume_ready_text']) for owner in sent['owners'] for f in owner['eligible_facts']] == [
        (f.fact_id, f.resume_ready_text) for f in build.ledger.facts]
    assert build == before_build and views == before_views


def test_relevance_keeps_canonical_unlisted_terms_but_preserves_token_ambiguity():
    raw, build, _, rows = compile_background('了解QuillPad，接触过Token。')
    _, _, body = detail_return(raw)
    payload = schemas.GenerationPayload.model_validate(body)
    payload = guard_resume_skill_evidence(payload, aggregated_evidence=rows, canonical_evidence=True, write_log=False)
    payload = calibrate_resume_skill_taxonomy(payload, aggregated_evidence=rows, write_log=False)
    before = payload.model_copy(deep=True)
    result = guard_resume_output_relevance(payload, aggregated_evidence=rows, write_log=False)
    assert payload == before
    assert any('了解QuillPad' in s for s in result.resume_sections.skills)
    assert not any('Token' in s for s in result.resume_sections.skills)
    assert TOKEN_QUESTION in result.missing_questions
    assert result == guard_resume_output_relevance(result, aggregated_evidence=rows, write_log=False)


def test_missing_canonical_evidence_never_rebuilds_semantics(monkeypatch):
    from app.services import resume_skill_evidence_guard_service as service
    _, _, body = detail_return(PROJECT)
    def forbidden(*args, **kwargs):
        raise AssertionError('Missing evidence is not permission to rebuild')
    monkeypatch.setattr(service, 'aggregate_skill_evidence', forbidden)
    with pytest.raises(ValueError, match='request evidence'):
        service.guard_resume_skill_evidence(schemas.GenerationPayload.model_validate(body),
                                           canonical_evidence=True, write_log=False)


def test_heldout_operations_sample_save_export_and_sanitized_logs(monkeypatch, tmp_path, isolated):
    raw = ('基本信息：本科在读，专业：信息管理，预计2028年毕业。希望申请数据运营实习。\n'
           '技能：接触过Metabase，能够使用Excel完成基础汇总。\n'
           '课程项目：校园阅读记录分析\n'
           '2026年4月，使用Excel整理60条阅读记录，检查日期和分类信息。'
           '制作频数统计表并在课堂展示统计结果。')
    build, captured, _ = delivery(raw, '数据运营实习', monkeypatch, tmp_path)
    sections = captured['saved']['resume_sections']
    assert sections['education']['专业'] == '信息管理'
    assert sections['education']['时间'] == '预计2028年毕业'
    assert any('接触过Metabase' in s for s in sections['skills'])
    assert any('能够使用Excel完成基础汇总' in s for s in sections['skills'])
    assert len(sections['projects']) == 1
    assert_saved_evidence(sections['projects'], build)
    logs = '\n'.join(p.read_text(encoding='utf-8') for p in tmp_path.glob('*.jsonl'))
    assert 'Metabase' not in logs and '预计2028年毕业' not in logs
