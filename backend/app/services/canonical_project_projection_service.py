"""Deterministic owner-scoped project candidates from the canonical Ledger.

This service fills only a provenance gap: it projects already eligible facts
for an already known experience when the LLM did not produce a deliverable
owner-bound project.  It never reads raw input, scores titles, or freezes an
owner itself.
"""

from __future__ import annotations

import json
import copy
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .canonical_consumer_view_service import CanonicalPlannerView
from .canonical_display_name_service import NAME_PENDING_DISPLAY
from .experience_slot_service import CanonicalProjectionFreezeStats
from .structured_log_service import stable_hash
from .experience_fact_ledger_service import ExperienceFact
from .fact_coverage_guard_service import MAX_PROJECT_DETAILS, MAX_TOTAL_DETAILS


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_project_projection.jsonl"


@dataclass(frozen=True)
class CanonicalProjectProjectionPlan:
    candidates: tuple[dict, ...]
    eligible_owner_count: int
    owners_without_bound_project_count: int
    candidate_skipped_existing_count: int
    projected_fact_count: int
    pending_name_owner_ids: tuple[str, ...]
    pending_time_owner_ids: tuple[str, ...]
    projection_fingerprint: str
    # References to existing Ledger facts, never a second extracted state.
    detail_projections: tuple[tuple[str, str, tuple[ExperienceFact, ...]], ...] = ()
    detail_skip_counts: tuple[tuple[str, int], ...] = ()


def _project_fingerprint(project: dict) -> str:
    return stable_hash(json.dumps(project, sort_keys=True, ensure_ascii=False), purpose="projection_target")


def _field_fact_evidence(project: dict, facts: tuple[ExperienceFact, ...]) -> tuple[set[str], bool]:
    """Read exact rows only. Project aggregates cannot prove a field's content."""
    local = {fact.fact_id: fact for fact in facts}
    rows = [
        (project.get(field), project.get(f"{field}_source_fact_ids", []), project.get(f"{field}_source_claim_ids", []))
        for field in ("intro", "role")
    ]
    fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
    claim_rows = project.get("detail_claim_ids") if isinstance(project.get("detail_claim_ids"), list) else []
    for index, detail in enumerate(project.get("details", []) or []):
        rows.append((detail, fact_rows[index] if index < len(fact_rows) else [],
                     claim_rows[index] if index < len(claim_rows) else []))
    covered: set[str] = set()
    ambiguous = False
    for text, ids, claims in rows:
        if not str(text or "").strip():
            continue
        if not isinstance(ids, list) or not isinstance(claims, list) or not ids or any(i not in local for i in ids):
            ambiguous = True
            continue
        if set(claims) != {local[i].claim_id for i in ids}:
            ambiguous = True
            continue
        covered.update(ids)
    return covered, ambiguous


def _plan_existing_details(payload, planner_view, candidates):
    additions = []
    skips = Counter()
    total = sum(len(p.get("details", []) or []) for p in [*payload.resume_sections.projects, *candidates])
    for owner in planner_view.experience_ids:
        targets = [p for p in payload.resume_sections.projects
                   if p.get("immutable_source_experience_id") == owner and p.get("source_binding_locked") is True]
        if len(targets) != 1:
            skips["no_frozen_target" if not targets else "multiple_frozen_targets"] += 1
            continue
        project = targets[0]
        if project.get("source_experience_id") != owner:
            skips["owner_conflict"] += 1
            continue
        scope = planner_view.owner_scope(owner)
        facts = tuple(f for f in planner_view.eligible_facts(owner) if f.resume_ready_text)
        if not scope or any(f.claim_id not in scope.eligible_claim_ids for f in facts):
            skips["invalid_lineage"] += 1
            continue
        if (not set(project.get("source_fact_ids", []) or []).issubset(scope.eligible_fact_ids)
                or not set(project.get("source_claim_ids", []) or []).issubset(scope.eligible_claim_ids)):
            skips["invalid_aggregate_reference"] += 1
            continue
        covered, ambiguous = _field_fact_evidence(project, facts)
        # Do not duplicate unbound wording or promote an aggregate to an intro
        # binding. That requires evidence this planner does not possess.
        if ambiguous:
            skips["ambiguous_field_provenance"] += 1
            continue
        unknown = set(project.get("source_fact_ids", []) or []) - covered
        selected = []
        for fact in sorted(facts, key=lambda f: {"high": 0, "medium": 1, "low": 2}[f.importance]):
            if fact.fact_id in covered:
                continue
            if fact.fact_id in unknown:
                skips["aggregate_without_field_evidence"] += 1
                continue
            if fact.importance != "high" and len(covered) / max(1, len(facts)) >= 0.8:
                skips["recovery_condition_not_met"] += 1
                continue
            if len(project.get("details", []) or []) + len(selected) >= MAX_PROJECT_DETAILS or total >= MAX_TOTAL_DETAILS:
                skips["detail_limit"] += 1
                continue
            if fact.resume_ready_text in project.get("details", []):
                skips["existing_wording_without_binding"] += 1
                continue
            selected.append(fact)
            covered.add(fact.fact_id)
            total += 1
        if selected:
            additions.append((owner, _project_fingerprint(project), tuple(selected)))
    return tuple(additions), tuple(sorted(skips.items()))


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
    pending_time_owner_ids: list[str] = []

    for owner in planner_view.experience_ids:
        scope = planner_view.owner_scope(owner)
        facts = planner_view.eligible_facts(owner)
        qualification = planner_view.display_name_qualification_for_owner(owner)
        time_decision = planner_view.experience_time_decision_for_owner(owner)
        if not scope or not facts or qualification is None or time_decision is None:
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
        if not time_decision.qualified:
            pending_time_owner_ids.append(owner)
        candidates.append({
            "name": name,
            "meta": scope.canonical_experience_type,
            "time": time_decision.display_time,
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

    detail_projections, detail_skip_counts = _plan_existing_details(payload, planner_view, candidates)
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
        "pending_time_owner_ids": sorted(pending_time_owner_ids),
        "view": planner_view.fingerprint,
        "detail_projections": [(owner, fingerprint, [f.fact_id for f in facts]) for owner, fingerprint, facts in detail_projections],
        "detail_skip_counts": detail_skip_counts,
    }
    return CanonicalProjectProjectionPlan(
        candidates=tuple(candidates),
        eligible_owner_count=eligible_owner_count,
        owners_without_bound_project_count=len(candidates),
        candidate_skipped_existing_count=skipped_existing,
        projected_fact_count=projected_fact_count,
        pending_name_owner_ids=tuple(pending_name_owner_ids),
        pending_time_owner_ids=tuple(pending_time_owner_ids),
        projection_fingerprint=stable_hash(
            json.dumps(safe, sort_keys=True), purpose="canonical_project_projection",
        ),
        detail_projections=detail_projections,
        detail_skip_counts=detail_skip_counts,
    )


def append_canonical_project_projection_candidates(
    payload: schemas.GenerationPayload,
    plan: CanonicalProjectProjectionPlan,
) -> schemas.GenerationPayload:
    """Apply local additions once; existing wording and authority stay intact."""
    updated = payload.model_copy(deep=True)
    for owner, fingerprint, facts in plan.detail_projections:
        targets = [p for p in updated.resume_sections.projects
                   if p.get("immutable_source_experience_id") == owner and p.get("source_binding_locked") is True]
        if len(targets) != 1 or _project_fingerprint(targets[0]) != fingerprint:
            continue
        project = targets[0]
        count = len(project.get("details", []) or [])
        # Empty rows retain original indexes; stale orphan rows cannot attach
        # themselves to newly appended text.
        for key in ("detail_fact_ids", "detail_claim_ids"):
            rows = project.get(key, [])
            project[key] = [rows[i] if i < len(rows) and isinstance(rows[i], list) else [] for i in range(count)]
        for fact in facts:
            project.setdefault("details", []).append(fact.resume_ready_text)
            project["detail_fact_ids"].append([fact.fact_id])
            project["detail_claim_ids"].append([fact.claim_id])
            for key, value in (("source_fact_ids", fact.fact_id), ("source_claim_ids", fact.claim_id)):
                if value not in project.setdefault(key, []):
                    project[key].append(value)
    existing = _bound_owner_ids(updated)
    updated.resume_sections.projects.extend(copy.deepcopy(candidate) for candidate in plan.candidates
                                           if candidate["source_experience_id"] not in existing)
    if plan.pending_name_owner_ids:
        question = "请补充尚未明确命名的项目、实习、科研课题、竞赛或活动名称。"
        if question not in updated.missing_questions:
            updated.missing_questions.append(question)
    if plan.pending_time_owner_ids:
        question = "请补充尚未明确的经历起止时间或学期。"
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
    payload: schemas.GenerationPayload | None = None,
) -> None:
    """Persist aggregate-only activation evidence; never serialize candidate text."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        selected_ids = {f.fact_id for _, _, facts in plan.detail_projections for f in facts}
        retained_ids = set()
        if payload is not None:
            for owner, _, facts in plan.detail_projections:
                for project in payload.resume_sections.projects:
                    if project.get("immutable_source_experience_id") == owner and project.get("source_binding_locked") is True:
                        covered, _ = _field_fact_evidence(project, facts)
                        retained_ids.update(covered & selected_ids)
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
            "pending_time_owner_count": len(plan.pending_time_owner_ids),
            "projected_fact_count": plan.projected_fact_count,
            "projection_fingerprint": plan.projection_fingerprint,
            "detail_selected_fact_ids": sorted(selected_ids),
            "detail_selected_count": len(selected_ids),
            "detail_retained_count": len(retained_ids) if payload is not None else None,
            "detail_unretained_fact_ids": sorted(selected_ids - retained_ids) if payload is not None else [],
            "detail_skip_counts": dict(plan.detail_skip_counts),
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return
