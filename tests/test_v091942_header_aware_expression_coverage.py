"""Frozen header evidence can contribute to owner Fact display coverage."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from app.services import experience_slot_service as slots
from app.services.prompt_service import build_expression_review_prompt
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from test_v09174_fact_reference_composition import isolated
from test_v091941_expression_unit_coverage import full_reply
from test_v09172_initial_evidence_preservation import detail_return
from test_v09176_delivery_closure import deliver


RAW = """基本信息：
软件工程专业本科在读，想申请前端开发实习。

课程项目：课程展示网站
2026年5月，我和两位同学一起制作课程展示网站。
我使用 Vue 完成课程列表、课程详情和搜索框页面，按照同学提供的接口展示查询结果。
我还帮忙测试了空搜索结果和较长课程名称的页面显示，发现的问题交给负责接口的同学处理。
项目用于课程结课展示，展示后没有继续运营。

技能：
会使用 Vue 和 Git，接触过基础的接口联调。"""


def prepared():
    build = build_canonical_semantic_build(RAW)
    views = build_canonical_consumer_views(build)
    facts = views.facts_for_owner("EXP-001")
    assert len(facts) == 4
    header = views.planner_view.experience_header_decision_for_owner("EXP-001")
    assert header.field("name").qualified and header.field("time").qualified
    assert RAW[slice(*header.field("time").source_span)] == "2026年5月"
    assert facts[0].source_span[0] <= header.field("time").source_span[0]
    assert header.field("time").source_span[1] <= facts[0].source_span[1]
    assert not (facts[3].source_span[0] <= header.field("time").source_span[0]
                < facts[3].source_span[1])
    units = [{"fact_ids": [fact.fact_id], "position": "detail", "text": text}
             for fact, text in zip(facts, (
                 "我和两位同学一起制作课程展示网站",
                 "使用 Vue 完成课程列表、课程详情和搜索框页面，按照同学提供的接口展示查询结果",
                 "协助测试空搜索结果和较长课程名称的页面显示，将发现的问题交给负责接口的同学处理",
                 "项目用于课程结课展示，展示后没有继续运营",
             ), strict=True)]
    body = {"resume_sections": {"projects": [
        {"source_experience_id": "EXP-001", "expression_units": units}
    ]}}
    review = slots.CanonicalExpressionReview(build, views.build_fingerprint)
    composed = slots.compose_model_fact_references(body, views, expression_review=review)
    return build, views, facts, review, composed


def coverage_prompt(review, views):
    text = build_expression_review_prompt(review, views)
    return json.loads(text.split("<fact_coverage>\n", 1)[1].split("\n</fact_coverage>", 1)[0])


def test_only_exact_delivered_header_spans_enter_coverage(isolated):
    _, views, facts, review, composed = prepared()
    coverage = coverage_prompt(review, views)
    first = coverage[facts[0].fact_id]
    assert [(row["field_key"], row["source_span"], row["source_text"])
            for row in first["delivered_header_evidence"]] == [
        ("name", list(views.planner_view.experience_header_decision_for_owner("EXP-001").field("name").source_span), "课程展示网站"),
        ("time", list(views.planner_view.experience_header_decision_for_owner("EXP-001").field("time").source_span), "2026年5月"),
    ]
    assert coverage[facts[3].fact_id]["delivered_header_evidence"] == []
    reply = full_reply(review)
    review.accept(reply)
    slots.validate_model_project_evidence(composed, views, expression_review=review,
                                          require_complete=True, write_log=False)


def test_header_change_invalidates_coverage_receipt(isolated):
    _, views, _, review, composed = prepared()
    review.accept(full_reply(review))
    changed = deepcopy(composed)
    changed["resume_sections"]["projects"][0]["time"] = "时间：【待填写】"
    with pytest.raises(slots.ModelEvidenceContractError):
        slots.validate_model_project_evidence(changed, views, expression_review=review,
                                              require_complete=True, write_log=False)


def test_f004_omission_and_unit_overclaim_still_rejected(isolated):
    _, _, facts, review, _ = prepared()
    reply = full_reply(review)
    reply["coverage"][facts[3].fact_id].update(
        verdict="omitted", source_excerpt="展示后没有继续运营")
    with pytest.raises(slots.ModelEvidenceContractError) as caught:
        review.accept(reply)
    assert caught.value.reason_counts == {"expression_review_coverage_omitted": 1}
    reply = full_reply(review)
    key = next(iter(review.pending))
    reply["decisions"][key].update(verdict="added_claim", candidate_excerpt="一起制作")
    with pytest.raises(slots.ModelEvidenceContractError):
        review.accept(reply)


def test_pending_header_cannot_contribute_to_coverage(isolated):
    build, _, facts, _, _ = prepared()
    header = build.experience_header_decisions[0]
    pending_time = replace(header.field("time"), status="pending")
    changed_header = replace(header, fields=tuple(
        pending_time if field.field_key == "time" else field for field in header.fields
    ))
    changed_build = replace(build, experience_header_decisions=(changed_header,))
    views = build_canonical_consumer_views(changed_build)
    units = [{"fact_ids": [fact.fact_id], "position": "detail", "text": fact.resume_ready_text}
             for fact in facts]
    units[0]["text"] = "我和两位同学一起制作课程展示网站"
    body = {"resume_sections": {"projects": [
        {"source_experience_id": "EXP-001", "expression_units": units}
    ]}}
    review = slots.CanonicalExpressionReview(changed_build, views.build_fingerprint)
    slots.compose_model_fact_references(body, views, expression_review=review)
    evidence = coverage_prompt(review, views)[facts[0].fact_id]["delivered_header_evidence"]
    assert [row["field_key"] for row in evidence] == ["name"]


def test_controlled_receipt_reaches_save_and_docx(monkeypatch, tmp_path, isolated):
    build, views, facts, review, _ = prepared()
    case, actual_build, response = detail_return(RAW)
    assert [f.resume_ready_text for f in actual_build.ledger.facts] == [
        f.resume_ready_text for f in build.ledger.facts
    ]
    response["resume_sections"]["projects"] = [{
        "source_experience_id": "EXP-001", "expression_units": [
            {"fact_ids": [fact.fact_id], "position": "detail", "text": text}
            for fact, text in zip(facts, (
                "我和两位同学一起制作课程展示网站",
                "使用 Vue 完成课程列表、课程详情和搜索框页面，按照同学提供的接口展示查询结果",
                "协助测试空搜索结果和较长课程名称的页面显示，将发现的问题交给负责接口的同学处理",
                "项目用于课程结课展示，展示后没有继续运营",
            ), strict=True)
        ],
    }]
    outcome = deliver(monkeypatch, tmp_path, case, [
        (json.dumps(response, ensure_ascii=False), "stop"),
        (json.dumps(full_reply(review), ensure_ascii=False), "stop"),
    ])
    assert outcome["results"] == 1 and "docx" in outcome, outcome
    assert len(outcome["sent"]) == 2
    project = outcome["saved"]["resume_sections"]["projects"][0]
    assert project["time"] == "时间：2026年5月"
    assert {tuple(ids) for ids in project["detail_fact_ids"]} == {
        (f.fact_id,) for f in facts
    }
    expected = {f.fact_id: f.claim_id for f in facts}
    for text, ids, claims in zip(project["details"], project["detail_fact_ids"],
                                  project["detail_claim_ids"], strict=True):
        assert len(ids) == 1 and claims == [expected[ids[0]]]
        if ids[0] == facts[0].fact_id:
            assert "我和两位同学一起制作课程展示网站" in text
            assert "2026年5月" not in text
        if ids[0] == facts[3].fact_id:
            assert "展示后没有继续运营" in text
    sent_coverage = json.loads(outcome["sent"][1]["messages"][1]["content"].split(
        "<fact_coverage>\n", 1)[1].split("\n</fact_coverage>", 1)[0])
    assert sent_coverage[facts[0].fact_id]["delivered_header_evidence"]
    assert not sent_coverage[facts[3].fact_id]["delivered_header_evidence"]
