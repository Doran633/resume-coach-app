"""Current-code controls, not historical model response reconstruction."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from docx import Document

from app.services import generation_service as generation
from app import schemas
from app.services.resume_fact_dedup_service import deduplicate_resume_facts
from app.services.resume_fact_cluster_dedup_service import deduplicate_fact_clusters
from test_v09162_model_output_evidence_contract import real_receiver, reference_return
from test_v09172_initial_evidence_preservation import detail_input, detail_return
from test_v09174_fact_reference_composition import isolated


WRITERS = (
    'cleanup_generation_payload', 'guard_hard_facts', 'fill_resume_sections',
    'guard_experience_boundaries', 'sanitize_resume_body', 'reconcile_resume_projects',
    'deduplicate_resume_facts', 'guard_fact_coverage', 'layer_resume_sections',
    'ensure_resume_fact_increment', 'organize_adaptive_narrative', 'ensure_information_gain',
    'ensure_dedup_quality', 'deduplicate_fact_clusters', 'guard_template_language',
    'guard_resume_output', 'professionalize_resume_language',
    'ensure_resume_experience_validity', 'contain_ownerless_projects',
    'guard_resume_skill_evidence', 'calibrate_resume_skill_taxonomy',
    'guard_resume_output_relevance', 'ensure_recruiter_facing_technical_language',
    'ensure_recruiter_readability', 'ensure_paired_symbol_integrity',
    'ensure_resume_section_integrity', 'ensure_resume_whitespace_quality',
    'ensure_typography_quality', 'resolve_canonical_resume_titles',
    'deduplicate_resume_experience_entities',
)


def multi_detail_input(total):
    counts = [7, 7, total - 14]
    return '\n'.join(
        f'项目{label}：接口校验工具{label}\n' + '。'.join(
            f'使用Python编写第{i}组接口测试用例并记录{i + 10}条结果'
            for i in range(1, count + 1)
        ) + '。'
        for label, count in zip('一二三', counts)
    )


def field_rows(project):
    rows = [(project.get(name, ''), project.get(f'{name}_source_fact_ids', []),
             project.get(f'{name}_source_claim_ids', [])) for name in ('intro', 'role')]
    details = project.get('details', [])
    facts = project.get('detail_fact_ids', [])
    claims = project.get('detail_claim_ids', [])
    assert len(details) == len(facts) == len(claims)
    return rows + list(zip(details, facts, claims))


def assert_complete(projects, build):
    by_owner = {p.get('source_experience_id'): p for p in projects}
    assert len(by_owner) == len(projects) == len(build.identities)
    for identity in build.identities:
        facts = {f.fact_id: f for f in build.ledger.for_experience(identity.experience_id)}
        p = by_owner[identity.experience_id]
        seen = set()
        for text, ids, claims in field_rows(p):
            if not text:
                assert not ids and not claims
                continue
            assert ids and set(ids) <= facts.keys()
            assert set(claims) == {facts[fid].claim_id for fid in ids}
            for fid in ids:
                assert facts[fid].resume_ready_text.rstrip('。；;') in text, (fid, text)
            seen.update(ids)
        assert seen == facts.keys(), {'missing': sorted(facts.keys() - seen)}
        assert set(p.get('source_fact_ids', [])) == seen
        assert set(p.get('source_claim_ids', [])) == {facts[fid].claim_id for fid in seen}


def trace_delivery(raw, position, monkeypatch, tmp_path):
    case, build, body = detail_return(raw)
    before = deepcopy(build)
    reply = reference_return(body)
    for p in reply['resume_sections']['projects']:
        for index, fid in enumerate(p['fact_placements']):
            p['fact_placements'][fid] = (
                ['intro', 'role', 'detail'][index % 3] if position == 'mixed' else position
            )
    snapshots, gates, frozen_objects, compiled_objects = [], [], [], []
    for name in ('build_canonical_semantic_build', 'build_canonical_consumer_views'):
        original = getattr(generation, name)
        def remember(*args, _fn=original, **kwargs):
            value = _fn(*args, **kwargs)
            compiled_objects.append(value)
            return value
        monkeypatch.setattr(generation, name, remember)
    for name in WRITERS:
        original = getattr(generation, name)
        def observe(*args, _fn=original, _name=name, **kwargs):
            # Generation first associates the build with the new isolated input row.
            # Freeze the comparison at reception, before any presentation writer.
            if not frozen_objects:
                frozen_objects.extend((value, repr(value)) for value in compiled_objects)
            result = _fn(*args, **kwargs)
            payload = result[0] if isinstance(result, tuple) else result
            snapshots.append((_name, kwargs.get('stage'), deepcopy(payload.resume_sections.projects)))
            return result
        monkeypatch.setattr(generation, name, observe)
    gate = generation.validate_resume_delivery_quality
    def observe_gate(*args, **kwargs):
        result = gate(*args, **kwargs)
        gates.append({'passed': result.stats.gate_passed, 'issues': [i.issue_code for i in result.issues]})
        return result
    monkeypatch.setattr(generation, 'validate_resume_delivery_quality', observe_gate)
    captured = real_receiver(case, reply, monkeypatch, tmp_path, deliver=True)
    assert build == before
    assert frozen_objects
    for value, snapshot in frozen_objects:
        current = repr(value)
        if current != snapshot:
            index = next((i for i, (a, b) in enumerate(zip(snapshot, current)) if a != b), 0)
            pytest.fail(f'{type(value).__name__} changed: BEFORE {snapshot[max(0,index-60):index+180]} AFTER {current[max(0,index-60):index+180]}')
    report = {'stages': snapshots, 'gates': gates, 'saved': captured['saved']['resume_sections']['projects']}
    (tmp_path/'post-processing-stages.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return build, captured, snapshots


@pytest.mark.parametrize('total', [8, 9, 20, 21])
@pytest.mark.parametrize('position', ['detail', 'mixed', 'role'])
def test_fact_placement_and_budgets_preserve_every_stage(total, position, monkeypatch, tmp_path, isolated):
    raw = detail_input(total) if total < 10 else multi_detail_input(total)
    build, captured, snapshots = trace_delivery(raw, position, monkeypatch, tmp_path)
    assert len(build.ledger.facts) == total
    assert_complete(captured['payload'].resume_sections.projects, build)
    for name, stage, projects in snapshots:
        try:
            assert_complete(projects, build)
        except AssertionError as exc:
            pytest.fail(f'First invalid stage {name}/{stage}: {exc}')
    assert_complete(captured['saved']['resume_sections']['projects'], build)
    rendered = '\n'.join(p.text for path in tmp_path.glob('*.docx') for p in Document(path).paragraphs)
    for fact in build.ledger.facts:
        assert fact.resume_ready_text.rstrip('。；;') in rendered


@pytest.mark.parametrize('position', ['detail', 'mixed', 'role'])
def test_award_and_non_numeric_work_survive(position, monkeypatch, tmp_path, isolated):
    raw = ('竞赛经历：数据分析竞赛\n团队获得三等奖。使用Python整理调查结果。'
           '负责汇总同学提出的问题。\n'
           '项目经历：课程练习工具\n使用Java开发查询页面，没有获奖。')
    build, captured, snapshots = trace_delivery(raw, position, monkeypatch, tmp_path)
    for name, stage, projects in snapshots:
        try:
            assert_complete(projects, build)
        except AssertionError as exc:
            pytest.fail(f'First invalid stage {name}/{stage}: {exc}')
    assert_complete(captured['saved']['resume_sections']['projects'], build)


def unit_project():
    _, build, body = detail_return(detail_input(3))
    return build, schemas.GenerationPayload.model_validate(body)


@pytest.mark.parametrize('kind', ['exact', 'same_text_other_source', 'missing_source', 'missing_claim',
                                  'different_qualification', 'partial_overlap', 'foreign_owner', 'unknown_id'])
def test_only_proven_exact_duplicates_can_be_removed(kind):
    build, payload = unit_project()
    p = payload.resume_sections.projects[0]
    text, fid, cid = p['details'][0], p['detail_fact_ids'][0], p['detail_claim_ids'][0]
    p['details'] = [text, text]
    p['detail_fact_ids'] = [fid[:], fid[:]]
    p['detail_claim_ids'] = [cid[:], cid[:]]
    facts = list(build.ledger.facts)
    if kind == 'same_text_other_source':
        p['detail_fact_ids'][1] = [facts[1].fact_id]
        p['detail_claim_ids'][1] = [facts[1].claim_id]
    elif kind == 'missing_source':
        p['detail_fact_ids'] = [[], []]
        p['detail_claim_ids'] = [[], []]
    elif kind == 'missing_claim':
        p['detail_claim_ids'] = [[], []]
    elif kind == 'different_qualification':
        p['details'][1] += '，仅在本地演示'
    elif kind == 'partial_overlap':
        p['details'] = ['；'.join(f.resume_ready_text for f in facts[:2]),
                        '；'.join(f.resume_ready_text for f in facts[1:])]
        p['detail_fact_ids'] = [[f.fact_id for f in facts[:2]], [f.fact_id for f in facts[1:]]]
        p['detail_claim_ids'] = [[f.claim_id for f in facts[:2]], [f.claim_id for f in facts[1:]]]
    elif kind == 'foreign_owner':
        p['source_experience_id'] = 'EXP-999'
    elif kind == 'unknown_id':
        p['detail_fact_ids'] = [['UNKNOWN'], ['UNKNOWN']]
    before, frozen = payload.model_copy(deep=True), deepcopy(build)
    result = deduplicate_resume_facts(payload, semantic_build=build, write_log=False)
    assert payload == before and build == frozen
    expected = 1 if kind == 'exact' else 2
    assert len(result.resume_sections.projects[0]['details']) == expected
    assert result == deduplicate_resume_facts(result, semantic_build=build, write_log=False)
    if kind != 'exact':
        for key in ('details', 'detail_fact_ids', 'detail_claim_ids'):
            assert result.resume_sections.projects[0][key] == p[key]


def test_retired_cluster_writer_retains_legacy_behavior(isolated):
    build, payload = unit_project()
    p = payload.resume_sections.projects[0]
    text = p['details'][0]
    p['details'] = [text, text + '，仅在本地演示']
    p['detail_fact_ids'] = [p['detail_fact_ids'][0][:], p['detail_fact_ids'][0][:]]
    p['detail_claim_ids'] = [p['detail_claim_ids'][0][:], p['detail_claim_ids'][0][:]]
    narrow = deduplicate_resume_facts(payload, semantic_build=build, write_log=False)
    clustered = deduplicate_fact_clusters(narrow, write_log=False)
    # This is the approved reason to exit this writer, not permission to change its legacy API.
    assert len(narrow.resume_sections.projects[0]['details']) == 2
    assert clustered.resume_sections.projects[0]['details'] == [text + '，仅在本地演示']


def test_generation_never_runs_retired_writers(monkeypatch, tmp_path, isolated):
    def forbidden(*args, **kwargs):
        raise AssertionError('Retired Canonical writer was reached')
    for name in ('layer_resume_sections', 'ensure_resume_fact_increment', 'ensure_information_gain',
                 'ensure_dedup_quality', 'deduplicate_fact_clusters'):
        monkeypatch.setattr(generation, name, forbidden)
    build, captured, snapshots = trace_delivery(detail_input(9), 'detail', monkeypatch, tmp_path)
    assert_complete(captured['saved']['resume_sections']['projects'], build)
    assert sum(name == 'deduplicate_resume_facts' for name, _, _ in snapshots) == 1


@pytest.mark.parametrize('blank_index', [0, 1])
def test_blank_rows_and_cross_field_aggregates_stay_aligned(blank_index):
    build, payload = unit_project()
    p = payload.resume_sections.projects[0]
    # The same Fact remains carried by intro when its empty detail attachment is removed.
    p['intro'] = p['details'][blank_index]
    p['intro_source_fact_ids'] = p['detail_fact_ids'][blank_index][:]
    p['intro_source_claim_ids'] = p['detail_claim_ids'][blank_index][:]
    p['details'][blank_index] = ' \n '
    p['role'] = ' '
    p['role_source_fact_ids'] = ['orphan']
    p['role_source_claim_ids'] = ['orphan-claim']
    p['source_fact_ids'].append('orphan')
    p['source_claim_ids'].append('orphan-claim')
    result = deduplicate_resume_facts(payload, semantic_build=build, write_log=False)
    assert_complete(result.resume_sections.projects, build)


def test_cross_field_dedup_never_uses_project_aggregate_as_intro_proof():
    build, payload = unit_project()
    p = payload.resume_sections.projects[0]
    p['intro'] = p['details'][0]
    unbound = deduplicate_resume_facts(payload, semantic_build=build, write_log=False)
    assert len(unbound.resume_sections.projects[0]['details']) == 3
    p['intro_source_fact_ids'] = p['detail_fact_ids'][0][:]
    p['intro_source_claim_ids'] = p['detail_claim_ids'][0][:]
    bound = deduplicate_resume_facts(payload, semantic_build=build, write_log=False)
    assert len(bound.resume_sections.projects[0]['details']) == 2
    assert_complete(bound.resume_sections.projects, build)


@pytest.mark.parametrize('name', ['layer_resume_sections', 'ensure_resume_fact_increment',
                                 'ensure_dedup_quality', 'deduplicate_resume_facts'])
def test_retired_legacy_limits_remain_explicit(name, isolated):
    _, build, body = detail_return(detail_input(9))
    payload = schemas.GenerationPayload.model_validate(body)
    legacy = getattr(generation, name)(payload)
    assert len(legacy.resume_sections.projects[0]['details']) == 8
    canonical = deduplicate_resume_facts(payload, semantic_build=build, write_log=False)
    assert_complete(canonical.resume_sections.projects, build)


def test_unbound_low_information_is_preserved_not_promoted(isolated):
    raw = '项目经历：活动宣传工具\n整理活动通知并核对报名方式。'
    _, build, body = detail_return(raw)
    payload = schemas.GenerationPayload.model_validate(body)
    p = payload.resume_sections.projects[0]
    p['detail_fact_ids'] = [[] for _ in p['details']]
    p['detail_claim_ids'] = [[] for _ in p['details']]
    legacy = generation.ensure_resume_fact_increment(payload)
    assert legacy.resume_sections.projects[0]['details'] == []
    canonical = deduplicate_resume_facts(payload, semantic_build=build, write_log=False)
    assert canonical.resume_sections.projects[0]['details'] == p['details']
    assert canonical.resume_sections.projects[0]['detail_fact_ids'] == p['detail_fact_ids']
    assert canonical.resume_sections.projects[0]['detail_claim_ids'] == p['detail_claim_ids']


def test_aggregate_helper_preserves_other_live_fields_without_guessing():
    build, payload = unit_project()
    p = payload.resume_sections.projects[0]
    p['intro'] = p['details'][0]
    p['intro_source_fact_ids'] = p['detail_fact_ids'][0][:]
    p['intro_source_claim_ids'] = p['detail_claim_ids'][0][:]
    p['details'][0] = ''
    result = deduplicate_resume_facts(payload, semantic_build=build, write_log=False)
    assert p['intro_source_fact_ids'][0] in result.resume_sections.projects[0]['source_fact_ids']
    assert result.resume_sections.projects[0]['intro_source_fact_ids'] == p['intro_source_fact_ids']


def test_reserved_sample_after_business_changes(monkeypatch, tmp_path, isolated):
    raw = (Path(__file__).parent/'fixtures/v091742_holdout_input.txt').read_text(encoding='utf-8')
    build, captured, snapshots = trace_delivery(raw, 'detail', monkeypatch, tmp_path)
    assert len(build.identities) == 2
    for name, stage, projects in snapshots:
        try:
            assert_complete(projects, build)
        except AssertionError as exc:
            pytest.fail(f'Reserved sample first invalid stage {name}/{stage}: {exc}')
    assert_complete(captured['saved']['resume_sections']['projects'], build)


def test_existing_dedup_log_reports_reasons_without_body(monkeypatch, tmp_path):
    from app.services import resume_fact_dedup_service as dedup
    build, payload = unit_project()
    p = payload.resume_sections.projects[0]
    p['details'].append(p['details'][0] + '，仅在本地演示')
    p['detail_fact_ids'].append(p['detail_fact_ids'][0][:])
    p['detail_claim_ids'].append(p['detail_claim_ids'][0][:])
    path = tmp_path/'dedup.jsonl'
    monkeypatch.setattr(dedup, 'LOG_PATH', path)
    dedup.deduplicate_resume_facts(payload, semantic_build=build)
    row = json.loads(path.read_text(encoding='utf-8'))
    assert row['nonidentical_source_overlap_count'] == 1
    assert 'nonidentical_text_or_lineage_preserved' in row['decision_reason']
    assert p['name'] not in path.read_text(encoding='utf-8')
    assert p['details'][0] not in path.read_text(encoding='utf-8')


def test_product_name_substring_does_not_authorize_project_removal(monkeypatch, tmp_path, isolated):
    from app.services.resume_project_reconciliation_service import _is_comprehensive
    raw = '项目经历：综合经历记录工具\n使用Python开发综合经历记录工具，实现文件上传与记录查询。编写接口测试检查空文件。'
    build, captured, snapshots = trace_delivery(raw, 'detail', monkeypatch, tmp_path)
    assert len(build.identities) == 1
    assert any(_is_comprehensive(project) for _, _, projects in snapshots for project in projects)
    for name, stage, projects in snapshots:
        try:
            assert_complete(projects, build)
        except AssertionError as exc:
            pytest.fail(f'First invalid stage {name}/{stage}: {exc}')
    assert_complete(captured['saved']['resume_sections']['projects'], build)
