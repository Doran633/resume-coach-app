"""Read-only consumer contracts projected from one semantic compilation.

The views in this module do not introduce another semantic model.  They retain
only identifiers and frozen decisions publicly, while resolving existing
request-local Ledger objects through scoped methods when a consumer needs them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from zoneinfo import ZoneInfo

from .canonical_semantic_state_service import CanonicalSemanticBuild
from .experience_fact_ledger_service import ExperienceFact, fact_match_score, normalize_fact_text
from .input_claim_resolution_service import DENIED, ELIGIBLE, PLANNED, UNCERTAIN
from .resume_skill_evidence_aggregation_service import AggregatedSkillEvidence
from .structured_log_service import stable_hash


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_consumer_views.jsonl"
_WITHHELD_ROLES = {"USER_INSTRUCTION", "NEGATIVE_CONSTRAINT", "UNCERTAIN_FACT"}


def _fingerprint(value: object) -> str:
    return stable_hash(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        purpose="canonical_consumer_views",
    )


@dataclass(frozen=True)
class CanonicalConsumerOwnerScope:
    """Identifier-only permissions for one frozen experience owner."""

    experience_id: str
    canonical_experience_id: str
    canonical_experience_type: str
    eligible_claim_ids: tuple[str, ...]
    withheld_claim_ids: tuple[str, ...]
    excluded_claim_ids: tuple[str, ...]
    eligible_fact_ids: tuple[str, ...]
    repair_eligible_fact_ids: tuple[str, ...]
    high_value_fact_ids: tuple[str, ...]

    def permits_fact(self, fact_id: str, *, repair: bool = False) -> bool:
        allowed = self.repair_eligible_fact_ids if repair else self.eligible_fact_ids
        return str(fact_id or "") in allowed

    def permits_claim(self, claim_id: str, *, repair: bool = False) -> bool:
        # Repair may only start from claims that remain eligible in the frozen state.
        return str(claim_id or "") in self.eligible_claim_ids


@dataclass
class CanonicalConsumerViewAccessStats:
    rejected_cross_owner_access_count: int = 0


@dataclass(frozen=True)
class CanonicalConsumerViews:
    """The sole request-scoped read contract for canonical consumers.

    ``_build`` is a private reference to the existing compilation, not a copy of
    input or fact text.  Public fields and logs remain identifier-only.
    """

    build_fingerprint: str
    owner_scopes: Mapping[str, CanonicalConsumerOwnerScope]
    fact_owner_by_id: Mapping[str, str]
    claim_owner_by_id: Mapping[str, str]
    verified_skill_evidence_keys: frozenset[str]
    explicit_experience_ids: frozenset[str]
    _build: CanonicalSemanticBuild = field(repr=False, compare=False)

    @property
    def planner_view(self) -> "CanonicalPlannerView":
        return CanonicalPlannerView(self)

    @property
    def guard_view(self) -> "CanonicalGuardView":
        return CanonicalGuardView(self)

    @property
    def repair_view(self) -> "CanonicalRepairView":
        return CanonicalRepairView(self)

    @property
    def presentation_view(self) -> "CanonicalPresentationView":
        return CanonicalPresentationView(self)

    @property
    def experience_ids(self) -> tuple[str, ...]:
        return tuple(self.owner_scopes)

    @property
    def eligible_fact_ids(self) -> frozenset[str]:
        return frozenset(
            fact_id
            for scope in self.owner_scopes.values()
            for fact_id in scope.eligible_fact_ids
        )

    @property
    def eligible_claim_ids(self) -> frozenset[str]:
        return frozenset(
            claim_id
            for scope in self.owner_scopes.values()
            for claim_id in scope.eligible_claim_ids
        )

    @property
    def withheld_claim_ids(self) -> frozenset[str]:
        return frozenset(
            claim_id
            for scope in self.owner_scopes.values()
            for claim_id in (*scope.withheld_claim_ids, *scope.excluded_claim_ids)
        )

    def scope_for_owner(self, experience_id: str) -> CanonicalConsumerOwnerScope | None:
        return self.owner_scopes.get(str(experience_id or ""))

    def facts_for_owner(
        self,
        experience_id: str,
        *,
        repair: bool = False,
        access_stats: CanonicalConsumerViewAccessStats | None = None,
    ) -> tuple[ExperienceFact, ...]:
        scope = self.scope_for_owner(experience_id)
        if scope is None:
            if access_stats is not None:
                access_stats.rejected_cross_owner_access_count += 1
            return ()
        return tuple(
            fact
            for fact in self._build.ledger.for_experience(scope.experience_id)
            if scope.permits_fact(fact.fact_id, repair=repair)
        )

    def fact_owner(self, fact_id: str) -> str:
        return self.fact_owner_by_id.get(str(fact_id or ""), "")

    def claim_owner(self, claim_id: str) -> str:
        return self.claim_owner_by_id.get(str(claim_id or ""), "")

    def permits_fact(
        self,
        experience_id: str,
        fact_id: str,
        *,
        repair: bool = False,
        access_stats: CanonicalConsumerViewAccessStats | None = None,
    ) -> bool:
        scope = self.scope_for_owner(experience_id)
        permitted = bool(scope and scope.permits_fact(fact_id, repair=repair))
        if not permitted and access_stats is not None:
            access_stats.rejected_cross_owner_access_count += 1
        return permitted

    def permits_claim(
        self,
        experience_id: str,
        claim_id: str,
        *,
        repair: bool = False,
        access_stats: CanonicalConsumerViewAccessStats | None = None,
    ) -> bool:
        scope = self.scope_for_owner(experience_id)
        permitted = bool(scope and scope.permits_claim(claim_id, repair=repair))
        if not permitted and access_stats is not None:
            access_stats.rejected_cross_owner_access_count += 1
        return permitted

    def matched_fact_ids(self, value: str, owner: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return local and foreign candidate IDs without exposing Fact text."""
        if not value:
            return (), ()
        local: list[str] = []
        foreign: list[str] = []
        for fact in self._build.ledger.facts:
            if fact_match_score(value, fact) < 0.82:
                continue
            if owner and self.permits_fact(owner, fact.fact_id):
                local.append(fact.fact_id)
            elif owner and fact.experience_id != owner:
                foreign.append(fact.fact_id)
            elif not owner and fact.fact_id in self.eligible_fact_ids:
                local.append(fact.fact_id)
        return tuple(dict.fromkeys(local)), tuple(dict.fromkeys(foreign))

    def has_lexical_withheld_overlap(self, value: str) -> bool:
        """Return an observer-only hint without exposing withheld claim text."""
        normalized = normalize_fact_text(value)
        if not normalized:
            return False
        return any(
            normalized and normalize_fact_text(claim.text) and (
                normalized in normalize_fact_text(claim.text)
                or normalize_fact_text(claim.text) in normalized
            )
            for claim in self._build.ledger.withheld_claims + self._build.ledger.excluded_claims
            if claim.claim_id in self.withheld_claim_ids
        )


@dataclass(frozen=True)
class CanonicalPlannerView:
    _views: CanonicalConsumerViews = field(repr=False, compare=False)

    @property
    def fingerprint(self) -> str:
        return self._views.build_fingerprint

    @property
    def experience_ids(self) -> tuple[str, ...]:
        return self._views.experience_ids

    def owner_scope(self, experience_id: str) -> CanonicalConsumerOwnerScope | None:
        return self._views.scope_for_owner(experience_id)

    def canonical_identity(self, experience_id: str) -> str:
        scope = self.owner_scope(experience_id)
        return scope.canonical_experience_id if scope else ""

    def identity_for_owner(self, experience_id: str):
        """Return the existing request-local identity for a permitted owner.

        This is intentionally an in-memory accessor rather than a new identity
        projection.  Callers must not serialize the returned object or use it
        to discover a different owner.
        """
        scope = self.owner_scope(experience_id)
        if scope is None:
            return None
        return next(
            (
                identity
                for identity in self._views._build.identities
                if identity.experience_id == scope.experience_id
            ),
            None,
        )

    @property
    def verified_skill_evidence_keys(self) -> frozenset[str]:
        return self._views.verified_skill_evidence_keys

    def eligible_facts(self, experience_id: str) -> tuple[ExperienceFact, ...]:
        return self._views.facts_for_owner(experience_id)


@dataclass(frozen=True)
class CanonicalGuardView:
    _views: CanonicalConsumerViews = field(repr=False, compare=False)

    @property
    def fingerprint(self) -> str:
        return self._views.build_fingerprint

    def fact_owner(self, fact_id: str) -> str:
        return self._views.fact_owner(fact_id)

    def claim_owner(self, claim_id: str) -> str:
        return self._views.claim_owner(claim_id)

    @property
    def ledger(self):
        """Read-only existing Ledger reference for validation-only consumers."""
        return self._views._build.ledger

    def permits_fact(self, experience_id: str, fact_id: str, *, access_stats: CanonicalConsumerViewAccessStats | None = None) -> bool:
        return self._views.permits_fact(experience_id, fact_id, access_stats=access_stats)

    def permits_claim(self, experience_id: str, claim_id: str, *, access_stats: CanonicalConsumerViewAccessStats | None = None) -> bool:
        return self._views.permits_claim(experience_id, claim_id, access_stats=access_stats)

    def eligible_facts(self, experience_id: str) -> tuple[ExperienceFact, ...]:
        return self._views.facts_for_owner(experience_id)

    def unprojected_eligible_fact_ids(self, projected_fact_ids: set[str]) -> frozenset[str]:
        return self._views.eligible_fact_ids - frozenset(projected_fact_ids)


@dataclass(frozen=True)
class CanonicalRepairView:
    _views: CanonicalConsumerViews = field(repr=False, compare=False)

    @property
    def fingerprint(self) -> str:
        return self._views.build_fingerprint

    def eligible_facts(self, experience_id: str) -> tuple[ExperienceFact, ...]:
        return self._views.facts_for_owner(experience_id, repair=True)

    def permits_fact(self, experience_id: str, fact_id: str) -> bool:
        return self._views.permits_fact(experience_id, fact_id, repair=True)

    def permits_claim(self, experience_id: str, claim_id: str) -> bool:
        return self._views.permits_claim(experience_id, claim_id, repair=True)


@dataclass(frozen=True)
class CanonicalPresentationView:
    """Owner-scoped authority for deterministic presentation transforms."""

    _views: CanonicalConsumerViews = field(repr=False, compare=False)

    @property
    def fingerprint(self) -> str:
        return self._views.build_fingerprint

    def owner_for_project(self, project: Mapping[str, object]) -> str:
        owner = str(project.get("immutable_source_experience_id") or "")
        if not owner or project.get("source_binding_locked") is not True:
            return ""
        return owner if self._views.scope_for_owner(owner) is not None else ""

    def eligible_facts(self, experience_id: str) -> tuple[ExperienceFact, ...]:
        return self._views.facts_for_owner(experience_id)

    def fact_ids_for_field(
        self,
        project: Mapping[str, object],
        field_name: str,
        detail_index: int | None = None,
    ) -> tuple[str, ...]:
        def ids(value: object) -> tuple[str, ...]:
            if not isinstance(value, (list, tuple, set)):
                return ()
            return tuple(dict.fromkeys(str(item) for item in value if str(item or "")))

        if field_name == "role":
            return ids(project.get("role_source_fact_ids")) or ids(project.get("source_fact_ids"))
        if field_name == "details" and detail_index is not None:
            rows = project.get("detail_fact_ids")
            if isinstance(rows, list) and detail_index < len(rows):
                return ids(rows[detail_index])
            return ()
        if field_name == "intro":
            return ids(project.get("source_fact_ids"))
        return ()

    def permits_project_field(
        self,
        project: Mapping[str, object],
        field_name: str,
        detail_index: int | None = None,
        *,
        access_stats: CanonicalConsumerViewAccessStats | None = None,
    ) -> bool:
        owner = self.owner_for_project(project)
        fact_ids = self.fact_ids_for_field(project, field_name, detail_index)
        permitted = bool(
            owner
            and fact_ids
            and all(self._views.permits_fact(owner, fact_id) for fact_id in fact_ids)
        )
        if not permitted and access_stats is not None:
            access_stats.rejected_cross_owner_access_count += 1
        return permitted

    def supports_global_text(self, value: str) -> bool:
        local, foreign = self._views.matched_fact_ids(value, "")
        return bool(local and not foreign)


def build_canonical_consumer_views(
    build: CanonicalSemanticBuild,
    skill_evidence: tuple[AggregatedSkillEvidence, ...] | list[AggregatedSkillEvidence] = (),
) -> CanonicalConsumerViews:
    """Project one immutable semantic compilation into consumer permissions."""
    if build.state is None or not build.state.validation.valid:
        raise ValueError("Canonical Consumer Views require a validated CanonicalSemanticState.")
    decisions = build.canonical_type_by_experience_id
    claims = {claim.claim_id: claim for claim in build.ledger.claims}
    scopes: dict[str, CanonicalConsumerOwnerScope] = {}
    explicit: set[str] = set()
    for identity in build.identities:
        owner = identity.experience_id
        decision = decisions.get(owner)
        if identity.declared_experience_type:
            explicit.add(owner)
        eligible_claim_ids = tuple(build.ownership_index.eligible_claim_ids_by_experience.get(owner, ()))
        repair_claim_ids = {
            claim_id
            for claim_id in eligible_claim_ids
            if (claim := claims.get(claim_id)) is not None
            and claim.eligibility == ELIGIBLE
            and claim.polarity != "negative"
            and claim.certainty not in {UNCERTAIN, DENIED}
            and claim.temporal_status != PLANNED
        }
        facts = tuple(
            fact
            for fact in build.ledger.for_experience(owner)
            if fact.fact_id in build.ownership_index.eligible_fact_ids_by_experience.get(owner, ())
        )
        scopes[owner] = CanonicalConsumerOwnerScope(
            experience_id=owner,
            canonical_experience_id=owner,
            canonical_experience_type=decision.canonical_experience_type if decision else identity.experience_type,
            eligible_claim_ids=eligible_claim_ids,
            withheld_claim_ids=tuple(
                claim.claim_id for claim in build.ledger.withheld_claims
                if claim.source_experience_id == owner
            ),
            excluded_claim_ids=tuple(
                claim.claim_id for claim in build.ledger.excluded_claims
                if claim.source_experience_id == owner
            ),
            eligible_fact_ids=tuple(fact.fact_id for fact in facts),
            repair_eligible_fact_ids=tuple(
                fact.fact_id for fact in facts if fact.claim_id in repair_claim_ids
            ),
            high_value_fact_ids=tuple(
                fact.fact_id for fact in facts if fact.importance == "high"
            ),
        )
    source = {
        "owners": {
            owner: {
                "canonical_experience_id": scope.canonical_experience_id,
                "type": scope.canonical_experience_type,
                "eligible_claim_ids": scope.eligible_claim_ids,
                "withheld_claim_ids": scope.withheld_claim_ids,
                "excluded_claim_ids": scope.excluded_claim_ids,
                "eligible_fact_ids": scope.eligible_fact_ids,
                "repair_eligible_fact_ids": scope.repair_eligible_fact_ids,
                "high_value_fact_ids": scope.high_value_fact_ids,
            }
            for owner, scope in sorted(scopes.items())
        },
        "fact_owners": build.ownership_index.fact_owner_by_id,
        "claim_owners": build.ownership_index.claim_owner_by_id,
        "skill_keys": sorted(
            stable_hash(row.term.lower(), purpose="canonical_consumer_skill")
            for row in skill_evidence
            if row.term
        ),
    }
    return CanonicalConsumerViews(
        build_fingerprint=_fingerprint(source),
        owner_scopes=MappingProxyType(dict(scopes)),
        fact_owner_by_id=MappingProxyType(dict(build.ownership_index.fact_owner_by_id)),
        claim_owner_by_id=MappingProxyType(dict(build.ownership_index.claim_owner_by_id)),
        verified_skill_evidence_keys=frozenset(source["skill_keys"]),
        explicit_experience_ids=frozenset(explicit),
        _build=build,
    )


def write_canonical_consumer_views_log(
    views: CanonicalConsumerViews,
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
    access_stats: CanonicalConsumerViewAccessStats | None = None,
) -> None:
    """Write aggregate-only view observability; never serialize view objects."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        scopes = tuple(views.owner_scopes.values())
        row = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "request_id": request_id,
            "attempt_id": attempt_id,
            "generation_result_id": generation_result_id,
            "stage": stage,
            "experience_count": len(scopes),
            "eligible_claim_count": sum(len(scope.eligible_claim_ids) for scope in scopes),
            "withheld_claim_count": sum(
                len(scope.withheld_claim_ids) + len(scope.excluded_claim_ids)
                for scope in scopes
            ),
            "eligible_fact_count": sum(len(scope.eligible_fact_ids) for scope in scopes),
            "high_value_fact_count": sum(len(scope.high_value_fact_ids) for scope in scopes),
            "owner_scope_count": len(scopes),
            "rejected_cross_owner_access_count": (
                access_stats.rejected_cross_owner_access_count if access_stats else 0
            ),
            "view_fingerprint": views.build_fingerprint,
            "validation_result": "valid",
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return
