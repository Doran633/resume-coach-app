import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .resume_adaptive_narrative_service import narrative_dimension, narrative_distribution, narrative_order
from .resume_fact_dedup_service import same_fact_action, similarity
from .resume_information_gain_service import information_terms


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_narrative_quality.jsonl"


@dataclass
class NarrativeQualityStats:
    created_at: str
    generation_result_id: int | None
    stage: str
    total_projects: int
    total_details_before: int
    total_details_after: int
    low_information_gain_count: int
    cross_field_repetition_count: int
    reordered_detail_count: int
    merged_detail_count: int
    removed_template_detail_count: int
    narrative_dimension_distribution: dict[str, int]
    template_similarity_count: int
    affected_experience_ids: list[str] = field(default_factory=list)
    information_gain_score: int = 100
    narrative_coherence_score: int = 100
    template_diversity_score: int = 100
    cross_field_repetition_score: int = 100


def _cross_field_repetitions(payload: schemas.GenerationPayload) -> int:
    count = 0
    for project in payload.resume_sections.projects:
        headers = [str(project.get("intro") or ""), str(project.get("role") or "")]
        for detail in project.get("details", []) or []:
            count += any(similarity(str(detail), header) >= 0.90 or same_fact_action(str(detail), header) for header in headers if header)
    return count


def _low_gain_count(payload: schemas.GenerationPayload) -> int:
    count = 0
    for project in payload.resume_sections.projects:
        seen: set[str] = set()
        for detail in project.get("details", []) or []:
            terms = information_terms(str(detail))
            if not terms or terms <= seen:
                count += 1
            seen.update(terms)
    return count


def _template_similarity(payload: schemas.GenerationPayload) -> int:
    starts = Counter()
    for project in payload.resume_sections.projects:
        for detail in project.get("details", []) or []:
            value = str(detail).strip()
            starts[value[:6]] += 1
    return sum(count - 1 for prefix, count in starts.items() if prefix and count > 1)


def evaluate_narrative_quality(
    payload: schemas.GenerationPayload,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
    change_stats: dict | None = None,
) -> NarrativeQualityStats:
    change_stats = change_stats or {}
    details = [str(item) for project in payload.resume_sections.projects for item in project.get("details", []) or []]
    low_gain = _low_gain_count(payload)
    cross_field = _cross_field_repetitions(payload)
    template_count = _template_similarity(payload)
    disorder = 0
    for project in payload.resume_sections.projects:
        order = narrative_order(str(project.get("meta") or ""))
        rank = {dimension: index for index, dimension in enumerate(order)}
        values = [rank.get(narrative_dimension(str(item)), len(rank)) for item in project.get("details", []) or []]
        disorder += sum(left > right for left, right in zip(values, values[1:]))
    total = max(1, len(details))
    stats = NarrativeQualityStats(
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        generation_result_id=generation_result_id,
        stage=stage,
        total_projects=len(payload.resume_sections.projects),
        total_details_before=len(details),
        total_details_after=len(details),
        low_information_gain_count=low_gain,
        cross_field_repetition_count=cross_field,
        reordered_detail_count=int(change_stats.get("reordered_detail_count", 0)),
        merged_detail_count=int(change_stats.get("merged_detail_count", 0)),
        removed_template_detail_count=int(change_stats.get("removed_template_detail_count", 0)),
        narrative_dimension_distribution=narrative_distribution(payload),
        template_similarity_count=template_count,
        affected_experience_ids=[str(project.get("source_experience_id")) for project in payload.resume_sections.projects if project.get("source_experience_id")],
        information_gain_score=max(0, round(100 - low_gain / total * 100)),
        narrative_coherence_score=max(0, 100 - disorder * 15),
        template_diversity_score=max(0, 100 - template_count * 12),
        cross_field_repetition_score=max(0, 100 - cross_field * 20),
    )
    if write_log:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(stats), ensure_ascii=False) + "\n")
        except OSError:
            pass
    return stats
