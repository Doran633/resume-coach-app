"""Fixed v0.9.13.2 replays; these are not historical request snapshots."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import enhancement_guard_service  # noqa: E402
from app.services.canonical_consumer_view_service import build_canonical_consumer_views  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.enhancement_guard_service import ensure_packaging_gain  # noqa: E402
from app.services.resume_language_professionalization_service import (  # noqa: E402
    professionalize_resume_language,
)


RAW = """项目：后台管理工具
我写了几个页面。我做了数据整理。我写了几个接口。我帮忙测试。我做了用户调研。"""


def _context():
    build = build_canonical_semantic_build(RAW)
    views = build_canonical_consumer_views(build)
    facts = list(build.ledger.for_experience("EXP-001"))
    assert len(facts) == 5
    return build, views, facts


def _payload(facts) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=90,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="边界版本保持事实口径。",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=["具备项目实践能力。"],
            skills=["编程语言：Python"],
            projects=[{
                "name": "项目：后台管理工具",
                "position": "",
                "meta": "项目经历",
                "time": "时间：【待填写】",
                "intro": "我写了几个页面",
                "role": "我写了几个页面",
                "details": ["我做了数据整理", "我写了几个接口", "我帮忙测试", "我做了用户调研"],
                "source_experience_id": "EXP-001",
                "immutable_source_experience_id": "EXP-001",
                "source_binding_locked": True,
                "source_fact_ids": [fact.fact_id for fact in facts],
                "source_claim_ids": [fact.claim_id for fact in facts],
                "role_source_fact_ids": [facts[0].fact_id],
                "role_source_claim_ids": [facts[0].claim_id],
                "detail_fact_ids": [[fact.fact_id] for fact in facts[1:]],
                "detail_claim_ids": [[fact.claim_id] for fact in facts[1:]],
            }],
        ),
    )


def _frozen_metadata(payload: schemas.GenerationPayload) -> dict:
    project = payload.resume_sections.projects[0]
    return {
        key: project.get(key)
        for key in (
            "name", "position", "meta", "time", "source_experience_id",
            "immutable_source_experience_id", "source_binding_locked",
            "source_fact_ids", "source_claim_ids", "role_source_fact_ids",
            "role_source_claim_ids", "detail_fact_ids", "detail_claim_ids",
        )
    }


def test_bold_scope_allows_approved_soft_professionalization_without_hard_facts():
    _, views, facts = _context()
    payload = _payload(facts)
    before = _frozen_metadata(payload)

    result = professionalize_resume_language(
        payload,
        packaging_level="大胆",
        write_log=False,
        presentation_view=views.presentation_view,
    )
    project = result.resume_sections.projects[0]

    assert project["intro"] == "我写了几个页面"
    assert project["role"] == "参与前端架构设计与完整交互流程建设"
    assert project["details"] == [
        "负责数据清洗、结构化整理与分析流程建设",
        "参与接口设计与服务端功能实现",
        "参与功能验证、问题定位与交付质量保障",
        "负责用户需求调研、反馈归纳与产品优化分析",
    ]
    assert _frozen_metadata(result) == before
    output = result.model_dump_json()
    for unsupported in ("React", "Vue", "微服务", "RAG", "30%", "主导", "独立负责"):
        assert unsupported not in output


def test_packaging_levels_are_distinct_and_idempotent():
    _, views, facts = _context()
    payload = _payload(facts)
    values = {}
    for level in ("稳妥", "大胆", "极限"):
        first = professionalize_resume_language(
            payload,
            packaging_level=level,
            write_log=False,
            presentation_view=views.presentation_view,
        )
        second = professionalize_resume_language(
            first,
            packaging_level=level,
            write_log=False,
            presentation_view=views.presentation_view,
        )
        assert second.model_dump(mode="json") == first.model_dump(mode="json")
        values[level] = first.resume_sections.projects[0]["role"]

    assert len(set(values.values())) == 3
    assert "页面开发" in values["稳妥"]
    assert "前端架构设计" in values["大胆"]
    assert "后续迭代" in values["极限"]


def test_missing_or_invalid_field_provenance_skips_professionalization():
    _, views, facts = _context()
    payload = _payload(facts)
    project = payload.resume_sections.projects[0]
    project["role_source_fact_ids"] = []
    project["role_source_claim_ids"] = []
    project["detail_claim_ids"][0] = [facts[0].claim_id]

    result = professionalize_resume_language(
        payload,
        packaging_level="极限",
        write_log=False,
        presentation_view=views.presentation_view,
    )

    assert result.resume_sections.projects[0]["role"] == "我写了几个页面"
    assert result.resume_sections.projects[0]["details"][0] == "我做了数据整理"
    assert result.resume_sections.projects[0]["details"][1] != "我写了几个接口"


def test_canonical_packaging_does_not_rebuild_raw_semantics_and_selects_level(monkeypatch):
    _, views, facts = _context()
    payload = _payload(facts)

    def forbidden(*args, **kwargs):
        raise AssertionError("canonical packaging accessed a raw semantic rebuild")

    monkeypatch.setattr(enhancement_guard_service, "build_experience_identities", forbidden)
    monkeypatch.setattr(enhancement_guard_service, "_soft_upgrades_from_raw", forbidden)
    result = ensure_packaging_gain(
        payload,
        target_role="前端开发",
        packaging_level="极限",
        presentation_view=views.presentation_view,
    )

    assert result.normal_version != result.bold_version
    assert result.recommended_version not in {result.normal_version, result.bold_version}
    assert "后续迭代" in result.recommended_version
    assert result.boundary_version == payload.boundary_version
    assert _frozen_metadata(result) == _frozen_metadata(payload)


def test_log_is_identifier_only(tmp_path, monkeypatch):
    from app.services import resume_language_professionalization_service as service

    _, views, facts = _context()
    payload = _payload(facts)
    log_path = tmp_path / "professionalization.jsonl"
    monkeypatch.setattr(service, "LOG_PATH", log_path)

    service.professionalize_resume_language(
        payload,
        packaging_level="大胆",
        presentation_view=views.presentation_view,
    )
    text = log_path.read_text(encoding="utf-8")
    row = json.loads(text)

    assert row["packaging_level"] == "大胆"
    assert row["soft_derivation_count"] == 5
    assert row["insufficient_provenance_skip_count"] >= 1
    for private in ("我写了几个页面", "后台管理工具", "用户调研", "数据整理"):
        assert private not in text
