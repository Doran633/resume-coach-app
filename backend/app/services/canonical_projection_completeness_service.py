"""Read-only completeness tracing between canonical facts and visible projects.

The observer answers whether an already-eligible canonical fact reached a
project with an attributable owner.  It deliberately has no repair method and
retains only identifiers, counts, stages, and fingerprints in its logs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .. import schemas
from .canonical_consumer_view_service import CanonicalConsumerViews
from .experience_slot_service import OwnerDeliveryContractStats
from .structured_log_service import stable_hash


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_projection_completeness.jsonl"
_OWNER_FREEZE_STAGES = frozenset({
    "after_owner_freeze",
    "after_ownerless_containment",
    "after_presentation",
    "before_persistence",
    "generation_persisted",
})


def _ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(dict.fromkeys(str(item) for item in value if str(item or "")))


def _project_fact_ids(project: dict[str, Any]) -> tuple[str, ...]:
    values = list(_ids(project.get("source_fact_ids")))
    values.extend(_ids(project.get("role_source_fact_ids")))
    rows = project.get("detail_fact_ids")
    if isinstance(rows, list):
        for row in rows:
            values.extend(_ids(row))
    return tuple(dict.fromkeys(values))


def _project_owner(project: dict[str, Any]) -> str:
    return str(
        project.get("immutable_source_experience_id")
        or project.get("source_experience_id")
        or ""
    ).strip()


def _is_owner_bound(
    project: dict[str, Any],
    owner: str,
    *,
    persisted_projection: bool = False,
) -> bool:
    """Treat persisted source ownership as a prior frozen binding projection.

    ``strip_experience_slot_metadata`` removes the internal immutable/locked
    fields immediately before persistence.  The public persisted source ID is
    therefore the only available owner attachment at the final checkpoint.
    """
    immutable = str(project.get("immutable_source_experience_id") or "").strip()
    if immutable:
        return immutable == owner and bool(project.get("source_binding_locked"))
    return persisted_projection and str(project.get("source_experience_id") or "").strip() == owner


@dataclass(frozen=True)
class ProjectionOwnerSnapshot:
    experience_id: str
    canonical_experience_type: str
    eligible_claim_count: int
    eligible_fact_count: int
    high_value_fact_count: int
    projected_fact_count: int
    fact_binding_count: int
    owner_bound_project_count: int
    unowned_candidate_project_count: int
    removed_by_ownerless_containment_count: int
    unprojected_eligible_fact_count: int
    issue_codes: tuple[str, ...]
    status: str


@dataclass
class CanonicalProjectionCompletenessObserver:
    """Request-local projection audit; it never returns or changes a payload."""

    consumer_views: CanonicalConsumerViews
    request_id: str = ""
    attempt_id: str = ""
    generation_result_id: int | None = None
    sequence: int = 0
    events: list[dict[str, object]] = field(default_factory=list)
    _first_projection_gap: dict[str, str] = field(default_factory=dict, repr=False)
    _first_binding_gap: dict[str, str] = field(default_factory=dict, repr=False)
    _post_freeze_projection: dict[str, tuple[str, ...]] = field(default_factory=dict, repr=False)

    @property
    def fingerprint(self) -> str:
        return self.consumer_views.build_fingerprint

    def _owner_snapshot(
        self,
        payload: schemas.GenerationPayload,
        owner: str,
        *,
        stage: str,
        containment_stats: OwnerDeliveryContractStats | None,
    ) -> ProjectionOwnerSnapshot:
        scope = self.consumer_views.scope_for_owner(owner)
        if scope is None:
            raise ValueError("Canonical projection observation requires a canonical owner scope.")

        owner_projects = [
            project for project in payload.resume_sections.projects
            if _project_owner(project) == owner
        ]
        bound_projects = [
            project for project in owner_projects
            if _is_owner_bound(project, owner, persisted_projection=stage == "generation_persisted")
        ]
        bound_fact_ids = tuple(dict.fromkeys(
            fact_id
            for project in bound_projects
            for fact_id in _project_fact_ids(project)
            if self.consumer_views.permits_fact(owner, fact_id)
        ))
        projected_fact_ids = frozenset(bound_fact_ids)
        eligible_fact_ids = frozenset(scope.eligible_fact_ids)
        unprojected = eligible_fact_ids - projected_fact_ids
        issue_codes: list[str] = []
        if stage in _OWNER_FREEZE_STAGES and eligible_fact_ids and not bound_projects:
            issue_codes.append("EXPERIENCE_WITHOUT_VISIBLE_PROJECT")
        if stage in _OWNER_FREEZE_STAGES and unprojected:
            issue_codes.append("ELIGIBLE_FACT_UNPROJECTED")
        if bound_projects and not bound_fact_ids:
            issue_codes.append("OWNER_BOUND_PROJECT_WITHOUT_FACT_BINDING")
        previous_projected = self._post_freeze_projection.get(owner)
        if previous_projected is not None and stage in _OWNER_FREEZE_STAGES:
            if set(previous_projected) - projected_fact_ids:
                issue_codes.append("PROJECTION_DROPPED_AFTER_OWNER_FREEZE")
        if stage in _OWNER_FREEZE_STAGES:
            self._post_freeze_projection[owner] = tuple(sorted(projected_fact_ids))
        # The raw LLM response is intentionally observed, but it is not yet a
        # delivery projection contract.  Otherwise every LLM payload without
        # provenance would obscure the first actionable post-freeze gap.
        if stage in _OWNER_FREEZE_STAGES and unprojected and owner not in self._first_projection_gap:
            self._first_projection_gap[owner] = stage
        if stage in _OWNER_FREEZE_STAGES and bound_projects and not bound_fact_ids and owner not in self._first_binding_gap:
            self._first_binding_gap[owner] = stage

        removed_count = 0
        if containment_stats is not None and containment_stats.removed_unowned_project_count:
            # An ownerless candidate cannot be honestly attributed to any owner.
            # The request-level row records it separately; per-owner rows remain
            # intentionally unassigned rather than guessing.
            removed_count = 0
        status = "complete" if not issue_codes else "gap_observed"
        return ProjectionOwnerSnapshot(
            experience_id=owner,
            canonical_experience_type=scope.canonical_experience_type,
            eligible_claim_count=len(scope.eligible_claim_ids),
            eligible_fact_count=len(eligible_fact_ids),
            high_value_fact_count=len(scope.high_value_fact_ids),
            projected_fact_count=len(projected_fact_ids),
            fact_binding_count=len(bound_fact_ids),
            owner_bound_project_count=len(bound_projects),
            unowned_candidate_project_count=0,
            removed_by_ownerless_containment_count=removed_count,
            unprojected_eligible_fact_count=len(unprojected),
            issue_codes=tuple(issue_codes),
            status=status,
        )

    def checkpoint(
        self,
        payload: schemas.GenerationPayload,
        stage: str,
        *,
        parent_stage: str = "",
        containment_stats: OwnerDeliveryContractStats | None = None,
    ) -> None:
        """Record a privacy-safe projection checkpoint without mutating payload."""
        self.sequence += 1
        owners = tuple(sorted(self.consumer_views.experience_ids))
        unowned_count = sum(1 for project in payload.resume_sections.projects if not _project_owner(project))
        removed_count = containment_stats.removed_unowned_project_count if containment_stats else 0
        now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
        for owner in owners:
            snapshot = self._owner_snapshot(
                payload,
                owner,
                stage=stage,
                containment_stats=containment_stats,
            )
            row = {
                "created_at": now,
                "event_type": "projection_checkpoint",
                "request_id": self.request_id,
                "attempt_id": self.attempt_id,
                "generation_result_id": self.generation_result_id,
                "stage": stage,
                "parent_stage": parent_stage,
                "sequence": self.sequence,
                "experience_id": snapshot.experience_id,
                "canonical_experience_type": snapshot.canonical_experience_type,
                "eligible_claim_count": snapshot.eligible_claim_count,
                "eligible_fact_count": snapshot.eligible_fact_count,
                "high_value_fact_count": snapshot.high_value_fact_count,
                "projected_fact_count": snapshot.projected_fact_count,
                "fact_binding_count": snapshot.fact_binding_count,
                "owner_bound_project_count": snapshot.owner_bound_project_count,
                "unowned_candidate_project_count": snapshot.unowned_candidate_project_count,
                "removed_by_ownerless_containment_count": snapshot.removed_by_ownerless_containment_count,
                "unprojected_eligible_fact_count": snapshot.unprojected_eligible_fact_count,
                "first_projection_gap_stage": self._first_projection_gap.get(owner, ""),
                "first_binding_gap_stage": self._first_binding_gap.get(owner, ""),
                "issue_codes": list(snapshot.issue_codes),
                "status": snapshot.status,
                "view_fingerprint": self.fingerprint,
            }
            self.events.append(row)
        if containment_stats is not None and removed_count:
            self.events.append({
                "created_at": now,
                "event_type": "unassigned_ownerless_containment",
                "request_id": self.request_id,
                "attempt_id": self.attempt_id,
                "generation_result_id": self.generation_result_id,
                "stage": stage,
                "parent_stage": parent_stage,
                "sequence": self.sequence,
                "experience_id": "",
                "canonical_experience_type": "",
                "eligible_claim_count": 0,
                "eligible_fact_count": 0,
                "high_value_fact_count": 0,
                "projected_fact_count": 0,
                "fact_binding_count": 0,
                "owner_bound_project_count": 0,
                "unowned_candidate_project_count": containment_stats.unowned_candidate_count,
                "removed_by_ownerless_containment_count": removed_count,
                "unprojected_eligible_fact_count": 0,
                "first_projection_gap_stage": "",
                "first_binding_gap_stage": "",
                "issue_codes": ["OWNERLESS_CANDIDATE_REMOVED"],
                "status": "unassigned_gap_observed",
                "view_fingerprint": self.fingerprint,
            })

    def flush(self, generation_result_id: int | None = None) -> None:
        if generation_result_id is not None:
            self.generation_result_id = generation_result_id
        if not self.events:
            return
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                for event in self.events:
                    event["generation_result_id"] = self.generation_result_id
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            return


def projection_event_fingerprint(event: dict[str, object]) -> str:
    """Stable helper for query tooling and tests; never hashes user text."""
    safe = {
        key: event.get(key)
        for key in (
            "experience_id", "stage", "eligible_fact_count", "projected_fact_count",
            "fact_binding_count", "owner_bound_project_count", "issue_codes", "view_fingerprint",
        )
    }
    return stable_hash(json.dumps(safe, sort_keys=True), purpose="canonical_projection_completeness")
