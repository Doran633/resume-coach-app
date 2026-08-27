import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .resume_fact_cluster_service import classify_fact_cluster
from .resume_fact_dedup_service import information_score, similarity
from .resume_semantic_unit_service import fragment_reasons


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_semantic_quality.jsonl"


@dataclass
class SemanticQualityStats:
    created_at: str
    generation_result_id: int | None
    stage: str
    total_details_before: int = 0
    total_details_after: int = 0
    fragment_detected_count: int = 0
    fragment_recovered_count: int = 0
    fragment_removed_count: int = 0
    adjacent_units_merged_count: int = 0
    fact_cluster_count: int = 0
    duplicate_cluster_count: int = 0
    generic_summary_removed_count: int = 0
    low_information_gain_removed_count: int = 0
    independent_fact_preserved_count: int = 0
    semantic_completeness_score: int = 100
    sentence_independence_score: int = 100
    information_density_score: int = 100
    fact_cluster_uniqueness_score: int = 100
    cluster_dedup_precision_warning_count: int = 0
    affected_experience_ids: list[str] | None = None


def _is_duplicate(left: str, right: str, left_ids: list[str], right_ids: list[str]) -> bool:
    a, b = classify_fact_cluster(left), classify_fact_cluster(right)
    if a.name != b.name:
        return False
    unique_left, unique_right = a.components - b.components, b.components - a.components
    if unique_left and unique_right:
        return False
    shared_source = bool(set(left_ids) & set(right_ids))
    return similarity(left, right) >= 0.82 or shared_source or bool(a.components and (a.components <= b.components or b.components <= a.components))


def deduplicate_fact_clusters(
    payload: schemas.GenerationPayload,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    change_stats: dict | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    changes = change_stats or {}
    before_total = 0
    after_total = 0
    duplicate_count = 0
    cluster_names: set[tuple[str, str]] = set()
    affected: list[str] = []
    preserved = 0
    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        details = [str(item).strip() for item in project.get("details", []) if str(item).strip()]
        fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        before_total += len(details)
        kept: list[tuple[str, list[str]]] = []
        for index, detail in enumerate(details):
            ids = [str(item) for item in fact_rows[index]] if index < len(fact_rows) and isinstance(fact_rows[index], list) else []
            cluster_names.add((source_id, classify_fact_cluster(detail).name))
            match = next((position for position, (existing, existing_ids) in enumerate(kept) if _is_duplicate(existing, detail, existing_ids, ids)), -1)
            if match < 0:
                kept.append((detail, ids))
                preserved += 1
                continue
            duplicate_count += 1
            affected.append(source_id)
            existing, existing_ids = kept[match]
            if information_score(detail, ids) > information_score(existing, existing_ids):
                kept[match] = (detail, list(dict.fromkeys([*existing_ids, *ids])))
            else:
                kept[match] = (existing, list(dict.fromkeys([*existing_ids, *ids])))
        project["details"] = [item[0] for item in kept]
        project["detail_fact_ids"] = [item[1] for item in kept]
        project["source_fact_ids"] = list(dict.fromkeys(fact_id for _, ids in kept for fact_id in ids))
        after_total += len(kept)

    all_details = [str(detail) for project in updated.resume_sections.projects for detail in project.get("details", []) or []]
    fragment_count = sum(bool(fragment_reasons(detail)) for detail in all_details)
    total = max(1, len(all_details))
    stats = SemanticQualityStats(
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        generation_result_id=generation_result_id,
        stage=stage,
        total_details_before=before_total,
        total_details_after=after_total,
        fragment_detected_count=int(changes.get("fragment_detected_count", 0)),
        fragment_recovered_count=int(changes.get("fragment_recovered_count", 0)),
        fragment_removed_count=int(changes.get("fragment_removed_count", 0)),
        adjacent_units_merged_count=int(changes.get("adjacent_units_merged_count", 0)),
        fact_cluster_count=len(cluster_names),
        duplicate_cluster_count=duplicate_count,
        generic_summary_removed_count=int(changes.get("generic_summary_removed_count", 0)),
        low_information_gain_removed_count=int(changes.get("low_information_gain_count", 0)),
        independent_fact_preserved_count=preserved,
        semantic_completeness_score=max(0, round(100 - fragment_count / total * 100)),
        sentence_independence_score=max(0, round(100 - fragment_count / total * 100)),
        information_density_score=max(0, round(100 - duplicate_count / max(1, before_total) * 100)),
        fact_cluster_uniqueness_score=max(0, round(100 - duplicate_count / max(1, before_total) * 100)),
        affected_experience_ids=sorted(set(item for item in affected if item)),
    )
    if write_log:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(stats), ensure_ascii=False) + "\n")
        except OSError:
            pass
    return updated


def evaluate_semantic_quality(payload: schemas.GenerationPayload) -> dict[str, int]:
    details = [str(detail) for project in payload.resume_sections.projects for detail in project.get("details", []) or []]
    fragments = sum(bool(fragment_reasons(detail)) for detail in details)
    duplicates = 0
    for project in payload.resume_sections.projects:
        rows = [str(item) for item in project.get("details", []) or []]
        ids = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        for index, left in enumerate(rows):
            left_ids = ids[index] if index < len(ids) and isinstance(ids[index], list) else []
            for right_index in range(index + 1, len(rows)):
                right_ids = ids[right_index] if right_index < len(ids) and isinstance(ids[right_index], list) else []
                duplicates += _is_duplicate(left, rows[right_index], left_ids, right_ids)
    total = max(1, len(details))
    return {
        "semantic_completeness_score": max(0, round(100 - fragments / total * 100)),
        "sentence_independence_score": max(0, round(100 - fragments / total * 100)),
        "information_density_score": max(0, round(100 - duplicates / total * 100)),
        "fact_cluster_uniqueness_score": max(0, round(100 - duplicates / total * 100)),
    }
