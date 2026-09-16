"""Current-code replays; fixtures are user-visible inputs, not model snapshots."""
from dataclasses import replace
import json
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.input_claim_resolution_service import resolve_experience_claims
from app.services.experience_type_resolution_service import resolve_identity_type
from app.services.semantic_experience_segmentation_service import segment_semantic_experiences
from app.services.prompt_service import build_generation_prompt
from test_v0916_canonical_model_evidence import request_for, evidence, capture_generation
from test_v09174_fact_reference_composition import isolated
from test_v09175_post_processing_evidence import trace_delivery, assert_complete, field_rows
from docx import Document

CASES = json.loads((ROOT / "tests/fixtures/v091811_normal_inputs.json").read_text(encoding="utf-8"))


def compact(text):
    return re.sub(r"\s+", "", text)


def signature(build):
    return [(f.experience_id, compact(f.resume_ready_text)) for f in build.ledger.facts]


def check_sources(raw, build):
    for identity in build.identities:
        assert raw[slice(*identity.source_span)] == identity.raw_text
    for claim in build.ledger.claims:
        assert compact(raw[slice(*claim.source_span)]) == compact(claim.text)
    for fact in build.ledger.facts:
        assert compact(raw[slice(*fact.source_span)]) == compact(fact.fact_text)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case"])
def test_full_normal_inputs_admit_only_real_experiences(case):
    raw = case["raw_input"]
    intro, body = raw.split("\n\n", 1)
    build = build_canonical_semantic_build(raw)
    direct = build_canonical_semantic_build(body)
    assert len(build.identities) == 2
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == case["types"]
    assert signature(build) == signature(direct)
    assert not any("2027" in c.text for c in build.ledger.claims)
    spans = build.long_input_context.non_experience_source_spans
    for match in re.finditer(r"\S", intro):
        if match.group() not in "，,。；;":
            assert any(a <= match.start() < b for a, b in spans)
    views = build_canonical_consumer_views(build)
    request = request_for(raw)
    prompt = build_generation_prompt(request, build.long_input_context, consumer_views=views)
    data = evidence(prompt)
    assert len(data["owners"]) == 2
    assert "2027" not in json.dumps(data["owners"], ensure_ascii=False)
    background = data["non_experience_context_not_project_facts"]
    assert "2027" in json.dumps(background, ensure_ascii=False)
    assert all(raw[slice(*row["source_span"])] == row["text"] for row in background)
    assert request.raw_input == raw
    check_sources(raw, build)
    assert signature(build_canonical_semantic_build(raw)) == signature(build)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case"])
@pytest.mark.parametrize("style", ["crlf", "blank", "sentence", "wrap"])
def test_layout_does_not_admit_background(case, style):
    raw = case["raw_input"]
    variant = {"crlf": raw.replace("\n", "\r\n"), "blank": raw.replace("\n", "\n\n"),
               "sentence": raw.replace("。", "。\n"), "wrap": raw.replace("专业", "专\n业").replace("申请", "申\n请")}[style]
    a, b = build_canonical_semantic_build(raw), build_canonical_semantic_build(variant)
    assert len(b.identities) == 2
    assert signature(a) == signature(b)
    check_sources(variant, b)


PROSE = "2026年6月至8月，在星禾软件公司担任前端开发实习生，使用Vue完成工单页面，修复12个问题。"


@pytest.mark.parametrize("prefix", ["", "我是软件工程专业本科生，预计2027年毕业。", "希望申请前端开发实习。熟悉Vue。"])
@pytest.mark.parametrize("separator", ["", "\n", "\n\n", "\r\n"])
def test_real_first_prose_is_kept_with_or_without_intro(prefix, separator):
    raw = prefix + separator + PROSE
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 1
    assert build.experience_type_decisions[0].canonical_experience_type == "实习经历"
    assert "12" in build.identities[0].raw_text and "2027" not in build.identities[0].raw_text
    assert "申请" not in build.identities[0].raw_text
    check_sources(raw, build)


@pytest.mark.parametrize("raw", [c["raw_input"].split("\n\n", 1)[0] for c in CASES])
def test_only_context_never_creates_any_owner(raw):
    b = build_canonical_semantic_build(raw)
    assert not b.identities and not b.ledger.facts
    assert b.long_input_context.non_experience_source_spans


def test_unproven_first_fragment_is_pending_not_a_default_project():
    raw = "一些零散记录。"
    partition = segment_semantic_experiences(raw)
    assert not partition.segments
    assert partition.ambiguous_source_spans and partition.clarification_questions
    assert raw[slice(*partition.ambiguous_source_spans[0])] == "一些零散记录"


def test_intent_does_not_remove_real_duties_in_the_same_sentence():
    raw = "在星禾软件公司担任开发实习生，完成接口开发，这段经历让我希望申请后端岗位。"
    b = build_canonical_semantic_build(raw)
    assert len(b.identities) == 1
    assert any("完成接口开发" in f.fact_text for f in b.ledger.facts)
    assert not any("希望申请" in f.fact_text for f in b.ledger.facts)
    check_sources(raw, b)


def test_type_cannot_combine_target_role_with_unrelated_skill_predicates():
    base = build_canonical_semantic_build(PROSE).identities[0]
    raw = "想申请Java后端开发实习。使用Python完成课程项目的接口测试。"
    identity = replace(base, raw_text=raw, title="项目经历", declared_experience_type="", source_span=(0, len(raw)))
    resolution = resolve_experience_claims(identity.experience_id, raw)
    result = resolve_identity_type(identity, claim_resolution=resolution)
    assert result.resolved_type == "项目经历"
    assert any(c.semantic_role == "TARGET_ROLE_CONTEXT" for c in resolution.excluded_claims)


@pytest.mark.parametrize("limitation", ["目前尚未开展相关实验", "团队尚未验证跨设备效果", "截至目前尚未提交报告", "我尚未整理实验结果"])
def test_aspect_negation_is_not_an_action_whitelist(limitation):
    raw = "使用Python完成数据整理，" + limitation + "。"
    r = resolve_experience_claims("EXP-001", raw)
    assert [c.text for c in r.eligible_claims] == ["使用Python完成数据整理"]
    restricted, = r.excluded_claims
    assert restricted.text == limitation
    assert (restricted.polarity, restricted.certainty) == ("negative", "denied")
    assert raw[slice(*restricted.source_span)] == limitation


@pytest.mark.parametrize("raw", ["开发未完成任务管理系统，实现状态查询。", "开发计划管理系统，实现任务登记。", "我负责未完成订单的复查。"])
def test_noun_and_duty_objects_are_not_negated_assertions(raw):
    r = resolve_experience_claims("EXP-001", raw)
    assert r.eligible_claims and not r.excluded_claims and not r.withheld_claims


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case"])
def test_real_request_preparation_retains_background_outside_owners(case, monkeypatch, tmp_path):
    captured = capture_generation(case["raw_input"], monkeypatch, tmp_path, forbid_rebuild=True)
    data = evidence(captured["prompts"][0])
    assert len(data["owners"]) == 2
    assert "2027" not in json.dumps(data["owners"], ensure_ascii=False)
    assert "2027" in json.dumps(data["non_experience_context_not_project_facts"], ensure_ascii=False)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case"])
@pytest.mark.parametrize("placement", ["detail", "mixed"])
def test_real_delivery_preserves_each_local_fact(case, placement, monkeypatch, tmp_path, isolated):
    build, captured, snapshots = trace_delivery(case["raw_input"], placement, monkeypatch, tmp_path)
    assert len(build.identities) == 2
    before_professionalization = True
    for name, stage, projects in snapshots:
        if name == "professionalize_resume_language":
            before_professionalization = False
        if before_professionalization:
            assert_complete(projects, build)
        else:
            assert_saved_evidence(projects, build)
        assert "2027" not in json.dumps(projects, ensure_ascii=False), (name, stage)
    assert_saved_evidence(captured["saved"]["resume_sections"]["projects"], build)
    text = '\n'.join(p.text for path in tmp_path.glob('*.docx') for p in Document(path).paragraphs)
    for fact in build.ledger.facts:
        expected = fact.resume_ready_text.rstrip('。；;')
        assert expected in text or (expected.startswith("我负责") and expected[1:] in text)


def assert_saved_evidence(projects, build):
    # Existing professionalization removes the first-person subject. This is
    # observed downstream behavior, not permission to rewrite frozen evidence.
    assert {p['source_experience_id'] for p in projects} == {i.experience_id for i in build.identities}
    for project in projects:
        facts = {f.fact_id: f for f in build.ledger.for_experience(project['source_experience_id'])}
        seen = set()
        for text, ids, claims in field_rows(project):
            if not text:
                assert not ids and not claims
                continue
            assert ids and set(ids) <= facts.keys()
            assert set(claims) == {facts[fid].claim_id for fid in ids}
            for fid in ids:
                expected = facts[fid].resume_ready_text.rstrip('。；;')
                assert expected in text or (expected.startswith("我负责") and expected[1:] in text)
            seen.update(ids)
        assert seen == facts.keys()
        assert set(project['source_fact_ids']) == seen
        assert set(project['source_claim_ids']) == {facts[fid].claim_id for fid in seen}


def test_pending_preamble_is_not_lost_when_a_later_heading_is_present():
    raw = "一些零散记录。\n项目一：预约工具\n开发预约查询接口。"
    partition = segment_semantic_experiences(raw)
    assert len(partition.segments) == 1
    assert partition.clarification_questions
    assert raw[slice(*partition.ambiguous_source_spans[0])] == "一些零散记录"


def test_independent_aspect_limit_remains_outside_model_facts():
    raw = "科研经历：音频分类研究\n使用Python整理240段音频。后续计划研究跨设备适配，目前尚未开展相关实验。"
    build = build_canonical_semantic_build(raw)
    views = build_canonical_consumer_views(build)
    data = evidence(build_generation_prompt(request_for(raw), build.long_input_context, consumer_views=views))
    assert "尚未开展" not in json.dumps(data["owners"], ensure_ascii=False)
    assert "尚未开展" in json.dumps(data["internal_constraints_not_resume_facts"], ensure_ascii=False)
    assert any("240" in f.fact_text for f in build.ledger.facts)
    check_sources(raw, build)


def test_reserved_industrial_sample_without_a_background_heading():
    background = "我是工业工程专业本科生，预计2028年毕业，想应聘质量工程实习。熟悉Excel。"
    work = "2026年4月至6月，在远行制造公司担任质量实习生，整理37份巡检记录。使用Excel统计缺陷分布，目前尚未验证改进效果。"
    raw = background + work
    build = build_canonical_semantic_build(raw)
    direct = build_canonical_semantic_build(work)
    assert len(build.identities) == 1
    assert signature(build) == signature(direct)
    assert build.experience_type_decisions[0].canonical_experience_type == "实习经历"
    assert any("37份" in f.fact_text for f in build.ledger.facts)
    assert not any("尚未" in f.fact_text for f in build.ledger.facts)
    assert any(c.text == "目前尚未验证改进效果" and c.eligibility == "excluded" for c in build.ledger.claims)
    check_sources(raw, build)


@pytest.mark.parametrize("ability", ["能够使用", "能使用", "会使用"])
def test_ability_without_performed_work_is_not_an_experience(ability):
    raw = ability + "Python和Git，了解基础Linux命令。"
    build = build_canonical_semantic_build(raw)
    assert not build.identities and not build.ledger.facts
    assert build.long_input_context.non_experience_source_spans


@pytest.mark.parametrize("connector", ["并", "并且", "随后", "同时"])
def test_skill_prefix_does_not_swallow_independent_performed_work(connector):
    raw = "熟悉Vue" + connector + "完成工单页面开发。"
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 1
    assert build.identities[0].raw_text == "完成工单页面开发"
    assert any(f.fact_text == "完成工单页面开发" for f in build.ledger.facts)
    assert "熟悉Vue" in ''.join(raw[slice(*span)] for span in build.long_input_context.non_experience_source_spans)
    check_sources(raw, build)
