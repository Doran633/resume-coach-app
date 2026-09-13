from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.experience_segmentation_service import split_experience_segments
from app.services.semantic_experience_segmentation_service import segment_semantic_experiences

RAW = (ROOT / "tests/fixtures/v0914_ecommerce_input.txt").read_text(encoding="utf-8").rstrip("\n")
LABELS = ("内容运营实习：", "校园社团宣传工作：", "市场营销课程调查：", "技能：")
OWNERS = ("EXP-001", "EXP-002", "EXP-003")


def with_newlines(raw):
    for label in LABELS:
        raw = raw.replace(label, "\n\n" + label)
    return raw


@pytest.mark.parametrize("raw", [RAW, with_newlines(RAW), "\n  " + RAW + "  \n"], ids=["original", "newlines", "padding"])
def test_ecommerce_real_build_keeps_three_local_experiences(raw):
    before = raw
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 3
    assert tuple(i.experience_id for i in build.identities) == OWNERS
    for identity, heading, next_heading in zip(build.identities, LABELS, LABELS[1:]):
        start = raw.index(heading)
        end = raw.index(next_heading)
        expected = raw[start:end].strip()
        assert identity.raw_text == expected
        assert raw[slice(*identity.source_span)] == expected
    internship, club, survey = build.identities
    assert "2026年6月至2026年8月" in internship.raw_text
    assert "2025年9月至2026年6月" in club.raw_text
    assert "2026年3月至2026年5月" in survey.raw_text
    assert "96份问卷" in survey.raw_text and "89份" in survey.raw_text
    for fact in build.ledger.facts:
        text = fact.fact_text
        assert all(word not in text for word in ("本科在读", "希望申请", "学习过市场营销", "Canva", "剪映"))
        if "96" in text or "89" in text:
            assert fact.experience_id == "EXP-003"
        if "摄影" in text or "投稿人" in text:
            assert fact.experience_id == "EXP-002"
    for identity, resolution in zip(build.identities, build.claim_resolutions):
        for claim in resolution.claims:
            assert claim.experience_id == identity.experience_id
            assert identity.source_span[0] <= claim.source_span[0] <= claim.source_span[1] <= identity.source_span[1]
            assert raw[slice(*claim.source_span)] == claim.text
    assert raw == before
    assert "预计2028年毕业" in raw and "技能：" in raw


def test_only_newlines_change_neither_identity_content_nor_fact_ownership():
    def signature(raw):
        build = build_canonical_semantic_build(raw)
        return (
            [(i.experience_id, i.raw_text) for i in build.identities],
            [(f.experience_id, f.fact_text) for f in build.ledger.facts],
        )
    assert with_newlines(RAW).replace("\n", "") == RAW
    assert signature(RAW) == signature(with_newlines(RAW)) == signature(RAW)


@pytest.mark.parametrize("raw", [
    "基本信息：本科在读，预计2028年毕业。求职意向：希望申请运营实习。技能：能够使用Excel。",
    "教育背景：本科电子商务专业。课程背景：学习过统计学。专业技能：使用Python。",
])
def test_non_experience_sections_do_not_create_identities(raw):
    assert segment_semantic_experiences(raw).segments == []
    assert split_experience_segments(raw) == []
    assert build_canonical_semantic_build(raw).identities == ()


def test_section_tasks_and_nested_field_labels_do_not_create_owners():
    raw = "数据维护实习：2025年3月至2025年6月，在某公司实习。工作内容：整理数据。技术栈：Python。负责校验并上线，准确率达到90%。技能：Excel。"
    segments = split_experience_segments(raw)
    assert len(segments) == 1
    assert "工作内容：整理数据" in segments[0].content
    assert "技术栈：Python" in segments[0].content
    assert "90%" in segments[0].content
    assert "技能：Excel" not in segments[0].content


def test_explicit_headings_and_non_experience_switches_share_boundaries():
    raw = "教育经历：某大学本科。\n项目一：图书借阅管理系统\n完成借阅接口。\n技能：Python。\n项目二：实验预约平台\n完成预约测试。"
    segments = split_experience_segments(raw)
    assert len(segments) == 2
    assert "借阅接口" in segments[0].content
    assert "预约测试" in segments[1].content
    assert all("Python" not in s.content and "某大学" not in s.content for s in segments)


def test_short_course_and_club_blocks_do_not_merge_by_length():
    raw = "校园社团工作：参与读书会宣传。统计学课程项目：完成居民出行调查。"
    segments = split_experience_segments(raw)
    assert len(segments) == 2
    assert "读书会" in segments[0].content and "调查" not in segments[0].content
    assert "调查" in segments[1].content and "读书会" not in segments[1].content


@pytest.mark.parametrize("raw", [
    "实习经历：2025年3月至2025年6月，在某公司实习，负责数据整理。",
    "项目经历：开发预约平台，完成预约流程和测试。",
])
def test_short_inline_body_is_not_mistaken_for_a_heading_only(raw):
    segments = split_experience_segments(raw)
    assert len(segments) == 1
    assert segments[0].content == raw
    assert raw[slice(*segments[0].source_span)] == raw


def test_unlabeled_background_preamble_is_not_an_experience():
    raw = "本科在读，预计2028年毕业。希望申请运营实习。内容运营实习：在某公司实习，整理产品资料。"
    segments = split_experience_segments(raw)
    assert len(segments) == 1
    assert "本科" not in segments[0].content and "希望申请" not in segments[0].content
    assert "整理产品资料" in segments[0].content


def test_role_and_resume_field_colons_are_not_section_switches():
    raw = "课程项目：开发预约平台。项目职责：维护预约记录。项目成果：完成测试。项目名称：预约平台。"
    segments = split_experience_segments(raw)
    assert len(segments) == 1
    assert segments[0].content == raw
