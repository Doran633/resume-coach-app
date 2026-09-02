import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import build_experience_fact_ledger, fact_match_score
from .experience_identity_service import ExperienceIdentity, build_experience_identities

if TYPE_CHECKING:
    from .canonical_semantic_state_service import CanonicalFactOwnershipIndex, CanonicalSemanticBuild


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "experience_slot_binding.jsonl"
INTERNAL_SLOT_FIELDS = {
    "immutable_source_experience_id",
    "source_binding_origin",
    "source_binding_confidence",
    "source_binding_locked",
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
    bindings: list[dict] = field(default_factory=list)


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


def _write_log(stats: SlotBindingStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "stage": stats.stage,
            "generation_result_id": stats.generation_result_id,
            "rejected_binding_count": stats.rejected_binding_count,
            "provenance_conflict_count": stats.provenance_conflict_count,
            "bindings": stats.bindings,
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def bind_projects_to_experience_slots(
    payload: schemas.GenerationPayload,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
    semantic_build: "CanonicalSemanticBuild | None" = None,
    ownership_index: "CanonicalFactOwnershipIndex | None" = None,
    return_stats: bool = False,
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

    for position, project in enumerate(updated.resume_sections.projects):
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
                if identity.experience_id not in used
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
            existing_score, existing_reasons = _candidate_score(project, identity_by_id[existing], raw_input, ledger)
            if existing_score >= 0.62 and existing not in used:
                chosen = identity_by_id[existing]
                origin = "llm_id_validated"
                confidence = existing_score
            elif best and best[1] >= 0.72 and best[1] - runner_score >= 0.16:
                chosen = best[0]
                origin = "corrected_by_title_and_local_fact"
                confidence = best[1]
                stats.provenance_conflict_count += 1
            else:
                stats.rejected_binding_count += 1
        elif existing:
            stats.rejected_binding_count += 1
        elif best and best[1] >= 0.72 and best[1] - runner_score >= 0.16:
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
            if canonical_mode and (canonical_index is None or source_id not in canonical_index.source_experience_ids):
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
