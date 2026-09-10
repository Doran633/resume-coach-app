"""Current-code replays for the immutable delivery revision boundary."""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service, generation_service  # noqa: E402
from app.services.docx_service import DocxRenderSourceError, create_docx  # noqa: E402
from app.services.immutable_delivery_revision_service import (  # noqa: E402
    build_immutable_delivery_revision,
    revision_matches_serialized_payload,
    revision_preserves_visible_delivery,
    write_immutable_delivery_revision_log,
)


RAW = "项目：资料检索工具\n使用 FastAPI 实现资料检索接口，并完成健康检查。"


def _project(index: int, details: list[str] | None = None) -> dict:
    return {
        "name": f"项目{index}", "meta": "项目经历", "time": "2026.09",
        "intro": f"完成项目{index}的核心功能。", "role": "参与功能实现。",
        "details": details or [f"项目{index}技术细节{i}" for i in range(1, 7)],
        "source_experience_id": f"EXP-{index:03d}",
        "immutable_source_experience_id": f"EXP-{index:03d}",
        "source_binding_locked": True,
        "source_fact_ids": [f"EXP-{index:03d}-F001"],
        "source_claim_ids": [f"EXP-{index:03d}-C001"],
        "role_source_fact_ids": [f"EXP-{index:03d}-F001"],
        "role_source_claim_ids": [f"EXP-{index:03d}-C001"],
        "detail_fact_ids": [[f"EXP-{index:03d}-F001"] for _ in range(6)],
        "detail_claim_ids": [[f"EXP-{index:03d}-C001"] for _ in range(6)],
        "canonical_project_name": f"内部项目{index}",
        "canonical_projection_candidate": True,
    }


def _payload(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=88, confirmed_facts=[], missing_questions=[],
        normal_version="", bold_version="", boundary_version="", recommended_version="",
        claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "测试用户"}, education={"学校": "测试学校"},
            summary=["具备项目实践能力。"], skills=["FastAPI"], projects=projects,
        ),
    )


def _database(payload: schemas.GenerationPayload, result_id: int = 911):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=1, anonymous_user_id=1, session_id="session", target_role="后端开发",
        mode="full_resume", packaging_level="稳妥", experience_type="项目经历", raw_input=RAW,
    ))
    db.add(models.GenerationResult(
        id=result_id, experience_input_id=1, completeness_score=payload.completeness_score,
        result_json=payload.model_dump_json(),
    ))
    db.commit()
    return db


def test_revision_is_deterministic_and_strips_only_documented_internal_metadata():
    payload = _payload([_project(1)])
    first = build_immutable_delivery_revision(payload, gate_passed=True)
    second = build_immutable_delivery_revision(payload, gate_passed=True)

    assert first.revision_fingerprint == second.revision_fingerprint
    assert revision_preserves_visible_delivery(payload, first)
    assert revision_matches_serialized_payload(first, first.serialized_payload)
    project = first.payload.resume_sections.projects[0]
    assert "immutable_source_experience_id" not in project
    assert "source_binding_locked" not in project
    assert "canonical_project_name" not in project
    assert "canonical_projection_candidate" not in project
    assert project["source_experience_id"] == "EXP-001"
    assert project["detail_fact_ids"] == [["EXP-001-F001"]] * 6
    assert project["detail_claim_ids"] == [["EXP-001-C001"]] * 6


def test_final_containment_happens_before_final_gate_recheck(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    events: list[str] = []
    real_containment = generation_service.contain_ownerless_projects
    real_gate = generation_service.validate_resume_delivery_quality

    def observe_containment(payload, *args, **kwargs):
        events.append(f"contain:{kwargs.get('stage')}")
        return real_containment(payload, *args, **kwargs)

    def observe_gate(payload, *args, **kwargs):
        events.append(f"gate:{kwargs.get('stage')}")
        return real_gate(payload, *args, write_log=False, **kwargs)

    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(generation_service, "LOG_DIR", tmp_path)
    monkeypatch.setattr(generation_service, "contain_ownerless_projects", observe_containment)
    monkeypatch.setattr(generation_service, "validate_resume_delivery_quality", observe_gate)
    try:
        generation_service.create_generation(
            db,
            schemas.GenerateRequest(
                anonymous_user_id="revision-user", session_id="revision-session",
                target_role="后端开发", mode="full_resume", packaging_level="稳妥",
                experience_type="项目经历", raw_input=RAW, attempt_id="attempt_v0911_order",
            ),
            request_id="req_v0911_order",
        )
        assert events.index("contain:generation_after_quality_repair") < events.index(
            "gate:after_final_owner_delivery_contract"
        )
    finally:
        db.close()


def test_persisted_and_returned_generation_payload_are_the_same_revision(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(generation_service, "LOG_DIR", tmp_path)
    try:
        response = generation_service.create_generation(
            db,
            schemas.GenerateRequest(
                anonymous_user_id="revision-return", session_id="revision-return-session",
                target_role="后端开发", mode="full_resume", packaging_level="稳妥",
                experience_type="项目经历", raw_input=RAW, attempt_id="attempt_v0911_return",
            ),
            request_id="req_v0911_return",
        )
        stored = db.get(models.GenerationResult, response.generation_result_id)
        assert stored is not None
        assert json.loads(stored.result_json) == response.result.model_dump(mode="json")
    finally:
        db.close()


def test_docx_renders_all_persisted_projects_and_details_without_mutating_result():
    payload = _payload([_project(index) for index in range(1, 7)])
    db = _database(payload)
    stored_before = db.get(models.GenerationResult, 911).result_json
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=911,
            ))
            text = "\n".join(item.text for item in Document(Path(tmpdir) / response.file_name).paragraphs)
            for index in range(1, 7):
                assert f"项目{index}｜项目经历｜2026.09" in text
                for detail_index in range(1, 7):
                    assert f"项目{index}技术细节{detail_index}" in text
            assert db.get(models.GenerationResult, 911).result_json == stored_before
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


def test_docx_rejects_instead_of_silently_removing_saved_project_content():
    project = _project(1, details=["面试准备：说明项目细节"])
    db = _database(_payload([project]), result_id=912)
    try:
        with pytest.raises(DocxRenderSourceError, match="无法在导出时静默删改"):
            create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=912,
            ))
        assert db.query(models.GeneratedFile).filter_by(generation_result_id=912).count() == 0
    finally:
        db.close()


def test_revision_log_is_aggregate_only(monkeypatch, tmp_path):
    payload = _payload([_project(1)])
    revision = build_immutable_delivery_revision(payload, gate_passed=True)
    from app.services import immutable_delivery_revision_service as service

    log_path = tmp_path / "immutable_delivery_revision.jsonl"
    monkeypatch.setattr(service, "LOG_PATH", log_path)
    write_immutable_delivery_revision_log(
        revision,
        request_id="req_v0911_log", attempt_id="attempt_v0911_log",
        generation_result_id=911, persisted_fingerprint_match=True,
        response_fingerprint_match=True,
    )
    content = log_path.read_text(encoding="utf-8")
    assert "项目1" not in content
    assert "FastAPI" not in content
    entry = json.loads(content)
    assert entry["persisted_fingerprint_match"] is True
    assert entry["response_fingerprint_match"] is True
