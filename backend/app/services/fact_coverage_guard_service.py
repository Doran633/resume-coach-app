import json
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
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    ledger = build_experience_fact_ledger(raw_input)
    identities = build_experience_identities(raw_input)
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
        source_ids = set(_project_source_ids(project))
        kept: list[str] = []
        detail_fact_ids: list[list[str]] = []
        existing_fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        for detail_index, raw_detail in enumerate(project.get("details", []) or []):
            detail = str(raw_detail).strip()
            if not detail:
                continue
            if is_generic_detail(detail):
                stats.removed_generic_detail_count += 1
                continue
            bound_fact_ids = (
                [str(item) for item in existing_fact_rows[detail_index]]
                if detail_index < len(existing_fact_rows) and isinstance(existing_fact_rows[detail_index], list)
                else []
            )
            owners = {fact_owner_id(fact_id) for fact_id in bound_fact_ids if fact_owner_id(fact_id)}
            if owners and source_id and owners != {source_id}:
                stats.provenance_conflict_count += 1
                stats.cross_experience_fact_count += 1
                continue
            best, best_score = _best_fact(detail, ledger.facts)
            current_facts = [
                fact for fact in ledger.facts if fact.experience_id in source_ids
            ]
            current_best, current_score = _best_fact(detail, current_facts)
            if best and best.experience_id not in source_ids and best_score >= 0.62 and current_score < 0.45:
                stats.cross_experience_fact_count += 1
                moves.append((best.experience_id, detail, best.fact_id))
                continue
            kept.append(detail)
            detail_fact_ids.append([current_best.fact_id] if current_best and current_score >= 0.45 else [])
        project["details"] = kept
        project["detail_fact_ids"] = detail_fact_ids
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
        facts = [fact for fact in ledger.for_experience(identity.experience_id) if fact.resume_ready_text]
        if not project or not facts:
            stats.missing_fact_ids.extend(fact.fact_id for fact in facts if fact.importance == "high")
            stats.coverage_by_experience_id[identity.experience_id] = 0.0
            continue

        covered = {fact.fact_id for fact in facts if _fact_covered(fact, project)}
        restore_order = sorted(
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

        stats.covered_fact_count += len(covered)
        stats.coverage_by_experience_id[identity.experience_id] = round(len(covered) / max(1, len(facts)), 3)
        stats.missing_fact_ids.extend(fact.fact_id for fact in facts if fact.fact_id not in covered and fact.importance == "high")

    if write_log:
        _write_log(stats)
    return updated
