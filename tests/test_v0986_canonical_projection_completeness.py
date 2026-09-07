import copy
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import canonical_projection_completeness_service as projection_service  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_projection_completeness_service import (  # noqa: E402
    CanonicalProjectionCompletenessObserver,
)
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.experience_slot_service import contain_ownerless_projects, strip_experience_slot_metadata  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence_from_ledger  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """项目一：资料检索工具
使用 FastAPI 实现资料检索接口，并完成日志记录。

项目二：迎新志愿活动
参与新生引导和物资整理。"""


def _build_views():
    build = build_canonical_semantic_build(RAW)
    views = build_canonical_consumer_views(
        build,
        aggregate_skill_evidence_from_ledger(build.ledger),
    )
    return build, views


def _payload(projects):
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={}, education={}, summary=[], skills=[], projects=projects,
            interview_preparation=[],
        ),
    )


def _bound_project(owner, fact_ids, *, locked=True):
    return {
        "name": "匿名项目",
        "meta": "项目经历",
        "time": "[待填写]",
        "intro": "已验证的本地项目事实。",
        "role": "",
        "details": ["已验证的本地项目事实。"],
        "source_experience_id": owner,
        "immutable_source_experience_id": owner,
        "source_binding_locked": locked,
        "source_fact_ids": list(fact_ids),
        "detail_fact_ids": [list(fact_ids)] if fact_ids else [],
    }


def _events_for(observer, owner):
    return [
        row for row in observer.events
        if row.get("event_type") == "projection_checkpoint" and row.get("experience_id") == owner
    ]


def test_complete_single_owner_projection_has_no_gap_and_never_mutates_payload():
    build, views = _build_views()
    owner = build.identities[0].experience_id
    fact_ids = views.owner_scopes[owner].eligible_fact_ids
    payload = _payload([_bound_project(owner, fact_ids)])
    before = copy.deepcopy(payload.model_dump(mode="json"))
    observer = CanonicalProjectionCompletenessObserver(views, request_id="req_v0986")

    observer.checkpoint(payload, "after_owner_freeze")
    observer.checkpoint(payload, "before_persistence")

    final = _events_for(observer, owner)[-1]
    assert final["status"] == "complete"
    assert final["unprojected_eligible_fact_count"] == 0
    assert final["owner_bound_project_count"] == 1
    assert payload.model_dump(mode="json") == before


def test_multi_experience_missing_projection_reports_only_affected_owner():
    build, views = _build_views()
    first, second = (identity.experience_id for identity in build.identities)
    payload = _payload([_bound_project(first, views.owner_scopes[first].eligible_fact_ids)])
    observer = CanonicalProjectionCompletenessObserver(views)

    observer.checkpoint(payload, "after_owner_freeze")
    first_final = _events_for(observer, first)[-1]
    second_final = _events_for(observer, second)[-1]

    assert first_final["issue_codes"] == []
    assert "EXPERIENCE_WITHOUT_VISIBLE_PROJECT" in second_final["issue_codes"]
    assert "ELIGIBLE_FACT_UNPROJECTED" in second_final["issue_codes"]
    assert second_final["first_projection_gap_stage"] == "after_owner_freeze"


def test_ownerless_candidate_removal_is_logged_without_guessing_an_owner():
    build, views = _build_views()
    unowned = _bound_project("", (), locked=False)
    unowned.pop("source_experience_id")
    unowned.pop("immutable_source_experience_id")
    payload = _payload([unowned])
    observer = CanonicalProjectionCompletenessObserver(views)

    observer.checkpoint(payload, "after_llm")
    contained, stats = contain_ownerless_projects(
        payload,
        build.ownership_index,
        stage="test",
        write_log=False,
        return_stats=True,
    )
    observer.checkpoint(
        contained,
        "after_ownerless_containment",
        containment_stats=stats,
    )

    unassigned = [row for row in observer.events if row.get("event_type") == "unassigned_ownerless_containment"]
    assert len(unassigned) == 1
    assert unassigned[0]["experience_id"] == ""
    assert unassigned[0]["removed_by_ownerless_containment_count"] == 1
    assert unassigned[0]["issue_codes"] == ["OWNERLESS_CANDIDATE_REMOVED"]
    assert all(row["removed_by_ownerless_containment_count"] == 0 for row in _events_for(observer, build.identities[0].experience_id))


def test_owner_bound_project_without_fact_binding_is_distinguished():
    build, views = _build_views()
    owner = build.identities[0].experience_id
    payload = _payload([_bound_project(owner, ())])
    observer = CanonicalProjectionCompletenessObserver(views)

    observer.checkpoint(payload, "after_owner_freeze")
    final = _events_for(observer, owner)[-1]

    assert "OWNER_BOUND_PROJECT_WITHOUT_FACT_BINDING" in final["issue_codes"]
    assert final["fact_binding_count"] == 0
    assert final["first_binding_gap_stage"] == "after_owner_freeze"


def test_projection_drop_after_freeze_is_reported_without_repairing_anything():
    build, views = _build_views()
    owner = build.identities[0].experience_id
    fact_ids = views.owner_scopes[owner].eligible_fact_ids
    payload = _payload([_bound_project(owner, fact_ids)])
    observer = CanonicalProjectionCompletenessObserver(views)

    observer.checkpoint(payload, "after_owner_freeze")
    dropped = _payload([_bound_project(owner, ())])
    observer.checkpoint(dropped, "after_presentation")
    final = _events_for(observer, owner)[-1]

    assert "PROJECTION_DROPPED_AFTER_OWNER_FREEZE" in final["issue_codes"]
    assert dropped.resume_sections.projects[0]["source_fact_ids"] == []


def test_persisted_public_source_id_remains_a_projection_attachment_after_internal_strip():
    build, views = _build_views()
    owner = build.identities[0].experience_id
    fact_ids = views.owner_scopes[owner].eligible_fact_ids
    payload = _payload([_bound_project(owner, fact_ids)])
    observer = CanonicalProjectionCompletenessObserver(views)

    observer.checkpoint(payload, "before_persistence")
    persisted = strip_experience_slot_metadata(payload)
    observer.checkpoint(persisted, "generation_persisted")
    final = _events_for(observer, owner)[-1]

    assert final["owner_bound_project_count"] == 1
    assert final["unprojected_eligible_fact_count"] == 0


def test_log_and_query_are_identifier_only(tmp_path, monkeypatch):
    build, views = _build_views()
    owner = build.identities[0].experience_id
    fact_ids = views.owner_scopes[owner].eligible_fact_ids
    payload = _payload([_bound_project(owner, fact_ids)])
    log_path = tmp_path / "projection.jsonl"
    monkeypatch.setattr(projection_service, "LOG_PATH", log_path)
    observer = CanonicalProjectionCompletenessObserver(
        views,
        request_id="req_v0986_log",
        attempt_id="attempt_v0986_log",
    )
    observer.checkpoint(payload, "after_owner_freeze")
    observer.flush(986)

    content = log_path.read_text(encoding="utf-8")
    assert RAW not in content
    assert "资料检索工具" not in content
    assert "FastAPI" not in content
    assert "已验证的本地项目事实" not in content

    spec = importlib.util.spec_from_file_location("projection_query", ROOT / "scripts" / "list_canonical_projection_gaps.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.summarize(module._load_events(log_path))
    assert report["owners"][0]["experience_id"] == owner
    assert report["owners"][0]["final"]["status"] == "complete"


def test_query_reports_the_first_actionable_post_freeze_gap(tmp_path, monkeypatch):
    build, views = _build_views()
    first, second = (identity.experience_id for identity in build.identities)
    payload = _payload([_bound_project(first, views.owner_scopes[first].eligible_fact_ids)])
    log_path = tmp_path / "projection.jsonl"
    monkeypatch.setattr(projection_service, "LOG_PATH", log_path)
    observer = CanonicalProjectionCompletenessObserver(views)

    observer.checkpoint(payload, "after_llm")
    observer.checkpoint(payload, "after_owner_freeze")
    observer.flush(987)

    spec = importlib.util.spec_from_file_location("projection_query_gap", ROOT / "scripts" / "list_canonical_projection_gaps.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.summarize(module._load_events(log_path))
    affected = next(owner for owner in report["owners"] if owner["experience_id"] == second)
    assert affected["first_projection_gap_stage"] == "after_owner_freeze"


def test_observer_has_no_raw_input_parameter_or_mutating_public_api():
    assert "raw_input" not in CanonicalProjectionCompletenessObserver.checkpoint.__annotations__
    assert "repair" not in projection_service.__dict__


def test_generation_uses_all_projection_checkpoints_without_changing_its_public_response(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    original = generation_service.CanonicalProjectionCompletenessObserver
    observers = []

    class RecordingObserver(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            observers.append(self)

    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(generation_service, "CanonicalProjectionCompletenessObserver", RecordingObserver)
    monkeypatch.setattr(generation_service, "LOG_DIR", tmp_path / "logs")
    generation_service.LOG_DIR.mkdir()
    monkeypatch.setattr(projection_service, "LOG_PATH", tmp_path / "projection.jsonl")
    try:
        response = generation_service.create_generation(
            db,
            schemas.GenerateRequest(
                anonymous_user_id="anon-v0986",
                session_id="session-v0986",
                target_role="后端开发",
                mode="full_resume",
                packaging_level="稳妥",
                experience_type="项目经历",
                raw_input=RAW,
                attempt_id="attempt_v0986_generation",
            ),
            request_id="req_v0986_generation",
        )
    finally:
        db.close()

    assert response.generation_result_id > 0
    assert response.result.resume_sections.projects
    assert len(observers) == 1
    stages = {
        row["stage"] for row in observers[0].events
        if row.get("event_type") == "projection_checkpoint"
    }
    assert {
        "after_llm", "after_owner_freeze", "after_ownerless_containment",
        "after_presentation", "before_persistence", "generation_persisted",
    }.issubset(stages)
    assert projection_service.LOG_PATH.exists()
