import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .experience_fact_ledger_service import build_experience_fact_ledger, fact_match_score
from .resume_role_resolution_service import resolve_role_for_experience
from .experience_slot_service import fact_owner_id
from .canonical_semantic_state_service import (
    CanonicalScopedFactAccessStats,
    canonical_fact_scope_for_owner,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .canonical_semantic_state_service import CanonicalFactOwnershipIndex, CanonicalSemanticBuild


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_PATH = LOG_DIR / "experience_boundary.jsonl"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(re.escape(term), text or "", re.IGNORECASE))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


class BoundaryStats:
    def __init__(self, generation_result_id: int | None = None, stage: str = "unknown"):
        self.generation_result_id = generation_result_id
        self.stage = stage
        self.total_experiences = 0
        self.project_count = 0
        self.projects_with_source_id = 0
        self.projects_missing_source_id = 0
        self.unmatched_project_count = 0
        self.contamination_fixed_count = 0
        self.fixed_fields: list[str] = []
        self.provenance_conflict_count = 0

    def fixed(self, field: str):
        self.contamination_fixed_count += 1
        if field not in self.fixed_fields:
            self.fixed_fields.append(field)


def _write_boundary_log(stats: BoundaryStats):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "generation_result_id": stats.generation_result_id,
            "total_experiences": stats.total_experiences,
            "project_count": stats.project_count,
            "projects_with_source_id": stats.projects_with_source_id,
            "projects_missing_source_id": stats.projects_missing_source_id,
            "unmatched_project_count": stats.unmatched_project_count,
            "contamination_fixed_count": stats.contamination_fixed_count,
            "fixed_fields": stats.fixed_fields,
            "provenance_conflict_count": stats.provenance_conflict_count,
            "stage": stats.stage,
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(log, ensure_ascii=False) + "\n")
    except Exception:
        return


def _project_text(project: dict[str, Any]) -> str:
    return "\n".join(str(project.get(key, "")) for key in ["name", "meta", "intro", "role", "details"])


def _project_source_ids(project: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ["immutable_source_experience_id", "source_experience_id", "merged_source_experience_ids", "source_experience_ids"]:
        raw = project.get(key)
        rows = raw if isinstance(raw, list) else [raw]
        for item in rows:
            value = str(item or "").strip()
            if value and value not in values:
                values.append(value)
    return values


def _score_project_identity(project: dict[str, Any], identity: ExperienceIdentity) -> int:
    project_text = _normalize(_project_text(project))
    score = 0
    title = _normalize(identity.title)
    if title and title in project_text:
        score += 16
    if identity.experience_type and identity.experience_type in _project_text(project):
        score += 5
    for term in identity.explicit_tech_terms + identity.evidence_terms + identity.risk_terms:
        if _contains_term(_project_text(project), term):
            score += 3
    return score


def _match_project_to_segment(project: dict[str, Any], segments: list[ExperienceIdentity], index: int):
    source_id = str(project.get("immutable_source_experience_id") or project.get("source_experience_id") or "").strip()
    if source_id and project.get("source_binding_locked"):
        for segment in segments:
            if segment.experience_id == source_id:
                return segment
    fact_ids = [
        str(fact_id)
        for row in project.get("detail_fact_ids", []) or []
        if isinstance(row, list)
        for fact_id in row
        if fact_id
    ]
    fact_ids.extend(str(item) for item in project.get("source_fact_ids", []) or [] if item)
    fact_owners = {fact_owner_id(fact_id) for fact_id in fact_ids if fact_owner_id(fact_id)}
    if source_id and fact_owners == {source_id}:
        for segment in segments:
            if segment.experience_id == source_id:
                project["source_binding_origin"] = "fact_owner_validated"
                project["source_binding_confidence"] = 1.0
                project["source_binding_locked"] = True
                project["immutable_source_experience_id"] = source_id
                return segment

    project_text = _normalize(" ".join(str(project.get(key, "")) for key in ["name", "meta", "intro", "role"]))
    for segment in segments:
        title = _normalize(segment.title)
        if title and (title in project_text or project_text in title):
            return segment
        if segment.experience_type != "项目经历" and segment.experience_type in _project_text(project):
            return segment
    ranked = sorted(segments, key=lambda item: _score_project_identity(project, item), reverse=True)
    best_score = _score_project_identity(project, ranked[0]) if ranked else 0
    runner_score = _score_project_identity(project, ranked[1]) if len(ranked) > 1 else 0
    if ranked and best_score >= 14 and best_score - runner_score >= 6:
        return ranked[0]
    return None


def _split_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[。！？；;])\s*|\n+", text or "") if item.strip()]


def _remove_contaminated_sentences(text: str, blocked_terms: set[str]) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return text
    cleaned = [sentence for sentence in sentences if not any(_contains_term(sentence, term) for term in blocked_terms)]
    if not cleaned:
        return ""
    return "".join(cleaned)


def _has_metric_contamination(text: str, segment_content: str) -> bool:
    metric_patterns = [
        r"\d+\s*(?:\+|余|多)?\s*(?:用户|人|访问|UV|PV)",
        r"\d+\s*(?:\+|余|多)?\s*(?:star|stars)",
        r"(?:公网|域名|上线|部署|访问记录)",
    ]
    return any(re.search(pattern, text or "", re.IGNORECASE) and not re.search(pattern, segment_content or "", re.IGNORECASE) for pattern in metric_patterns)


def _allowed_terms(segment: ExperienceIdentity) -> set[str]:
    return set(segment.explicit_tech_terms + segment.evidence_terms + segment.risk_terms + segment.supported_inference_terms)


def _global_terms(segments: list[ExperienceIdentity]) -> set[str]:
    result: set[str] = set()
    for segment in segments:
        result.update(segment.explicit_tech_terms)
        result.update(term for term in segment.evidence_terms if term not in {"用户", "奖"})
        result.update(segment.risk_terms)
        for term in ["论文", "实验结果", "科研", "排名", "立项", "证书"]:
            if _contains_term(segment.raw_text, term):
                result.add(term)
    return result


def _scoped_fact_text(facts: list) -> str:
    return "\n".join(str(fact.fact_text or "") for fact in facts)


def _requires_local_evidence(text: str) -> bool:
    return bool(re.search(
        r"(?:React|FastAPI|Docker|RAG|Embedding|Nginx|systemd|Python|TypeScript|"
        r"\d+(?:\.\d+)?\s*(?:%|条|次|token|用户|人)|部署|上线|测试集|命中率|提升|降低)",
        text or "",
        re.IGNORECASE,
    ))


def guard_experience_boundaries(
    payload: schemas.GenerationPayload,
    raw_input: str,
    generation_result_id: int | None = None,
    stage: str = "unknown",
    write_log: bool = True,
    semantic_build: "CanonicalSemanticBuild | None" = None,
    ownership_index: "CanonicalFactOwnershipIndex | None" = None,
    scoped_access_stats: CanonicalScopedFactAccessStats | None = None,
) -> schemas.GenerationPayload:
    canonical_mode = semantic_build is not None or ownership_index is not None
    ownership = ownership_index or (semantic_build.ownership_index if semantic_build is not None else None)
    segments = list(semantic_build.identities) if semantic_build is not None else build_experience_identities(raw_input)
    stats = BoundaryStats(generation_result_id=generation_result_id, stage=stage)
    stats.total_experiences = len(segments)
    stats.project_count = len(payload.resume_sections.projects)
    if len(segments) <= 1:
        for project in payload.resume_sections.projects:
            if project.get("source_experience_id"):
                stats.projects_with_source_id += 1
            else:
                stats.projects_missing_source_id += 1
                stats.unmatched_project_count += 1
        if write_log:
            _write_boundary_log(stats)
        return payload

    updated = payload.model_copy(deep=True)
    ledger = semantic_build.ledger if semantic_build is not None else build_experience_fact_ledger(raw_input)
    all_terms = set() if canonical_mode else _global_terms(segments)
    guarded_projects: list[dict[str, Any]] = []
    pending_moves: list[tuple[str, str, str]] = []

    for index, project in enumerate(updated.resume_sections.projects):
        guarded = deepcopy(project)
        if guarded.get("source_experience_id"):
            stats.projects_with_source_id += 1
        else:
            stats.projects_missing_source_id += 1
        frozen_owner = str(guarded.get("immutable_source_experience_id") or "")
        if canonical_mode:
            segment = next((item for item in segments if item.experience_id == frozen_owner), None) if frozen_owner else None
            scope = canonical_fact_scope_for_owner(ownership, frozen_owner)
            if segment is None or scope is None:
                # Ownership is not evidence we may recreate here. Keep the
                # project for later validity handling, but do not guess.
                stats.unmatched_project_count += 1
                if scoped_access_stats is not None:
                    scoped_access_stats.unowned_project_skipped_count += 1
                guarded.pop("source_experience_id", None)
                guarded_projects.append(guarded)
                continue
            if scoped_access_stats is not None:
                scoped_access_stats.record_scope_read()
        else:
            segment = _match_project_to_segment(guarded, segments, index)
            scope = None
        if not segment:
            stats.unmatched_project_count += 1
            guarded_projects.append(guarded)
            continue
        if not canonical_mode:
            guarded["source_experience_id"] = segment.experience_id
            guarded["immutable_source_experience_id"] = segment.experience_id

        related_ids = {segment.experience_id} if canonical_mode else (set(_project_source_ids(guarded)) or {segment.experience_id})
        related_segments = [item for item in segments if item.experience_id in related_ids] or [segment]
        local_facts = scope.eligible_facts(ledger) if scope is not None else [
            fact for related_segment in related_segments for fact in ledger.for_experience(related_segment.experience_id)
        ]
        related_raw_text = _scoped_fact_text(local_facts) if canonical_mode else "\n".join(item.raw_text for item in related_segments)
        related_allowed_terms = set() if canonical_mode else set().union(
            *(_allowed_terms(related_segment) for related_segment in related_segments),
        )

        blocked_terms = all_terms - related_allowed_terms
        for key in ["intro", "role"]:
            cleaned = _remove_contaminated_sentences(str(guarded.get(key, "")), blocked_terms)
            if cleaned != str(guarded.get(key, "")):
                stats.fixed(f"projects[{index}].{key}")
            if _has_metric_contamination(cleaned, related_raw_text):
                stats.fixed(f"projects[{index}].{key}")
                cleaned = ""
            if cleaned:
                guarded[key] = cleaned
            elif key == "intro":
                resume_ready = [fact.resume_ready_text for fact in local_facts if fact.resume_ready_text]
                guarded[key] = resume_ready[0] if resume_ready else ""
            else:
                guarded[key], role_fact_ids = resolve_role_for_experience(
                    "" if canonical_mode else raw_input,
                    segment.experience_id,
                    details=guarded.get("details", []),
                    intro=str(guarded.get("intro") or ""),
                    ledger=ledger,
                )
                if role_fact_ids:
                    guarded["role_source_fact_ids"] = role_fact_ids
        details = []
        original_details = guarded.get("details", []) or []
        existing_fact_rows = guarded.get("detail_fact_ids") if isinstance(guarded.get("detail_fact_ids"), list) else []
        kept_fact_rows: list[list[str]] = []
        for detail_index, detail in enumerate(original_details):
            detail_text = str(detail)
            fact_ids = (
                [str(item) for item in existing_fact_rows[detail_index]]
                if detail_index < len(existing_fact_rows) and isinstance(existing_fact_rows[detail_index], list)
                else []
            )
            owners = {fact_owner_id(fact_id) for fact_id in fact_ids if fact_owner_id(fact_id)}
            if owners and (not owners.issubset(related_ids) or (scope is not None and not all(scope.permits_fact(fact_id) for fact_id in fact_ids))):
                stats.provenance_conflict_count += 1
                stats.fixed(f"projects[{index}].details")
                if scoped_access_stats is not None:
                    scoped_access_stats.rejected_cross_owner_access_count += 1
                continue
            if any(_contains_term(detail_text, term) for term in blocked_terms):
                stats.fixed(f"projects[{index}].details")
                continue
            if _has_metric_contamination(detail_text, related_raw_text):
                stats.fixed(f"projects[{index}].details")
                continue
            local_ranked = sorted(
                ((fact, fact_match_score(detail_text, fact)) for fact in local_facts),
                key=lambda item: item[1], reverse=True,
            )
            local_score = local_ranked[0][1] if local_ranked else 0.0
            if canonical_mode and _requires_local_evidence(detail_text) and local_score < 0.45:
                stats.fixed(f"projects[{index}].details")
                continue
            if not canonical_mode:
                all_ranked = sorted(((fact, fact_match_score(detail_text, fact)) for fact in ledger.facts), key=lambda item: item[1], reverse=True)
                best_fact, best_score = all_ranked[0] if all_ranked else (None, 0.0)
                if best_fact and best_fact.experience_id not in related_ids and best_score >= 0.62 and local_score < 0.45:
                    stats.fixed(f"projects[{index}].details")
                    pending_moves.append((best_fact.experience_id, detail_text, best_fact.fact_id))
                    continue
            details.append(detail_text)
            kept_fact_rows.append(fact_ids)
        guarded["details"] = _dedupe(details)
        guarded["detail_fact_ids"] = kept_fact_rows[:len(guarded["details"])]
        guarded_projects.append(guarded)

    by_source = {
        source_id: project
        for project in guarded_projects
        for source_id in _project_source_ids(project)
    }
    for target_id, detail, fact_id in pending_moves:
        target = by_source.get(target_id)
        if target is not None and detail not in target.get("details", []):
            target.setdefault("details", []).append(detail)
            target.setdefault("detail_fact_ids", []).append([fact_id])

    updated.resume_sections.projects = guarded_projects
    if stats.contamination_fixed_count:
        note = "已清理部分跨经历混用的技术、指标或成果表达；面试时请按每段经历分别准备事实证据。"
        if note not in updated.resume_sections.interview_preparation:
            updated.resume_sections.interview_preparation.append(note)
    if write_log:
        _write_boundary_log(stats)
    return updated
