"""Deterministic, request-local delivery revision construction.

This module deliberately has no semantic dependencies.  It receives the
already validated delivery payload, removes only documented internal delivery
metadata, and serializes the exact JSON that will be stored in
``GenerationResult.result_json``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_slot_service import strip_experience_slot_metadata
from .project_hierarchy_service import strip_project_hierarchy_metadata


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "immutable_delivery_revision.jsonl"


def _fingerprint(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:24]


def _visible_projection(payload: schemas.GenerationPayload) -> dict:
    sections = payload.resume_sections
    return {
        "personal_info": sections.personal_info,
        "education": sections.education,
        "summary": sections.summary,
        "skills": sections.skills,
        "projects": [
            {
                key: project.get(key)
                for key in (
                    "name", "position", "meta", "time", "intro", "role", "details",
                    "source_experience_id", "source_fact_ids", "role_source_fact_ids",
                    "detail_fact_ids", "source_claim_ids", "role_source_claim_ids",
                    "detail_claim_ids",
                )
                if key in project
            }
            for project in sections.projects
        ],
    }


def _detail_count(payload: schemas.GenerationPayload) -> int:
    return sum(len(project.get("details", []) or []) for project in payload.resume_sections.projects)


@dataclass(frozen=True)
class ImmutableDeliveryRevision:
    payload: schemas.GenerationPayload
    serialized_payload: str
    revision_fingerprint: str
    visible_content_fingerprint: str
    project_count: int
    detail_count: int
    gate_passed: bool


def build_immutable_delivery_revision(
    payload: schemas.GenerationPayload,
    *,
    gate_passed: bool,
) -> ImmutableDeliveryRevision:
    """Freeze the final delivery payload without reinterpreting its semantics."""
    public_payload = strip_project_hierarchy_metadata(payload)
    public_payload = strip_experience_slot_metadata(public_payload)
    serialized_payload = public_payload.model_dump_json()
    canonical_json = json.loads(serialized_payload)
    return ImmutableDeliveryRevision(
        payload=schemas.GenerationPayload.model_validate_json(serialized_payload),
        serialized_payload=serialized_payload,
        revision_fingerprint=_fingerprint(canonical_json),
        visible_content_fingerprint=_fingerprint(_visible_projection(public_payload)),
        project_count=len(public_payload.resume_sections.projects),
        detail_count=_detail_count(public_payload),
        gate_passed=gate_passed,
    )


def revision_matches_serialized_payload(
    revision: ImmutableDeliveryRevision,
    serialized_payload: str,
) -> bool:
    try:
        return revision.revision_fingerprint == _fingerprint(json.loads(serialized_payload))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False


def revision_preserves_visible_delivery(
    payload: schemas.GenerationPayload,
    revision: ImmutableDeliveryRevision,
) -> bool:
    """Allow only documented internal metadata removal at the revision boundary."""
    return _fingerprint(_visible_projection(payload)) == revision.visible_content_fingerprint


def write_immutable_delivery_revision_log(
    revision: ImmutableDeliveryRevision,
    *,
    request_id: str,
    attempt_id: str,
    generation_result_id: int | None,
    persisted_fingerprint_match: bool,
    response_fingerprint_match: bool,
    render_source: str = "generation_result.result_json",
) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "request_id": request_id,
            "attempt_id": attempt_id,
            "generation_result_id": generation_result_id,
            "revision_fingerprint": revision.revision_fingerprint,
            "visible_content_fingerprint": revision.visible_content_fingerprint,
            "project_count": revision.project_count,
            "detail_count": revision.detail_count,
            "gate_passed": revision.gate_passed,
            "persisted_fingerprint_match": persisted_fingerprint_match,
            "response_fingerprint_match": response_fingerprint_match,
            "render_source": render_source,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return
