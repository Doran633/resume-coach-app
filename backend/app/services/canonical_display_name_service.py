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

    @property
    def qualified(self) -> bool:
        return self.status == QUALIFIED and bool(self.display_name)


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


def _candidate_rows(identity: ExperienceIdentity) -> tuple[tuple[str, str], ...]:
    """Return all identity-derived candidates; none is trusted by default."""
    raw = (
        ("canonical_project_name", identity.canonical_project_name),
        ("identity_title", identity.title),
        *(("project_alias", alias) for alias in identity.project_aliases),
    )
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source, value in raw:
        compact = _compact(value)
        key = _comparison_key(compact)
        if not compact or not key or key in seen:
            continue
        seen.add(key)
        deduped.append((source, compact))
    return tuple(deduped)


def _matching_claims(candidate: str, resolution: ClaimResolution) -> tuple:
    candidate_key = _comparison_key(candidate)
    if not candidate_key:
        return ()
    matches = []
    for claim in resolution.claims:
        claim_key = _comparison_key(claim.text)
        if claim_key and (candidate_key == claim_key or candidate_key in claim_key or claim_key in candidate_key):
            matches.append(claim)
    return tuple(matches)


def _claim_reasons(matches: tuple) -> tuple[str, ...]:
    reasons: list[str] = []
    for claim in matches:
        eligibility, _ = effective_claim_eligibility(claim)
        if eligibility != ELIGIBLE:
            reasons.append(f"claim_{eligibility}")
        if claim.polarity == NEGATIVE:
            reasons.append("negative_claim")
        if claim.semantic_role in {"USER_INSTRUCTION", "NEGATIVE_CONSTRAINT", "UNCERTAIN_FACT", "STRUCTURE_MARKER"}:
            reasons.append(claim.semantic_role.lower())
    return tuple(dict.fromkeys(reasons))


def _qualify_identity_name(
    identity: ExperienceIdentity,
    resolution: ClaimResolution,
) -> CanonicalDisplayNameQualification:
    """Choose the first independently proven candidate for one owner.

    An explicit heading supplies structural provenance for a non-generic title.
    A semantic title instead needs a compatible eligible Claim.  Negative is a
    Claim attribute here, never a raw keyword rule, so a legitimate product
    name containing "没有" is not rejected merely by spelling.
    """
    fallback_reasons: list[str] = []
    for source, raw_candidate in _candidate_rows(identity):
        display_name = _display_form(raw_candidate)
        if not display_name or _is_generic_label(display_name):
            fallback_reasons.append("generic_structure_label")
            continue
        if _is_semantic_constraint_title(display_name):
            fallback_reasons.append("constraint_statement_title")
            continue
        matches = _matching_claims(raw_candidate, resolution)
        claim_reasons = _claim_reasons(matches)
        if claim_reasons:
            fallback_reasons.extend(claim_reasons)
            continue
        eligible_matches = tuple(
            claim for claim in matches
            if effective_claim_eligibility(claim)[0] == ELIGIBLE
            and claim.polarity != NEGATIVE
            and claim.certainty == CONFIRMED
        )
        heading_proven = bool(
            identity.boundary_source == "explicit_heading"
            and identity.declared_experience_type
        )
        if not (heading_proven or eligible_matches):
            fallback_reasons.append("unproven_name_source")
            continue
        reason = "explicit_heading_name" if heading_proven else "eligible_claim_name"
        return CanonicalDisplayNameQualification(
            experience_id=identity.experience_id,
            display_name=display_name,
            candidate_source=source,
            source_span=identity.source_span,
            status=QUALIFIED,
            reason_codes=(reason,),
            source_claim_ids=tuple(claim.claim_id for claim in eligible_matches),
            name_fingerprint=stable_hash(display_name, purpose="canonical_display_name"),
        )

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
        reason_counts: dict[str, int] = {}
        for item in qualifications:
            source_counts[item.candidate_source or "none"] = source_counts.get(item.candidate_source or "none", 0) + 1
            for reason in item.reason_codes:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
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
            "reason_code_counts": reason_counts,
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
