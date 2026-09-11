"""Regression coverage for Canonical Experience Header Completeness Authority.

These cases are fixed current-code replays, not historical request snapshots.
"""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import canonical_semantic_state_service as header_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_project_projection_service import (  # noqa: E402
    append_canonical_project_projection_candidates,
    plan_canonical_project_projections,
)
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.resume_title_format_service import resolve_canonical_resume_titles  # noqa: E402


PENDING = "\u3010\u5f85\u586b\u5199\u3011"


def _empty_payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=0,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(),
    )


def _bound_payload(build) -> schemas.GenerationPayload:
    fact = build.ledger.facts[0]
    owner = fact.experience_id
    return schemas.GenerationPayload(
        completeness_score=0,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{
            "name": "legacy title",
            "meta": build.canonical_type_by_experience_id[owner],
            "time": "[\u5f85\u586b\u5199]",
            "position": "legacy position",
            "intro": fact.resume_ready_text,
            "role": "",
            "details": [],
            "source_experience_id": owner,
            "immutable_source_experience_id": owner,
            "source_binding_locked": True,
            "source_fact_ids": [fact.fact_id],
            "role_source_fact_ids": [],
            "detail_fact_ids": [],
            "source_claim_ids": [fact.claim_id],
            "role_source_claim_ids": [],
            "detail_claim_ids": [],
        }]),
    )


def _attachments(project: dict) -> dict:
    return {
        key: project.get(key)
        for key in (
            "source_fact_ids", "role_source_fact_ids", "detail_fact_ids",
            "source_claim_ids", "role_source_claim_ids", "detail_claim_ids",
        )
    }


def _header(raw: str, index: int = 0):
    return build_canonical_semantic_build(raw).experience_header_decisions[index]


def test_known_project_name_and_time_form_labeled_header_without_employment_fields():
    raw = (
        "\u9879\u76ee\u540d\u79f0\u660e\u786e\u4e3a\u5927\u5b66\u751f\u6d88\u8d39\u884c\u4e3a\u6570\u636e\u5206\u6790\u3002"
        "2024.03-2024.06 \u5b8c\u6210\u6570\u636e\u6e05\u6d17\u4e0e\u53ef\u89c6\u5316\u3002"
    )
    build = build_canonical_semantic_build(raw)
    views = build_canonical_consumer_views(build)
    resolved = resolve_canonical_resume_titles(_bound_payload(build), views.planner_view)
    project = resolved.resume_sections.projects[0]

    assert project["name"] == "\u9879\u76ee\uff1a\u5927\u5b66\u751f\u6d88\u8d39\u884c\u4e3a\u6570\u636e\u5206\u6790"
    assert project["time"] == "\u65f6\u95f4\uff1a2024.03-2024.06"
    assert "position" not in project
    assert not resolved.missing_questions


def test_unknown_project_name_and_time_are_explicit_and_do_not_drop_the_experience():
    build = build_canonical_semantic_build("\u5b8c\u6210\u6570\u636e\u5bfc\u5165\u548c\u56de\u5f52\u6a21\u578b\u5bf9\u6bd4\u3002")
    views = build_canonical_consumer_views(build)
    plan = plan_canonical_project_projections(_empty_payload(), views.planner_view)
    projected = append_canonical_project_projection_candidates(_empty_payload(), plan)
    project = projected.resume_sections.projects[0]

    assert project["name"] == f"\u9879\u76ee\uff1a{PENDING}"
    assert project["time"] == f"\u65f6\u95f4\uff1a{PENDING}"
    assert project["source_experience_id"] == "EXP-001"
    assert project["source_fact_ids"]
    assert set(projected.missing_questions) == {
        "\u8bf7\u8865\u5145\u8be5\u9879\u76ee\u7ecf\u5386\u7684\u9879\u76ee\u540d\u79f0\u3002",
        "\u8bf7\u8865\u5145\u5c1a\u672a\u660e\u786e\u7684\u7ecf\u5386\u8d77\u6b62\u65f6\u95f4\u6216\u5b66\u671f\u3002",
    }


def test_internship_company_position_and_time_are_independently_qualified():
    known = _header(
        "\u5728\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8\u62c5\u4efb\u4ea7\u54c1\u8fd0\u8425\u5b9e\u4e60\uff0c"
        "2024.03-2024.06 \u8d1f\u8d23\u7528\u6237\u8c03\u7814\u548c\u6570\u636e\u590d\u76d8\u3002"
    )
    fields = {field.field_key: field for field in known.fields}

    assert known.canonical_experience_type == "\u5b9e\u4e60\u7ecf\u5386"
    assert fields["organization"].display_text == "\u4f01\u4e1a\uff1a\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8"
    assert fields["position"].display_text == "\u5c97\u4f4d\uff1a\u4ea7\u54c1\u8fd0\u8425\u5b9e\u4e60"
    assert fields["time"].display_text == "\u65f6\u95f4\uff1a2024.03-2024.06"

    no_company = _header("\u4ea7\u54c1\u8fd0\u8425\u5b9e\u4e60\uff0c2024.03-2024.06 \u8d1f\u8d23\u7528\u6237\u8c03\u7814\u3002")
    no_position = _header("\u5728\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8\u5b9e\u4e60\uff0c2024.03-2024.06 \u5b8c\u6210\u6570\u636e\u590d\u76d8\u3002")
    no_time = _header("\u5728\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8\u62c5\u4efb\u4ea7\u54c1\u8fd0\u8425\u5b9e\u4e60\uff0c\u8d1f\u8d23\u7528\u6237\u8c03\u7814\u3002")

    assert no_company.field("organization").display_text == f"\u4f01\u4e1a\uff1a{PENDING}"
    assert no_company.field("position").qualified
    assert no_position.field("organization").qualified
    assert no_position.field("position").display_text == f"\u5c97\u4f4d\uff1a{PENDING}"
    assert no_time.field("time").display_text == f"\u65f6\u95f4\uff1a{PENDING}"


def test_non_internship_types_use_only_their_own_name_label_and_time():
    samples = (
        ("\u79d1\u7814\u7ecf\u5386\uff1a\u63a8\u8350\u7cfb\u7edf\u7814\u7a76\n\u53c2\u4e0e\u5b9e\u9a8c\u8bbe\u8ba1\u3002", "\u8bfe\u9898"),
        ("\u7ade\u8d5b\u7ecf\u5386\uff1a\u5168\u56fd\u5927\u5b66\u751f\u6570\u5b66\u5efa\u6a21\u7ade\u8d5b\n\u8d1f\u8d23\u5efa\u6a21\u5206\u6790\u3002", "\u7ade\u8d5b"),
        ("\u5f00\u6e90\u7ecf\u5386\uff1aOpenSearch Toolkit\n\u63d0\u4ea4 PR \u5e76\u5b8c\u6210\u5408\u5e76\u3002", "\u9879\u76ee"),
        ("\u6821\u56ed\u7ecf\u5386\uff1a\u6821\u5e86\u5fd7\u613f\u6d3b\u52a8\n\u53c2\u4e0e\u73b0\u573a\u7ec4\u7ec7\u3002", "\u6d3b\u52a8/\u7ec4\u7ec7"),
    )

    for raw, label in samples:
        header = _header(raw)
        assert header.field("name").label == label
        assert header.field("time").label == "\u65f6\u95f4"
        assert header.field("organization") is None
        assert header.field("position") is None


def test_multi_owner_header_values_do_not_cross_scopes():
    build = build_canonical_semantic_build(
        "\u9879\u76ee\u4e00\uff1a\u56fe\u4e66\u501f\u9605\u7cfb\u7edf\n2024.03-2024.06 \u5b8c\u6210\u501f\u9605\u767b\u8bb0\u3002\n\n"
        "\u5b9e\u4e60\u7ecf\u5386\uff1a\u5728\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8\u62c5\u4efb\u4ea7\u54c1\u8fd0\u8425\u5b9e\u4e60\n"
        "2025.01-2025.03 \u8d1f\u8d23\u7528\u6237\u8c03\u7814\u3002"
    )
    views = build_canonical_consumer_views(build)
    first = views.planner_view.experience_header_decision_for_owner("EXP-001")
    second = views.planner_view.experience_header_decision_for_owner("EXP-002")

    assert first.field("name").display_text == "\u9879\u76ee\uff1a\u56fe\u4e66\u501f\u9605\u7cfb\u7edf"
    assert first.field("time").display_text == "\u65f6\u95f4\uff1a2024.03-2024.06"
    assert first.field("organization") is None
    assert second.field("organization").display_text == "\u4f01\u4e1a\uff1a\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8"
    assert second.field("time").display_text == "\u65f6\u95f4\uff1a2025.01-2025.03"


def test_intent_responsibility_and_project_partner_do_not_become_company_or_position():
    header = _header(
        "\u5b9e\u4e60\u7ecf\u5386\uff1a\u7528\u6237\u7814\u7a76\u5b9e\u4e60\n"
        "\u9879\u76ee\u5408\u4f5c\u65b9\u4e3a\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8\uff0c\u8d1f\u8d23\u6570\u636e\u5206\u6790\uff0c\u76ee\u6807\u5c97\u4f4d\u4e3a\u4ea7\u54c1\u7ecf\u7406\u3002"
    )

    assert header.field("organization").display_text == f"\u4f01\u4e1a\uff1a{PENDING}"
    assert header.field("position").display_text != "\u5c97\u4f4d\uff1a\u4ea7\u54c1\u7ecf\u7406"


def test_header_assembly_preserves_owner_fact_claim_and_attachment_state_and_is_idempotent():
    raw = (
        "\u9879\u76ee\u540d\u79f0\u660e\u786e\u4e3a\u5927\u5b66\u751f\u6d88\u8d39\u884c\u4e3a\u6570\u636e\u5206\u6790\u3002"
        "\u5b8c\u6210\u6570\u636e\u6e05\u6d17\u4e0e\u53ef\u89c6\u5316\u3002"
    )
    build = build_canonical_semantic_build(raw)
    views = build_canonical_consumer_views(build)
    payload = _bound_payload(build)
    before_project = payload.resume_sections.projects[0]
    before_attachments = _attachments(before_project)
    before_owner = before_project["immutable_source_experience_id"]

    first = resolve_canonical_resume_titles(payload, views.planner_view)
    second = resolve_canonical_resume_titles(first, views.planner_view)

    assert first.model_dump() == second.model_dump()
    assert _attachments(first.resume_sections.projects[0]) == before_attachments
    assert first.resume_sections.projects[0]["immutable_source_experience_id"] == before_owner
    assert [(fact.fact_id, fact.claim_id, fact.experience_id) for fact in build.ledger.facts]
    assert payload.resume_sections.projects[0]["name"] == "legacy title"


def test_header_qualification_log_contains_aggregates_only(tmp_path, monkeypatch):
    raw = (
        "\u5728\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8\u62c5\u4efb\u4ea7\u54c1\u8fd0\u8425\u5b9e\u4e60\uff0c"
        "2024.03-2024.06 \u8d1f\u8d23\u7528\u6237\u8c03\u7814\u3002"
    )
    build = build_canonical_semantic_build(raw)
    log_path = tmp_path / "canonical_experience_header_qualification.jsonl"
    monkeypatch.setattr(header_service, "HEADER_QUALIFICATION_LOG_PATH", log_path)

    header_service.write_canonical_experience_header_qualification_log(
        build.experience_header_decisions,
        stage="test",
        request_id="req_v09123",
    )
    row = json.loads(log_path.read_text(encoding="utf-8"))
    serialized = json.dumps(row, ensure_ascii=False)

    assert row["experience_count"] == 1
    assert sum(row["field_status_counts"].values()) == 3
    assert all(key.endswith(":qualified") for key in row["field_status_counts"])
    assert "\u661f\u6cb3\u79d1\u6280\u6709\u9650\u516c\u53f8" not in serialized
    assert "\u4ea7\u54c1\u8fd0\u8425\u5b9e\u4e60" not in serialized
    assert "2024.03-2024.06" not in serialized
