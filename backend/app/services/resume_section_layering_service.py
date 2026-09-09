import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .resume_fact_dedup_service import similarity, _detail_records, _preserve_project_aggregates
from .resume_information_gain_service import information_gain_components


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_section_layering.jsonl"
ROLE_MARKERS = re.compile(r"独立|主导|负责|参与|承担|协作|推进|owner", re.I)
INVALID_ROLE = re.compile(r"负责相关工作|围绕该段经历完成相关任务|以用户原文(?:提供的信息)?为准|具体职责以", re.I)
SENTENCE_SPLIT = re.compile(r"(?<=[。！？])\s*|\n+")


@dataclass
class LayeringStats:
    stage: str
    generation_result_id: int | None
    projects_checked: int = 0
    intro_role_overlap_count: int = 0
    role_detail_overlap_count: int = 0
    details_without_increment_count: int = 0
    details_merged_count: int = 0
    details_removed_count: int = 0
    facts_preserved_count: int = 0
    affected_experience_ids: list[str] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    return [item.strip(" \t\r\n，、；;") for item in SENTENCE_SPLIT.split(str(text or "")) if item.strip()]


def _components(text: str) -> set[str]:
    values = information_gain_components(text)
    return {f"{name}:{term.lower()}" for name, terms in values.items() for term in terms}


def _high_value(text: str) -> bool:
    return bool(re.search(r"\d+(?:\.\d+)?|上线|部署|用户反馈|测试集|评测|指标|日志|健康检查|Smoke Test|数据隔离|权限|Citation|Groundedness", text, re.I))


def _write_log(stats: LayeringStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        entry["affected_experience_ids"] = sorted(set(entry["affected_experience_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def layer_resume_sections(
    payload: schemas.GenerationPayload,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    """Keep context in intro, ownership in role, and implementation/results in details."""
    updated = payload.model_copy(deep=True)
    stats = LayeringStats(stage=stage, generation_result_id=generation_result_id)
    for project in updated.resume_sections.projects:
        stats.projects_checked += 1
        source_id = str(project.get("source_experience_id") or "")
        intro_parts = _sentences(str(project.get("intro") or ""))
        intro = "".join(intro_parts[:2])
        role_parts = [item for item in _sentences(str(project.get("role") or "")) if not INVALID_ROLE.search(item)]
        role = next((item for item in role_parts if ROLE_MARKERS.search(item)), role_parts[0] if role_parts else "")

        if intro and role and similarity(intro, role) >= 0.84:
            stats.intro_role_overlap_count += 1
            if ROLE_MARKERS.search(role):
                # Preserve only the ownership-bearing sentence; downstream increment checks details.
                role = next((item for item in role_parts if ROLE_MARKERS.search(item)), role)
            else:
                role = ""
            if source_id:
                stats.affected_experience_ids.append(source_id)

        # These transforms cannot attribute a multi-sentence binding to a
        # retained substring. Keep bound text intact instead of orphaning it.
        if project.get("source_fact_ids") or project.get("source_claim_ids"):
            intro = str(project.get("intro") or "")
        if project.get("role_source_fact_ids") or project.get("role_source_claim_ids"):
            role = str(project.get("role") or "")
        project["intro"] = intro
        project["role"] = role
        header_components = _components(intro) | _components(role)
        original_records = _detail_records(project, include_empty=True)
        kept = []
        for record in original_records:
            detail, ids = record.text, record.source_fact_ids
            if not detail:
                continue
            detail_components = _components(detail)
            covered = bool(detail_components) and detail_components <= header_components
            near_header = any(similarity(detail, value) >= 0.92 for value in (intro, role) if value)
            if (covered or near_header) and not ids and not record.source_claim_ids and not _high_value(detail):
                stats.details_without_increment_count += 1
                stats.details_removed_count += 1
                if source_id:
                    stats.affected_experience_ids.append(source_id)
                continue
            kept.append(record)
            stats.facts_preserved_count += max(1, len(ids))
        kept = kept[:8]
        project["details"] = [row.text for row in kept]
        project["detail_fact_ids"] = [row.source_fact_ids for row in kept]
        project["detail_claim_ids"] = [row.source_claim_ids for row in kept]
        _preserve_project_aggregates(project, kept, original_records)

    if write_log:
        _write_log(stats)
    return updated
