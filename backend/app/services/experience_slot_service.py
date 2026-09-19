import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import build_experience_fact_ledger, fact_match_score
from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .structured_log_service import stable_hash

if TYPE_CHECKING:
    from .canonical_semantic_state_service import CanonicalFactOwnershipIndex, CanonicalSemanticBuild


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "experience_slot_binding.jsonl"
OWNER_DELIVERY_CONTRACT_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_owner_delivery_contract.jsonl"
INTERNAL_SLOT_FIELDS = {
    "immutable_source_experience_id",
    "source_binding_origin",
    "source_binding_confidence",
    "source_binding_locked",
    "canonical_projection_candidate",
}


@dataclass(frozen=True)
class ExperienceSlot:
    experience_id: str
    declared_experience_type: str
    title: str
    source_span: tuple[int, int]
    fact_ids: tuple[str, ...]


@dataclass
class SlotBindingStats:
    stage: str
    generation_result_id: int | None = None
    rejected_binding_count: int = 0
    provenance_conflict_count: int = 0
    frozen_project_count: int = 0
    provisional_owner_count: int = 0
    owner_mutation_blocked_count: int = 0
    unresolved_owner_count: int = 0
    attempt_id: str = ""
    request_id: str = ""
    model_attempt: int = 0
    contract_passed: bool | None = None
    evidence_reason_counts: dict[str, int] = field(default_factory=dict)
    verified_field_count: int = 0
    unverified_field_count: int = 0
    reference_protocol: str = ""
    required_fact_count: int = 0
    assigned_fact_count: int = 0
    bindings: list[dict] = field(default_factory=list)


@dataclass
class OwnerDeliveryContractStats:
    """Counts only; project text must never enter this delivery audit."""

    stage: str
    generation_result_id: int | None = None
    total_project_count: int = 0
    owner_bound_project_count: int = 0
    unowned_candidate_count: int = 0
    removed_unowned_project_count: int = 0
    missing_question_added_count: int = 0
    ownerless_visible_after_count: int = 0
    canonical_owner_ids: tuple[str, ...] = ()
    contract_passed: bool = True


@dataclass
class CanonicalProjectionFreezeStats:
    """Outcome of Slot Binder validation for canonical projection candidates."""

    stage: str
    candidate_frozen_count: int = 0
    candidate_rejected_count: int = 0


def build_experience_slots(raw_input: str) -> list[ExperienceSlot]:
    identities = build_experience_identities(raw_input)
    ledger = build_experience_fact_ledger(raw_input)
    return [ExperienceSlot(
        experience_id=identity.experience_id,
        declared_experience_type=identity.declared_experience_type or identity.experience_type,
        title=identity.title,
        source_span=identity.source_span,
        fact_ids=tuple(fact.fact_id for fact in ledger.for_experience(identity.experience_id)),
    ) for identity in identities]


def _normalize_title(text: str) -> str:
    value = re.sub(
        r"(?:个人项目|课程项目|项目经历|实习经历|科研经历|竞赛经历|开源经历|独立开发者|负责人|核心成员)",
        "",
        str(text or ""),
        flags=re.IGNORECASE,
    )
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", value).lower()


def _project_text(project: dict) -> str:
    return "\n".join([
        str(project.get("name") or ""),
        str(project.get("intro") or ""),
        str(project.get("role") or ""),
        *[str(item) for item in project.get("details", []) or []],
    ])


def _bound_fact_owner_ids(project: dict) -> set[str]:
    """Return only explicit Fact-ID owners already attached to a project."""
    fact_ids: list[str] = []
    for key in ("source_fact_ids", "role_source_fact_ids"):
        values = project.get(key, [])
        if isinstance(values, list):
            fact_ids.extend(str(value) for value in values if value)
    for row in project.get("detail_fact_ids", []) if isinstance(project.get("detail_fact_ids"), list) else []:
        if isinstance(row, list):
            fact_ids.extend(str(value) for value in row if value)
    return {owner for owner in (fact_owner_id(value) for value in fact_ids) if owner}


def _is_verified_singleton_candidate(
    project: dict,
    candidate_owner: str,
    identities: list[ExperienceIdentity],
    canonical_index: "CanonicalFactOwnershipIndex | None",
) -> bool:
    """Accept the sole canonical owner only when attached Fact provenance agrees."""
    if canonical_index is None or len(identities) != 1:
        return False
    if canonical_index.source_experience_ids != (candidate_owner,):
        return False
    return _bound_fact_owner_ids(project).issubset({candidate_owner})


def _candidate_score(project: dict, identity: ExperienceIdentity, raw_input: str, ledger=None) -> tuple[float, list[str]]:
    project_title = _normalize_title(project.get("name", ""))
    identity_titles = [_normalize_title(identity.title), _normalize_title(identity.canonical_project_name)]
    identity_titles.extend(_normalize_title(alias) for alias in identity.project_aliases)
    identity_titles = [title for title in dict.fromkeys(identity_titles) if title]
    reasons: list[str] = []
    title_score = 0.0
    for title in identity_titles:
        if project_title and min(len(project_title), len(title)) >= 3 and (
            project_title in title or title in project_title
        ):
            title_score = max(title_score, 1.0)
        elif project_title and title:
            title_score = max(title_score, SequenceMatcher(None, project_title, title).ratio() * 0.65)
    if title_score >= 0.72:
        reasons.append("title_or_alias")

    fact_ledger = ledger or build_experience_fact_ledger(raw_input)
    local_facts = fact_ledger.for_experience(identity.experience_id)
    text = _project_text(project)
    fact_score = max((fact_match_score(text, fact) for fact in local_facts), default=0.0)
    if fact_score >= 0.66:
        reasons.append("local_fact")
    # Shared frameworks are deliberately not used as a standalone ownership signal.
    score = title_score * 0.75 + fact_score * 0.25
    return round(score, 4), reasons


def provenance_text_unchanged(before: object, after: object) -> bool:
    """Only layout and terminal sentence punctuation are presentation-neutral.

    Do not use the lexical fact matcher here: removing operators, qualifiers or
    internal punctuation can turn an unsupported statement into a false match.
    """
    def canonical(value: object) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip().rstrip("。；;").strip()
    return canonical(before) == canonical(after)


def _reference_ids(value: object) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        return None
    return list(dict.fromkeys(v.strip() for v in value))


class ModelEvidenceContractError(RuntimeError):
    """Only fixed reason codes, never model text, cross the failure boundary."""

    def __init__(self, reasons: dict[str, int]):
        self.reason_counts = dict(reasons)
        if 'format_expression_review' in reasons:
            self.code = 'MODEL_EXPRESSION_REVIEW_INVALID'
        elif any(code.startswith('expression_review_') for code in reasons):
            self.code = 'MODEL_EXPRESSION_REVIEW_UNCERTAIN' if 'expression_review_uncertain' in reasons else 'MODEL_EXPRESSION_REJECTED'
        elif any(code.startswith("format_") for code in reasons):
            self.code = "MODEL_EVIDENCE_FORMAT"
        elif any(code.startswith("missing_") for code in reasons):
            self.code = "MODEL_EVIDENCE_MISSING"
        elif "unverified_rewrite" in reasons:
            self.code = "MODEL_EVIDENCE_UNSUPPORTED"
        else:
            self.code = "MODEL_EVIDENCE_INVALID"
        super().__init__(self.code + ": " + ", ".join(sorted(reasons)))


class ModelJSONObject(dict):
    """Transient decode metadata; duplicate project keys cannot be overwritten silently."""

    def __init__(self, pairs):
        super().__init__()
        self.duplicate_keys = set()
        for key, value in pairs:
            if key in self:
                self.duplicate_keys.add(key)
            self[key] = value


EXPRESSION_PROTOCOL = "canonical_fact_expressions_v1"


@dataclass
class CanonicalExpressionReview:
    """Request-local validation receipts, never model fields or frozen facts."""

    build: object = field(repr=False)
    build_fingerprint: str = ""
    candidates: dict = field(default_factory=dict, repr=False)
    accepted: dict = field(default_factory=dict, repr=False)

    def signature(self, fact) -> str:
        return stable_hash(json.dumps([
            EXPRESSION_PROTOCOL, self.build_fingerprint, self.build.raw_input_hash,
            fact.experience_id, fact.fact_id, fact.claim_id, fact.source_span,
            fact.resume_ready_text,
            [(c.claim_id, c.text, c.eligibility, c.polarity, c.certainty, c.temporal_status)
             for c in self.build.ledger.claims if c.source_experience_id == fact.experience_id],
        ], ensure_ascii=False, default=str), purpose="expression_review")

    @property
    def pending(self) -> dict:
        return {fid: row for fid, row in self.candidates.items() if not row['literal']}

    def accept(self, decisions: object) -> None:
        if (not isinstance(decisions, dict) or set(decisions) != {'decisions'}
                or getattr(decisions, 'duplicate_keys', ())):
            raise ModelEvidenceContractError({'format_expression_review': 1})
        rows = decisions['decisions']
        if (not isinstance(rows, dict) or getattr(rows, 'duplicate_keys', ())
                or set(rows) != set(self.pending)
                or any(not isinstance(value, str) or value not in {
                    'supported', 'added_claim', 'omitted_fact', 'changed_qualification', 'uncertain',
                } for value in rows.values())):
            raise ModelEvidenceContractError({'format_expression_review': 1})
        rejected = {f'expression_review_{value}': list(rows.values()).count(value)
                    for value in set(rows.values()) if value != 'supported'}
        if rejected:
            raise ModelEvidenceContractError(rejected)
        self.accepted = {fid: (row['signature'], row['candidate']) for fid, row in self.candidates.items()}

    def text_for(self, fact, build) -> str | None:
        receipt = self.accepted.get(fact.fact_id)
        if build is not self.build or not receipt or receipt[0] != self.signature(fact):
            return None
        return receipt[1]


def compose_model_fact_references(
    raw: object, consumer_views, *, request_id: str = "", attempt_id: str = "",
    model_attempt: int = 0, expression_review: CanonicalExpressionReview | None = None,
) -> dict:
    """Validate references and prepare candidates; review precedes trusted delivery."""
    stats = SlotBindingStats(
        stage="generation_model_evidence_received", request_id=request_id,
        attempt_id=attempt_id, model_attempt=model_attempt,
        reference_protocol=EXPRESSION_PROTOCOL,
    )

    def reject(code: str) -> None:
        stats.evidence_reason_counts[code] = stats.evidence_reason_counts.get(code, 0) + 1

    fields = {"source_experience_id", "fact_placements"}
    if expression_review is not None:
        if (expression_review.build is not consumer_views._build
                or expression_review.build_fingerprint != consumer_views.build_fingerprint):
            raise ModelEvidenceContractError({'invalid_expression_context': 1})
        expression_review.candidates.clear()
        expression_review.accepted.clear()
    facts_by_owner = {
        owner: consumer_views.facts_for_owner(owner)
        for owner in consumer_views.experience_ids
    }
    required = {fact.fact_id for facts in facts_by_owner.values() for fact in facts}
    assigned: set[str] = set()
    owners: set[str] = set()
    result = []
    sections = raw.get("resume_sections") if isinstance(raw, dict) else None
    projects = sections.get("projects") if isinstance(sections, dict) else None
    if ("resume_sections" in getattr(raw, "duplicate_keys", ())
            or "projects" in getattr(sections, "duplicate_keys", ())):
        reject("duplicate_project_key")
    if not isinstance(projects, list):
        reject("format_projects")
        projects = []
    for project in projects:
        if not isinstance(project, dict):
            reject("format_project")
            continue
        if getattr(project, "duplicate_keys", ()):
            reject("duplicate_project_key")
        if set(project) - fields:
            reject("format_forbidden_project_fields")
        if fields - set(project):
            reject("missing_reference_fields")
        owner = project.get("source_experience_id")
        if not isinstance(owner, str) or owner not in facts_by_owner:
            reject("invalid_owner_reference")
            continue
        if owner in owners:
            reject("duplicate_owner_reference")
        owners.add(owner)
        facts = facts_by_owner[owner]
        local = {fact.fact_id: fact for fact in facts}
        # Stable frozen source order, never JSON object key order.
        ordered_facts = sorted(facts, key=lambda f: f.source_span)
        scope = consumer_views.scope_for_owner(owner)
        claims = {claim.claim_id for claim in consumer_views.claims_for_owner(owner) if scope.permits_claim(claim.claim_id)}
        header = consumer_views.planner_view.experience_header_decision_for_owner(owner)
        if header is None:
            reject("invalid_frozen_header")
            continue

        placements = project.get("fact_placements")
        if not isinstance(placements, dict):
            reject("format_fact_placements")
            continue
        if getattr(placements, "duplicate_keys", ()):
            reject("duplicate_project_key")
        if set(placements) - set(local):
            reject("invalid_owner_or_fact_reference")
        if set(local) - set(placements):
            reject("missing_fact_assignment")
        valid_placements = {}
        for fid, value in placements.items():
            if (not isinstance(value, dict) or set(value) != {'position', 'text'}
                    or getattr(value, 'duplicate_keys', ())):
                reject("format_fact_expression")
                continue
            if not isinstance(value['position'], str) or value['position'] not in ('intro', 'role', 'detail'):
                reject("format_fact_position")
                continue
            if not isinstance(value['text'], str) or not value['text'].strip():
                reject("format_expression_text")
                continue
            if fid not in local:
                continue
            valid_placements[fid] = value
            fact = local[fid]
            literal = provenance_text_unchanged(value['text'], fact.resume_ready_text)
            if expression_review is not None:
                expression_review.candidates[fid] = {
                    'owner': owner, 'source': fact.resume_ready_text, 'candidate': value['text'],
                    'claim_id': fact.claim_id, 'literal': literal,
                    'signature': expression_review.signature(fact),
                }
            elif not literal:
                reject('unverified_rewrite')
        if assigned.intersection(placements):
            reject("duplicate_fact_reference")
        assigned.update(fid for fid in placements if fid in local)

        def row(value):
            selected = [local[fid] for fid in value]
            if any(consumer_views.fact_owner(f.fact_id) != owner or f.claim_id not in claims
                   or consumer_views.claim_owner(f.claim_id) != owner for f in selected):
                reject("invalid_claim_lineage")
                return "", [], []
            texts = [valid_placements[f.fact_id]['text'] for f in selected]
            if any(not text.strip() for text in texts):
                reject("invalid_empty_fact_text")
            text = texts[0] if len(texts) == 1 else "；".join(t.rstrip("。；;") for t in texts)
            return text, list(value), list(dict.fromkeys(f.claim_id for f in selected))

        grouped = {
            position: [f.fact_id for f in ordered_facts if valid_placements.get(f.fact_id, {}).get('position') == position]
            for position in ("intro", "role", "detail")
        }
        intro, intro_facts, intro_claims = row(grouped["intro"])
        role, role_facts, role_claims = row(grouped["role"])
        detail_rows = [row([fid]) for fid in grouped["detail"]]
        public_header = {
            ("name" if field.field_key == "organization" else field.field_key): field.display_text
            for field in header.fields
        }
        result.append({
            **public_header, "meta": scope.canonical_experience_type,
            "source_experience_id": owner,
            "intro": intro, "role": role, "details": [r[0] for r in detail_rows],
            "intro_source_fact_ids": intro_facts, "intro_source_claim_ids": intro_claims,
            "role_source_fact_ids": role_facts, "role_source_claim_ids": role_claims,
            "detail_fact_ids": [r[1] for r in detail_rows],
            "detail_claim_ids": [r[2] for r in detail_rows],
            "source_fact_ids": list(dict.fromkeys(intro_facts + role_facts + [fid for r in detail_rows for fid in r[1]])),
            "source_claim_ids": list(dict.fromkeys(intro_claims + role_claims + [cid for r in detail_rows for cid in r[2]])),
        })
    if required - assigned:
        reject("missing_fact_assignment")
    stats.required_fact_count = len(required)
    stats.assigned_fact_count = len(assigned)
    if stats.evidence_reason_counts:
        stats.contract_passed = False
        _write_log(stats)
        raise ModelEvidenceContractError(stats.evidence_reason_counts)
    if expression_review is not None and not expression_review.pending:
        expression_review.accept({'decisions': {}})
    updated = deepcopy(raw)
    updated["resume_sections"]["projects"] = result
    stats.stage = "generation_model_expression_candidates_prepared"
    stats.contract_passed = not bool(expression_review and expression_review.pending)
    _write_log(stats)
    return updated


def validate_model_output_structure(
    raw: object, consumer_views, *, request_id: str = "", attempt_id: str = "",
    model_attempt: int = 0,
) -> None:
    """Check the actual declarations before normalization can erase defects."""
    stats = SlotBindingStats(
        stage="generation_model_evidence_received", request_id=request_id,
        attempt_id=attempt_id, model_attempt=model_attempt,
    )

    def reject(code: str) -> None:
        stats.evidence_reason_counts[code] = stats.evidence_reason_counts.get(code, 0) + 1

    def check_row(text: str, container: dict, fact_key: str, claim_key: str) -> None:
        reasons: set[str] = set()
        for key in (fact_key, claim_key):
            if key not in container:
                if text.strip():
                    reasons.add("missing_field_reference")
                continue
            ids = _reference_ids(container[key])
            if ids is None:
                reasons.add("format_field_reference")
            elif text.strip() and not ids:
                reasons.add("missing_field_reference")
            elif not text.strip() and ids:
                reasons.add("orphan_field_reference")
        for code in sorted(reasons):
            reject(code)
        if reasons and text.strip():
            stats.unverified_field_count += 1

    sections = raw.get("resume_sections") if isinstance(raw, dict) else None
    projects = sections.get("projects") if isinstance(sections, dict) else None
    if not isinstance(projects, list):
        reject("format_projects")
    else:
        if not projects and any(consumer_views.facts_for_owner(owner) for owner in consumer_views.experience_ids):
            reject("missing_projects")
        for project in projects:
            if not isinstance(project, dict):
                reject("format_project")
                continue
            owner = project.get("source_experience_id")
            if not owner:
                reject("missing_owner_reference")
            elif not isinstance(owner, str) or consumer_views.scope_for_owner(owner) is None:
                reject("invalid_owner_reference")
            for field_name in ("intro", "role"):
                if field_name not in project:
                    reject("missing_body_field")
                elif not isinstance(project[field_name], str):
                    reject("format_body_field")
                else:
                    check_row(project[field_name], project, f"{field_name}_source_fact_ids", f"{field_name}_source_claim_ids")
            details = project.get("details")
            if not isinstance(details, list) or any(not isinstance(text, str) for text in details):
                reject("format_details")
                continue
            for key in ("detail_fact_ids", "detail_claim_ids"):
                rows = project.get(key)
                if key not in project:
                    continue
                if not isinstance(rows, list) or len(rows) != len(details):
                    reject("format_detail_rows")
            for index, text in enumerate(details):
                row = {}
                for key in ("detail_fact_ids", "detail_claim_ids"):
                    rows = project.get(key)
                    if isinstance(rows, list) and index < len(rows):
                        row[key] = rows[index]
                check_row(text, row, "detail_fact_ids", "detail_claim_ids")
            if all(not str(project.get(key) or "").strip() for key in ("intro", "role")) and not any(text.strip() for text in details):
                if isinstance(owner, str) and consumer_views.facts_for_owner(owner):
                    reject("missing_project_body")
    if stats.evidence_reason_counts:
        stats.contract_passed = False
        _write_log(stats)
        raise ModelEvidenceContractError(stats.evidence_reason_counts)


def _validate_project_evidence(project: dict, facts, claim_ids, stats: SlotBindingStats,
                               *, expression_review=None, semantic_build=None) -> bool:
    local = {fact.fact_id: fact for fact in facts}
    allowed_claims = set(claim_ids)
    supported_facts: list[str] = []
    supported_claims: list[str] = []
    aggregate_facts = _reference_ids(project.get("source_fact_ids", []))
    aggregate_claims = _reference_ids(project.get("source_claim_ids", []))
    invalid_reference = (
        aggregate_facts is None or aggregate_claims is None
        or any(fid not in local for fid in (aggregate_facts or []))
        or not set(aggregate_claims or []) <= allowed_claims
    )
    if invalid_reference:
        code = "invalid_aggregate_reference"
        stats.evidence_reason_counts[code] = stats.evidence_reason_counts.get(code, 0) + 1

    def validate(text, raw_facts, raw_claims):
        nonlocal invalid_reference
        ids, claims = _reference_ids(raw_facts), _reference_ids(raw_claims)
        reason = ""
        if not str(text or "").strip():
            reason = "orphan_field_reference" if raw_facts or raw_claims else ""
        elif ids is None or claims is None:
            reason = "malformed_field_reference"
        elif not ids:
            reason = "missing_field_reference"
        elif any(fid not in local for fid in ids):
            reason = "invalid_owner_or_fact_reference"
        elif set(claims) != {local[fid].claim_id for fid in ids} or not set(claims) <= allowed_claims:
            reason = "invalid_claim_lineage"
        else:
            texts = [expression_review.text_for(local[fid], semantic_build)
                     if expression_review is not None else local[fid].resume_ready_text for fid in ids]
            # A multi-Fact row is verifiable only as a literal composition of
            # its cited facts in the supplied order, not a semantic inference.
            variants = [separator.join(t.rstrip("。；;") for t in texts) for separator in ("；", ";", "。")] if all(t is not None for t in texts) else []
            if not any(provenance_text_unchanged(text, value) for value in variants):
                reason = "unverified_rewrite"
            else:
                stats.verified_field_count += 1
                supported_facts.extend(ids)
                supported_claims.extend(claims)
                return ids, claims
        if reason:
            if reason in {"malformed_field_reference", "invalid_owner_or_fact_reference", "invalid_claim_lineage"}:
                invalid_reference = True
            stats.evidence_reason_counts[reason] = stats.evidence_reason_counts.get(reason, 0) + 1
            if str(text or "").strip():
                stats.unverified_field_count += 1
        return [], []

    for field_name in ("intro", "role"):
        fact_key, claim_key = f"{field_name}_source_fact_ids", f"{field_name}_source_claim_ids"
        ids, claims = validate(project.get(field_name), project.get(fact_key, []), project.get(claim_key, []))
        if fact_key in project or ids:
            project[fact_key] = ids
        if claim_key in project or claims:
            project[claim_key] = claims
    rows = project.get("detail_fact_ids", [])
    claim_rows = project.get("detail_claim_ids", [])
    result_facts, result_claims = [], []
    for index, text in enumerate(project.get("details", []) or []):
        ids, claims = validate(
            text, rows[index] if isinstance(rows, list) and index < len(rows) else [],
            claim_rows[index] if isinstance(claim_rows, list) and index < len(claim_rows) else [],
        )
        result_facts.append(ids)
        result_claims.append(claims)
    project["detail_fact_ids"], project["detail_claim_ids"] = result_facts, result_claims
    # Aggregates summarize verified fields; an aggregate declaration alone
    # cannot establish which visible field carries a fact.
    project["source_fact_ids"] = list(dict.fromkeys(supported_facts))
    project["source_claim_ids"] = list(dict.fromkeys(supported_claims))
    return invalid_reference


def validate_model_project_evidence(
    payload: schemas.GenerationPayload | dict, consumer_views, *, attempt_id: str = "",
    write_log: bool = True, require_complete: bool = False,
    request_id: str = "", model_attempt: int = 0, expression_review=None,
) -> schemas.GenerationPayload | dict:
    """Validate candidate references without inventing bindings or rewriting body."""
    if expression_review is not None:
        if (expression_review.build is not consumer_views._build
                or expression_review.build_fingerprint != consumer_views.build_fingerprint):
            raise ModelEvidenceContractError({'invalid_expression_context': 1})
        if require_complete and not isinstance(payload, dict):
            validate_model_output_structure(payload.model_dump(), consumer_views,
                                            request_id=request_id, attempt_id=attempt_id,
                                            model_attempt=model_attempt)
    if isinstance(payload, dict):
        # Inspect source evidence before unrelated schema failures or defaults
        # can conceal it. Raw Canonical responses always require the contract.
        require_complete = True
        validate_model_output_structure(
            payload, consumer_views, request_id=request_id, attempt_id=attempt_id,
            model_attempt=model_attempt,
        )
        updated = deepcopy(payload)
        projects = updated["resume_sections"]["projects"]
    else:
        updated = payload.model_copy(deep=True)
        projects = updated.resume_sections.projects
    stats = SlotBindingStats(
        stage="generation_model_evidence_received", attempt_id=attempt_id,
        request_id=request_id, model_attempt=model_attempt,
    )
    for project in projects:
        original_aggregates = (set(_reference_ids(project.get('source_fact_ids', [])) or []),
                               set(_reference_ids(project.get('source_claim_ids', [])) or []))
        owner = str(project.get("source_experience_id") or "")
        scope = consumer_views.scope_for_owner(owner)
        if require_complete and scope is None:
            code = "invalid_owner_reference" if owner else "missing_owner_reference"
            stats.evidence_reason_counts[code] = stats.evidence_reason_counts.get(code, 0) + 1
        invalid = _validate_project_evidence(
            project, consumer_views.facts_for_owner(owner) if scope else (),
            scope.eligible_claim_ids if scope else (), stats,
            expression_review=expression_review, semantic_build=consumer_views._build,
        )
        if expression_review is not None and original_aggregates != (
                set(project.get('source_fact_ids', [])), set(project.get('source_claim_ids', []))):
            stats.evidence_reason_counts['invalid_expression_aggregate'] = 1
        if invalid and not project.get("source_fact_ids"):
            # Clearing bad IDs must not turn them into a vacuously valid
            # singleton-owner declaration. Independent valid fields still
            # retain their owner and provenance when another field is rejected.
            project.pop("source_experience_id", None)
    if require_complete:
        if expression_review is not None:
            assigned = [fid for project in projects for key in ('intro_source_fact_ids', 'role_source_fact_ids')
                        for fid in project.get(key, [])]
            assigned += [fid for project in projects for row in project.get('detail_fact_ids', []) for fid in row]
            if (set(assigned) != set(consumer_views.eligible_fact_ids)
                    or len(assigned) != len(set(assigned))):
                stats.evidence_reason_counts['invalid_expression_coverage'] = 1
        stats.contract_passed = not bool(stats.evidence_reason_counts)
    if write_log:
        _write_log(stats)
    if require_complete and not stats.contract_passed:
        raise ModelEvidenceContractError(stats.evidence_reason_counts)
    return updated


def _write_log(stats: SlotBindingStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "stage": stats.stage,
            "generation_result_id": stats.generation_result_id,
            "rejected_binding_count": stats.rejected_binding_count,
            "provenance_conflict_count": stats.provenance_conflict_count,
            "attempt_id": stats.attempt_id,
            "request_id": stats.request_id,
            "model_attempt": stats.model_attempt,
            "contract_passed": stats.contract_passed,
            "verified_field_count": stats.verified_field_count,
            "unverified_field_count": stats.unverified_field_count,
            "reference_protocol": stats.reference_protocol,
            "required_fact_count": stats.required_fact_count,
            "assigned_fact_count": stats.assigned_fact_count,
            "evidence_reason_counts": stats.evidence_reason_counts,
            "bindings": stats.bindings,
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def _write_owner_delivery_contract_log(
    stats: OwnerDeliveryContractStats,
    *,
    request_id: str = "",
    attempt_id: str = "",
) -> None:
    try:
        OWNER_DELIVERY_CONTRACT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "request_id": request_id,
            "attempt_id": attempt_id,
            "generation_result_id": stats.generation_result_id,
            "stage": stats.stage,
            "total_project_count": stats.total_project_count,
            "owner_bound_project_count": stats.owner_bound_project_count,
            "unowned_candidate_count": stats.unowned_candidate_count,
            "removed_unowned_project_count": stats.removed_unowned_project_count,
            "missing_question_added_count": stats.missing_question_added_count,
            "ownerless_visible_after_count": stats.ownerless_visible_after_count,
            "canonical_owner_ids": list(stats.canonical_owner_ids),
            "contract_passed": stats.contract_passed,
        }
        with OWNER_DELIVERY_CONTRACT_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def contain_ownerless_projects(
    payload: schemas.GenerationPayload,
    ownership_index: "CanonicalFactOwnershipIndex | None",
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    request_id: str = "",
    attempt_id: str = "",
    write_log: bool = True,
    return_stats: bool = False,
) -> schemas.GenerationPayload | tuple[schemas.GenerationPayload, OwnerDeliveryContractStats]:
    """Enforce the post-freeze delivery contract without inferring ownership.

    A project is deliverable only when the Slot Binder has already frozen an
    owner which belongs to the canonical ownership index.  Candidates without
    that proof are removed rather than merged, rebound, or rewritten.
    """
    updated = payload.model_copy(deep=True)
    canonical_owner_ids = tuple(ownership_index.source_experience_ids) if ownership_index is not None else ()
    valid_owner_ids = set(canonical_owner_ids)
    stats = OwnerDeliveryContractStats(
        stage=stage,
        generation_result_id=generation_result_id,
        total_project_count=len(updated.resume_sections.projects),
        canonical_owner_ids=canonical_owner_ids,
    )
    retained: list[dict] = []

    for project in updated.resume_sections.projects:
        owner = str(project.get("immutable_source_experience_id") or "").strip()
        is_bound = bool(project.get("source_binding_locked"))
        if owner and is_bound and owner in valid_owner_ids:
            retained.append(project)
            stats.owner_bound_project_count += 1
        else:
            stats.unowned_candidate_count += 1
            stats.removed_unowned_project_count += 1

    updated.resume_sections.projects = retained
    if stats.unowned_candidate_count and not stats.owner_bound_project_count:
        question = "请补充无法确认归属经历的具体名称和可验证事实。"
        if question not in updated.missing_questions:
            updated.missing_questions.append(question)
            updated.missing_questions = updated.missing_questions[:8]
            stats.missing_question_added_count = 1

    stats.ownerless_visible_after_count = sum(
        not (
            str(project.get("immutable_source_experience_id") or "").strip()
            and bool(project.get("source_binding_locked"))
            and str(project.get("immutable_source_experience_id") or "").strip() in valid_owner_ids
        )
        for project in updated.resume_sections.projects
    )
    stats.contract_passed = stats.ownerless_visible_after_count == 0
    if write_log:
        _write_owner_delivery_contract_log(stats, request_id=request_id, attempt_id=attempt_id)
    return (updated, stats) if return_stats else updated


def write_owner_delivery_contract_log(
    stats: OwnerDeliveryContractStats,
    *,
    request_id: str = "",
    attempt_id: str = "",
) -> None:
    _write_owner_delivery_contract_log(stats, request_id=request_id, attempt_id=attempt_id)


def _project_provenance_ids(project: dict, kind: str) -> tuple[str, ...]:
    values: list[str] = []
    direct_key = f"source_{kind}_ids"
    role_key = f"role_source_{kind}_ids"
    detail_key = f"detail_{kind}_ids"
    for direct_key in (direct_key, role_key):
        direct = project.get(direct_key)
        if isinstance(direct, list):
            values.extend(str(item) for item in direct if str(item or ""))
    rows = project.get(detail_key)
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, list):
                values.extend(str(item) for item in row if str(item or ""))
    return tuple(dict.fromkeys(values))


def freeze_canonical_projection_candidates(
    payload: schemas.GenerationPayload,
    ownership_index: "CanonicalFactOwnershipIndex",
    *,
    stage: str = "canonical_project_projection_freeze",
    return_stats: bool = False,
) -> schemas.GenerationPayload | tuple[schemas.GenerationPayload, CanonicalProjectionFreezeStats]:
    """Freeze only candidates created by the canonical projection planner.

    The planner may nominate an owner, but only this Slot Binder entry point can
    make it immutable.  A malformed candidate is discarded; it is never
    rebound through text similarity, position, title, or technology overlap.
    """
    updated = payload.model_copy(deep=True)
    stats = CanonicalProjectionFreezeStats(stage=stage)
    retained: list[dict] = []

    for project in updated.resume_sections.projects:
        if not project.get("canonical_projection_candidate"):
            retained.append(project)
            continue

        owner = str(project.get("source_experience_id") or "").strip()
        fact_ids = _project_provenance_ids(project, "fact")
        claim_ids = _project_provenance_ids(project, "claim")
        valid_owner = owner in ownership_index.source_experience_ids
        valid_facts = bool(fact_ids) and all(
            ownership_index.fact_owner(fact_id) == owner
            and fact_id in ownership_index.eligible_fact_ids_by_experience.get(owner, ())
            for fact_id in fact_ids
        )
        valid_claims = bool(claim_ids) and all(
            ownership_index.claim_owner(claim_id) == owner
            and claim_id in ownership_index.eligible_claim_ids_by_experience.get(owner, ())
            for claim_id in claim_ids
        )
        candidate_is_unfrozen = not project.get("immutable_source_experience_id") and not project.get("source_binding_locked")

        if valid_owner and valid_facts and valid_claims and candidate_is_unfrozen:
            project["immutable_source_experience_id"] = owner
            project["source_binding_locked"] = True
            project["source_binding_origin"] = "canonical_project_projection"
            project["source_binding_confidence"] = 1.0
            retained.append(project)
            stats.candidate_frozen_count += 1
        else:
            stats.candidate_rejected_count += 1

    updated.resume_sections.projects = retained
    return (updated, stats) if return_stats else updated


def bind_projects_to_experience_slots(
    payload: schemas.GenerationPayload,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
    semantic_build: "CanonicalSemanticBuild | None" = None,
    ownership_index: "CanonicalFactOwnershipIndex | None" = None,
    return_stats: bool = False, expression_review=None,
) -> schemas.GenerationPayload | tuple[schemas.GenerationPayload, SlotBindingStats]:
    """Freeze project owners once when canonical compilation is available.

    The legacy raw-input path remains for DOCX and un-migrated callers.  In
    canonical mode there is intentionally no positional fallback: an uncertain
    candidate is safer unbound than assigned to a neighbouring experience.
    """
    updated = payload.model_copy(deep=True)
    canonical_mode = semantic_build is not None or ownership_index is not None
    identities = list(semantic_build.identities) if semantic_build is not None else build_experience_identities(raw_input)
    ledger = semantic_build.ledger if semantic_build is not None else None
    canonical_index = ownership_index or (semantic_build.ownership_index if semantic_build is not None else None)
    identity_by_id = {identity.experience_id: identity for identity in identities}
    stats = SlotBindingStats(stage=stage, generation_result_id=generation_result_id)
    used: set[str] = set()

    positions = list(range(len(updated.resume_sections.projects)))
    invalid_reference_positions: set[int] = set()
    verified_reference_positions: set[int] = set()
    if canonical_mode and semantic_build is not None and canonical_index is not None:
        priorities = {}
        for position, project in enumerate(updated.resume_sections.projects):
            if project.get("immutable_source_experience_id"):
                priorities[position] = (-2, 0, 0, "")
                continue
            owner = str(project.get("source_experience_id") or "")
            reasons_before = dict(stats.evidence_reason_counts)
            invalid = _validate_project_evidence(
                project, [fact for fact in semantic_build.ledger.for_experience(owner)
                          if fact.fact_id in canonical_index.eligible_fact_ids_by_experience.get(owner, ())],
                canonical_index.eligible_claim_ids_by_experience.get(owner, ()), stats,
                expression_review=expression_review, semantic_build=semantic_build,
            )
            if invalid:
                invalid_reference_positions.add(position)
            rows = [(project.get(name), project.get(f"{name}_source_fact_ids")) for name in ("intro", "role")]
            rows += list(zip(project.get("details", []), project.get("detail_fact_ids", [])))
            visible_rows = [(text, ids) for text, ids in rows if str(text or "").strip()]
            complete = bool(visible_rows) and all(ids for text, ids in visible_rows)
            if complete and not invalid and stats.evidence_reason_counts == reasons_before:
                verified_reference_positions.add(position)
            best_score = max((_candidate_score(project, i, raw_input, ledger)[0] for i in identities), default=0)
            priorities[position] = (
                -int(complete), -len(project.get("source_fact_ids", [])), -best_score,
                stable_hash(json.dumps(project, ensure_ascii=False, sort_keys=True), purpose="slot_candidate_order"),
            )
        positions.sort(key=priorities.__getitem__)

    for position in positions:
        project = updated.resume_sections.projects[position]
        frozen_owner = str(project.get("immutable_source_experience_id") or "")
        if canonical_mode and frozen_owner:
            stats.owner_mutation_blocked_count += 1
            used.add(frozen_owner)
            continue
        existing = str(project.get("source_experience_id") or "")
        if existing:
            stats.provisional_owner_count += 1
        ranked = sorted(
            (
                (identity, *_candidate_score(project, identity, raw_input, ledger))
                for identity in identities
                if canonical_mode or identity.experience_id not in used
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        best = ranked[0] if ranked else None
        runner_score = ranked[1][1] if len(ranked) > 1 else 0.0
        chosen: ExperienceIdentity | None = None
        origin = "unbound"
        confidence = 0.0

        if existing in identity_by_id:
            if canonical_mode and existing not in used and position not in invalid_reference_positions and _is_verified_singleton_candidate(
                project, existing, identities, canonical_index,
            ):
                # A valid candidate for the only canonical experience has no
                # competing owner. This is provenance validation, not a
                # positional or keyword-based ownership inference.
                chosen = identity_by_id[existing]
                origin = "canonical_singleton_candidate"
                confidence = 1.0
            elif canonical_mode and existing not in used and position in verified_reference_positions:
                # Every visible field already proved its owner-local lineage
                # and literal support. A frozen display label is not identity evidence.
                chosen = identity_by_id[existing]
                origin = "canonical_field_evidence"
                confidence = 1.0
            else:
                existing_score, existing_reasons = _candidate_score(project, identity_by_id[existing], raw_input, ledger)
                if existing_score >= 0.62 and existing not in used:
                    chosen = identity_by_id[existing]
                    origin = "llm_id_validated"
                    confidence = existing_score
                elif best and best[0].experience_id not in used and best[1] >= 0.72 and best[1] - runner_score >= 0.16:
                    chosen = best[0]
                    origin = "corrected_by_title_and_local_fact"
                    confidence = best[1]
                    stats.provenance_conflict_count += 1
                else:
                    stats.rejected_binding_count += 1
        elif existing:
            stats.rejected_binding_count += 1
        elif best and best[0].experience_id not in used and best[1] >= 0.72 and best[1] - runner_score >= 0.16:
            chosen = best[0]
            origin = "title_and_local_fact"
            confidence = best[1]
        elif not canonical_mode and position < len(identities) and identities[position].experience_id not in used:
            # Slot order is an internal generation contract. It is weaker than title
            # evidence and remains visibly marked as positional provenance.
            chosen = identities[position]
            origin = "fixed_slot_order"
            confidence = 0.7
        else:
            stats.rejected_binding_count += 1

        if chosen:
            source_id = chosen.experience_id
            conflicting_field_owner = canonical_mode and bool(_bound_fact_owner_ids(project) - {source_id})
            if conflicting_field_owner:
                # Owner matching cannot relocate already validated field evidence.
                chosen = None
                stats.provenance_conflict_count += 1
                stats.rejected_binding_count += 1
            elif canonical_mode and (canonical_index is None or source_id not in canonical_index.source_experience_ids):
                chosen = None
                stats.rejected_binding_count += 1
            else:
                project["source_experience_id"] = source_id
                project["immutable_source_experience_id"] = source_id
                project["source_binding_origin"] = origin
                project["source_binding_confidence"] = round(confidence, 3)
                project["source_binding_locked"] = True
                stats.frozen_project_count += 1
                used.add(source_id)
        if not chosen:
            project.pop("source_experience_id", None)
            project.pop("immutable_source_experience_id", None)
            project["source_binding_origin"] = "rejected"
            project["source_binding_confidence"] = 0.0
            project["source_binding_locked"] = False
            if canonical_mode:
                stats.unresolved_owner_count += 1
                if best and best[0].experience_id in used:
                    code = "competing_owner_candidate_unresolved"
                    stats.evidence_reason_counts[code] = stats.evidence_reason_counts.get(code, 0) + 1

        stats.bindings.append({
            "project_index": position,
            "source_experience_id": str(project.get("source_experience_id") or ""),
            "slot_binding_source": project.get("source_binding_origin"),
            "slot_binding_confidence": project.get("source_binding_confidence"),
            "candidate_scores": [
                {"experience_id": item[0].experience_id, "score": item[1], "reasons": item[2]}
                for item in ranked[:3]
            ],
        })

    if write_log:
        _write_log(stats)
    return (updated, stats) if return_stats else updated


def fact_owner_id(fact_id: str) -> str:
    match = re.match(r"^(EXP-\d{3})-F\d{3}$", str(fact_id or ""))
    return match.group(1) if match else ""


def strip_experience_slot_metadata(payload: schemas.GenerationPayload) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        for key in INTERNAL_SLOT_FIELDS:
            project.pop(key, None)
    return updated
