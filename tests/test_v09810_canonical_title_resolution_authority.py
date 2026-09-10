import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import resume_title_format_service as title_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.semantic_mutation_trace_service import (  # noqa: E402
    SemanticMutationTracer,
    build_semantic_commit_snapshot,
)


RAW = """项目二：论文阅读助手
使用 FastAPI 实现论文检索与摘要阅读。"""
ATTACHMENT_KEYS = (
    "source_fact_ids",
    "role_source_fact_ids",
    "detail_fact_ids",
    "source_claim_ids",
    "role_source_claim_ids",
    "detail_claim_ids",
)


def _payload(build):
    fact = build.ledger.facts[0]
    return schemas.GenerationPayload(
        completeness_score=90,
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
            "name": "项目实践",
            "meta": "项目经历",
            "resolved_experience_type": "项目经历",
            "time": "[待填写]",
            "intro": fact.resume_ready_text,
            "role": fact.resume_ready_text,
            "details": [fact.resume_ready_text],
            "source_experience_id": fact.experience_id,
            "immutable_source_experience_id": fact.experience_id,
            "source_binding_locked": True,
            "source_fact_ids": [fact.fact_id],
            "role_source_fact_ids": [fact.fact_id],
            "detail_fact_ids": [[fact.fact_id]],
            "source_claim_ids": [fact.claim_id],
            "role_source_claim_ids": [fact.claim_id],
            "detail_claim_ids": [[fact.claim_id]],
        }]),
    )


def _views():
    build = build_canonical_semantic_build(RAW)
    return build, build_canonical_consumer_views(build)


def _attachments(project):
    return {key: project.get(key) for key in ATTACHMENT_KEYS}


def test_canonical_title_resolution_preserves_result_173_style_attachments(monkeypatch):
    build, views = _views()
    payload = _payload(build)
    before_payload = payload.model_dump(mode="json")
    before_attachments = _attachments(payload.resume_sections.projects[0])

    monkeypatch.setattr(title_service, "build_experience_identities", lambda _raw: (_ for _ in ()).throw(AssertionError("raw identity rebuild forbidden")))
    monkeypatch.setattr(title_service, "build_experience_fact_ledger", lambda _raw: (_ for _ in ()).throw(AssertionError("raw ledger rebuild forbidden")))
    monkeypatch.setattr(title_service, "resolve_experience_claims", lambda *_args: (_ for _ in ()).throw(AssertionError("raw claim rebuild forbidden")))

    resolved = title_service.resolve_canonical_resume_titles(payload, views.planner_view)
    project = resolved.resume_sections.projects[0]

    assert payload.model_dump(mode="json") == before_payload
    assert _attachments(project) == before_attachments
    assert project["name"] == "论文阅读助手"
    assert project["meta"] == "项目经历"
    assert project["immutable_source_experience_id"] == build.ledger.facts[0].experience_id


def test_canonical_title_resolution_does_not_reclassify_from_keywords():
    build, views = _views()
    payload = _payload(build)
    payload.resume_sections.projects[0]["name"] = "论文阅读助手"
    payload.resume_sections.projects[0]["meta"] = "项目经历"

    resolved = title_service.resolve_canonical_resume_titles(payload, views.planner_view)

    assert resolved.resume_sections.projects[0]["meta"] == "项目经历"


def test_pending_name_keeps_project_and_attachments_without_raw_inference():
    build = build_canonical_semantic_build("项目经历\n完成资料整理与数据导入。")
    views = build_canonical_consumer_views(build)
    payload = _payload(build)
    project = payload.resume_sections.projects[0]
    project["name"] = "[待填写]"
    project["source_experience_id"] = build.ledger.facts[0].experience_id
    project["immutable_source_experience_id"] = build.ledger.facts[0].experience_id
    project["source_fact_ids"] = [build.ledger.facts[0].fact_id]
    project["role_source_fact_ids"] = [build.ledger.facts[0].fact_id]
    project["detail_fact_ids"] = [[build.ledger.facts[0].fact_id]]
    project["source_claim_ids"] = [build.ledger.facts[0].claim_id]
    project["role_source_claim_ids"] = [build.ledger.facts[0].claim_id]
    project["detail_claim_ids"] = [[build.ledger.facts[0].claim_id]]
    before = _attachments(project)

    resolved = title_service.resolve_canonical_resume_titles(payload, views.planner_view)
    resolved_project = resolved.resume_sections.projects[0]

    assert resolved_project["name"] == "[待补充经历名称]"
    assert _attachments(resolved_project) == before


def test_trace_records_no_attachment_coarsening_at_canonical_title_boundary():
    build, views = _views()
    payload = _payload(build)
    tracer = SemanticMutationTracer(
        snapshot=build_semantic_commit_snapshot(consumer_views=views),
        consumer_views=views,
    )
    tracer.checkpoint(payload, "after_presentation")
    resolved = title_service.resolve_canonical_resume_titles(payload, views.planner_view)
    tracer.checkpoint(resolved, "after_title_resolution", parent_stage="resolve_canonical_resume_titles")

    codes = [event["mutation_code"] for event in tracer.events if event["event_type"] == "mutation"]

    assert "FACT_BINDING_DROPPED" not in codes
    assert "PROVENANCE_METADATA_COARSENED" not in codes


def test_legacy_title_api_still_formats_an_internship_from_raw_input():
    build, _ = _views()
    payload = _payload(build)
    project = payload.resume_sections.projects[0]
    project["name"] = "自行者科技有限公司 AI Agent 开发实习"
    project["meta"] = "实习经历"
    project["resolved_experience_type"] = "实习经历"

    resolved = title_service.resolve_resume_titles(
        payload,
        "在自行者科技有限公司担任 AI Agent 开发实习，负责测试集建设。",
    )

    assert resolved.resume_sections.projects[0]["name"] == "自行者科技有限公司"
    assert resolved.resume_sections.projects[0]["position"] == "AI Agent 开发实习"
