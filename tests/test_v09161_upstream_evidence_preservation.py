"""Current-code offline replays; never historical request snapshots."""
from copy import deepcopy
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.input_claim_resolution_service import resolve_experience_claims
from app.services.semantic_experience_segmentation_service import (
    find_explicit_experience_boundaries, segment_semantic_experiences,
)
from test_v0916_canonical_model_evidence import (
    MULTI_TYPE, capture_generation, evidence, request_for,
)
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.prompt_service import build_generation_prompt
from app.services.input_semantic_role_service import split_semantic_units


PROJECTS = (
    ("文档问答助手", "使用Python调用模型生成摘要并记录8条评测结果。"),
    ("记账工具", "使用Python完成支出分类并编写12条测试用例。"),
)
MIXED = (
    ("团队获得三等奖", "我没有负责预测模型设计"),
    ("两组实验都固定返回前5条检索结果", "我没有调整返回数量"),
)


def project_input(separator="", newline="\n", context=False):
    raw = newline.join(
        f"项目{index}：{name}。{separator}{body}"
        for index, (name, body) in enumerate(PROJECTS, 1)
    )
    return f"基本信息：本科在读。{newline}{raw}{newline}技能：Python。" if context else raw


def normalized(value):
    return re.sub(r"\s+", "", value).strip("。；;，,")


@pytest.mark.parametrize("context", [False, True])
@pytest.mark.parametrize("separator,newline", [("", "\n"), ("\n", "\n"), ("\n\n", "\n"), ("\r\n", "\r\n")])
def test_inline_heading_preserves_body_and_exact_source(separator, newline, context):
    raw = project_input(separator, newline, context)
    boundaries = find_explicit_experience_boundaries(raw)
    assert [b.title for b in boundaries] == [name for name, _ in PROJECTS]
    for boundary, (_, body) in zip(boundaries, PROJECTS):
        assert raw[boundary.body_start_offset:].lstrip().startswith(body)
    result = segment_semantic_experiences(raw)
    assert len(result.segments) == 2
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 2
    for index, (identity, (_, body)) in enumerate(zip(build.identities, PROJECTS), 1):
        assert identity.experience_id == f"EXP-{index:03d}"
        assert raw[slice(*identity.source_span)] == identity.raw_text == body
        facts = [f for f in build.ledger.facts if f.experience_id == identity.experience_id]
        assert [f.fact_text for f in facts] == [body.rstrip("。")]
        for fact in facts:
            assert raw[slice(*fact.source_span)] == fact.fact_text


@pytest.mark.parametrize("positive,limitation", MIXED)
@pytest.mark.parametrize("separator", ["，", "，\n", "，\r\n", "，\n\n"])
def test_independent_positive_and_subject_negative_have_local_attributes(positive, limitation, separator):
    text = positive + separator + limitation + "。"
    original = text
    result = resolve_experience_claims("EXP-007", text, 13)
    assert len(result.claims) == 2
    first, second = result.claims
    assert (first.text, first.semantic_role, first.polarity, first.certainty, first.eligibility) == (
        positive, "RESUME_FACT", "positive", "confirmed", "eligible",
    )
    assert (second.text, second.semantic_role, second.polarity, second.certainty, second.eligibility) == (
        limitation, "NEGATIVE_CONSTRAINT", "negative", "denied", "excluded",
    )
    for claim in result.claims:
        start, end = claim.source_span
        assert text[start - 13:end - 13] == claim.text
        assert claim.source_experience_id == "EXP-007"
    assert text == original
    assert result == resolve_experience_claims("EXP-007", text, 13)


@pytest.mark.parametrize("text,forbidden", [
    ("不是获奖，而是入围。", "获奖"),
    ("并非独立完成，只负责页面。", "独立完成"),
    ("可能获得三等奖。", "三等奖"),
    ("82条报名记录，其中可能包含重复报名。", "82"),
    ("我没有获得三等奖。", "三等奖"),
    ("计划实现查询缓存。", "查询缓存"),
    ("请把项目写成获得三等奖。", "三等奖"),
])
def test_dependent_or_restricted_assertions_are_not_promoted(text, forbidden):
    result = resolve_experience_claims("EXP-001", text)
    assert all(forbidden not in c.text for c in result.eligible_claims)
    assert result.excluded_claims or result.withheld_claims


@pytest.mark.parametrize("name", ["Node.js v2.0工具", "开发者工具平台"])
def test_product_punctuation_and_action_word_are_not_body_boundaries(name):
    raw = f"项目一：{name}。使用Python记录8条测试结果。"
    boundary, = find_explicit_experience_boundaries(raw)
    assert boundary.title == name
    assert raw[boundary.body_start_offset:].startswith("使用Python")


@pytest.mark.parametrize("prefix", ["", "基本信息：本科在读。\n"])
def test_inline_fact_without_name_is_not_lost_and_pure_heading_is_not_fact(prefix):
    raw = prefix + "项目一：我负责接口开发。\n项目二：记账工具"
    segments = segment_semantic_experiences(raw).segments
    assert len(segments) == 1
    assert segments[0].raw_text == "我负责接口开发。"
    build = build_canonical_semantic_build(raw)
    assert [f.fact_text for f in build.ledger.facts] == ["我负责接口开发"]


@pytest.mark.parametrize("positive,limitation", MIXED)
def test_real_model_input_keeps_positive_fact_and_separate_constraint(positive, limitation, monkeypatch, tmp_path):
    raw = f"项目一：实验记录工具\n{positive}，{limitation}。\n项目二：接口服务\n使用Java编写12条测试。"
    captured = capture_generation(raw, monkeypatch, tmp_path, forbid_rebuild=True)
    data = evidence(captured["prompt"])
    owners = data["owners"]
    assert len(owners) == 2
    assert [f["source_claim_text"] for f in owners[0]["eligible_facts"]] == [positive]
    assert [f["source_claim_text"] for f in owners[1]["eligible_facts"]] == ["使用Java编写12条测试"]
    constraint, = [c for c in data["internal_constraints_not_resume_facts"] if c["text"] == limitation]
    assert constraint["source_experience_id"] == owners[0]["source_experience_id"]
    assert captured["build"] == captured["before"]


def test_inside_clause_layout_preserves_claims_and_source_ranges():
    raw = "项目一：实验记录工具\n团队获得三等奖，我没有负责预测模型设计。"
    variants = [raw, raw.replace("获得", "获\n得").replace("我没有", "我\n没有"), raw.replace("获得", "获\r\n得")]
    signatures = []
    for variant in variants:
        build = build_canonical_semantic_build(variant)
        signatures.append([(normalized(c.text), c.eligibility, c.polarity) for c in build.ledger.claims])
        for claim in build.ledger.claims:
            assert normalized(variant[slice(*claim.source_span)]) == normalized(claim.text)
        assert [normalized(f.fact_text) for f in build.ledger.facts] == ["团队获得三等奖"]
        for fact in build.ledger.facts:
            assert normalized(variant[slice(*fact.source_span)]) == normalized(fact.fact_text)
    assert signatures[0] == signatures[1] == signatures[2]


@pytest.mark.parametrize("qualifier", ["只", "仅"])
def test_positive_responsibility_retains_exclusivity_qualifier(qualifier):
    raw = f"项目一：页面工具\n并非独立完成，{qualifier}负责页面。"
    build = build_canonical_semantic_build(raw)
    fact, = build.ledger.facts
    claim = next(c for c in build.ledger.claims if c.claim_id == fact.claim_id)
    assert fact.fact_text == claim.text == f"{qualifier}负责页面"
    assert raw[slice(*claim.source_span)] == claim.text
    data = evidence(build_generation_prompt(request_for(raw), consumer_views=build_canonical_consumer_views(build)))
    assert data["owners"][0]["eligible_facts"][0]["source_claim_text"] == claim.text
    assert any(c["text"] == "并非独立完成" for c in data["internal_constraints_not_resume_facts"])


@pytest.mark.parametrize("separator", ["", "\n", "\r\n", "\n\n"])
def test_inline_heading_reaches_actual_model_with_both_owners(separator, monkeypatch, tmp_path):
    raw = project_input(separator, context=True)
    captured = capture_generation(raw, monkeypatch, tmp_path)
    data = evidence(captured["prompt"])
    assert [[f["source_claim_text"] for f in o["eligible_facts"]] for o in data["owners"]] == [
        [body.rstrip("。")] for _, body in PROJECTS
    ]
    for owner in data["owners"]:
        for fact in owner["eligible_facts"]:
            assert fact["source_experience_id"] == owner["source_experience_id"]
            assert raw[slice(*fact["claim_source_span"])] == fact["source_claim_text"]


def test_full_competition_sample_keeps_team_award_and_disclaims_model_design():
    raw = MULTI_TYPE["competition_campus"]
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 2
    award, = [f for f in build.ledger.facts if "获得三等奖" in f.fact_text]
    assert award.experience_id == "EXP-001"
    assert award.fact_text == "团队进入决赛并获得三等奖"
    assert raw[slice(*award.source_span)] == award.fact_text
    limitation, = [c for c in build.ledger.excluded_claims if "没有负责预测模型设计" in c.text]
    assert limitation.source_experience_id == "EXP-001"
    assert not any("三等奖" in f.fact_text for f in build.ledger.facts if f.experience_id == "EXP-002")
    assert any("82条报名记录可能包含重复报名" in c.text for c in build.ledger.withheld_claims)


def test_layout_option_preserves_source_but_legacy_unit_splitting_is_unchanged():
    text = "团队获\n得三等奖。\n- 完成12条测试。"
    old = split_semantic_units(text)
    assert [u[0] for u in old][:2] == ["团队获", "得三等奖"]
    scoped = split_semantic_units(text, 7, preserve_layout=True)
    assert scoped[0][0] == "团队获\n得三等奖"
    assert len(scoped) == 2
    for value, start, end in scoped:
        assert text[start - 7:end - 7] == value


def test_build_and_views_are_repeatable_for_corrected_input():
    raw = project_input() + "\n团队获得三等奖，我没有负责预测模型设计。"
    first = build_canonical_semantic_build(raw)
    before = deepcopy(first)
    views = build_canonical_consumer_views(first)
    one = evidence(build_generation_prompt(request_for(raw), consumer_views=views))
    two = evidence(build_generation_prompt(request_for(raw), consumer_views=views))
    assert one == two
    assert first == before == build_canonical_semantic_build(raw)


def test_long_inline_body_is_not_limited_by_heading_name_length():
    body = "使用Python记录测试结果。" * 10
    raw = "项目一：评测记录工具。" + body
    boundary, = find_explicit_experience_boundaries(raw)
    assert boundary.title == "评测记录工具"
    assert raw[boundary.body_start_offset:] == body
    identity, = build_canonical_semantic_build(raw).identities
    assert identity.raw_text == body


def test_inline_body_date_cannot_veto_confirmed_heading_after_background():
    body = "2024年3月至2024年6月，使用Python记录8条测试结果。"
    raw = "基本信息：本科在读。\n项目一：文档问答助手。" + body + "\n技能：Python。"
    identity, = build_canonical_semantic_build(raw).identities
    assert identity.raw_text == raw[slice(*identity.source_span)] == body
