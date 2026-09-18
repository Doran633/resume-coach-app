"""Current exact-input replay and new relation controls, not historical responses."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest
from docx import Document

from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.experience_type_resolution_service import resolve_identity_type
from test_v09174_fact_reference_composition import isolated
from test_v09181_claim_and_type_evidence import source_assertions, COURSE
from test_v09172_initial_evidence_preservation import detail_return
from test_v09162_model_output_evidence_contract import reference_return
from test_v09176_delivery_closure import deliver


RAW = '''基本信息：
软件工程专业本科在读，预计2028年毕业，希望申请前端开发实习。

课程项目：校园活动报名系统
2026年3月至2026年5月，在四人小组中负责前端页面开发。
使用Vue 3实现活动列表、活动详情、报名表单和报名记录页面。
根据后端接口文档完成页面联调，处理加载、空数据和请求失败状态。
使用16组测试数据检查必填项、重复报名和日期格式。
根据同学试用反馈调整表单提示和移动端按钮布局。

校园经历：程序设计社技术分享活动
2025年10月至2026年5月，担任程序设计社活动组成员。
协助组织4次技术分享，负责收集报名信息、整理活动通知和检查演示设备。
活动结束后汇总参与同学的反馈，并调整后续活动的签到说明。

技能：
能够使用JavaScript、Vue、HTML、CSS和Git，接触过TypeScript。'''


@pytest.mark.parametrize('raw', [RAW, RAW.replace('\n', '\r\n'), RAW.replace('\n', '\n\n'), RAW.replace('。', '。\n')], ids=['original', 'crlf', 'blank', 'sentences'])
def test_full_input_uses_participation_not_product_name(raw, isolated):
    build = build_canonical_semantic_build(raw)
    before = deepcopy(build)
    views = build_canonical_consumer_views(build)
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == ['项目经历', '校园 / 社团经历']
    assert len(build.identities) == 2
    result = resolve_identity_type(build.identities[0], build.claim_resolutions[0])
    assert result.evidence_scores['校园 / 社团经历'] == 0
    assert result.evidence_scores['项目经历'] > 0
    assert any('16组' in f.fact_text and f.experience_id == 'EXP-001' for f in build.ledger.facts)
    assert any('4次' in f.fact_text and f.experience_id == 'EXP-002' for f in build.ledger.facts)
    assert not any('4次' in f.fact_text and f.experience_id == 'EXP-001' for f in build.ledger.facts)
    source_assertions(raw, build)
    assert views.experience_ids == ('EXP-001', 'EXP-002')
    assert build == before == build_canonical_semantic_build(raw)


@pytest.mark.parametrize('name', ['校园活动报名系统', '志愿服务登记工具', '学生会信息平台', '科研助手', '实验室设备登记系统'])
def test_product_name_does_not_supply_participation(name):
    raw = f'课程项目：{name}\n2026年3月至2026年5月，在四人小组中负责前端页面开发。使用Vue实现查询页面。'
    build = build_canonical_semantic_build(raw)
    assert build.experience_type_decisions[0].canonical_experience_type == '项目经历'
    result = resolve_identity_type(build.identities[0], build.claim_resolutions[0])
    assert result.evidence_scores['校园 / 社团经历'] == result.evidence_scores['科研经历'] == 0
    source_assertions(raw, build)


@pytest.mark.parametrize('body,expected', [
    ('参与校园活动报名系统开发，负责页面联调。', '项目经历'),
    ('为学生会开发资料管理平台，负责接口测试。', '项目经历'),
    ('参与志愿服务登记工具开发，完成查询页面。', '项目经历'),
    ('参与校园活动，负责签到登记。', '校园 / 社团经历'),
    ('组织校园活动，开发报名工具。', '校园 / 社团经历'),
    ('加入学生会，负责活动通知。', '校园 / 社团经历'),
    ('在摄影协会担任成员，开发报名页面。', '校园 / 社团经历'),
    ('参与志愿服务，负责信息登记。', '校园 / 社团经历'),
    ('参与课题研究，开发实验记录工具。', '科研经历'),
    ('为实验室开发设备登记系统，负责接口联调。', '项目经历'),
])
def test_actual_relation_not_domain_cooccurrence(body, expected):
    raw = '个人项目：记录工具\n' + body
    build = build_canonical_semantic_build(raw)
    assert build.experience_type_decisions[0].canonical_experience_type == expected
    source_assertions(raw, build)


def test_existing_lab_course_input_stays_closed():
    build = build_canonical_semantic_build(COURSE)
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == ['项目经历', '项目经历']
    source_assertions(COURSE, build)


def test_full_control_saves_correct_headers_and_all_sources(monkeypatch, tmp_path, isolated):
    case, build, data = detail_return(RAW)
    data['resume_sections']['summary'] = ['具备前端页面开发实践。']
    for key in ('normal_version', 'bold_version', 'boundary_version', 'recommended_version'):
        data[key] = ''
    outcome = deliver(monkeypatch, tmp_path, case, [(json.dumps(reference_return(data), ensure_ascii=False), 'stop')])
    assert outcome['results'] == 1 and 'docx' in outcome, outcome
    projects = outcome['saved']['resume_sections']['projects']
    for fact in build.ledger.facts:
        project = next(p for p in projects if p['source_experience_id'] == fact.experience_id)
        assert fact.fact_id in project['source_fact_ids']
        assert fact.resume_ready_text.strip(' 。') in json.dumps(project, ensure_ascii=False)
        for index, ids in enumerate(project['detail_fact_ids']):
            if fact.fact_id in ids:
                assert fact.claim_id in project['detail_claim_ids'][index]
    rows = [p.text for p in Document(next(tmp_path.glob('*.docx'))).paragraphs]
    assert any('项目：校园活动报名系统' in row for row in rows)
    assert any('活动/组织：程序设计社技术分享活动' in row for row in rows)


@pytest.mark.parametrize('reverse', [False, True])
def test_owner_order_and_generated_title_cannot_supply_evidence(reverse):
    blocks = ['课程项目：校园活动报名系统\n使用Vue开发查询页面。',
              '校园经历：协会活动\n在摄影协会担任成员，负责活动通知。']
    if reverse:
        blocks.reverse()
    raw = '\n\n'.join(blocks)
    build = build_canonical_semantic_build(raw)
    expected = ['项目经历', '校园 / 社团经历']
    if reverse:
        expected.reverse()
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == expected
    for identity, claims, kind in zip(build.identities, build.claim_resolutions, expected):
        before = deepcopy((identity, claims))
        changed = replace(identity, title='科研经历：校园活动', experience_type='科研经历')
        assert resolve_identity_type(changed, claims).resolved_type == kind
        assert (identity, claims) == before
    source_assertions(raw, build)


def test_explicit_type_keeps_priority():
    build = build_canonical_semantic_build('项目经历：活动登记工具\n参与校园活动，开发登记页面。')
    assert build.experience_type_decisions[0].canonical_experience_type == '项目经历'
    assert build.experience_type_decisions[0].explicit


def test_holdout_service_object_and_real_membership():
    raw = ('课程项目：校庆资料查询工具\n2026年5月，为校庆开发资料查询工具，使用Python整理资料。'
           '\n\n个人项目：协会工作\n2026年6月，在书法协会担任成员，开发签到工具。')
    build = build_canonical_semantic_build(raw)
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == ['项目经历', '校园 / 社团经历']
    assert any('Python' in f.fact_text and f.experience_id == 'EXP-001' for f in build.ledger.facts)
    assert any('签到工具' in f.fact_text and f.experience_id == 'EXP-002' for f in build.ledger.facts)
    source_assertions(raw, build)
