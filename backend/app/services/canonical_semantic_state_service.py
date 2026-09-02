import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .experience_fact_ledger_service import (
    ExperienceFactLedger,
    build_experience_fact_ledger_from_components,
)
from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .input_claim_resolution_service import ClaimResolution, ELIGIBLE, resolve_experience_claims
from .input_semantic_role_service import InputSemanticAnalysis, analyze_experience_semantics
from .long_input_service import LongInputContext, analyze_long_input
from .structured_log_service import stable_hash


SEMANTIC_SCHEMA_VERSION = "canonical-semantic-state/v1"
LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_semantic_state.jsonl"
OWNERSHIP_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_fact_ownership.jsonl"
SCOPED_ACCESS_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_scoped_fact_access.jsonl"
_NON_RESUME_ROLES = {"USER_INSTRUCTION", "NEGATIVE_CONSTRAINT", "UNCERTAIN_FACT"}
CANONICAL_EXPERIENCE_TYPES = (
    "项目经历",
    "实习经历",
    "科研经历",
    "竞赛获奖",
    "竞赛经历",
    "开源经历",
    "校园 / 社团经历",
)


@dataclass(frozen=True)
class CanonicalSemanticSource:
    experience_input_id: int | None
    raw_input_hash: str
    semantic_schema_version: str = SEMANTIC_SCHEMA_VERSION


@dataclass(frozen=True)
class CanonicalExperience:
    experience_id: str
    canonical_name: str
    aliases: tuple[str, ...]
    preliminary_experience_type: str
    canonical_experience_type: str
    type_source: str
    type_explicit: bool
    type_confidence: float
    source_span: tuple[int, int]


@dataclass(frozen=True)
class CanonicalClaim:
    claim_id: str
    source_experience_id: str
    semantic_role: str
    certainty: str
    polarity: str
    temporal_status: str
    eligibility: str
    source_span: tuple[int, int]


@dataclass(frozen=True)
class CanonicalFactProvenance:
    source_span: tuple[int, int]
    semantic_unit_id: str
    fact_type: str
    evidence_type: str
    explicit: bool


@dataclass(frozen=True)
class CanonicalFact:
    fact_id: str
    source_experience_id: str
    source_claim_ids: tuple[str, ...]
    eligibility: str
    provenance: CanonicalFactProvenance


@dataclass(frozen=True)
class CanonicalStateValidation:
    valid: bool
    issue_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalExperienceTypeDecision:
    experience_id: str
    canonical_experience_type: str
    type_source: str
    explicit: bool
    confidence: float


@dataclass(frozen=True)
class CanonicalFactOwnershipIndex:
    """Request-scoped owner index projected from the canonical ledger.

    It deliberately contains identifiers only.  Presentation code may use it to
    validate ownership, but never needs a second copy of user text to do so.
    """

    fact_owner_by_id: dict[str, str]
    claim_owner_by_id: dict[str, str]
    eligible_fact_ids_by_experience: dict[str, tuple[str, ...]]
    eligible_claim_ids_by_experience: dict[str, tuple[str, ...]]
    source_experience_ids: tuple[str, ...]
    ownership_fingerprint: str

    def fact_owner(self, fact_id: str) -> str:
        return self.fact_owner_by_id.get(str(fact_id or ""), "")

    def claim_owner(self, claim_id: str) -> str:
        return self.claim_owner_by_id.get(str(claim_id or ""), "")


@dataclass(frozen=True)
class CanonicalFactScope:
    """Identifier-only read permission for one frozen experience owner.

    The scope deliberately stores no user text. Callers provide the existing
    request-local ledger when they need the eligible facts for this owner.
    """

    source_experience_id: str
    eligible_fact_ids: tuple[str, ...]
    eligible_claim_ids: tuple[str, ...]

    def permits_fact(self, fact_id: str) -> bool:
        return str(fact_id or "") in self.eligible_fact_ids

    def permits_claim(self, claim_id: str) -> bool:
        return str(claim_id or "") in self.eligible_claim_ids

    def eligible_facts(self, ledger: ExperienceFactLedger) -> list:
        return [
            fact
            for fact in ledger.for_experience(self.source_experience_id)
            if self.permits_fact(fact.fact_id)
        ]


@dataclass
class CanonicalScopedFactAccessStats:
    """Aggregate-only observability for post-freeze scoped consumers."""

    scoped_read_count: int = 0
    rejected_cross_owner_access_count: int = 0
    local_fact_recovered_count: int = 0
    unowned_project_skipped_count: int = 0
    raw_input_fallback_blocked_count: int = 0

    def record_scope_read(self) -> None:
        self.scoped_read_count += 1


def canonical_fact_scope_for_owner(
    ownership_index: CanonicalFactOwnershipIndex | None,
    source_experience_id: str,
) -> CanonicalFactScope | None:
    """Return the eligible-only fact view for a canonical owner, if known."""
    owner = str(source_experience_id or "")
    if ownership_index is None or owner not in ownership_index.source_experience_ids:
        return None
    return CanonicalFactScope(
        source_experience_id=owner,
        eligible_fact_ids=ownership_index.eligible_fact_ids_by_experience.get(owner, ()),
        eligible_claim_ids=ownership_index.eligible_claim_ids_by_experience.get(owner, ()),
    )


@dataclass(frozen=True)
class CanonicalSemanticState:
    source: CanonicalSemanticSource
    experiences: tuple[CanonicalExperience, ...]
    claims: tuple[CanonicalClaim, ...]
    facts: tuple[CanonicalFact, ...]
    state_fingerprint: str
    validation: CanonicalStateValidation

    @property
    def eligible_fact_count(self) -> int:
        return len(self.facts)


@dataclass
class CanonicalSemanticBuild:
    """Request-scoped semantic compilation; never persisted or passed to presentation."""

    long_input_context: LongInputContext
    raw_input_hash: str
    identities: tuple[ExperienceIdentity, ...]
    experience_type_decisions: tuple[CanonicalExperienceTypeDecision, ...]
    semantic_analyses: tuple[InputSemanticAnalysis, ...]
    claim_resolutions: tuple[ClaimResolution, ...]
    ledger: ExperienceFactLedger
    ownership_index: CanonicalFactOwnershipIndex
    state: CanonicalSemanticState | None = None

    @property
    def canonical_type_by_experience_id(self) -> dict[str, CanonicalExperienceTypeDecision]:
        return {item.experience_id: item for item in self.experience_type_decisions}


def _fingerprint(
    source: CanonicalSemanticSource,
    experiences: tuple[CanonicalExperience, ...],
    claims: tuple[CanonicalClaim, ...],
    facts: tuple[CanonicalFact, ...],
) -> str:
    payload = {
        "source": asdict(source),
        "experiences": [asdict(item) for item in experiences],
        "claims": [asdict(item) for item in claims],
        "facts": [asdict(item) for item in facts],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _validate(
    experiences: tuple[CanonicalExperience, ...],
    claims: tuple[CanonicalClaim, ...],
    facts: tuple[CanonicalFact, ...],
) -> CanonicalStateValidation:
    issues: set[str] = set()
    experience_ids = [item.experience_id for item in experiences]
    claim_ids = [item.claim_id for item in claims]
    fact_ids = [item.fact_id for item in facts]
    if len(experience_ids) != len(set(experience_ids)):
        issues.add("DUPLICATE_EXPERIENCE_ID")
    if len(claim_ids) != len(set(claim_ids)):
        issues.add("DUPLICATE_CLAIM_ID")
    if len(fact_ids) != len(set(fact_ids)):
        issues.add("DUPLICATE_FACT_ID")

    experience_id_set = set(experience_ids)
    claims_by_id = {item.claim_id: item for item in claims}
    for experience in experiences:
        if experience.canonical_experience_type not in CANONICAL_EXPERIENCE_TYPES:
            issues.add("INVALID_CANONICAL_EXPERIENCE_TYPE")
    for claim in claims:
        if claim.source_experience_id not in experience_id_set:
            issues.add("CLAIM_OWNER_MISSING")
    for fact in facts:
        if fact.source_experience_id not in experience_id_set:
            issues.add("FACT_OWNER_MISSING")
        if fact.eligibility != ELIGIBLE:
            issues.add("INELIGIBLE_FACT_PRESENT")
        if not fact.source_claim_ids:
            issues.add("FACT_PROVENANCE_MISSING")
        for claim_id in fact.source_claim_ids:
            claim = claims_by_id.get(claim_id)
            if claim is None:
                issues.add("FACT_CLAIM_MISSING")
                continue
            if claim.source_experience_id != fact.source_experience_id:
                issues.add("FACT_CLAIM_OWNER_MISMATCH")
            if claim.eligibility != ELIGIBLE or claim.semantic_role in _NON_RESUME_ROLES:
                issues.add("INELIGIBLE_CLAIM_FACT_PRESENT")
    return CanonicalStateValidation(valid=not issues, issue_codes=tuple(sorted(issues)))


def _build_experience_type_decision(identity: ExperienceIdentity) -> CanonicalExperienceTypeDecision:
    declared = str(identity.declared_experience_type or "")
    if declared in CANONICAL_EXPERIENCE_TYPES:
        return CanonicalExperienceTypeDecision(
            experience_id=identity.experience_id,
            canonical_experience_type=declared,
            type_source="declared_experience_type",
            explicit=True,
            confidence=1.0,
        )
    inherited = str(identity.experience_type or "")
    resolved = inherited if inherited in CANONICAL_EXPERIENCE_TYPES else "项目经历"
    return CanonicalExperienceTypeDecision(
        experience_id=identity.experience_id,
        canonical_experience_type=resolved,
        type_source="experience_identity",
        explicit=False,
        confidence=0.9 if inherited in CANONICAL_EXPERIENCE_TYPES else 0.55,
    )


def _build_ownership_index(ledger: ExperienceFactLedger) -> CanonicalFactOwnershipIndex:
    fact_owner_by_id: dict[str, str] = {}
    claim_owner_by_id: dict[str, str] = {}
    eligible_fact_ids_by_experience: dict[str, list[str]] = {}
    eligible_claim_ids_by_experience: dict[str, list[str]] = {}

    for claim in ledger.claims:
        owner = str(claim.source_experience_id or "")
        if not owner:
            continue
        claim_owner_by_id[claim.claim_id] = owner
        if claim.eligibility == ELIGIBLE:
            eligible_claim_ids_by_experience.setdefault(owner, []).append(claim.claim_id)
    for fact in ledger.facts:
        owner = str(fact.experience_id or "")
        if not owner:
            continue
        fact_owner_by_id[fact.fact_id] = owner
        if fact.eligibility == ELIGIBLE:
            eligible_fact_ids_by_experience.setdefault(owner, []).append(fact.fact_id)

    serializable = {
        "fact_owner_by_id": fact_owner_by_id,
        "claim_owner_by_id": claim_owner_by_id,
        "eligible_fact_ids_by_experience": eligible_fact_ids_by_experience,
        "eligible_claim_ids_by_experience": eligible_claim_ids_by_experience,
    }
    encoded = json.dumps(serializable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return CanonicalFactOwnershipIndex(
        fact_owner_by_id=fact_owner_by_id,
        claim_owner_by_id=claim_owner_by_id,
        eligible_fact_ids_by_experience={key: tuple(value) for key, value in eligible_fact_ids_by_experience.items()},
        eligible_claim_ids_by_experience={key: tuple(value) for key, value in eligible_claim_ids_by_experience.items()},
        source_experience_ids=tuple(sorted({*fact_owner_by_id.values(), *claim_owner_by_id.values()})),
        ownership_fingerprint=hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24],
    )


def build_canonical_semantic_build(
    raw_input: str,
    *,
    long_input_context: LongInputContext | None = None,
) -> CanonicalSemanticBuild:
    """Compile request semantics once before projecting the shadow state."""
    context = long_input_context or analyze_long_input(raw_input)
    identities = tuple(build_experience_identities(raw_input, long_input_context=context))
    experience_type_decisions = tuple(_build_experience_type_decision(identity) for identity in identities)
    semantic_analyses = tuple(
        analyze_experience_semantics(identity.experience_id, identity.raw_text, identity.source_span[0])
        for identity in identities
    )
    claim_resolutions = tuple(
        resolve_experience_claims(identity.experience_id, identity.raw_text, identity.source_span[0])
        for identity in identities
    )
    ledger = build_experience_fact_ledger_from_components(
        raw_input,
        identities=identities,
        semantic_analyses=semantic_analyses,
        claim_resolutions=claim_resolutions,
    )
    ownership_index = _build_ownership_index(ledger)
    return CanonicalSemanticBuild(
        long_input_context=context,
        raw_input_hash=stable_hash(raw_input, purpose="canonical_semantic_state"),
        identities=identities,
        experience_type_decisions=experience_type_decisions,
        semantic_analyses=semantic_analyses,
        claim_resolutions=claim_resolutions,
        ledger=ledger,
        ownership_index=ownership_index,
    )


def build_canonical_semantic_state_from_build(
    build: CanonicalSemanticBuild,
    *,
    experience_input_id: int | None = None,
) -> CanonicalSemanticState:
    """Project a safe state snapshot from an already-compiled semantic request."""
    identities = build.identities
    ledger = build.ledger
    type_decisions = build.canonical_type_by_experience_id
    source = CanonicalSemanticSource(
        experience_input_id=experience_input_id,
        raw_input_hash=build.raw_input_hash,
    )
    experiences = tuple(
        CanonicalExperience(
            experience_id=identity.experience_id,
            canonical_name=identity.canonical_project_name or identity.title,
            aliases=tuple(identity.project_aliases),
            preliminary_experience_type=identity.declared_experience_type or identity.experience_type,
            canonical_experience_type=type_decisions[identity.experience_id].canonical_experience_type,
            type_source=type_decisions[identity.experience_id].type_source,
            type_explicit=type_decisions[identity.experience_id].explicit,
            type_confidence=type_decisions[identity.experience_id].confidence,
            source_span=identity.source_span,
        )
        for identity in identities
    )
    claims = tuple(
        CanonicalClaim(
            claim_id=claim.claim_id,
            source_experience_id=claim.source_experience_id,
            semantic_role=claim.semantic_role,
            certainty=claim.certainty,
            polarity=claim.polarity,
            temporal_status=claim.temporal_status,
            eligibility=claim.eligibility,
            source_span=claim.source_span,
        )
        for claim in ledger.claims
    )
    facts = tuple(
        CanonicalFact(
            fact_id=fact.fact_id,
            source_experience_id=fact.experience_id,
            source_claim_ids=tuple(item for item in [fact.claim_id] if item),
            eligibility=fact.eligibility,
            provenance=CanonicalFactProvenance(
                source_span=fact.source_span,
                semantic_unit_id=fact.semantic_unit_id,
                fact_type=fact.fact_type,
                evidence_type=fact.evidence_type,
                explicit=fact.explicit,
            ),
        )
        for fact in ledger.facts
    )
    validation = _validate(experiences, claims, facts)
    state = CanonicalSemanticState(
        source=source,
        experiences=experiences,
        claims=claims,
        facts=facts,
        state_fingerprint=_fingerprint(source, experiences, claims, facts),
        validation=validation,
    )
    build.state = state
    return state


def build_canonical_semantic_state(
    raw_input: str,
    *,
    experience_input_id: int | None = None,
) -> CanonicalSemanticState:
    """Backward-compatible Phase 1 convenience builder."""
    return build_canonical_semantic_state_from_build(
        build_canonical_semantic_build(raw_input),
        experience_input_id=experience_input_id,
    )


def write_canonical_semantic_state_log(
    state: CanonicalSemanticState,
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
) -> None:
    entry = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "stage": stage,
        "request_id": request_id,
        "attempt_id": attempt_id,
        "generation_result_id": generation_result_id,
        "experience_input_id": state.source.experience_input_id,
        "semantic_schema_version": state.source.semantic_schema_version,
        "experience_count": len(state.experiences),
        "claim_count": len(state.claims),
        "eligible_fact_count": state.eligible_fact_count,
        "state_fingerprint": state.state_fingerprint,
        "validation_result": "valid" if state.validation.valid else "invalid",
        "validation_issue_codes": list(state.validation.issue_codes),
    }
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return


def write_canonical_fact_ownership_log(
    ownership_index: CanonicalFactOwnershipIndex,
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
    frozen_project_count: int = 0,
    provisional_owner_count: int = 0,
    rejected_owner_binding_count: int = 0,
    owner_mutation_blocked_count: int = 0,
    foreign_fact_removed_count: int = 0,
    local_fact_recovered_count: int = 0,
    unresolved_owner_count: int = 0,
) -> None:
    """Write aggregate ownership observability without resume text or titles."""
    entry = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "stage": stage,
        "request_id": request_id,
        "attempt_id": attempt_id,
        "generation_result_id": generation_result_id,
        "frozen_project_count": frozen_project_count,
        "provisional_owner_count": provisional_owner_count,
        "rejected_owner_binding_count": rejected_owner_binding_count,
        "owner_mutation_blocked_count": owner_mutation_blocked_count,
        "foreign_fact_removed_count": foreign_fact_removed_count,
        "local_fact_recovered_count": local_fact_recovered_count,
        "unresolved_owner_count": unresolved_owner_count,
        "affected_source_experience_ids": list(ownership_index.source_experience_ids),
        "ownership_fingerprint": ownership_index.ownership_fingerprint,
    }
    try:
        OWNERSHIP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with OWNERSHIP_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return


def write_canonical_scoped_fact_access_log(
    ownership_index: CanonicalFactOwnershipIndex,
    access_stats: CanonicalScopedFactAccessStats,
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
) -> None:
    """Write only aggregate scoped-access diagnostics; never resume content."""
    entry = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "stage": stage,
        "request_id": request_id,
        "attempt_id": attempt_id,
        "generation_result_id": generation_result_id,
        "scoped_read_count": access_stats.scoped_read_count,
        "rejected_cross_owner_access_count": access_stats.rejected_cross_owner_access_count,
        "local_fact_recovered_count": access_stats.local_fact_recovered_count,
        "unowned_project_skipped_count": access_stats.unowned_project_skipped_count,
        "raw_input_fallback_blocked_count": access_stats.raw_input_fallback_blocked_count,
        "affected_source_experience_ids": list(ownership_index.source_experience_ids),
        "ownership_fingerprint": ownership_index.ownership_fingerprint,
    }
    try:
        SCOPED_ACCESS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SCOPED_ACCESS_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return
