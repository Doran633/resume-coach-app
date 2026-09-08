"""Deterministic owner-scoped project candidates from the canonical Ledger.

This service fills only a provenance gap: it projects already eligible facts
for an already known experience when the LLM did not produce a deliverable
owner-bound project.  It never reads raw input, scores titles, or freezes an
owner itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .canonical_consumer_view_service import CanonicalPlannerView
from .canonical_display_name_service import NAME_PENDING_DISPLAY
from .experience_slot_service import CanonicalProjectionFreezeStats
from .structured_log_service import stable_hash


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_project_projection.jsonl"


@dataclass(frozen=True)
class CanonicalProjectProjectionPlan:
    candidates: tuple[dict, ...]
    eligible_owner_count: int
    owners_without_bound_project_count: int
    candidate_skipped_existing_count: int
    projected_fact_count: int
    pending_name_owner_ids: tuple[str, ...]
    projection_fingerprint: str


def _bound_owner_ids(payload: schemas.GenerationPayload) -> set[str]:
    return {
        str(project.get("immutable_source_experience_id") or "").strip()
        for project in payload.resume_sections.projects
        if project.get("source_binding_locked")
        and str(project.get("immutable_source_experience_id") or "").strip()
    }


def plan_canonical_project_projections(
    payload: schemas.GenerationPayload,
    planner_view: CanonicalPlannerView,
) -> CanonicalProjectProjectionPlan:
    """Build candidates only from one owner's existing eligible facts."""
    bound_owners = _bound_owner_ids(payload)
    candidates: list[dict] = []
    eligible_owner_count = 0
    skipped_existing = 0
    projected_fact_count = 0
    pending_name_owner_ids: list[str] = []

    for owner in planner_view.experience_ids:
        scope = planner_view.owner_scope(owner)
        facts = planner_view.eligible_facts(owner)
        qualification = planner_view.display_name_qualification_for_owner(owner)
        if not scope or not facts or qualification is None:
            continue
        eligible_owner_count += 1
        if owner in bound_owners:
            skipped_existing += 1
            continue

        first, *remaining = facts
        detail_facts = list(remaining)
        if qualification.qualified:
            name = qualification.display_name
        else:
            # Keep the owner and eligible facts visible without inventing a
            # display name. The companion missing question is generic and
            # contains neither the title nor source text.
            name = NAME_PENDING_DISPLAY
            pending_name_owner_ids.append(owner)
        candidates.append({
            "name": name,
            "meta": scope.canonical_experience_type,
            "time": "[待填写]",
            "intro": first.resume_ready_text,
            "role": "",
            "details": [fact.resume_ready_text for fact in detail_facts],
            "source_experience_id": owner,
            "source_fact_ids": [first.fact_id],
            "role_source_fact_ids": [],
            "detail_fact_ids": [[fact.fact_id] for fact in detail_facts],
            "source_claim_ids": [first.claim_id],
            "role_source_claim_ids": [],
            "detail_claim_ids": [[fact.claim_id] for fact in detail_facts],
            "canonical_projection_candidate": True,
        })
        projected_fact_count += len(facts)

    safe = {
        "owners": sorted(
            str(candidate["source_experience_id"])
            for candidate in candidates
        ),
        "fact_counts": [
            len(candidate["source_fact_ids"]) + sum(len(row) for row in candidate["detail_fact_ids"])
            for candidate in candidates
        ],
        "pending_name_owner_ids": sorted(pending_name_owner_ids),
        "view": planner_view.fingerprint,
    }
    return CanonicalProjectProjectionPlan(
        candidates=tuple(candidates),
        eligible_owner_count=eligible_owner_count,
        owners_without_bound_project_count=len(candidates),
        candidate_skipped_existing_count=skipped_existing,
        projected_fact_count=projected_fact_count,
        pending_name_owner_ids=tuple(pending_name_owner_ids),
        projection_fingerprint=stable_hash(
            json.dumps(safe, sort_keys=True), purpose="canonical_project_projection",
        ),
    )


def append_canonical_project_projection_candidates(
    payload: schemas.GenerationPayload,
    plan: CanonicalProjectProjectionPlan,
) -> schemas.GenerationPayload:
    """Append planner output without editing any existing project."""
    updated = payload.model_copy(deep=True)
    updated.resume_sections.projects.extend(dict(candidate) for candidate in plan.candidates)
    if plan.pending_name_owner_ids:
        question = "请补充尚未明确命名的项目、实习、科研课题、竞赛或活动名称。"
        if question not in updated.missing_questions:
            updated.missing_questions.append(question)
    return updated


def write_canonical_project_projection_log(
    plan: CanonicalProjectProjectionPlan,
    freeze_stats: CanonicalProjectionFreezeStats,
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
) -> None:
    """Persist aggregate-only activation evidence; never serialize candidate text."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "request_id": request_id,
            "attempt_id": attempt_id,
            "generation_result_id": generation_result_id,
            "stage": stage,
            "eligible_owner_count": plan.eligible_owner_count,
            "owners_without_bound_project_count": plan.owners_without_bound_project_count,
            "candidate_created_count": len(plan.candidates),
            "candidate_frozen_count": freeze_stats.candidate_frozen_count,
            "candidate_rejected_count": freeze_stats.candidate_rejected_count,
            "candidate_skipped_existing_count": plan.candidate_skipped_existing_count,
            "pending_name_owner_count": len(plan.pending_name_owner_ids),
            "projected_fact_count": plan.projected_fact_count,
            "projection_fingerprint": plan.projection_fingerprint,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return
