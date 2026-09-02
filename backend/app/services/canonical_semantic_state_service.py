import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .experience_fact_ledger_service import build_experience_fact_ledger
from .experience_identity_service import build_experience_identities
from .input_claim_resolution_service import ELIGIBLE
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


def build_canonical_semantic_state(
    raw_input: str,
    *,
    experience_input_id: int | None = None,
) -> CanonicalSemanticState:
    """Build a Phase 1 shadow snapshot without changing existing consumers."""
    identities = build_experience_identities(raw_input)
    ledger = build_experience_fact_ledger(raw_input)
    source = CanonicalSemanticSource(
        experience_input_id=experience_input_id,
        raw_input_hash=stable_hash(raw_input, purpose="canonical_semantic_state"),
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
    return CanonicalSemanticState(
        source=source,
        experiences=experiences,
        claims=claims,
        facts=facts,
        state_fingerprint=_fingerprint(source, experiences, claims, facts),
        validation=validation,
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
