import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import (
    ExperienceFact,
    build_experience_fact_ledger,
    fact_match_score,
    fact_signature_terms,
    is_generic_detail,
)
from .experience_identity_service import build_experience_identities
from .experience_slot_service import fact_owner_id
from .canonical_semantic_state_service import (
    CanonicalScopedFactAccessStats,
    canonical_fact_scope_for_owner,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .canonical_semantic_state_service import CanonicalFactOwnershipIndex, CanonicalSemanticBuild


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "fact_coverage.jsonl"
MAX_PROJECT_DETAILS = 8
MAX_TOTAL_DETAILS = 20


@dataclass
class CoverageStats:
    stage: str
    generation_result_id: int | None = None
    total_experiences: int = 0
    explicit_fact_count: int = 0
    high_value_fact_count: int = 0
    covered_fact_count: int = 0
    restored_fact_count: int = 0
    cross_experience_fact_count: int = 0
    coverage_by_experience_id: dict[str, float] = field(default_factory=dict)
    missing_fact_ids: list[str] = field(default_factory=list)
    removed_generic_detail_count: int = 0
    provenance_conflict_count: int = 0


def _project_text(project: dict) -> str:
    details = project.get("details", []) if isinstance(project.get("details"), list) else []
    return "\n".join([str(project.get("intro", "")), str(project.get("role", "")), *map(str, details)])


def _project_source_ids(project: dict) -> list[str]:
    values: list[str] = []
    for key in ["immutable_source_experience_id", "source_experience_id", "merged_source_experience_ids", "source_experience_ids"]:
        raw = project.get(key)
        rows = raw if isinstance(raw, list) else [raw]
        for item in rows:
            value = str(item or "").strip()
            if value and value not in values:
                values.append(value)
    return values


def _ids(value: object) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item or "").strip()))


def _canonical_fact_ids(value: object, scope) -> list[str]:
    return [fact_id for fact_id in _ids(value) if scope.permits_fact(fact_id)]


def _canonical_claim_ids(value: object, scope) -> list[str]:
    return [claim_id for claim_id in _ids(value) if scope.permits_claim(claim_id)]


def _has_visible_project_body(project: dict) -> bool:
    return bool(
        str(project.get("intro") or "").strip()
        or str(project.get("role") or "").strip()
        or any(str(item or "").strip() for item in project.get("details", []) or [])
    )


def _fact_covered(fact: ExperienceFact, project: dict) -> bool:
    project_text = _project_text(project).lower()
    signature = fact_signature_terms(fact)
    if len(signature) >= 2:
        hit_ratio = sum(term in project_text for term in signature) / len(signature)
        if hit_ratio < 0.8:
            return False
    return fact_match_score(project_text, fact) >= 0.52


def _best_fact(text: str, facts: list[ExperienceFact]) -> tuple[ExperienceFact | None, float]:
    ranked = sorted(((fact, fact_match_score(text, fact)) for fact in facts), key=lambda item: item[1], reverse=True)
    return ranked[0] if ranked else (None, 0.0)


def _requires_local_evidence(text: str) -> bool:
    return bool(re.search(
        r"(?:React|FastAPI|Docker|RAG|Embedding|Nginx|systemd|Python|TypeScript|"
        r"\d+(?:\.\d+)?\s*(?:%|条|次|token|用户|人)|部署|上线|测试集|命中率|提升|降低)",
        text or "",
        re.IGNORECASE,
    ))


def _write_log(stats: CoverageStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "generation_result_id": stats.generation_result_id,
            "stage": stats.stage,
            "total_experiences": stats.total_experiences,
            "explicit_fact_count": stats.explicit_fact_count,
            "high_value_fact_count": stats.high_value_fact_count,
            "covered_fact_count": stats.covered_fact_count,
            "restored_fact_count": stats.restored_fact_count,
            "cross_experience_fact_count": stats.cross_experience_fact_count,
            "coverage_by_experience_id": stats.coverage_by_experience_id,
            "missing_fact_ids": stats.missing_fact_ids,
            "removed_generic_detail_count": stats.removed_generic_detail_count,
            "provenance_conflict_count": stats.provenance_conflict_count,
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def guard_fact_coverage(
    payload: schemas.GenerationPayload,
    raw_input: str,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
    semantic_build: "CanonicalSemanticBuild | None" = None,
    ownership_index: "CanonicalFactOwnershipIndex | None" = None,
    scoped_access_stats: CanonicalScopedFactAccessStats | None = None,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    canonical_mode = semantic_build is not None or ownership_index is not None
    ownership = ownership_index or (semantic_build.ownership_index if semantic_build is not None else None)
    ledger = semantic_build.ledger if semantic_build is not None else build_experience_fact_ledger(raw_input)
    identities = list(semantic_build.identities) if semantic_build is not None else build_experience_identities(raw_input)
    stats = CoverageStats(stage=stage, generation_result_id=generation_result_id)
    stats.total_experiences = len(identities)
    stats.explicit_fact_count = len(ledger.facts)
    stats.high_value_fact_count = sum(fact.importance == "high" for fact in ledger.facts)

    projects = updated.resume_sections.projects
    project_by_source: dict[str, dict] = {}
    for project in projects:
        for source_id in _project_source_ids(project):
            project_by_source[source_id] = project

    moves: list[tuple[str, str, str]] = []
    for project in projects:
        source_id = str(project.get("immutable_source_experience_id") or project.get("source_experience_id") or "")
        scope = canonical_fact_scope_for_owner(ownership, source_id) if canonical_mode else None
        source_ids = {source_id} if scope is not None else set(_project_source_ids(project))
        if canonical_mode and scope is None:
            if scoped_access_stats is not None:
                scoped_access_stats.unowned_project_skipped_count += 1
            project["source_fact_ids"] = []
            project["role_source_fact_ids"] = []
            project["detail_fact_ids"] = [[] for _ in project.get("details", []) or []]
            project["source_claim_ids"] = []
            project["role_source_claim_ids"] = []
            project["detail_claim_ids"] = [[] for _ in project.get("details", []) or []]
            continue
        if scope is not None and scoped_access_stats is not None:
            scoped_access_stats.record_scope_read()
        scoped_facts = scope.eligible_facts(ledger) if scope is not None else [
            fact for fact in ledger.facts if fact.experience_id in source_ids
        ]
        preserved_project_fact_ids = _canonical_fact_ids(project.get("source_fact_ids"), scope) if scope is not None else []
        preserved_role_fact_ids = _canonical_fact_ids(project.get("role_source_fact_ids"), scope) if scope is not None else []
        preserved_project_claim_ids = _canonical_claim_ids(project.get("source_claim_ids"), scope) if scope is not None else []
        preserved_role_claim_ids = _canonical_claim_ids(project.get("role_source_claim_ids"), scope) if scope is not None else []
        if scope is not None and (
            len(preserved_project_fact_ids) != len(_ids(project.get("source_fact_ids")))
            or len(preserved_role_fact_ids) != len(_ids(project.get("role_source_fact_ids")))
            or len(preserved_project_claim_ids) != len(_ids(project.get("source_claim_ids")))
            or len(preserved_role_claim_ids) != len(_ids(project.get("role_source_claim_ids")))
        ):
            stats.provenance_conflict_count += 1
            if scoped_access_stats is not None:
                scoped_access_stats.rejected_cross_owner_access_count += 1
        kept: list[str] = []
        detail_fact_ids: list[list[str]] = []
        detail_claim_ids: list[list[str]] = []
        removed_detail_fact_ids: set[str] = set()
        removed_detail_claim_ids: set[str] = set()
        existing_fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        existing_claim_rows = project.get("detail_claim_ids") if isinstance(project.get("detail_claim_ids"), list) else []
        for detail_index, raw_detail in enumerate(project.get("details", []) or []):
            detail = str(raw_detail).strip()
            if not detail:
                continue
            bound_fact_ids = (
                [str(item) for item in existing_fact_rows[detail_index]]
                if detail_index < len(existing_fact_rows) and isinstance(existing_fact_rows[detail_index], list)
                else []
            )
            bound_claim_ids = (
                [str(item) for item in existing_claim_rows[detail_index]]
                if detail_index < len(existing_claim_rows) and isinstance(existing_claim_rows[detail_index], list)
                else []
            )
            if is_generic_detail(detail):
                stats.removed_generic_detail_count += 1
                removed_detail_fact_ids.update(bound_fact_ids)
                removed_detail_claim_ids.update(bound_claim_ids)
                continue
            if scope is not None:
                valid_fact_ids = _canonical_fact_ids(bound_fact_ids, scope)
                valid_claim_ids = _canonical_claim_ids(bound_claim_ids, scope)
                if len(valid_fact_ids) != len(_ids(bound_fact_ids)) or len(valid_claim_ids) != len(_ids(bound_claim_ids)):
                    stats.provenance_conflict_count += 1
                    stats.cross_experience_fact_count += 1
                    if scoped_access_stats is not None:
                        scoped_access_stats.rejected_cross_owner_access_count += 1
                    continue
                bound_fact_ids = valid_fact_ids
                bound_claim_ids = valid_claim_ids
            owners = {fact_owner_id(fact_id) for fact_id in bound_fact_ids if fact_owner_id(fact_id)}
            if owners and source_id and (owners != {source_id} or (scope is not None and not all(scope.permits_fact(fact_id) for fact_id in bound_fact_ids))):
                stats.provenance_conflict_count += 1
                stats.cross_experience_fact_count += 1
                if scoped_access_stats is not None:
                    scoped_access_stats.rejected_cross_owner_access_count += 1
                continue
            current_best, current_score = _best_fact(detail, scoped_facts)
            if canonical_mode:
                if not bound_fact_ids and _requires_local_evidence(detail) and current_score < 0.45:
                    stats.cross_experience_fact_count += 1
                    if scoped_access_stats is not None:
                        scoped_access_stats.rejected_cross_owner_access_count += 1
                    continue
            else:
                best, best_score = _best_fact(detail, ledger.facts)
                if best and best.experience_id not in source_ids and best_score >= 0.62 and current_score < 0.45:
                    stats.cross_experience_fact_count += 1
                    moves.append((best.experience_id, detail, best.fact_id))
                    continue
            kept.append(detail)
            detail_fact_ids.append(bound_fact_ids or ([current_best.fact_id] if current_best and current_score >= 0.45 else []))
            detail_claim_ids.append(bound_claim_ids)
        project["details"] = kept
        project["detail_fact_ids"] = detail_fact_ids
        project["detail_claim_ids"] = detail_claim_ids
        if scope is not None:
            if not _has_visible_project_body(project):
                project["source_fact_ids"] = []
                project["role_source_fact_ids"] = []
                project["source_claim_ids"] = []
                project["role_source_claim_ids"] = []
            else:
                role_fact_ids = preserved_role_fact_ids if str(project.get("role") or "").strip() else []
                role_claim_ids = preserved_role_claim_ids if str(project.get("role") or "").strip() else []
                surviving_fact_ids = {
                    fact_id for ids in detail_fact_ids for fact_id in ids
                } | set(role_fact_ids)
                surviving_claim_ids = {
                    claim_id for ids in detail_claim_ids for claim_id in ids
                } | set(role_claim_ids)
                preserved_project_fact_ids = [
                    fact_id for fact_id in preserved_project_fact_ids
                    if fact_id not in removed_detail_fact_ids or fact_id in surviving_fact_ids
                ]
                preserved_project_claim_ids = [
                    claim_id for claim_id in preserved_project_claim_ids
                    if claim_id not in removed_detail_claim_ids or claim_id in surviving_claim_ids
                ]
                project["source_fact_ids"] = list(dict.fromkeys([
                    *preserved_project_fact_ids,
                    *role_fact_ids,
                    *(fact_id for ids in detail_fact_ids for fact_id in ids),
                ]))
                project["source_claim_ids"] = list(dict.fromkeys([
                    *preserved_project_claim_ids,
                    *role_claim_ids,
                    *(claim_id for ids in detail_claim_ids for claim_id in ids),
                ]))
                if "role_source_fact_ids" in project:
                    project["role_source_fact_ids"] = role_fact_ids
                if "role_source_claim_ids" in project:
                    project["role_source_claim_ids"] = role_claim_ids
        else:
            project["source_fact_ids"] = list(dict.fromkeys(fact_id for ids in detail_fact_ids for fact_id in ids))

    for target_id, detail, fact_id in moves:
        target = project_by_source.get(target_id)
        target_owner = str(target.get("immutable_source_experience_id") or target.get("source_experience_id") or "") if target else ""
        if target is not None and target_owner == target_id and detail not in target.get("details", []):
            target.setdefault("details", []).append(detail)
            target.setdefault("detail_fact_ids", []).append([fact_id])
            if fact_id not in target.setdefault("source_fact_ids", []):
                target["source_fact_ids"].append(fact_id)

    total_details = sum(len(project.get("details", [])) for project in projects)
    for identity in identities:
        project = project_by_source.get(identity.experience_id)
        if project and str(project.get("immutable_source_experience_id") or project.get("source_experience_id") or "") != identity.experience_id:
            project = None
            stats.provenance_conflict_count += 1
        scope = canonical_fact_scope_for_owner(ownership, identity.experience_id) if canonical_mode else None
        if canonical_mode and scope is None:
            stats.coverage_by_experience_id[identity.experience_id] = 0.0
            continue
        if scope is not None and scoped_access_stats is not None:
            scoped_access_stats.record_scope_read()
        facts = [
            fact for fact in (scope.eligible_facts(ledger) if scope is not None else ledger.for_experience(identity.experience_id))
            if fact.resume_ready_text
        ]
        if not project or not facts:
            stats.missing_fact_ids.extend(fact.fact_id for fact in facts if fact.importance == "high")
            stats.coverage_by_experience_id[identity.experience_id] = 0.0
            continue

        covered = {fact.fact_id for fact in facts if _fact_covered(fact, project)}
        # Canonical body recovery belongs exclusively to the pre-presentation
        # project projection plan. Legacy callers retain their existing API.
        restore_order = [] if canonical_mode else sorted(
            (fact for fact in facts if fact.fact_id not in covered),
            key=lambda fact: {"high": 0, "medium": 1, "low": 2}[fact.importance],
        )
        for fact in restore_order:
            ratio = len(covered) / max(1, len(facts))
            must_restore = fact.importance == "high" or ratio < 0.8
            if not must_restore or len(project.get("details", [])) >= MAX_PROJECT_DETAILS or total_details >= MAX_TOTAL_DETAILS:
                continue
            wording = fact.resume_ready_text
            if wording and wording not in project.get("details", []):
                project.setdefault("details", []).append(wording)
                project.setdefault("detail_fact_ids", []).append([fact.fact_id])
                if fact.fact_id not in project.setdefault("source_fact_ids", []):
                    project["source_fact_ids"].append(fact.fact_id)
                covered.add(fact.fact_id)
                total_details += 1
                stats.restored_fact_count += 1
                if scoped_access_stats is not None:
                    scoped_access_stats.local_fact_recovered_count += 1

        stats.covered_fact_count += len(covered)
        stats.coverage_by_experience_id[identity.experience_id] = round(len(covered) / max(1, len(facts)), 3)
        stats.missing_fact_ids.extend(fact.fact_id for fact in facts if fact.fact_id not in covered and fact.importance == "high")

    if write_log:
        _write_log(stats)
    return updated
