import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import build_experience_fact_ledger, fact_match_score
from .resume_fact_dedup_service import same_fact_action, similarity
from .resume_typography_quality_service import count_typography_issues
from .resume_narrative_coherence_service import evaluate_narrative_quality
from .resume_fact_cluster_dedup_service import evaluate_semantic_quality


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_output_quality.jsonl"
COLLOQUIAL = ["我做过", "我写了", "我调了", "技术动作", "随便做", "简单小项目"]
INTERNAL = ["source_experience_id", "source_fact_ids", "detail_fact_ids", "fact_id", "原文截断", "需补充原文", "section summary", "section 个人优势"]
COACHING = ["面试准备清单", "如果被问到", "建议补充", "降级表达", "可面试承接"]


@dataclass
class OutputQualityScores:
    created_at: str
    generation_result_id: int | None
    stage: str
    fact_coverage_score: int
    experience_boundary_score: int
    duplicate_score: int
    language_professionalism_score: int
    typography_score: int
    internal_marker_score: int
    delivery_readiness_score: int
    information_gain_score: int
    narrative_coherence_score: int
    template_diversity_score: int
    cross_field_repetition_score: int
    semantic_completeness_score: int
    sentence_independence_score: int
    information_density_score: int
    fact_cluster_uniqueness_score: int
    overall_quality_score: int
    warning_codes: list[str] = field(default_factory=list)


def _visible_text(payload: schemas.GenerationPayload) -> str:
    sections = payload.resume_sections
    values = [*sections.summary, *sections.skills]
    for project in sections.projects:
        values.extend(str(project.get(key) or "") for key in ["name", "position", "meta", "time", "intro", "role"])
        values.extend(str(item) for item in project.get("details", []))
    return "\n".join(values)


def _fact_coverage(payload: schemas.GenerationPayload, raw_input: str) -> int:
    ledger = build_experience_fact_ledger(raw_input)
    high_facts = [fact for fact in ledger.facts if fact.importance == "high" and fact.resume_ready_text]
    if not high_facts:
        return 100
    project_text = {
        str(project.get("source_experience_id") or ""): "\n".join([
            str(project.get("intro") or ""), str(project.get("role") or ""),
            *[str(item) for item in project.get("details", [])],
        ])
        for project in payload.resume_sections.projects
    }
    covered = sum(fact_match_score(project_text.get(fact.experience_id, ""), fact) >= 0.48 for fact in high_facts)
    return round(covered / len(high_facts) * 100)


def _boundary_score(payload: schemas.GenerationPayload) -> int:
    projects = payload.resume_sections.projects
    if not projects:
        return 0
    ids = [str(project.get("source_experience_id") or "") for project in projects]
    missing = sum(not value for value in ids)
    duplicate_ids = len([value for value in ids if value]) - len(set(value for value in ids if value))
    return max(0, 100 - missing * 30 - duplicate_ids * 20)


def _duplicate_count(payload: schemas.GenerationPayload) -> int:
    count = 0
    for project in payload.resume_sections.projects:
        values = [str(project.get("intro") or ""), str(project.get("role") or ""), *[str(item) for item in project.get("details", [])]]
        values = [value for value in values if value]
        for index, left in enumerate(values):
            for right in values[index + 1:]:
                if similarity(left, right) >= 0.90 or same_fact_action(left, right):
                    count += 1
    return count


def evaluate_resume_output_quality(
    payload: schemas.GenerationPayload,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> OutputQualityScores:
    text = _visible_text(payload)
    duplicate_count = _duplicate_count(payload)
    typography_issues = count_typography_issues(text)
    colloquial_count = sum(text.count(marker) for marker in COLLOQUIAL)
    internal_count = sum(text.lower().count(marker.lower()) for marker in INTERNAL)
    coaching_count = sum(text.count(marker) for marker in COACHING)
    empty_required = sum(
        not str(project.get(key) or "").strip()
        for project in payload.resume_sections.projects
        for key in ["name", "intro", "role"]
    )
    narrative = evaluate_narrative_quality(
        payload, stage=stage, generation_result_id=generation_result_id, write_log=False,
    )
    semantic = evaluate_semantic_quality(payload)

    scores = {
        "fact_coverage_score": _fact_coverage(payload, raw_input),
        "experience_boundary_score": _boundary_score(payload),
        "duplicate_score": max(0, 100 - duplicate_count * 15),
        "language_professionalism_score": max(0, 100 - colloquial_count * 20),
        "typography_score": max(0, 100 - typography_issues * 10),
        "internal_marker_score": max(0, 100 - internal_count * 25),
        "delivery_readiness_score": max(0, 100 - coaching_count * 20 - empty_required * 15),
        "information_gain_score": narrative.information_gain_score,
        "narrative_coherence_score": narrative.narrative_coherence_score,
        "template_diversity_score": narrative.template_diversity_score,
        "cross_field_repetition_score": narrative.cross_field_repetition_score,
        **semantic,
    }
    warning_codes = []
    thresholds = {
        "fact_coverage_score": (80, "LOW_FACT_COVERAGE"),
        "experience_boundary_score": (90, "EXPERIENCE_BOUNDARY_RISK"),
        "duplicate_score": (85, "DUPLICATE_CONTENT"),
        "typography_score": (95, "TYPOGRAPHY_ISSUES"),
        "internal_marker_score": (100, "INTERNAL_MARKER_LEAK"),
        "delivery_readiness_score": (90, "DELIVERY_NOT_READY"),
        "information_gain_score": (85, "LOW_INFORMATION_GAIN"),
        "narrative_coherence_score": (80, "NARRATIVE_COHERENCE_RISK"),
        "template_diversity_score": (80, "TEMPLATE_LANGUAGE_RISK"),
        "cross_field_repetition_score": (90, "CROSS_FIELD_REPETITION"),
        "semantic_completeness_score": (90, "SEMANTIC_FRAGMENT_RISK"),
        "sentence_independence_score": (85, "SENTENCE_DEPENDENCY_RISK"),
        "information_density_score": (85, "LOW_INFORMATION_DENSITY"),
        "fact_cluster_uniqueness_score": (90, "FACT_CLUSTER_DUPLICATION"),
    }
    for key, (threshold, code) in thresholds.items():
        if scores[key] < threshold:
            warning_codes.append(code)
    overall = round(sum(scores.values()) / len(scores))
    result = OutputQualityScores(
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        generation_result_id=generation_result_id,
        stage=stage,
        overall_quality_score=overall,
        warning_codes=warning_codes,
        **scores,
    )
    if write_log:
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")
        except Exception:
            pass
    return result
