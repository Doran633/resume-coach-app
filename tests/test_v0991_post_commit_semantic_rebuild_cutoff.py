import inspect
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services import resume_output_quality_gate_service as output_quality_service  # noqa: E402
from app.services import resume_output_relevance_service as relevance_service  # noqa: E402
from app.services import resume_skill_evidence_guard_service as evidence_service  # noqa: E402
from app.services import resume_skill_taxonomy_service as taxonomy_service  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.resume_body_sanitizer_service import sanitize_resume_body  # noqa: E402
from app.services.resume_output_relevance_service import guard_resume_output_relevance  # noqa: E402
from app.services.resume_output_quality_gate_service import evaluate_resume_output_quality  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import (  # noqa: E402
    aggregate_skill_evidence_from_ledger,
)
from app.services.resume_skill_evidence_guard_service import guard_resume_skill_evidence  # noqa: E402
from app.services.resume_skill_taxonomy_service import calibrate_resume_skill_taxonomy  # noqa: E402
from app.services.technical_term_disambiguation_service import (  # noqa: E402
    resolve_technical_terms,
    resolve_technical_terms_from_ledger,
)


RAW = """项目：知识库检索工具
使用 FastAPI 实现资料检索接口，并完成访问 Token 鉴权校验。
没有使用 Docker。"""


def _payload(*, detail: str = "完成接口联调") -> schemas.GenerationPayload:
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
            skills=["安全机制：Token"],
            projects=[{
                "name": "知识库检索工具",
                "meta": "项目经历",
                "time": "[待填写]",
                "intro": detail,
                "role": "",
                "details": [detail],
            }],
        ),
    )


def test_technical_term_resolution_reuses_compiled_ledger():
    build = build_canonical_semantic_build(RAW)

    assert resolve_technical_terms_from_ledger(build.ledger) == resolve_technical_terms(RAW)


def test_precomputed_term_resolutions_skip_raw_input_reparse(monkeypatch):
    build = build_canonical_semantic_build(RAW)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)
    resolutions = resolve_technical_terms_from_ledger(build.ledger)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("post-commit skill processing reparsed raw input")

    monkeypatch.setattr(evidence_service, "resolve_technical_terms", forbidden)
    monkeypatch.setattr(taxonomy_service, "resolve_technical_terms", forbidden)
    monkeypatch.setattr(relevance_service, "resolve_technical_terms", forbidden)

    payload = guard_resume_skill_evidence(
        _payload(),
        aggregated_evidence=evidence,
        term_resolutions=resolutions,
        write_log=False,
    )
    payload = calibrate_resume_skill_taxonomy(
        payload,
        term_resolutions=resolutions,
        write_log=False,
    )
    payload = guard_resume_output_relevance(
        payload,
        term_resolutions=resolutions,
        write_log=False,
    )

    assert "安全机制：Token 鉴权" in payload.resume_sections.skills


def test_canonical_body_sanitizer_does_not_strengthen_claims():
    payload = _payload(detail="我写了几个页面")

    canonical = sanitize_resume_body(payload, semantic_safe=True)
    legacy = sanitize_resume_body(payload)

    assert canonical.resume_sections.projects[0]["intro"] == "我写了几个页面"
    assert canonical.resume_sections.projects[0]["details"] == ["我写了几个页面"]
    assert "核心页面开发" in legacy.resume_sections.projects[0]["intro"]


def test_canonical_generation_has_no_post_commit_legacy_semantic_creator_calls():
    source = inspect.getsource(generation_service.create_generation)
    post_commit = source.split('"after_owner_freeze"', maxsplit=1)[1]

    for creator in (
        "cleanup_uncertain_expressions",
        "guard_project_specificity",
        "strengthen_weak_profile_payload",
        "ensure_semantic_units",
        "ensure_resume_summary_quality",
        "ensure_resume_text_integrity",
        "guard_hard_facts",
    ):
        assert f"{creator}(" not in post_commit

    assert "resolve_technical_terms_from_ledger(semantic_build.ledger)" in source
    assert "term_resolutions=technical_term_resolutions" in post_commit
    assert "request.raw_input" not in post_commit


def test_output_quality_observation_reuses_compiled_state(monkeypatch):
    build = build_canonical_semantic_build(RAW)
    evidence = aggregate_skill_evidence_from_ledger(build.ledger)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("quality observation rebuilt the fact ledger")

    monkeypatch.setattr(output_quality_service, "build_experience_fact_ledger", forbidden)

    result = evaluate_resume_output_quality(
        _payload(),
        semantic_build=build,
        skill_evidence=evidence,
        write_log=False,
    )

    assert result.fact_coverage_score >= 0
