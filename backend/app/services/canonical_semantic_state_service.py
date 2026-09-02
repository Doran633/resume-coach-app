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
_NON_RESUME_ROLES = {"USER_INSTRUCTION", "NEGATIVE_CONSTRAINT", "UNCERTAIN_FACT"}


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
    semantic_analyses: tuple[InputSemanticAnalysis, ...]
    claim_resolutions: tuple[ClaimResolution, ...]
    ledger: ExperienceFactLedger
    state: CanonicalSemanticState | None = None


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


def build_canonical_semantic_build(
    raw_input: str,
    *,
    long_input_context: LongInputContext | None = None,
) -> CanonicalSemanticBuild:
    """Compile request semantics once before projecting the shadow state."""
    context = long_input_context or analyze_long_input(raw_input)
    identities = tuple(build_experience_identities(raw_input, long_input_context=context))
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
    return CanonicalSemanticBuild(
        long_input_context=context,
        raw_input_hash=stable_hash(raw_input, purpose="canonical_semantic_state"),
        identities=identities,
        semantic_analyses=semantic_analyses,
        claim_resolutions=claim_resolutions,
        ledger=ledger,
    )


def build_canonical_semantic_state_from_build(
    build: CanonicalSemanticBuild,
    *,
    experience_input_id: int | None = None,
) -> CanonicalSemanticState:
    """Project a safe state snapshot from an already-compiled semantic request."""
    identities = build.identities
    ledger = build.ledger
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
