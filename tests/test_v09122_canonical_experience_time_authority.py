"""Regression coverage for Canonical Experience Time Authority.

These are fixed current-code replays, not historical request snapshots.
"""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import canonical_semantic_state_service as time_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_project_projection_service import (  # noqa: E402
    append_canonical_project_projection_candidates,
    plan_canonical_project_projections,
)
from app.services.canonical_semantic_state_service import (  # noqa: E402
    TIME_PENDING_DISPLAY,
    build_canonical_semantic_build,
)
from app.services.resume_title_format_service import resolve_canonical_resume_titles  # noqa: E402


PROJECT = "\u9879\u76ee\u540d\u79f0\u660e\u786e\u4e3a\u5927\u5b66\u751f\u6d88\u8d39\u884c\u4e3a\u6570\u636e\u5206\u6790\u3002"
DONE = "\u5b8c\u6210\u6570\u636e\u6e05\u6d17\u3002"


def _payload(build, *, time: str = "[待填写]") -> schemas.GenerationPayload:
    fact = build.ledger.facts[0]
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
            "name": "\u6570\u636e\u5206\u6790\u5de5\u5177",
            "meta": "\u9879\u76ee\u7ecf\u5386",
            "time": time,
            "intro": fact.resume_ready_text,
            "role": "",
            "details": [],
            "source_experience_id": "EXP-001",
            "immutable_source_experience_id": "EXP-001",
            "source_binding_locked": True,
            "source_fact_ids": [fact.fact_id],
            "role_source_fact_ids": [],
            "detail_fact_ids": [],
            "source_claim_ids": [fact.claim_id],
            "role_source_claim_ids": [],
            "detail_claim_ids": [],
        }]),
    )


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


def _time(raw: str, index: int = 0):
    return build_canonical_semantic_build(raw).experience_time_decisions[index]


def _attachments(project: dict) -> dict:
    return {
        key: project.get(key)
        for key in (
            "source_fact_ids", "role_source_fact_ids", "detail_fact_ids",
            "source_claim_ids", "role_source_claim_ids", "detail_claim_ids",
        )
    }


def test_explicit_ranges_semesters_and_ongoing_ranges_are_qualified_once():
    samples = {
        f"{PROJECT}2024.03-2024.06 {DONE}": "2024.03-2024.06",
        f"{PROJECT}2024\u5e743\u6708\u81f32024\u5e746\u6708{DONE}": "2024\u5e743\u6708\u81f32024\u5e746\u6708",
        f"{PROJECT}2024\u79cb\u5b63\u5b66\u671f{DONE}": "2024\u79cb\u5b63\u5b66\u671f",
        f"{PROJECT}2024.03-\u81f3\u4eca\u6301\u7eed\u8fed\u4ee3\u6570\u636e\u5206\u6790\u529f\u80fd\u3002": "2024.03-\u81f3\u4eca",
    }

    for raw, expected in samples.items():
        decision = _time(raw)
        assert decision.qualified
        assert decision.display_time == expected
        assert decision.experience_id == "EXP-001"
        assert decision.source_span[0] >= 0


def test_single_month_is_not_turned_into_an_invented_range():
    decision = _time(f"{PROJECT}2024\u5e743\u6708{DONE}")

    assert decision.qualified
    assert decision.display_time == "2024\u5e743\u6708"
    assert "\u81f3" not in decision.display_time
    assert "-" not in decision.display_time


def test_multiple_owners_cannot_borrow_each_others_time():
    build = build_canonical_semantic_build(
        "\u9879\u76ee\u4e00\uff1a\u56fe\u4e66\u501f\u9605\u7cfb\u7edf\n2024.03-2024.06 \u5b8c\u6210\u501f\u9605\u767b\u8bb0\u3002\n\n"
        "\u9879\u76ee\u4e8c\uff1a\u505c\u8f66\u7ba1\u7406\u7cfb\u7edf\n2025\u79cb\u5b63\u5b66\u671f\u5b8c\u6210\u8f66\u4f4d\u72b6\u6001\u91c7\u96c6\u3002"
    )

    assert len(build.experience_time_decisions) == 2
    assert [item.display_time for item in build.experience_time_decisions] == [
        "2024.03-2024.06", "2025\u79cb\u5b63\u5b66\u671f",
    ]
    assert [item.experience_id for item in build.experience_time_decisions] == ["EXP-001", "EXP-002"]


def test_versions_metrics_sessions_and_paper_years_are_not_experience_time():
    samples = (
        "\u5f00\u53d1 Python 3 \u6570\u636e\u5904\u7406\u5de5\u5177\uff0c\u4f7f\u7528 GPT-4 v2.0\uff0c\u51c6\u786e\u7387\u63d0\u5347 24%\u3002",
        "\u53c2\u52a0\u7b2c 3 \u5c4a\u6bd4\u8d5b\uff0c\u5b8c\u6210\u9879\u76ee\u7f16\u53f7 2024-01 \u7684\u63d0\u4ea4\u3002",
        "\u4f7f\u75282024\u5e74\u6570\u636e\u96c6\u5e76\u9605\u8bfb2024\u5e74\u8bba\u6587\uff0c\u5b8c\u6210\u6a21\u578b\u5bf9\u6bd4\u3002",
    )

    for raw in samples:
        decision = _time(raw)
        assert not decision.qualified
        assert decision.display_time == TIME_PENDING_DISPLAY


def test_instruction_negative_uncertain_and_planned_time_cannot_support_authority():
    samples = (
        "\u8bf7\u5199\u62102024\u5e743\u6708\u5f00\u59cb\u7684\u6570\u636e\u5206\u6790\u9879\u76ee\u3002",
        "\u6ca1\u6709\u57282024\u5e743\u6708\u53c2\u4e0e\u8be5\u9879\u76ee\u3002",
        "\u4e0d\u786e\u5b9a\u662f\u5426\u57282024\u5e743\u6708\u5b8c\u6210\u9879\u76ee\u3002",
        "\u8ba1\u5212\u4e0a\u7ebf2025\u5e743\u6708\u7684\u6570\u636e\u5206\u6790\u5de5\u5177\u3002",
    )

    for raw in samples:
        decision = _time(raw)
        assert not decision.qualified
        assert decision.display_time == TIME_PENDING_DISPLAY


def test_unknown_time_preserves_owner_facts_and_uses_only_time_placeholder():
    build = build_canonical_semantic_build(f"{PROJECT}\u5b8c\u6210\u6570\u636e\u6e05\u6d17\u4e0e\u53ef\u89c6\u5316\u3002")
    views = build_canonical_consumer_views(build)
    payload = _payload(build)
    before = _attachments(payload.resume_sections.projects[0])

    resolved = resolve_canonical_resume_titles(payload, views.planner_view)
    project = resolved.resume_sections.projects[0]

    assert project["time"] == "\u65f6\u95f4\uff1a\u3010\u5f85\u586b\u5199\u3011"
    assert _attachments(project) == before
    assert resolved.missing_questions == ["\u8bf7\u8865\u5145\u5c1a\u672a\u660e\u786e\u7684\u7ecf\u5386\u8d77\u6b62\u65f6\u95f4\u6216\u5b66\u671f\u3002"]
    assert all("\u4f01\u4e1a\uff1a" not in value and "\u5c97\u4f4d\uff1a" not in value for value in [project["time"], *resolved.missing_questions])


def test_projection_and_title_resolver_only_consume_frozen_time_decision():
    build = build_canonical_semantic_build(f"{PROJECT}2024.03-2024.06 {DONE}")
    views = build_canonical_consumer_views(build)
    plan = plan_canonical_project_projections(_empty_payload(), views.planner_view)
    projected = append_canonical_project_projection_candidates(_empty_payload(), plan)

    assert plan.candidates[0]["time"] == "\u65f6\u95f4\uff1a2024.03-2024.06"
    assert projected.resume_sections.projects[0]["time"] == "\u65f6\u95f4\uff1a2024.03-2024.06"
    assert not plan.pending_time_owner_ids


def test_decision_is_deterministic_and_does_not_change_identity_claim_or_fact_state():
    raw = f"{PROJECT}2024.03-2024.06 {DONE}"
    first = build_canonical_semantic_build(raw)
    second = build_canonical_semantic_build(raw)

    assert first.experience_time_decisions == second.experience_time_decisions
    assert [item.claim_id for item in first.ledger.claims] == [item.claim_id for item in second.ledger.claims]
    assert [item.fact_id for item in first.ledger.facts] == [item.fact_id for item in second.ledger.facts]
    assert [item.experience_id for item in first.identities] == [item.experience_id for item in second.identities]


def test_time_log_is_aggregate_only(tmp_path, monkeypatch):
    raw = f"{PROJECT}2024.03-2024.06 {DONE}"
    build = build_canonical_semantic_build(raw)
    log_path = tmp_path / "canonical_experience_time_qualification.jsonl"
    monkeypatch.setattr(time_service, "TIME_QUALIFICATION_LOG_PATH", log_path)

    time_service.write_canonical_experience_time_qualification_log(
        build.experience_time_decisions,
        stage="test",
        request_id="req_v09122",
    )
    row = json.loads(log_path.read_text(encoding="utf-8"))
    serialized = json.dumps(row, ensure_ascii=False)

    assert row["qualified_time_count"] == 1
    assert row["qualified_source_counts"]
    assert "2024.03-2024.06" not in serialized
    assert "\u6570\u636e\u5206\u6790\u5de5\u5177" not in serialized
    assert "\u6570\u636e\u6e05\u6d17" not in serialized
