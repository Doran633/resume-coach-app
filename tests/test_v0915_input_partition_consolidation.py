"""Current-code replays, not snapshots of historical production requests."""
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.experience_segmentation_service import split_experience_segments
from app.services.experience_identity_service import build_experience_identities
from app.services import long_input_service as long_input
from app.services import semantic_experience_segmentation_service as segmentation


@pytest.mark.parametrize("heading", ["前端开发实习", "后端开发实习", "产品运营实习", "开发工程师实习"])
@pytest.mark.parametrize("separator", ["：", "\n", "：\r\n"])
def test_internship_after_background_is_not_swallowed(heading, separator):
    raw = ("基本信息" + separator + "本科在读。\n" + heading + separator
           + "在星河软件公司担任实习生，修复12个页面问题。\n"
           + "课程项目" + separator + "开发预约平台。\n技能" + separator + "使用Excel。")
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 2
    assert "修复12个页面" in build.identities[0].raw_text
    assert "预约平台" in build.identities[1].raw_text
    for identity in build.identities:
        assert raw[slice(*identity.source_span)] == identity.raw_text
        assert "本科在读" not in identity.raw_text and "Excel" not in identity.raw_text
    assert any("12" in f.fact_text and f.experience_id == "EXP-001" for f in build.ledger.facts)


def test_all_recognized_experiences_reach_identity():
    raw = "\n".join(f"项目{i}：系统{i}\n完成第{i}项接口开发。" for i in range(1, 10))
    assert len(segmentation.segment_semantic_experiences(raw).segments) == 9
    assert len(split_experience_segments(raw)) == 9
    assert len(build_experience_identities(raw)) == 9


def test_cross_project_reference_stays_in_original_section():
    raw = ("项目一：图书预约平台\n使用Python完成预约接口。\n"
           "项目二：活动通知系统\n使用React完成通知页面。\n\n"
           "与图书预约平台对接完成通知接口。")
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 2
    assert "对接" not in build.identities[0].raw_text
    assert "对接" in build.identities[1].raw_text
    assert all(f.experience_id == "EXP-002" for f in build.ledger.facts if "对接" in f.fact_text)
    for identity in build.identities:
        assert raw[slice(*identity.source_span)] == identity.raw_text
    assert not segmentation.segment_semantic_experiences(raw).ambiguous_source_spans


def test_inline_body_is_not_a_heading_only_residue():
    raw = "课程项目：图书平台｜个人项目，负责接口开发"
    identities = build_experience_identities(raw)
    assert len(identities) == 1
    assert "负责接口开发" in identities[0].raw_text


@pytest.mark.parametrize("raw", [
    "我是本科学生。我开发了图书预约平台。完成预约接口。",
    "  项目一：图书平台\n\n完成接口开发。\n",
    "我开发了图书预约平台。\n\n完成预约接口。",
])
def test_original_source_ranges_are_not_reconstructed_offsets(raw):
    build = build_canonical_semantic_build(raw)
    assert build.identities
    for identity in build.identities:
        assert raw[slice(*identity.source_span)] == identity.raw_text
        assert "我是本科学生" not in identity.raw_text
    for fact in build.ledger.facts:
        assert raw[slice(*fact.source_span)].strip("。；;，, \n") == fact.fact_text


def test_long_input_observation_reuses_partition(monkeypatch):
    calls = []
    original = segmentation.segment_semantic_experiences
    def counted(*args, **kwargs):
        calls.append(args[0])
        return original(*args, **kwargs)
    monkeypatch.setattr(segmentation, "segment_semantic_experiences", counted)
    monkeypatch.setattr(segmentation, "write_segmentation_log", lambda *a, **k: None)
    # The adapter import is also counted, without replacing actual partitioning.
    from app.services import experience_segmentation_service as adapter
    monkeypatch.setattr(adapter, "segment_semantic_experiences", counted)
    raw = "课程项目：开发图书预约平台。完成预约接口。"
    context = long_input.analyze_long_input(raw, write_segmentation_log=True)
    build_experience_identities(raw, long_input_context=context)
    assert calls == [raw]


@pytest.mark.parametrize("label", ["希望申请前端开发实习", "没有实习", "目标岗位为实习", "负责开发项目"])
def test_intent_negation_and_action_are_not_experience_headings(label):
    assert segmentation.input_section_kind(label) != "labeled_experience"


def test_explicit_legacy_limit_reports_instead_of_returning_partial_data():
    raw = "项目一：平台甲\n完成接口。\n项目二：平台乙\n完成页面。"
    with pytest.raises(ValueError, match="explicit segment limit"):
        split_experience_segments(raw, max_segments=1)
    assert len(split_experience_segments(raw, max_segments=2)) == 2


@pytest.mark.parametrize("raw", ["课程项目\n", "前端开发实习：", "## 图书平台｜个人项目"])
def test_heading_without_body_does_not_create_owner(raw):
    assert build_experience_identities(raw) == []


def test_identity_does_not_reapply_heading_filter_to_an_existing_partition():
    raw = "图书平台｜个人项目，负责接口开发"
    context = long_input.analyze_long_input("课程项目：" + raw)
    # An existing caller-supplied partition is authoritative at this boundary.
    context.segments[0].content = raw
    context.segments[0].source_span = (0, len(raw))
    identities = build_experience_identities(raw, long_input_context=context)
    assert len(identities) == 1
    assert identities[0].raw_text == raw


def test_full_ecommerce_and_ae_keep_real_build_scopes():
    # Reuse the exact versioned fixtures, including full original input.
    from test_v09141_structured_experience_boundary import SAMPLES, FULL, assert_scopes, signature, formatted
    for key, raw in {**SAMPLES, "FULL": FULL}.items():
        original = build_canonical_semantic_build(raw)
        count = 1 if key == "E" else 3
        assert_scopes(raw, original, count)
        for style in ("heading_lines", "sentences", "inside_sentence", "crlf"):
            variant = formatted(raw, style)
            build = build_canonical_semantic_build(variant)
            assert_scopes(variant, build, count)
            assert signature(build) == signature(original)


def test_background_is_retained_in_request_context_not_experience_scope():
    raw = "基本信息：本科在读。课程项目：完成预约页面。技能：使用Excel。"
    context = long_input.analyze_long_input(raw)
    assert context.raw_input_for_prompt == raw
    identities = build_experience_identities(raw, long_input_context=context)
    assert len(identities) == 1
    assert "本科" not in identities[0].raw_text and "Excel" not in identities[0].raw_text


@pytest.mark.parametrize("separator", ["\n\n", "\r\n\r\n"])
def test_conflicting_named_self_introduction_is_pending_not_moved(separator):
    raw = ("项目一：预约平台\n开发预约接口。\n项目二：通知系统\n完成通知页面。"
           + separator + "我做过一个预约平台，完成预约统计。")
    partition = segmentation.segment_semantic_experiences(raw)
    assert len(partition.segments) == 2
    assert len(partition.ambiguous_source_spans) == 1
    assert "我做过一个预约平台" in raw[slice(*partition.ambiguous_source_spans[0])]
    assert all("预约统计" not in s.raw_text for s in partition.segments)
    assert partition.clarification_questions
    assert all(raw[s.start_offset:s.end_offset] == s.raw_text for s in partition.segments)


def test_legacy_explicit_title_retains_position_without_changing_claim_eligibility():
    from app.services.input_claim_resolution_service import resolve_experience_claims
    from app.services.resume_title_format_service import resolve_resume_titles
    from app import schemas
    import json
    case = json.loads((ROOT / "tests/fixtures/golden_resume_cases.json").read_text(encoding="utf-8"))[0]
    payload = schemas.GenerationPayload.model_validate(case["fixed_payload"])
    payload.resume_sections.projects = [{
        "name": "某科技公司", "position": "[待填写]", "meta": "实习经历",
        "time": "[待填写]", "intro": "参与模块测试", "role": "", "details": [],
        "source_experience_id": "EXP-001",
    }]
    raw = "实习经历｜某科技公司 AI Agent 开发实习\n参与模块测试。"
    before = payload.model_dump()
    result = resolve_resume_titles(payload, raw)
    assert result.resume_sections.projects[0]["position"] == "AI Agent 开发实习"
    assert payload.model_dump() == before
    title_claim = resolve_experience_claims("EXP-001", "某科技公司 AI Agent 开发实习").claims[0]
    assert title_claim.eligibility == "excluded"


def test_context_gap_is_not_a_new_experience_anchor():
    raw = "我开发了预约平台。希望更适合后端岗位。完成接口测试。"
    partition = segmentation.segment_semantic_experiences(raw)
    assert len(partition.segments) == 1
    assert "希望" not in partition.segments[0].raw_text
    assert partition.clarification_questions
    assert "完成接口测试" == raw[slice(*partition.ambiguous_source_spans[0])]
