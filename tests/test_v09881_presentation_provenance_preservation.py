from pathlib import Path
from types import SimpleNamespace
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import fact_coverage_guard_service as coverage_service  # noqa: E402
from app.services.canonical_projection_completeness_service import _project_fact_ids  # noqa: E402
from app.services.canonical_semantic_state_service import CanonicalFactOwnershipIndex  # noqa: E402
from app.services.experience_fact_ledger_service import ExperienceFact, ExperienceFactLedger  # noqa: E402
from app.services.experience_identity_service import ExperienceIdentity  # noqa: E402
from app.services.fact_coverage_guard_service import guard_fact_coverage  # noqa: E402
from app.services.resume_body_sanitizer_service import sanitize_resume_body  # noqa: E402


OWNER = "EXP-001"
FOREIGN_OWNER = "EXP-002"
FACT_ID = "EXP-001-F001"
SECOND_FACT_ID = "EXP-001-F002"
FOREIGN_FACT_ID = "EXP-002-F001"
CLAIM_ID = "EXP-001-C001"
SECOND_CLAIM_ID = "EXP-001-C002"
FOREIGN_CLAIM_ID = "EXP-002-C001"


def _payload(project: dict) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=100,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[project]),
    )


def _project(**overrides) -> dict:
    project = {
        "name": "示例项目",
        "meta": "项目经历",
        "time": "2026.01",
        "intro": "实现服务端接口",
        "role": "负责服务端接口开发",
        "details": ["完成服务端接口联调"],
        "source_experience_id": OWNER,
        "immutable_source_experience_id": OWNER,
        "source_binding_locked": True,
        "source_fact_ids": [FACT_ID, SECOND_FACT_ID],
        "role_source_fact_ids": [FACT_ID],
        "detail_fact_ids": [[SECOND_FACT_ID]],
        "source_claim_ids": [CLAIM_ID, SECOND_CLAIM_ID],
        "role_source_claim_ids": [CLAIM_ID],
        "detail_claim_ids": [[SECOND_CLAIM_ID]],
    }
    project.update(overrides)
    return project


def _build() -> SimpleNamespace:
    facts = [
        ExperienceFact(
            experience_id=OWNER,
            fact_id=FACT_ID,
            fact_type="技术实现",
            fact_text="负责服务端接口开发",
            importance="medium",
            explicit=True,
            resume_ready_text="负责服务端接口开发",
            source_span=(0, 8),
            immutable_experience_id=OWNER,
            claim_id=CLAIM_ID,
        ),
        ExperienceFact(
            experience_id=OWNER,
            fact_id=SECOND_FACT_ID,
            fact_type="联调",
            fact_text="完成服务端接口联调",
            importance="medium",
            explicit=True,
            resume_ready_text="完成服务端接口联调",
            source_span=(9, 16),
            immutable_experience_id=OWNER,
            claim_id=SECOND_CLAIM_ID,
        ),
    ]
    identity = ExperienceIdentity(
        experience_id=OWNER,
        experience_type="项目经历",
        title="示例项目",
        raw_text="",
        explicit_tech_terms=[],
        explicit_metrics=[],
        evidence_terms=[],
        risk_terms=[],
        supported_inference_terms=[],
        immutable_experience_id=OWNER,
    )
    ownership = CanonicalFactOwnershipIndex(
        fact_owner_by_id={FACT_ID: OWNER, SECOND_FACT_ID: OWNER, FOREIGN_FACT_ID: FOREIGN_OWNER},
        claim_owner_by_id={CLAIM_ID: OWNER, SECOND_CLAIM_ID: OWNER, FOREIGN_CLAIM_ID: FOREIGN_OWNER},
        eligible_fact_ids_by_experience={OWNER: (FACT_ID, SECOND_FACT_ID), FOREIGN_OWNER: ()},
        eligible_claim_ids_by_experience={OWNER: (CLAIM_ID, SECOND_CLAIM_ID), FOREIGN_OWNER: ()},
        source_experience_ids=(OWNER, FOREIGN_OWNER),
        ownership_fingerprint="test",
    )
    return SimpleNamespace(
        ledger=ExperienceFactLedger(facts=facts),
        identities=(identity,),
        ownership_index=ownership,
    )


def _covered(payload: schemas.GenerationPayload) -> schemas.GenerationPayload:
    build = _build()
    return guard_fact_coverage(
        payload,
        "",
        semantic_build=build,
        ownership_index=build.ownership_index,
        write_log=False,
    )


def test_sanitizer_preserves_field_bindings_and_keeps_distinct_provenance_rows():
    payload = _payload(_project(details=["相同描述", "相同描述", "", "相同描述"], detail_fact_ids=[[FACT_ID], [SECOND_FACT_ID], [FACT_ID], [FACT_ID]], detail_claim_ids=[[CLAIM_ID], [SECOND_CLAIM_ID], [CLAIM_ID], [CLAIM_ID]]))

    result = sanitize_resume_body(payload)
    project = result.resume_sections.projects[0]

    assert project["details"] == ["相同描述", "相同描述"]
    assert project["detail_fact_ids"] == [[FACT_ID], [SECOND_FACT_ID]]
    assert project["detail_claim_ids"] == [[CLAIM_ID], [SECOND_CLAIM_ID]]
    assert project["role_source_fact_ids"] == [FACT_ID]
    assert project["role_source_claim_ids"] == [CLAIM_ID]
    assert payload.resume_sections.projects[0]["detail_fact_ids"] == [[FACT_ID], [SECOND_FACT_ID], [FACT_ID], [FACT_ID]]


def test_sanitizer_drops_orphaned_bindings_when_every_visible_body_field_is_removed():
    payload = _payload(_project(intro="", role="", details=[""], source_fact_ids=[FACT_ID], role_source_fact_ids=[FACT_ID], detail_fact_ids=[[FACT_ID]], source_claim_ids=[CLAIM_ID], role_source_claim_ids=[CLAIM_ID], detail_claim_ids=[[CLAIM_ID]]))

    project = sanitize_resume_body(payload).resume_sections.projects[0]

    assert project["details"] == []
    assert not any(key in project for key in (
        "source_fact_ids", "role_source_fact_ids", "detail_fact_ids",
        "source_claim_ids", "role_source_claim_ids", "detail_claim_ids",
    ))


def test_canonical_coverage_preserves_intro_and_role_provenance_without_details():
    payload = _payload(_project(details=[], detail_fact_ids=[], detail_claim_ids=[]))

    result = _covered(sanitize_resume_body(payload))
    project = result.resume_sections.projects[0]

    assert _project_fact_ids(project) == (FACT_ID, SECOND_FACT_ID)
    assert project["role_source_fact_ids"] == [FACT_ID]
    assert project["source_claim_ids"] == [CLAIM_ID, SECOND_CLAIM_ID]
    assert project["role_source_claim_ids"] == [CLAIM_ID]


def test_canonical_coverage_keeps_valid_detail_binding_when_text_match_is_low(monkeypatch):
    payload = _payload(_project(details=["技术实现"], detail_fact_ids=[[FACT_ID]], detail_claim_ids=[[CLAIM_ID]]))
    fact = _build().ledger.facts[0]
    monkeypatch.setattr(coverage_service, "_best_fact", lambda *_args: (fact, 0.1))

    result = _covered(sanitize_resume_body(payload))
    project = result.resume_sections.projects[0]

    # Existing Coverage may append another local fact. The original low-score
    # detail must remain attached to its verified provenance.
    assert project["details"][0] == "技术实现"
    assert project["detail_fact_ids"][0] == [FACT_ID]
    assert project["detail_claim_ids"][0] == [CLAIM_ID]


def test_canonical_coverage_rejects_foreign_bindings_without_retaining_them():
    payload = _payload(_project(source_fact_ids=[FACT_ID, FOREIGN_FACT_ID], detail_fact_ids=[[FOREIGN_FACT_ID]], source_claim_ids=[CLAIM_ID, FOREIGN_CLAIM_ID], detail_claim_ids=[[FOREIGN_CLAIM_ID]]))

    result = _covered(sanitize_resume_body(payload))
    project = result.resume_sections.projects[0]

    assert FOREIGN_FACT_ID not in _project_fact_ids(project)
    assert FOREIGN_CLAIM_ID not in project["source_claim_ids"]
    assert all(FOREIGN_FACT_ID not in row for row in project["detail_fact_ids"])
    assert all(FOREIGN_CLAIM_ID not in row for row in project["detail_claim_ids"])


def test_canonical_provenance_cleanup_and_coverage_are_idempotent():
    payload = _payload(_project())

    first = _covered(sanitize_resume_body(payload))
    second = _covered(sanitize_resume_body(first))

    assert first.model_dump() == second.model_dump()
    assert payload.resume_sections.projects[0]["role_source_fact_ids"] == [FACT_ID]
