"""Current-code controls, not historical model-response snapshots."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09174_fact_reference_composition import isolated
from test_v09175_post_processing_evidence import trace_delivery
from test_v091811_experience_admission import assert_saved_evidence
from app.services import canonical_display_name_service as names
from app.services import canonical_semantic_state_service as state
from app.services.resume_title_format_service import resolve_canonical_resume_titles
from test_v09123_canonical_experience_header_completeness import _bound_payload
from docx import Document

CASES = json.loads((ROOT / 'tests/fixtures/v091811_normal_inputs.json').read_text(encoding='utf-8'))
EXPECTED = {
    'frontend': [
        {'organization': '星禾软件公司', 'position': '前端开发实习', 'time': '2026年6月到8月'},
        {'name': '校园闲置物品展示站', 'time': '2026年3月到5月'},
    ],
    'java': [
        {'name': '校园自习室预约系统', 'time': '2026年3月至5月'},
        {'name': '大学生电子商务创新创意创业挑战赛', 'time': '2026年4月至6月'},
    ],
    'research': [
        {'name': '校园环境声音分类研究', 'time': '2026年2月到6月'},
        {'name': '程序设计社技术分享活动', 'time': '2025年9月到2026年1月'},
    ],
}


def fields(build, index=0):
    return {f.field_key: f for f in build.experience_header_decisions[index].fields}


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['case'])
def test_complete_inputs_consume_original_header_evidence(case):
    raw = case['raw_input']
    b = build_canonical_semantic_build(raw)
    assert len(b.identities) == 2
    assert [d.canonical_experience_type for d in b.experience_type_decisions] == case['types']
    for index, expected in enumerate(EXPECTED[case['case']]):
        actual = fields(b, index)
        assert {k: f.value for k, f in actual.items()} == expected
        for key, f in actual.items():
            assert f.qualified
            proof = raw[slice(*f.source_span)]
            assert proof and f.source_span != b.identities[index].source_span
            assert f.value in proof or (key == 'position' and proof == '前端开发实习生')


@pytest.mark.parametrize('raw,expected', [
    ('课程项目：Node.js 文件工具\n2026年3月至5月，开发文件检索功能。', 'Node.js 文件工具'),
    ('个人项目：没有烦恼记账助手\n2026年3月至5月，开发记账查询功能。', '没有烦恼记账助手'),
    ('项目一：Atlas Search\n2026年3月至5月，开发文档检索功能。', 'Atlas Search'),
])
def test_heading_name_has_precise_original_proof(raw, expected):
    b = build_canonical_semantic_build(raw)
    decision = b.display_name_qualifications[0]
    assert decision.display_name == expected
    assert raw[slice(*decision.source_span)] == expected


@pytest.mark.parametrize('time', ['2026年6月到8月', '2026年3月至5月', '2026.03-2026.05'])
def test_full_time_expression_is_not_replaced_by_its_start(time):
    raw = '个人项目：文件索引工具\n' + time + '，开发文件索引功能。'
    b = build_canonical_semantic_build(raw)
    d = b.experience_time_decisions[0]
    assert d.qualified and d.display_time == time
    assert raw[slice(*d.source_span)] == time


def test_local_department_is_not_part_of_the_position():
    raw = '前端开发实习\n2026年6月至8月，在星禾软件公司的研发部门做前端开发实习生，负责页面开发。'
    b = build_canonical_semantic_build(raw)
    fs = fields(b)
    assert fs['organization'].value == '星禾软件公司'
    assert fs['position'].value == '前端开发实习'
    assert raw[slice(*fs['organization'].source_span)] == '星禾软件公司'
    assert raw[slice(*fs['position'].source_span)] in {'前端开发实习', '前端开发实习生'}


@pytest.mark.parametrize('style', ['crlf', 'blank', 'sentence_wrap', 'colon_heading'])
@pytest.mark.parametrize('case', CASES, ids=lambda c: c['case'])
def test_layout_preserves_header_values_and_precise_spans(case, style):
    raw = case['raw_input']
    if style == 'crlf':
        raw = raw.replace('\n', '\r\n')
    elif style == 'blank':
        raw = raw.replace('\n', '\n\n')
    elif style == 'sentence_wrap':
        raw = raw.replace('。', '。\n')
    else:
        raw = raw.replace('前端开发实习\n', '前端开发实习：\n')
    b = build_canonical_semantic_build(raw)
    assert len(b.identities) == 2
    for index, expected in enumerate(EXPECTED[case['case']]):
        actual = fields(b, index)
        assert {k: f.value for k, f in actual.items()} == expected
        for f in actual.values():
            assert f.value in raw[slice(*f.source_span)]


@pytest.mark.parametrize('time', ['2026年12月至2月', '2026年13月至14月', '2026年8月至2026年6月'])
def test_ambiguous_or_invalid_range_cannot_fall_back_to_start(time):
    b = build_canonical_semantic_build('个人项目：索引工具\n' + time + '，开发文件索引功能。')
    assert not b.experience_time_decisions[0].qualified
    assert b.ledger.facts


@pytest.mark.parametrize('body,expected', [
    ('2025年12月至2026年2月，开发查询功能。', '2025年12月至2026年2月'),
    ('2026年3月至今，开发查询功能。', '2026年3月至今'),
    ('2026年3月，开发查询功能。', '2026年3月'),
    ('2026秋季学期，开发查询功能。', '2026秋季学期'),
    ('2025-2026学年，开发查询功能。', '2025-2026学年'),
    ('2026年3月至5月，开发查询功能。2026年4月完成测试。', '2026年3月至5月'),
    ('开发查询功能。测试日期为2026年4月。', ''),
    ('开发查询功能。测试时间为2026年4月。', ''),
    ('开发查询功能。预计2027年毕业。', ''),
    ('项目时间为2026年3月至5月。项目时间为2026年7月至9月。开发查询功能。', ''),
])
def test_experience_time_is_not_any_date_in_the_owner(body, expected):
    b = build_canonical_semantic_build('项目一：索引工具\n' + body)
    d = b.experience_time_decisions[0]
    assert (d.display_time if d.qualified else '') == expected


@pytest.mark.parametrize('heading', ['计划开发检索工具', '可能完成检索系统', '对开发的基本流程进行学习'])
def test_descriptive_or_restricted_title_is_not_a_name(heading):
    b = build_canonical_semantic_build('项目一：' + heading + '\n使用Python整理文件。')
    assert not b.display_name_qualifications[0].qualified


def test_equal_authority_name_conflict_is_pending_not_first_wins():
    raw = '项目一：索引工具\n项目名称为检索助手。使用Python整理文件。'
    b = build_canonical_semantic_build(raw)
    assert not b.display_name_qualifications[0].qualified
    assert 'ambiguous_local_names' in b.display_name_qualifications[0].reason_codes


def test_inferred_identity_aliases_cannot_overwrite_original_heading():
    raw = '个人项目：索引工具\n使用Python整理文件。'
    b = build_canonical_semantic_build(raw)
    altered = replace(b.identities[0], title='伪造名称', canonical_project_name='其他名称', project_aliases=['别名'])
    result = names.build_canonical_display_name_qualifications((altered,), b.claim_resolutions, raw_input=raw)
    assert result == b.display_name_qualifications


@pytest.mark.parametrize('text', [
    '在一家家居用品公司担任产品运营实习生，负责资料整理。',
    '项目合作方为星禾软件公司，负责接口开发。',
    '希望在星禾软件公司担任高级后端实习生。负责接口开发。',
    '没有在星禾软件公司担任后端实习生。负责接口开发。',
])
def test_unqualified_organization_never_becomes_employer(text):
    b = build_canonical_semantic_build('实习经历：产品运营实习\n' + text)
    assert not fields(b)['organization'].qualified


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['case'])
@pytest.mark.parametrize('placement', ['detail', 'mixed'])
def test_real_saved_header_and_docx_share_frozen_decisions(case, placement, monkeypatch, tmp_path, isolated):
    b, captured, snapshots = trace_delivery(case['raw_input'], placement, monkeypatch, tmp_path)
    projects = captured['saved']['resume_sections']['projects']
    assert_saved_evidence(projects, b)
    for name, stage, intermediate in snapshots:
        assert_saved_evidence(intermediate, b)
    text = '\n'.join(p.text for path in tmp_path.glob('*.docx') for p in Document(path).paragraphs)
    for index, expected in enumerate(EXPECTED[case['case']]):
        project = projects[index]
        for key, value in expected.items():
            output_key = 'name' if key == 'organization' else key
            assert project[output_key] == fields(b, index)[key].display_text
            assert value in text
    assert b == build_canonical_semantic_build(case['raw_input'])


def test_header_consumers_do_not_reinterpret_source_or_touch_facts(monkeypatch):
    raw = CASES[0]['raw_input']
    b = build_canonical_semantic_build(raw)
    before = deepcopy(b)
    views = build_canonical_consumer_views(b)
    view_snapshot = repr(views)
    payload = _bound_payload(b)
    original = payload.model_copy(deep=True)
    def forbidden(*args, **kwargs):
        raise AssertionError('Header assembly attempted semantic reconstruction')
    monkeypatch.setattr(state, 'build_canonical_semantic_build', forbidden)
    result = resolve_canonical_resume_titles(payload, views.planner_view)
    assert payload == original and b == before and repr(views) == view_snapshot
    assert result == resolve_canonical_resume_titles(result, views.planner_view)
    for key in ('intro', 'role', 'details', 'source_fact_ids', 'source_claim_ids', 'detail_fact_ids', 'detail_claim_ids'):
        assert result.resume_sections.projects[0].get(key) == original.resume_sections.projects[0].get(key)


def test_normalized_name_keeps_original_whitespace_span():
    raw = '项目名称为Atlas  Search。使用Python开发查询功能。'
    b = build_canonical_semantic_build(raw)
    d = b.display_name_qualifications[0]
    assert d.display_name == 'Atlas Search'
    assert raw[slice(*d.source_span)] == 'Atlas  Search'


@pytest.mark.parametrize('field_key', ['organization', 'position', 'time'])
def test_multi_owner_cannot_supply_missing_internship_header(field_key):
    known = '实习经历：在星禾软件公司担任前端开发实习生\n2026年3月至5月，负责页面开发。'
    missing = '实习经历：资料整理\n协助整理文档。'
    b = build_canonical_semantic_build(known + '\n\n' + missing)
    assert len(b.identities) == 2
    assert fields(b, 0)[field_key].qualified
    assert not fields(b, 1)[field_key].qualified
    assert b.ledger.for_experience('EXP-002')


def test_header_qualification_logs_never_include_values(tmp_path, monkeypatch):
    b = build_canonical_semantic_build(CASES[0]['raw_input'])
    monkeypatch.setattr(names, 'LOG_PATH', tmp_path / 'names.jsonl')
    monkeypatch.setattr(state, 'TIME_QUALIFICATION_LOG_PATH', tmp_path / 'times.jsonl')
    monkeypatch.setattr(state, 'HEADER_QUALIFICATION_LOG_PATH', tmp_path / 'headers.jsonl')
    names.write_canonical_display_name_qualification_log(b.display_name_qualifications, stage='test')
    state.write_canonical_experience_time_qualification_log(b.experience_time_decisions, stage='test')
    state.write_canonical_experience_header_qualification_log(b.experience_header_decisions, stage='test')
    logs = '\n'.join(p.read_text(encoding='utf-8') for p in tmp_path.glob('*.jsonl'))
    assert logs
    assert all(f.value not in logs for h in b.experience_header_decisions for f in h.fields if f.qualified)


def test_reserved_industrial_header_and_delivery(monkeypatch, tmp_path, isolated):
    raw = ('实习经历：质量检验实习\n'
           '2025年11月至2026年2月，在云帆制造公司担任质量检验实习生，使用Excel整理37份巡检记录。\n\n'
           '个人项目：巡检记录查询工具\n'
           '2026年3月至4月，使用Python开发巡检查询功能。使用18份记录测试查询结果。')
    b, captured, snapshots = trace_delivery(raw, 'mixed', monkeypatch, tmp_path)
    assert fields(b)['organization'].value == '云帆制造公司'
    assert fields(b)['position'].value == '质量检验实习'
    assert fields(b)['time'].value == '2025年11月至2026年2月'
    assert fields(b, 1)['name'].value == '巡检记录查询工具'
    assert fields(b, 1)['time'].value == '2026年3月至4月'
    assert_saved_evidence(captured['saved']['resume_sections']['projects'], b)
    for header in b.experience_header_decisions:
        for f in header.fields:
            assert f.value in raw[slice(*f.source_span)]


def test_conflicting_local_employers_and_positions_are_pending():
    raw = ('实习经历：产品运营实习\n'
           '在星禾软件公司担任产品运营实习生，负责资料整理。'
           '公司名称：云帆科技公司。担任后端开发实习生，完成接口开发。')
    b = build_canonical_semantic_build(raw)
    assert len(b.identities) == 1
    assert not fields(b)['organization'].qualified
    assert not fields(b)['position'].qualified


@pytest.mark.parametrize('prefix', ['计划', '不确定是否', '没有'])
def test_restricted_local_name_declaration_does_not_bypass_claim_qualification(prefix):
    raw = '项目一：\n使用Python整理文件。' + prefix + '开发图书借阅系统。'
    b = build_canonical_semantic_build(raw)
    assert not b.display_name_qualifications[0].qualified
    assert b.ledger.facts
