"""Current-code replays of exact inputs, not historical model responses."""
from copy import deepcopy
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
from app.services.experience_type_resolution_service import resolve_identity_type
from app.services.input_claim_resolution_service import resolve_experience_claims
from app.services.prompt_service import build_generation_prompt
from test_v0916_canonical_model_evidence import capture_generation, evidence, request_for, MULTI_TYPE
from test_v09174_fact_reference_composition import isolated
from test_v09175_post_processing_evidence import trace_delivery, assert_complete
from docx import Document

REQUESTS = json.loads((ROOT / "tests/fixtures/v09162_request_inputs.json").read_text(encoding="utf-8"))["requests"]
REQUEST_225 = next(row["raw_input"] for row in REQUESTS if row["result_id"] == 225)
COURSE = (ROOT / "tests/fixtures/v091741_course_projects_input.txt").read_text(encoding="utf-8")


def compact(text):
    return re.sub(r"\s+", "", text)


def source_assertions(raw, build):
    for identity in build.identities:
        assert raw[slice(*identity.source_span)] == identity.raw_text
    for claim in build.ledger.claims:
        assert compact(raw[slice(*claim.source_span)]) == compact(claim.text)
        identity = next(i for i in build.identities if i.experience_id == claim.source_experience_id)
        assert identity.source_span[0] <= claim.source_span[0] < claim.source_span[1] <= identity.source_span[1]
    claims = {c.claim_id: c for c in build.ledger.claims}
    for fact in build.ledger.facts:
        claim = claims[fact.claim_id]
        assert claim.eligibility == "eligible"
        assert fact.experience_id == claim.source_experience_id
        assert compact(raw[slice(*fact.source_span)]) == compact(fact.fact_text)


def test_exact_request_225_plan_is_not_a_completed_fact():
    build = build_canonical_semantic_build(REQUEST_225)
    assert len(build.identities) == 2
    plan, = [c for c in build.ledger.claims if c.text == "后续计划研究多语言标题处理"]
    assert (plan.source_span, plan.source_experience_id) == ((475, 488), "EXP-002")
    assert (plan.temporal_status, plan.eligibility, plan.exclusion_reason) == ("planned", "withheld", "planned_work")
    assert not any(f.claim_id == plan.claim_id for f in build.ledger.facts)
    assert len(build.ledger.facts) == 11
    assert any("固定返回前5条" in f.fact_text and f.experience_id == "EXP-001" for f in build.ledger.facts)
    assert any("补充9条自动化测试" in f.fact_text and f.experience_id == "EXP-002" for f in build.ledger.facts)
    assert any("尚未实现" in c.text for c in build.ledger.excluded_claims)
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == ["科研经历", "开源经历"]
    source_assertions(REQUEST_225, build)


@pytest.mark.parametrize("separator", ["", "\n", "\n\n", "\r\n"])
@pytest.mark.parametrize("plan", ["后续计划研究多语言标题处理", "我计划研究检索方法", "计划研究检索方法", "准备参与课题研究", "打算在实验室参与课题研究", "希望参与课题研究", "拟参与课题研究", "想要参与课题研究"])
def test_independent_completed_and_prospective_claims(plan, separator):
    raw = "使用Python完成接口测试，" + separator + plan + "。"
    resolution = resolve_experience_claims("EXP-007", raw, 19)
    assert [c.text for c in resolution.eligible_claims] == ["使用Python完成接口测试"]
    pending, = resolution.withheld_claims
    assert pending.text == plan and pending.temporal_status == "planned"
    for claim in resolution.claims:
        assert raw[claim.source_span[0] - 19:claim.source_span[1] - 19] == claim.text
        assert claim.source_experience_id == "EXP-007"


@pytest.mark.parametrize("text", [
    "开发计划管理系统，完成任务登记功能。",
    "计划管理系统已完成开发。",
    "计划管理系统支持任务登记。",
    "希望小学的学生参加活动。",
    "使用Python生成项目计划。",
    "我负责准备实验材料。",
    "我准备了实验材料。",
    "准备过实验记录。",
    "拟合回归模型并记录误差。",
    "完成课题研究的实验记录。",
])
def test_planning_objects_and_completed_work_remain_facts(text):
    resolution = resolve_experience_claims("EXP-001", text)
    assert resolution.eligible_claims and not resolution.withheld_claims and not resolution.excluded_claims


@pytest.mark.parametrize("text", [
    "计划开发工具用于实验记录。", "准备开发系统支持资料查询。",
    "计划开发一个平台，支持任务登记。",
])
def test_prospective_product_purpose_is_not_an_asserted_noun_subject(text):
    resolution = resolve_experience_claims("EXP-001", text)
    assert not resolution.eligible_claims
    assert resolution.withheld_claims


@pytest.mark.parametrize("limitation", ["我可能参与课题研究", "团队也许参与课题研究", "我没有参与课题研究"])
def test_independent_subject_limitation_does_not_disqualify_completed_work(limitation):
    text = "完成接口测试，" + limitation + "。"
    resolution = resolve_experience_claims("EXP-001", text)
    assert [c.text for c in resolution.eligible_claims] == ["完成接口测试"]
    assert [c.text for c in resolution.claims][1:] == [limitation]


@pytest.mark.parametrize("text,forbidden", [
    ("可能完成检索实验。", "完成检索实验"),
    ("不是获奖，而是入围。", "获奖"),
    ("82条报名记录，其中可能包含重复报名。", "82"),
    ("请写成参与课题研究。", "参与课题研究"),
    ("没有参与课题研究。", "参与课题研究"),
])
def test_restrictions_are_not_upgraded(text, forbidden):
    resolution = resolve_experience_claims("EXP-001", text)
    assert not any(forbidden in c.text for c in resolution.eligible_claims)
    assert resolution.excluded_claims or resolution.withheld_claims


def test_partial_responsibility_keeps_its_qualifier():
    resolution = resolve_experience_claims("EXP-001", "并非独立完成，只负责页面。")
    assert [c.text for c in resolution.eligible_claims] == ["只负责页面"]
    assert [c.text for c in resolution.excluded_claims] == ["并非独立完成"]


@pytest.mark.parametrize("raw", [COURSE, COURSE.replace("\n", "\r\n"), COURSE.replace("\n", "\n\n"), COURSE.replace("。", "。\n")], ids=["original", "crlf", "blank", "sentences"])
def test_exact_course_input_has_two_project_owners_without_research_relation(raw):
    build = build_canonical_semantic_build(raw)
    assert [i.experience_id for i in build.identities] == ["EXP-001", "EXP-002"]
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == ["项目经历", "项目经历"]
    assert len(build.ledger.facts) == 10
    for identity, claims in zip(build.identities, build.claim_resolutions):
        result = resolve_identity_type(identity, claims)
        assert result.evidence_scores["科研经历"] == 0
        assert result.evidence_scores["项目经历"] > 0
    first = [f.fact_text for f in build.ledger.facts if f.experience_id == "EXP-001"]
    second = [f.fact_text for f in build.ledger.facts if f.experience_id == "EXP-002"]
    assert any("45份" in t for t in first) and not any("45份" in t for t in second)
    assert any("只在本地演示" in t for t in second)
    source_assertions(raw, build)


@pytest.mark.parametrize("body,expected", [
    ("为实验室开发设备登记系统，负责接口联调。", "项目经历"),
    ("开发课题管理系统，负责查询页面。", "项目经历"),
    ("参与课题管理系统开发，负责查询页面。", "项目经历"),
    ("参与课题研究管理系统开发，负责查询页面。", "项目经历"),
    ("在实验室参与设备登记系统开发，负责接口联调。", "项目经历"),
    ("在实验室负责开发研究平台，完成接口测试。", "项目经历"),
    ("在课题组参与图像检索课题研究，负责实验记录。", "科研经历"),
    ("在语音实验室参与声学算法研究，负责实验记录。", "科研经历"),
    ("参与智能问答课题组研究，完成实验设计和记录。", "科研经历"),
    ("参与课程问答检索课题，负责实验记录。", "科研经历"),
    ("参与语音识别课题研究，独立开发实验记录系统，持续迭代并开展用户测试。", "科研经历"),
])
def test_research_task_relation_not_an_organization_or_product_word(body, expected):
    raw = "个人项目：记录工具\n" + body
    build = build_canonical_semantic_build(raw)
    assert len(build.identities) == 1
    assert build.experience_type_decisions[0].canonical_experience_type == expected
    source_assertions(raw, build)


def test_explicit_type_still_has_priority_over_research_relations():
    raw = "项目经历：研究记录工具\n参与检索课题研究，开发实验记录系统。"
    build = build_canonical_semantic_build(raw)
    assert build.experience_type_decisions[0].canonical_experience_type == "项目经历"
    assert build.experience_type_decisions[0].type_source == "declared_experience_type"


@pytest.mark.parametrize("plan", ["计划参与课题研究", "我计划参与课题研究", "后续计划参与课题研究", "准备参与课题研究"])
def test_type_only_consumes_qualified_claims_and_cannot_borrow_another_owner(plan):
    raw = "项目一：记录工具\n完成文件整理，" + plan + "。\n科研经历：检索研究\n参与检索课题研究。"
    build = build_canonical_semantic_build(raw)
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == ["项目经历", "科研经历"]
    first = build.claim_resolutions[0]
    assert any(c.temporal_status == "planned" for c in first.withheld_claims)
    assert all("课题研究" not in c.text for c in first.eligible_claims)
    identity = replace(build.identities[0], title="科研经历", experience_type="科研经历")
    assert resolve_identity_type(identity, first).resolved_type == "项目经历"


@pytest.mark.parametrize("raw", [COURSE, REQUEST_225], ids=["course", "request225"])
def test_build_views_and_prompt_are_repeatable_and_preserve_local_sources(raw):
    build = build_canonical_semantic_build(raw)
    before = deepcopy(build)
    views = build_canonical_consumer_views(build)
    views_before = repr(views)
    one = evidence(build_generation_prompt(request_for(raw), consumer_views=views))
    two = evidence(build_generation_prompt(request_for(raw), consumer_views=views))
    assert one == two and build == before and repr(views) == views_before
    assert build == build_canonical_semantic_build(raw)
    for owner in one["owners"]:
        for fact in owner["eligible_facts"]:
            assert fact["source_experience_id"] == owner["source_experience_id"]
            assert compact(raw[slice(*fact["claim_source_span"])]) == compact(fact["source_claim_text"])
    if raw == REQUEST_225:
        assert not any("后续计划研究" in f["source_claim_text"] for o in one["owners"] for f in o["eligible_facts"])
        assert any(c["text"] == "后续计划研究多语言标题处理" for c in one["internal_constraints_not_resume_facts"])


@pytest.mark.parametrize("raw", [COURSE, REQUEST_225], ids=["course", "request225"])
def test_real_generation_prepares_corrected_frozen_evidence(raw, monkeypatch, tmp_path):
    captured = capture_generation(raw, monkeypatch, tmp_path, forbid_rebuild=True)
    data = evidence(captured["prompt"])
    assert captured["build"] == captured["before"]
    assert sum(len(o["eligible_facts"]) for o in data["owners"]) == (10 if raw == COURSE else 11)
    assert all("后续计划研究" not in f["source_claim_text"] for o in data["owners"] for f in o["eligible_facts"])


@pytest.mark.parametrize("name", list(MULTI_TYPE))
def test_existing_multitype_inputs_keep_boundaries_and_local_sources(name):
    raw = MULTI_TYPE[name]
    build = build_canonical_semantic_build(raw)
    expected = {
        "research_course": ["科研经历", "项目经历"],
        "opensource_personal": ["开源经历", "项目经历"],
        "competition_campus": ["竞赛经历", "校园 / 社团经历"],
    }
    assert [d.canonical_experience_type for d in build.experience_type_decisions] == expected[name]
    source_assertions(raw, build)


@pytest.mark.parametrize("raw", [COURSE, REQUEST_225], ids=["course", "request225"])
def test_corrected_evidence_survives_real_delivery_and_docx(raw, monkeypatch, tmp_path, isolated):
    build, captured, snapshots = trace_delivery(raw, "detail", monkeypatch, tmp_path)
    for name, stage, projects in snapshots:
        try:
            assert_complete(projects, build)
        except AssertionError as exc:
            pytest.fail(f"First evidence change: {name}/{stage}: {exc}")
    saved = captured["saved"]["resume_sections"]["projects"]
    assert_complete(saved, build)
    assert {p["source_experience_id"]: p["meta"] for p in saved} == {
        d.experience_id: d.canonical_experience_type for d in build.experience_type_decisions
    }
    rendered = "\n".join(p.text for path in tmp_path.glob("*.docx") for p in Document(path).paragraphs)
    for fact in build.ledger.facts:
        assert fact.resume_ready_text.rstrip("。；;") in rendered
    if raw == REQUEST_225:
        assert "后续计划研究多语言标题处理" not in "\n".join(
            str(p.get(field, "")) for p in saved for field in ("intro", "role", "details")
        )
