"""Request-scoped display-name qualification for canonical projections.

Experience identity text is useful internal evidence, but it is not
automatically safe to display as a resume project name.  This module records a
single deterministic decision per canonical owner.  The decision remains
request-local; logs contain only IDs, reasons, source kinds and fingerprints.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .experience_identity_service import ExperienceIdentity
from .input_claim_resolution_service import (
    CONFIRMED,
    ELIGIBLE,
    NEGATIVE,
    ClaimResolution,
    effective_claim_eligibility,
)
from .structured_log_service import stable_hash


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "canonical_display_name_qualification.jsonl"

QUALIFIED = "qualified"
PENDING = "pending"
NAME_PENDING_DISPLAY = "[待补充经历名称]"

_GENERIC_LABELS = frozenset({
    "项目", "项目经历", "经历", "实习", "实习经历", "科研", "科研经历",
    "研究经历", "开源", "开源经历", "竞赛", "竞赛经历", "竞赛获奖",
    "校园经历", "校园社团经历", "志愿活动", "活动经历", "工作经历",
})
_CONVERSATIONAL_TITLE_PREFIX = re.compile(
    r"^(?:第[一二三四五六七八九十0-9]+段(?:是|为|介绍的是|写的是)|"
    r"(?:这一段|该段)(?:是|为|介绍的是|写的是))\s*"
)
_NEGATIVE_ASSERTION_TITLE = re.compile(
    r"^(?:没有|并未|未曾|不曾|不是|不负责)\s*"
    r"(?:负责|参与|开发|实现|完成|部署|上线|设计|担任|获奖|使用|管理|主导|独立|做)",
    re.I,
)
_INSTRUCTION_TITLE = re.compile(r"^(?:请|不要|不得|别|希望|需要|想要)", re.I)
_EXPLICIT_NAME_DECLARATION = re.compile(
    r"(?:项目(?:名称|名)|产品(?:名称|名)|活动(?:名称|名)|课题(?:名称|名))"
    r"\s*(?:是|为|明确为|叫|[:：])\s*(?P<name>[^，,。；;\n]{2,60})",
    re.I,
)
_PROJECT_ENTITY = re.compile(
    r"(?:独立(?:设计并)?开发|从零(?:设计并)?开发|做过|开发(?:了|过)?|设计(?:了|过)?|搭建(?:了)?)"
    r"\s*(?:一个|一套)?\s*(?P<name>[^，,。；;\n]{2,48}"
    r"(?:项目|系统|平台|网站|工具|助手|应用|小程序))",
    re.I,
)
_PRODUCT_IDENTIFIER = re.compile(
    r"(?:独立(?:设计并)?开发|从零(?:设计并)?开发|做过|开发(?:了|过)?|设计(?:了|过)?|搭建(?:了)?)"
    r"\s*(?P<name>[A-Z][A-Za-z0-9_-]*(?:\s+[A-Z][A-Za-z0-9_-]*)+)",
)
_ACTIVITY_ENTITY = re.compile(
    r"(?:参加|参与|组织|加入|担任)\s*(?P<name>[^，,。；;\n]{2,48}"
    r"(?:竞赛|比赛|活动|计划|实践队))",
    re.I,
)
_GENERIC_ENTITY_NAMES = frozenset({
    "项目", "系统", "平台", "网站", "工具", "助手", "应用", "小程序", "活动", "比赛", "竞赛", "计划",
})


@dataclass(frozen=True)
class CanonicalDisplayNameQualification:
    """A qualified, request-local display name for one canonical owner."""

    experience_id: str
    display_name: str
    candidate_source: str
    source_span: tuple[int, int]
    status: str
    reason_codes: tuple[str, ...]
    source_claim_ids: tuple[str, ...]
    name_fingerprint: str
    candidate_sources: tuple[str, ...] = ()
    rejected_candidate_reason_codes: tuple[str, ...] = ()

    @property
    def qualified(self) -> bool:
        return self.status == QUALIFIED and bool(self.display_name)


@dataclass(frozen=True)
class _DisplayNameCandidate:
    value: str
    source: str
    source_span: tuple[int, int]
    source_claim_ids: tuple[str, ...] = ()


def _compact(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n:：-—|｜")


def _comparison_key(value: object) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9+#./-]", "", _compact(value)).lower()


def _display_form(value: object) -> str:
    return _compact(_CONVERSATIONAL_TITLE_PREFIX.sub("", _compact(value)))


def _is_generic_label(value: object) -> bool:
    return _comparison_key(value) in {_comparison_key(item) for item in _GENERIC_LABELS}


def _is_semantic_constraint_title(value: object) -> bool:
    """Reject a constraint sentence, not a product name containing one word.

    The existing Claim resolver catches these semantics when the sentence is
    in an experience body. Explicit headings are outside that body in some
    inputs, so this narrow syntactic check closes the provenance gap without
    treating every occurrence of "没有" as a negative assertion.
    """
    compact = _compact(value)
    return bool(_NEGATIVE_ASSERTION_TITLE.search(compact) or _INSTRUCTION_TITLE.search(compact))


def _clean_entity_name(value: object) -> str:
    name = _display_form(value)
    name = re.sub(r"^(?:一个|一套)\s*", "", name)
    return name


def _candidate_from_match(
    match: re.Match[str],
    *,
    source: str,
    identity: ExperienceIdentity,
    source_claim_ids: tuple[str, ...] = (),
) -> _DisplayNameCandidate | None:
    # A verb phrase can match inside a negative statement (for example,
    # "没有开发 AI 系统").  The surrounding source still belongs to the
    # candidate's owner, but it is not affirmative naming evidence.
    context = match.string[max(0, match.start() - 16):match.end()]
    if _is_semantic_constraint_title(context):
        return None
    value = _clean_entity_name(match.group("name"))
    if not value or _comparison_key(value) in {_comparison_key(item) for item in _GENERIC_ENTITY_NAMES}:
        return None
    # The identity span is the source-owner proof.  It deliberately does not
    # expose the local source text to downstream consumers.
    return _DisplayNameCandidate(
        value=value,
        source=source,
        source_span=identity.source_span,
        source_claim_ids=source_claim_ids,
    )


def _entity_candidates(
    text: str,
    identity: ExperienceIdentity,
    *,
    source_prefix: str,
    source_claim_ids: tuple[str, ...] = (),
) -> tuple[_DisplayNameCandidate, ...]:
    candidates: list[_DisplayNameCandidate] = []
    for pattern, source in (
        (_EXPLICIT_NAME_DECLARATION, f"{source_prefix}_name_declaration"),
        (_PROJECT_ENTITY, f"{source_prefix}_project_entity"),
        (_PRODUCT_IDENTIFIER, f"{source_prefix}_product_identifier"),
        (_ACTIVITY_ENTITY, f"{source_prefix}_activity_entity"),
    ):
        for match in pattern.finditer(text):
            candidate = _candidate_from_match(
                match,
                source=source,
                identity=identity,
                source_claim_ids=source_claim_ids,
            )
            if candidate is not None:
                candidates.append(candidate)
    return tuple(candidates)


def _eligible_claim_candidates(
    identity: ExperienceIdentity,
    resolution: ClaimResolution,
) -> tuple[_DisplayNameCandidate, ...]:
    candidates: list[_DisplayNameCandidate] = []
    for claim in resolution.claims:
        eligibility, _ = effective_claim_eligibility(claim)
        if (
            claim.source_experience_id != identity.experience_id
            or eligibility != ELIGIBLE
            or claim.polarity == NEGATIVE
            or claim.certainty != CONFIRMED
        ):
            continue
        candidates.extend(
            _entity_candidates(
                claim.text,
                identity,
                source_prefix="eligible_claim",
                source_claim_ids=(claim.claim_id,),
            )
        )
    return tuple(candidates)


def _heading_candidate(identity: ExperienceIdentity) -> tuple[_DisplayNameCandidate, ...]:
    """Explicit headings are structural proof; semantic titles are not."""
    if identity.boundary_source not in {"explicit_heading", "legacy_explicit_heading"}:
        return ()
    candidates: list[_DisplayNameCandidate] = []
    for value in (identity.canonical_project_name, identity.title, *identity.project_aliases):
        compact = _display_form(value)
        if compact:
            candidates.append(
                _DisplayNameCandidate(
                    value=compact,
                    source="explicit_heading_name",
                    source_span=identity.source_span,
                )
            )
    return tuple(candidates)


def _candidates_for_owner(
    identity: ExperienceIdentity,
    resolution: ClaimResolution,
) -> tuple[_DisplayNameCandidate, ...]:
    """Return only provenance-bearing local candidates, in authority order."""
    raw_candidates = _entity_candidates(identity.raw_text, identity, source_prefix="local")
    ordered = (
        *_heading_candidate(identity),
        *(item for item in raw_candidates if item.source.endswith("name_declaration")),
        *_eligible_claim_candidates(identity, resolution),
        *(item for item in raw_candidates if not item.source.endswith("name_declaration")),
    )
    deduped: list[_DisplayNameCandidate] = []
    seen: set[str] = set()
    for candidate in ordered:
        key = _comparison_key(candidate.value)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return tuple(deduped)


def _untrusted_identity_candidate_reasons(identity: ExperienceIdentity) -> tuple[str, ...]:
    """Describe rejected identity-derived candidates without trusting them."""
    reasons: list[str] = []
    for value in (identity.canonical_project_name, identity.title, *identity.project_aliases):
        display_name = _display_form(value)
        if not display_name:
            continue
        if _is_generic_label(display_name):
            reasons.append("generic_structure_label")
        elif _is_semantic_constraint_title(display_name):
            reasons.append("constraint_statement_title")
        else:
            reasons.append("identity_candidate_without_name_provenance")
    return tuple(dict.fromkeys(reasons))


def _qualify_identity_name(
    identity: ExperienceIdentity,
    resolution: ClaimResolution,
) -> CanonicalDisplayNameQualification:
    """Choose one explicitly sourced name; identity titles never self-prove."""
    fallback_reasons: list[str] = []
    candidates = _candidates_for_owner(identity, resolution)
    candidate_sources = tuple(dict.fromkeys(candidate.source for candidate in candidates))
    for candidate in candidates:
        display_name = _display_form(candidate.value)
        if not display_name or _is_generic_label(display_name):
            fallback_reasons.append("generic_structure_label")
            continue
        if _is_semantic_constraint_title(display_name):
            fallback_reasons.append("constraint_statement_title")
            continue
        reason = candidate.source
        return CanonicalDisplayNameQualification(
            experience_id=identity.experience_id,
            display_name=display_name,
            candidate_source=candidate.source,
            source_span=candidate.source_span,
            status=QUALIFIED,
            reason_codes=(reason,),
            source_claim_ids=candidate.source_claim_ids,
            name_fingerprint=stable_hash(display_name, purpose="canonical_display_name"),
            candidate_sources=candidate_sources,
            rejected_candidate_reason_codes=tuple(dict.fromkeys(fallback_reasons)),
        )

    # A semantic identity title may be useful for compilation diagnostics, but
    # without an independent source it is not a display-name candidate.
    fallback_reasons.extend(_untrusted_identity_candidate_reasons(identity))
    reasons = tuple(dict.fromkeys(fallback_reasons)) or ("name_not_available",)
    return CanonicalDisplayNameQualification(
        experience_id=identity.experience_id,
        display_name="",
        candidate_source="",
        source_span=identity.source_span,
        status=PENDING,
        reason_codes=reasons,
        source_claim_ids=(),
        name_fingerprint=stable_hash(
            f"{identity.experience_id}:{'|'.join(reasons)}",
            purpose="canonical_display_name",
        ),
        candidate_sources=candidate_sources,
        rejected_candidate_reason_codes=reasons,
    )


def build_canonical_display_name_qualifications(
    identities: tuple[ExperienceIdentity, ...],
    claim_resolutions: tuple[ClaimResolution, ...],
) -> tuple[CanonicalDisplayNameQualification, ...]:
    """Make exactly one immutable display-name decision per compiled identity."""
    resolutions = {
        resolution.claims[0].source_experience_id: resolution
        for resolution in claim_resolutions
        if resolution.claims
    }
    return tuple(
        _qualify_identity_name(identity, resolutions.get(identity.experience_id, ClaimResolution()))
        for identity in identities
    )


def write_canonical_display_name_qualification_log(
    qualifications: tuple[CanonicalDisplayNameQualification, ...],
    *,
    stage: str,
    request_id: str = "",
    attempt_id: str = "",
    generation_result_id: int | None = None,
) -> None:
    """Persist aggregate-only evidence; never serialize a title or user text."""
    try:
        source_counts: dict[str, int] = {}
        qualified_source_counts: dict[str, int] = {}
        rejected_reason_counts: dict[str, int] = {}
        for item in qualifications:
            for source in item.candidate_sources or (item.candidate_source or "none",):
                source_counts[source] = source_counts.get(source, 0) + 1
            if item.qualified:
                source = item.candidate_source or "none"
                qualified_source_counts[source] = qualified_source_counts.get(source, 0) + 1
            for reason in item.rejected_candidate_reason_codes:
                rejected_reason_counts[reason] = rejected_reason_counts.get(reason, 0) + 1
        payload = {
            "owners": [item.experience_id for item in qualifications],
            "statuses": [item.status for item in qualifications],
            "sources": [item.candidate_source for item in qualifications],
            "fingerprints": [item.name_fingerprint for item in qualifications],
        }
        row = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "request_id": request_id,
            "attempt_id": attempt_id,
            "generation_result_id": generation_result_id,
            "stage": stage,
            "experience_count": len(qualifications),
            "qualified_name_count": sum(item.qualified for item in qualifications),
            "pending_name_count": sum(not item.qualified for item in qualifications),
            "candidate_source_counts": source_counts,
            "qualified_source_counts": qualified_source_counts,
            "rejected_candidate_reason_counts": rejected_reason_counts,
            "selected_candidate_source": {
                item.experience_id: item.candidate_source or "none"
                for item in qualifications
            },
            "qualification_fingerprint": stable_hash(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                purpose="canonical_display_name_qualification",
            ),
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return
