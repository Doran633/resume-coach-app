import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import enhancement_guard_service  # noqa: E402
from app.services.canonical_consumer_view_service import (  # noqa: E402
    CanonicalConsumerViewAccessStats,
    build_canonical_consumer_views,
)
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.enhancement_guard_service import ensure_packaging_gain  # noqa: E402
from app.services.recruiter_facing_technical_language_service import (  # noqa: E402
    ensure_recruiter_facing_technical_language,
)
from app.services.resume_language_professionalization_service import (  # noqa: E402
    professionalize_resume_language,
)
from app.services.resume_skill_evidence_aggregation_service import (  # noqa: E402
    aggregate_skill_evidence_from_ledger,
)
from app.services.resume_template_language_guard_service import guard_template_language  # noqa: E402


RAW = """项目一：课程资料助手
我写了几个页面，使用 FastAPI 完成资料检索接口。
没有使用 Docker，也没有独立上线。

项目二：迎新志愿活动
我做了新生引导和物资整理，没有做技术工作。"""


def _build_views():
    build = build_canonical_semantic_build(RAW)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    return build, build_canonical_consumer_views(build, evidence)


def _payload(build, *, bind_first=True, bind_second=True):
    projects = []
    for index, identity in enumerate(build.identities):
        facts = tuple(build.ledger.for_experience(identity.experience_id))
        fact_ids = [fact.fact_id for fact in facts]
        is_bound = bind_first if index == 0 else bind_second
        detail = "我写了几个页面" if index == 0 else "我做了新生引导和物资整理"
        project = {
            "name": identity.title,
            "meta": build.canonical_type_by_experience_id[identity.experience_id].canonical_experience_type,
            "time": "[待填写]",
            "intro": detail,
            "role": detail,
            "details": [detail],
            "source_experience_id": identity.experience_id,
            "source_fact_ids": fact_ids,
            "role_source_fact_ids": fact_ids,
            "detail_fact_ids": [[fact_ids[0]]] if fact_ids else [[]],
        }
        if is_bound:
            project.update({
                "immutable_source_experience_id": identity.experience_id,
                "source_binding_locked": True,
            })
        projects.append(project)
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
            personal_info={},
            education={},
            summary=["具备项目实践能力。"],
            skills=["编程语言：Python"],
            projects=projects,
            interview_preparation=[],
        ),
    )


def _semantic_metadata(payload):
    return [
        {
            key: project.get(key)
            for key in (
                "source_experience_id",
                "immutable_source_experience_id",
                "source_binding_locked",
                "source_fact_ids",
                "role_source_fact_ids",
                "detail_fact_ids",
                "meta",
            )
        }
        for project in payload.resume_sections.projects
    ]


def test_presentation_view_limits_fields_to_frozen_local_fact_scope():
    build, views = _build_views()
    payload = _payload(build)
    first, second = payload.resume_sections.projects
    stats = CanonicalConsumerViewAccessStats()

    assert views.presentation_view.fingerprint == views.build_fingerprint
    assert views.presentation_view.permits_project_field(first, "details", 0, access_stats=stats)

    foreign_fact_id = second["source_fact_ids"][0]
    first["detail_fact_ids"] = [[foreign_fact_id]]
    assert not views.presentation_view.permits_project_field(first, "details", 0, access_stats=stats)
    assert stats.rejected_cross_owner_access_count == 1


def test_canonical_packaging_never_rebuilds_raw_semantics(monkeypatch):
    build, views = _build_views()
    payload = _payload(build)
    before_metadata = _semantic_metadata(payload)

    def forbidden(*args, **kwargs):
        raise AssertionError("canonical packaging rebuilt raw input semantics")

    monkeypatch.setattr(enhancement_guard_service, "build_experience_identities", forbidden)
    monkeypatch.setattr(enhancement_guard_service, "_soft_upgrades_from_raw", forbidden)
    result = ensure_packaging_gain(
        payload,
        target_role="后端开发",
        presentation_view=views.presentation_view,
    )

    assert _semantic_metadata(result) == before_metadata
    assert "Docker" not in result.model_dump_json()
    assert "新生引导" not in "\n".join(result.resume_sections.projects[0]["details"])
    assert len(result.recommended_version) >= 80


def test_unbound_project_is_not_professionalized_or_template_rewritten():
    build, views = _build_views()
    payload = _payload(build, bind_first=False)
    original = payload.resume_sections.projects[0].copy()

    language = professionalize_resume_language(
        payload,
        write_log=False,
        presentation_view=views.presentation_view,
    )
    template = guard_template_language(
        language,
        presentation_view=views.presentation_view,
    )

    assert template.resume_sections.projects[0] == original


def test_bound_project_keeps_current_professionalization_without_mutating_semantics():
    build, views = _build_views()
    payload = _payload(build)
    before_metadata = _semantic_metadata(payload)

    result = professionalize_resume_language(
        payload,
        write_log=False,
        presentation_view=views.presentation_view,
    )

    first = result.resume_sections.projects[0]
    assert "我写了" not in first["details"][0]
    assert "页面开发" in first["details"][0]
    assert _semantic_metadata(result) == before_metadata


def test_recruiter_language_does_not_rewrite_skills_or_foreign_bound_fields():
    build, views = _build_views()
    payload = _payload(build)
    first, second = payload.resume_sections.projects
    first["details"] = ["使用 result_cleanup 和 fact_guard 完成处理"]
    first["detail_fact_ids"] = [[second["source_fact_ids"][0]]]
    original_detail = first["details"][0]
    original_skills = list(payload.resume_sections.skills)

    result = ensure_recruiter_facing_technical_language(
        payload,
        write_log=False,
        presentation_view=views.presentation_view,
    )

    assert result.resume_sections.projects[0]["details"][0] == original_detail
    assert result.resume_sections.skills == original_skills


def test_scoped_presentation_is_idempotent():
    build, views = _build_views()
    payload = _payload(build)

    first = ensure_packaging_gain(payload, target_role="后端开发", presentation_view=views.presentation_view)
    first = guard_template_language(first, presentation_view=views.presentation_view)
    first = professionalize_resume_language(
        first, write_log=False, presentation_view=views.presentation_view,
    )
    first = ensure_recruiter_facing_technical_language(
        first, write_log=False, presentation_view=views.presentation_view,
    )
    second = ensure_packaging_gain(first, target_role="后端开发", presentation_view=views.presentation_view)
    second = guard_template_language(second, presentation_view=views.presentation_view)
    second = professionalize_resume_language(
        second, write_log=False, presentation_view=views.presentation_view,
    )
    second = ensure_recruiter_facing_technical_language(
        second, write_log=False, presentation_view=views.presentation_view,
    )

    assert second.model_dump(mode="json") == first.model_dump(mode="json")
