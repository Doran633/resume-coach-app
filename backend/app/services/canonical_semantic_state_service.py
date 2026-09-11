import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .experience_fact_ledger_service import (
    ExperienceFactLedger,
    build_experience_fact_ledger_from_components,
)
from .canonical_display_name_service import (
    CanonicalDisplayNameQualification,
    build_canonical_display_name_qualifications,
)
from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .experience_type_resolution_service import resolve_identity_type
from .input_claim_resolution_service import (
    ClaimResolution,
    ELIGIBLE,
    claim_is_fact_eligible,
    effective_claim_eligibility,
    resolve_experience_claims,
)
from .input_semantic_role_service import InputSemanticAnalysis, analyze_experience_semantics
from .long_input_service import LongInputContext, analyze_long_input
from .structured_log_service import stable_hash


SEMANTIC_SCHEMA_VERSION = "canonical-semantic-state/v1"
LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_semantic_state.jsonl"
OWNERSHIP_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_fact_ownership.jsonl"
SCOPED_ACCESS_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_scoped_fact_access.jsonl"
FALLBACK_RECOVERY_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_fallback_recovery.jsonl"
ELIGIBILITY_INTEGRITY_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_eligibility_integrity.jsonl"
TIME_QUALIFICATION_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_experience_time_qualification.jsonl"
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


TIME_QUALIFIED = "qualified"
TIME_PENDING = "pending"
TIME_PENDING_DISPLAY = "时间：【待填写】"


@dataclass(frozen=True)
class CanonicalExperienceTimeDecision:
    """One owner-scoped, display-safe time decision from Semantic Compilation."""

    experience_id: str
    display_time: str
    candidate_source: str
    source_span: tuple[int, int]
    status: str
    reason_codes: tuple[str, ...]
    source_claim_ids: tuple[str, ...]
    time_fingerprint: str
    candidate_sources: tuple[str, ...] = ()
    rejected_candidate_reason_codes: tuple[str, ...] = ()

    @property
    def qualified(self) -> bool:
        return self.status == TIME_QUALIFIED and bool(self.display_time)


@dataclass(frozen=True)
class _CanonicalTimeCandidate:
    display_time: str
    source: str
    source_span: tuple[int, int]
    source_claim_ids: tuple[str, ...]
    specificity: int


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


@dataclass
class CanonicalFallbackRecoveryStats:
    """Aggregate-only diagnostics for the demoted fallback/recovery paths."""

    local_fact_detail_recovered_count: int = 0
    local_role_recovered_count: int = 0
    candidate_rejected_count: int = 0
    unowned_project_skipped_count: int = 0
    raw_input_rebuild_blocked_count: int = 0
    missing_question_count: int = 0


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
    display_name_qualifications: tuple[CanonicalDisplayNameQualification, ...]
    experience_time_decisions: tuple[CanonicalExperienceTimeDecision, ...]
    ledger: ExperienceFactLedger
    ownership_index: CanonicalFactOwnershipIndex
    state: CanonicalSemanticState | None = None

    @property
    def canonical_type_by_experience_id(self) -> dict[str, CanonicalExperienceTypeDecision]:
        return {item.experience_id: item for item in self.experience_type_decisions}

    @property
    def display_name_qualification_by_experience_id(self) -> dict[str, CanonicalDisplayNameQualification]:
        return {item.experience_id: item for item in self.display_name_qualifications}

    @property
    def experience_time_decision_by_experience_id(self) -> dict[str, CanonicalExperienceTimeDecision]:
        return {item.experience_id: item for item in self.experience_time_decisions}


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
        effective_eligibility, _ = effective_claim_eligibility(claim)
        if claim.eligibility != effective_eligibility:
            issues.add("CLAIM_ELIGIBILITY_CONTRACT_VIOLATION")
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
            if not claim_is_fact_eligible(claim):
                issues.add("INELIGIBLE_CLAIM_FACT_PRESENT")
    return CanonicalStateValidation(valid=not issues, issue_codes=tuple(sorted(issues)))


def _build_experience_type_decision(
    identity: ExperienceIdentity,
    claim_resolution: ClaimResolution,
) -> CanonicalExperienceTypeDecision:
    """Freeze exactly one owner-scoped relation decision during compilation.

    Segmentation may provide a useful provisional hint, but its keyword order
    is not a Canonical authority.  The existing type resolver receives only
    this owner's eligible Claim Resolution and is the sole source here.
    """
    resolution = resolve_identity_type(identity, claim_resolution)
    resolved = resolution.resolved_type
    if resolved not in CANONICAL_EXPERIENCE_TYPES:
        resolved = "项目经历"
    return CanonicalExperienceTypeDecision(
        experience_id=identity.experience_id,
        canonical_experience_type=resolved,
        type_source=(
            "declared_experience_type"
            if resolution.resolution_method == "declared_experience_type"
            else resolution.resolution_method
        ),
        explicit=resolution.resolution_method == "declared_experience_type",
        confidence=resolution.confidence,
    )


_DATE_TOKEN = (
    r"(?:19|20)\d{2}(?:\s*年(?:\s*\d{1,2}\s*月?)?|\s*[./]\s*\d{1,2})?"
)
_TIME_RANGE_PATTERN = re.compile(
    rf"(?P<start>{_DATE_TOKEN})\s*(?:[-—–~～]|至|到)\s*(?P<end>{_DATE_TOKEN}|至今|目前)",
    re.I,
)
_TERM_PATTERN = re.compile(
    r"(?:(?:19|20)\d{2}\s*(?:年)?\s*(?:春季|秋季|春|秋)\s*学期|"
    r"(?:19|20)\d{2}\s*[-—–~～]\s*(?:19|20)\d{2}\s*学年)",
    re.I,
)
_SINGLE_DATE_PATTERN = re.compile(
    r"(?:19|20)\d{2}(?:\s*年\s*\d{1,2}\s*月|\s*[./]\s*\d{1,2}|\s*年)",
    re.I,
)
_NON_EXPERIENCE_TIME_CONTEXT = re.compile(
    r"(?:v\s*|版本|GPT[-\s]?|Python\s*|模型|数据集|论文|第\s*)$|"
    r"^(?:版|模型|数据集|论文|届|年度榜单)",
    re.I,
)
_TIME_DISQUALIFYING_PREFIX = re.compile(
    r"(?:\u8bf7|\u4e0d\u8981|\u4e0d\u5f97|\u6ca1\u6709|\u5e76\u672a|\u4e0d\u786e\u5b9a|"
    r"\u65e0\u6cd5\u786e\u8ba4|\u8ba1\u5212|\u51c6\u5907|\u6253\u7b97|\u62df).{0,16}$",
    re.I,
)


def _compact_time(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip("，,。；;：:")


def _is_non_experience_time_reference(text: str, start: int, end: int) -> bool:
    before = text[max(0, start - 18):start]
    after = text[end:min(len(text), end + 18)]
    return bool(
        _NON_EXPERIENCE_TIME_CONTEXT.search(before)
        or _NON_EXPERIENCE_TIME_CONTEXT.search(after)
        or _TIME_DISQUALIFYING_PREFIX.search(before)
    )


def _time_candidates_from_text(
    text: str,
    *,
    source: str,
    base_span: tuple[int, int],
    source_claim_ids: tuple[str, ...] = (),
) -> tuple[tuple[_CanonicalTimeCandidate, ...], tuple[str, ...]]:
    """Extract qualified temporal forms without treating arbitrary years as dates."""
    candidates: list[_CanonicalTimeCandidate] = []
    rejected: list[str] = []
    occupied: list[tuple[int, int]] = []
    for pattern, specificity in ((_TIME_RANGE_PATTERN, 3), (_TERM_PATTERN, 2), (_SINGLE_DATE_PATTERN, 1)):
        for match in pattern.finditer(text):
            if any(match.start() < end and start < match.end() for start, end in occupied):
                continue
            if _is_non_experience_time_reference(text, match.start(), match.end()):
                rejected.append("non_experience_temporal_reference")
                continue
            value = _compact_time(match.group(0))
            if not value:
                continue
            occupied.append((match.start(), match.end()))
            candidates.append(_CanonicalTimeCandidate(
                display_time=value,
                source=source,
                source_span=(base_span[0] + match.start(), base_span[0] + match.end()),
                source_claim_ids=source_claim_ids,
                specificity=specificity,
            ))
    return tuple(candidates), tuple(rejected)


def _build_experience_time_decision(
    identity: ExperienceIdentity,
    claim_resolution: ClaimResolution,
) -> CanonicalExperienceTimeDecision:
    """Derive one display-safe time from the current owner only."""
    candidates: list[_CanonicalTimeCandidate] = []
    rejected: list[str] = []
    # Identity.title is a local source-span field. It is not a semantic fact
    # authority, but explicit heading time is a valid display-time source.
    title_candidates, title_rejected = _time_candidates_from_text(
        str(identity.title or ""),
        source="identity_title_time",
        base_span=identity.source_span,
    )
    candidates.extend(title_candidates)
    rejected.extend(title_rejected)
    for claim in claim_resolution.eligible_claims:
        if claim.source_experience_id != identity.experience_id:
            continue
        claim_candidates, claim_rejected = _time_candidates_from_text(
            claim.text,
            source="eligible_claim_time",
            base_span=claim.source_span,
            source_claim_ids=(claim.claim_id,),
        )
        candidates.extend(claim_candidates)
        rejected.extend(claim_rejected)

    if candidates:
        selected = sorted(
            candidates,
            key=lambda item: (-item.specificity, item.source_span[0], item.source),
        )[0]
        return CanonicalExperienceTimeDecision(
            experience_id=identity.experience_id,
            display_time=selected.display_time,
            candidate_source=selected.source,
            source_span=selected.source_span,
            status=TIME_QUALIFIED,
            reason_codes=("owner_scoped_time",),
            source_claim_ids=selected.source_claim_ids,
            time_fingerprint=stable_hash(selected.display_time, purpose="canonical_experience_time"),
            candidate_sources=tuple(dict.fromkeys(item.source for item in candidates)),
            rejected_candidate_reason_codes=tuple(sorted(set(rejected))),
        )
    return CanonicalExperienceTimeDecision(
        experience_id=identity.experience_id,
        display_time=TIME_PENDING_DISPLAY,
        candidate_source="none",
        source_span=identity.source_span,
        status=TIME_PENDING,
        reason_codes=("no_qualified_local_time",),
        source_claim_ids=(),
        time_fingerprint=stable_hash(identity.experience_id, purpose="canonical_experience_time_pending"),
        candidate_sources=(),
        rejected_candidate_reason_codes=tuple(sorted(set(rejected))),
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
        if claim_is_fact_eligible(claim):
            eligible_claim_ids_by_experience.setdefault(owner, []).append(claim.claim_id)
    claims_by_id = {claim.claim_id: claim for claim in ledger.claims}
    for fact in ledger.facts:
        owner = str(fact.experience_id or "")
        if not owner:
            continue
        fact_owner_by_id[fact.fact_id] = owner
        source_claim = claims_by_id.get(fact.claim_id)
        if (
            fact.eligibility == ELIGIBLE
            and source_claim is not None
            and claim_is_fact_eligible(source_claim)
            and source_claim.source_experience_id == owner
        ):
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


def _project_canonical_semantic_state(
    *,
    raw_input_hash: str,
    identities: tuple[ExperienceIdentity, ...],
    experience_type_decisions: tuple[CanonicalExperienceTypeDecision, ...],
    ledger: ExperienceFactLedger,
    display_name_qualifications: tuple[CanonicalDisplayNameQualification, ...] = (),
    experience_input_id: int | None = None,
) -> CanonicalSemanticState:
    type_decisions = {item.experience_id: item for item in experience_type_decisions}
    name_qualifications = {
        item.experience_id: item for item in display_name_qualifications
    }
    source = CanonicalSemanticSource(
        experience_input_id=experience_input_id,
        raw_input_hash=raw_input_hash,
    )
    experiences = tuple(
        CanonicalExperience(
            experience_id=identity.experience_id,
            canonical_name=(
                name_qualifications.get(identity.experience_id).display_name
                if name_qualifications.get(identity.experience_id) is not None
                and name_qualifications[identity.experience_id].qualified
                else ""
            ),
            aliases=(),
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
    return CanonicalSemanticState(
        source=source,
        experiences=experiences,
        claims=claims,
        facts=facts,
        state_fingerprint=_fingerprint(source, experiences, claims, facts),
        validation=validation,
    )


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
    claim_resolution_by_owner = {
        identity.experience_id: resolution
        for identity, resolution in zip(identities, claim_resolutions)
    }
    experience_type_decisions = tuple(
        _build_experience_type_decision(identity, claim_resolution_by_owner[identity.experience_id])
        for identity in identities
    )
    experience_time_decisions = tuple(
        _build_experience_time_decision(identity, claim_resolution_by_owner[identity.experience_id])
        for identity in identities
    )
    display_name_qualifications = build_canonical_display_name_qualifications(
        identities,
        claim_resolutions,
    )
    ledger = build_experience_fact_ledger_from_components(
        raw_input,
        identities=identities,
        semantic_analyses=semantic_analyses,
        claim_resolutions=claim_resolutions,
    )
    raw_input_hash = stable_hash(raw_input, purpose="canonical_semantic_state")
    state = _project_canonical_semantic_state(
        raw_input_hash=raw_input_hash,
        identities=identities,
        experience_type_decisions=experience_type_decisions,
        ledger=ledger,
        display_name_qualifications=display_name_qualifications,
    )
    ownership_index = _build_ownership_index(
        ledger if state.validation.valid else ExperienceFactLedger()
    )
    return CanonicalSemanticBuild(
        long_input_context=context,
        raw_input_hash=raw_input_hash,
        identities=identities,
        experience_type_decisions=experience_type_decisions,
        semantic_analyses=semantic_analyses,
        claim_resolutions=claim_resolutions,
        display_name_qualifications=display_name_qualifications,
        experience_time_decisions=experience_time_decisions,
        ledger=ledger,
        ownership_index=ownership_index,
        state=state,
    )


def build_canonical_semantic_state_from_build(
    build: CanonicalSemanticBuild,
    *,
    experience_input_id: int | None = None,
) -> CanonicalSemanticState:
    """Project a safe state snapshot from an already-compiled semantic request."""
    state = _project_canonical_semantic_state(
        raw_input_hash=build.raw_input_hash,
        identities=build.identities,
        experience_type_decisions=build.experience_type_decisions,
        ledger=build.ledger,
        display_name_qualifications=build.display_name_qualifications,
        experience_input_id=experience_input_id,
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


def write_canonical_experience_time_qualification_log(
    decisions: tuple[CanonicalExperienceTimeDecision, ...],
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
) -> None:
    """Record time authority aggregates without time text or source text."""
    try:
        TIME_QUALIFICATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        qualified_sources: dict[str, int] = {}
        rejected_reasons: dict[str, int] = {}
        for decision in decisions:
            if decision.qualified:
                qualified_sources[decision.candidate_source] = (
                    qualified_sources.get(decision.candidate_source, 0) + 1
                )
            for reason in decision.rejected_candidate_reason_codes:
                rejected_reasons[reason] = rejected_reasons.get(reason, 0) + 1
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "request_id": request_id,
            "attempt_id": attempt_id,
            "generation_result_id": generation_result_id,
            "stage": stage,
            "experience_count": len(decisions),
            "qualified_time_count": sum(item.qualified for item in decisions),
            "pending_time_count": sum(not item.qualified for item in decisions),
            "qualified_source_counts": qualified_sources,
            "rejected_candidate_reason_counts": rejected_reasons,
            "decision_fingerprint": stable_hash(
                json.dumps([
                    (item.experience_id, item.status, item.candidate_source, item.time_fingerprint)
                    for item in decisions
                ], sort_keys=True),
                purpose="canonical_experience_time_qualification",
            ),
        }
        with TIME_QUALIFICATION_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return


def write_canonical_eligibility_integrity_log(
    build: CanonicalSemanticBuild,
    state: CanonicalSemanticState,
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
) -> None:
    """Record eligibility lineage using identifiers and aggregate counts only."""
    claims = tuple(build.ledger.claims)
    claims_by_id = {claim.claim_id: claim for claim in claims}
    invalid_fact_ids: list[str] = []
    affected_claim_ids = set(build.ledger.quarantined_claim_ids)
    affected_experience_ids: set[str] = set()
    for fact in build.ledger.facts:
        claim = claims_by_id.get(fact.claim_id)
        valid = bool(
            fact.eligibility == ELIGIBLE
            and claim is not None
            and claim_is_fact_eligible(claim)
            and claim.source_experience_id == fact.experience_id
        )
        if valid:
            continue
        invalid_fact_ids.append(fact.fact_id)
        affected_experience_ids.add(fact.experience_id)
        if fact.claim_id:
            affected_claim_ids.add(fact.claim_id)
    for claim in claims:
        effective, _ = effective_claim_eligibility(claim)
        if claim.eligibility != effective:
            affected_claim_ids.add(claim.claim_id)
            affected_experience_ids.add(claim.source_experience_id)
    affected_experience_ids.update(
        claim.source_experience_id
        for claim in claims
        if claim.claim_id in affected_claim_ids
    )
    entry = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "request_id": request_id,
        "attempt_id": attempt_id,
        "generation_result_id": generation_result_id,
        "stage": stage,
        "total_claim_count": len(claims),
        "eligible_claim_count": sum(claim_is_fact_eligible(claim) for claim in claims),
        "withheld_claim_count": sum(claim.eligibility == "withheld" for claim in claims),
        "excluded_claim_count": sum(claim.eligibility == "excluded" for claim in claims),
        "total_fact_count": len(build.ledger.facts),
        "quarantined_fact_count": (
            build.ledger.quarantined_fact_candidate_count + len(invalid_fact_ids)
        ),
        "affected_claim_ids": sorted(affected_claim_ids),
        "affected_fact_ids": sorted(invalid_fact_ids),
        "affected_experience_ids": sorted(item for item in affected_experience_ids if item),
        "validation_issue_codes": list(state.validation.issue_codes),
        "state_fingerprint": state.state_fingerprint,
        "validation_result": "valid" if state.validation.valid else "invalid",
    }
    try:
        ELIGIBILITY_INTEGRITY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with ELIGIBILITY_INTEGRITY_LOG_PATH.open("a", encoding="utf-8") as handle:
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


def write_canonical_fallback_recovery_log(
    ownership_index: CanonicalFactOwnershipIndex,
    recovery_stats: CanonicalFallbackRecoveryStats,
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
) -> None:
    """Persist aggregate fallback diagnostics without user-provided text."""
    entry = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "stage": stage,
        "request_id": request_id,
        "attempt_id": attempt_id,
        "generation_result_id": generation_result_id,
        "local_fact_detail_recovered_count": recovery_stats.local_fact_detail_recovered_count,
        "local_role_recovered_count": recovery_stats.local_role_recovered_count,
        "candidate_rejected_count": recovery_stats.candidate_rejected_count,
        "unowned_project_skipped_count": recovery_stats.unowned_project_skipped_count,
        "raw_input_rebuild_blocked_count": recovery_stats.raw_input_rebuild_blocked_count,
        "missing_question_count": recovery_stats.missing_question_count,
        "affected_source_experience_ids": list(ownership_index.source_experience_ids),
        "ownership_fingerprint": ownership_index.ownership_fingerprint,
    }
    try:
        FALLBACK_RECOVERY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FALLBACK_RECOVERY_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        return
