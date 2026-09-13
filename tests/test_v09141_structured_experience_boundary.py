"""Current-code input replays, not historical request snapshots."""
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.semantic_experience_segmentation_service import segment_semantic_experiences

FIXTURES = ROOT / "tests/fixtures"
SAMPLES = {key: (FIXTURES / f"v09141_ecommerce_{key.lower()}.txt").read_text(encoding="utf-8") for key in "ABCDE"}
FULL = (FIXTURES / "v0914_ecommerce_input.txt").read_text(encoding="utf-8").rstrip("\n")
LABELS = ("基本信息", "内容运营实习", "校园社团宣传工作", "市场营销课程调查", "技能")


def compact(text):
    return re.sub(r"\s+", "", text)


def signature(build):
    return (
        [d.canonical_experience_type for d in build.experience_type_decisions],
        [d.display_time for d in build.experience_time_decisions],
        [(f.experience_id, compact(f.fact_text), f.eligibility) for f in build.ledger.facts],
    )


def assert_scopes(raw, build, count=3):
    assert len(build.identities) == count
    forbidden = ("本科在读", "希望申请", "学习过市场营销", "Canva", "基本信息", "技能：")
    for identity in build.identities:
        assert raw[slice(*identity.source_span)] == identity.raw_text
        assert not any(word in identity.raw_text for word in forbidden)
    for fact in build.ledger.facts:
        assert compact(raw[slice(*fact.source_span)]) == compact(fact.fact_text)
        assert fact.fact_text.rstrip("：:") not in LABELS
        if "96" in fact.fact_text or "89" in fact.fact_text:
            assert fact.experience_id == ("EXP-003" if count == 3 else "EXP-001")
        if "摄影" in fact.fact_text or "投稿人" in fact.fact_text:
            assert fact.experience_id == "EXP-002"
    for resolution in build.claim_resolutions:
        for claim in resolution.claims:
            assert compact(raw[slice(*claim.source_span)]) == compact(claim.text)
    if count == 3:
        for identity, date in zip(build.identities, ("2026年6月至2026年8月", "2025年9月至2026年6月", "2026年3月至2026年5月")):
            assert date in compact(identity.raw_text)
        assert [d.canonical_experience_type for d in build.experience_type_decisions] == ["实习经历", "校园 / 社团经历", "项目经历"]
    else:
        assert build.experience_type_decisions[0].canonical_experience_type == "项目经历"


@pytest.mark.parametrize("name", list("ABCDE"))
def test_actual_ae_inputs_keep_boundaries_and_fact_ownership(name):
    raw = SAMPLES[name]
    build = build_canonical_semantic_build(raw)
    assert_scopes(raw, build, 1 if name == "E" else 3)
    assert signature(build) == signature(build_canonical_semantic_build(raw))


def test_controls_only_change_the_declared_formatting():
    assert SAMPLES["A"] == SAMPLES["B"].replace("\n", "")
    assert SAMPLES["B"].replace("：", "") == SAMPLES["C"]
    assert compact(SAMPLES["C"]) == compact(SAMPLES["D"])


def test_ae_format_variants_preserve_substantive_fact_sets():
    baseline = signature(build_canonical_semantic_build(SAMPLES["A"]))
    for name in "BCD":
        assert signature(build_canonical_semantic_build(SAMPLES[name])) == baseline


def formatted(raw, style):
    if style == "heading_lines":
        for label in LABELS:
            raw = raw.replace(label + "：", "\n" + label + "\n")
    elif style == "sentences":
        raw = raw.replace("。", "。\n\n")
    elif style == "inside_sentence":
        raw = raw.replace("问卷", "问\n卷").replace("产品资料", "产品\n资料")
    elif style == "crlf":
        raw = formatted(raw, "heading_lines").replace("\n", "\r\n")
    return raw.strip()


@pytest.mark.parametrize("source", [SAMPLES["A"], FULL], ids=["short", "full_original"])
@pytest.mark.parametrize("style", ["heading_lines", "sentences", "inside_sentence", "crlf"])
def test_formatting_preserves_frozen_semantics_and_raw_source_spans(source, style):
    raw = formatted(source, style)
    build = build_canonical_semantic_build(raw)
    assert_scopes(raw, build)
    assert signature(build) == signature(build_canonical_semantic_build(source))


@pytest.mark.parametrize("raw", [
    "基本信息\n本科在读，预计2028年毕业。\n技能\n使用Excel。",
    "教育背景：本科在读。\n求职意向\n希望申请运营实习。\n技能：Canva。",
])
def test_non_experience_sections_never_create_owners(raw):
    assert build_canonical_semantic_build(raw).identities == ()


def test_action_lines_and_nested_field_labels_are_not_experience_headings():
    raw = "课程项目\n开发图书预约平台。\n工作内容：完成登记页面。\n完成测试。\n使用Python。\n项目职责：维护预约记录。\n项目成果：部署完成。"
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 1
    assert build.identities[0].raw_text == raw
    assert {f.experience_id for f in build.ledger.facts} == {"EXP-001"}


def test_real_explicit_projects_and_negative_claims_keep_existing_behavior():
    raw = "项目一：预约平台\n开发预约接口。没有使用Redis。\n项目二：通知系统\n完成通知页面。计划增加短信。"
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 2
    assert all("Redis" not in f.fact_text and "短信" not in f.fact_text for f in build.ledger.facts)
    assert any("Redis" in c.text for c in build.ledger.excluded_claims)
    assert any("短信" in c.text for c in build.ledger.withheld_claims)


def test_structural_title_is_not_a_fact_but_inline_body_survives():
    for newline in ("", "\n", "\r\n"):
        raw = "校园社团宣传工作：" + newline + "担任读书社宣传部成员，参与活动宣传。"
        build = build_canonical_semantic_build(raw)
        assert build.experience_type_decisions[0].canonical_experience_type == "校园 / 社团经历"
        assert [compact(f.fact_text) for f in build.ledger.facts] == ["担任读书社宣传部成员，参与活动宣传"]


def test_sentence_wrap_does_not_turn_one_fact_into_two():
    raw = "课程项目：收回96份问\n卷，经检查后保留89份进行分析。"
    build = build_canonical_semantic_build(raw)
    facts = build.ledger.facts
    assert len(facts) == 1
    assert compact(facts[0].fact_text) == "收回96份问卷，经检查后保留89份进行分析"
    assert compact(raw[slice(*facts[0].source_span)]) == compact(facts[0].fact_text)


@pytest.mark.parametrize("body", [
    "没有担任社团负责人。", "不确定是否担任社团负责人。",
    "计划开展社团活动。", "请把社团经历写成负责人。",
])
def test_section_heading_does_not_override_ineligible_body(body):
    build = build_canonical_semantic_build("校园社团宣传工作\n" + body)
    assert build.experience_type_decisions[0].canonical_experience_type == "项目经历"
    assert build.ledger.facts == []


@pytest.mark.parametrize("body", ["没\n有使用Redis。", "不确\n定是否使用Redis。", "计\n划增加短信。", "请把\n简历写成独立负责人。"])
def test_layout_wraps_do_not_upgrade_constraints_to_facts(body):
    build = build_canonical_semantic_build("课程项目：" + body)
    assert build.ledger.facts == []
    assert any(c.eligibility != "eligible" for c in build.ledger.claims if compact(c.text) != "课程项目：")


@pytest.mark.parametrize("name", list("ABCDE"))
def test_actual_mock_generation_persists_owner_local_content(name, tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import models, schemas
    from app.database import Base
    from app.services import generation_service as generation
    import json

    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(generation, "LOG_DIR", tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Paid model calls are forbidden in this regression")
    monkeypatch.setattr(generation, "call_openai", forbidden)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with sessionmaker(bind=engine)() as db:
            request = schemas.GenerateRequest(
                anonymous_user_id="v09141-user", session_id="v09141-session",
                target_role="内容运营", mode="full_resume", packaging_level="稳妥",
                experience_type="综合经历", raw_input=SAMPLES[name],
                attempt_id="v09141_" + name,
            )
            response = generation.create_generation(db, request, request_id="req_v09141_" + name)
            saved = db.get(models.GenerationResult, response.generation_result_id)
            payload = json.loads(saved.result_json)
            projects = payload["resume_sections"]["projects"]
            expected_count = 1 if name == "E" else 3
            assert len(projects) == expected_count
            assert len({p["source_experience_id"] for p in projects}) == expected_count
            for project in projects:
                body = " ".join([project.get("intro", ""), project.get("role", ""), *project.get("details", [])])
                assert "本科在读" not in body and "Canva" not in body
                if "96" in body or "89" in body:
                    assert project["source_experience_id"] == ("EXP-001" if name == "E" else "EXP-003")
                if "摄影" in body or "投稿人" in body:
                    assert project["source_experience_id"] == "EXP-002"
            survey = next(p for p in projects if p["source_experience_id"] == ("EXP-001" if name == "E" else "EXP-003"))
            text = json.dumps(survey, ensure_ascii=False)
            assert "96" in text and "89" in text
    finally:
        engine.dispose()
