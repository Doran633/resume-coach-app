import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .experience_fact_ledger_service import build_experience_fact_ledger, fact_match_score, is_generic_detail
from .project_hierarchy_service import merge_parent_child_projects
from .resume_experience_entity_dedup_service import deduplicate_resume_experience_entities


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_PATH = LOG_DIR / "resume_project_reconciliation.jsonl"
MAX_PROJECT_DETAILS = 8
MAX_TOTAL_DETAILS = 20

GENERIC_MARKERS = [
    "综合经历",
    "综合经历项目",
    "围绕用户提供的真实经历",
    "根据现有经历整理",
    "整理个人参与内容与项目亮点",
]
LOW_VALUE_PATTERNS = [
    "提升用户体验",
    "负责相关工作",
    "整理项目亮点",
    "围绕项目目标完成任务",
    "围绕用户提供的真实经历",
]
VALUE_TERMS = [
    "架构", "模块", "接口", "测试", "评测", "指标", "日志", "部署", "数据隔离", "权限", "排查", "优化",
    "React", "TypeScript", "FastAPI", "SQLite", "RAG", "Embedding", "BAAI", "bge-m3", "Top-K", "Nginx",
    "systemd", "VPS", "Citation", "Retrieval", "Groundedness", "Fallback", "用户", "token", "相关度",
]


@dataclass
class ReconciliationStats:
    generation_result_id: int | None
    stage: str
    total_experiences: int = 0
    projects_before: int = 0
    projects_after: int = 0
    comprehensive_projects_found: int = 0
    comprehensive_projects_removed: int = 0
    details_recovered: int = 0
    details_deduplicated: int = 0
    unmatched_details: int = 0
    uncovered_experience_ids: list[str] = field(default_factory=list)
    project_names: list[str] = field(default_factory=list)


def _normalize(value: object) -> str:
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", str(value or "")).lower()


def _project_text(project: dict) -> str:
    details = project.get("details") if isinstance(project.get("details"), list) else []
    return "\n".join(str(project.get(key, "")) for key in ["name", "meta", "intro", "role"]) + "\n" + "\n".join(str(item) for item in details)


def _is_comprehensive(project: dict) -> bool:
    name_and_meta = f"{project.get('name', '')}\n{project.get('meta', '')}"
    if "综合经历" in name_and_meta:
        return True
    text = _project_text(project)
    generic_count = sum(1 for marker in GENERIC_MARKERS[2:] if marker in text)
    specific_name = str(project.get("name") or "").strip()
    return generic_count >= 2 and specific_name in {"", "项目经历", "核心项目经历", "其他经历"}


def _similar(left: str, right: str) -> float:
    left_key = _normalize(left)
    right_key = _normalize(right)
    if not left_key or not right_key:
        return 0.0
    if min(len(left_key), len(right_key)) >= 12 and (left_key in right_key or right_key in left_key):
        return 1.0
    return SequenceMatcher(None, left_key, right_key).ratio()


def _identity_score(text: str, identity: ExperienceIdentity) -> int:
    normalized_text = _normalize(text)
    normalized_raw = _normalize(identity.raw_text)
    score = 0
    title = _normalize(identity.title)
    if title and title in normalized_text:
        score += 12
    if identity.experience_type and identity.experience_type in text:
        score += 4
    entity_pattern = re.compile(r"[A-Za-z\u4e00-\u9fff]{2,32}(?:公司|网站|系统|平台|助手|计算器)", re.IGNORECASE)
    text_entities = {_normalize(item) for item in entity_pattern.findall(text)}
    raw_entities = {_normalize(item) for item in entity_pattern.findall(identity.raw_text)}
    if any(left in right or right in left for left in text_entities for right in raw_entities):
        score += 8
    text_numbers = set(re.findall(r"\d+(?:\.\d+)?", text))
    raw_numbers = set(re.findall(r"\d+(?:\.\d+)?", identity.raw_text))
    score += min(8, len(text_numbers & raw_numbers) * 4)
    for term in identity.explicit_tech_terms + identity.evidence_terms + identity.risk_terms:
        if term and re.search(re.escape(term), text, re.IGNORECASE):
            score += 3
    if normalized_text and normalized_raw:
        if len(normalized_text) >= 16 and normalized_text in normalized_raw:
            score += 12
        else:
            ratio = SequenceMatcher(None, normalized_text, normalized_raw).ratio()
            if ratio >= 0.65:
                score += 8
            elif ratio >= 0.42:
                score += 4
    return score


def _match_identity(text: str, identities: list[ExperienceIdentity]) -> ExperienceIdentity | None:
    ranked = sorted(((item, _identity_score(text, item)) for item in identities), key=lambda pair: pair[1], reverse=True)
    if not ranked or ranked[0][1] < 4:
        return None
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def _is_valuable(detail: str, identity: ExperienceIdentity) -> bool:
    if len(_normalize(detail)) < 12:
        return False
    if any(pattern in detail for pattern in LOW_VALUE_PATTERNS):
        return False
    if any(re.search(re.escape(term), detail, re.IGNORECASE) for term in VALUE_TERMS):
        return True
    if any(term and re.search(re.escape(term), detail, re.IGNORECASE) for term in identity.evidence_terms):
        return True
    return any(action in detail for action in ["设计", "实现", "建立", "完成", "解决", "负责", "搭建", "开发", "调优"])


def _contains_equivalent(project: dict, detail: str) -> bool:
    existing = [str(project.get("intro", "")), str(project.get("role", ""))]
    existing.extend(str(item) for item in project.get("details", []) if item)
    return any(_similar(detail, item) >= 0.92 for item in existing)


def _assign_project_sources(projects: list[dict], identities: list[ExperienceIdentity]) -> dict[str, int]:
    coverage: dict[str, int] = {}
    for index, project in enumerate(projects):
        source_id = str(project.get("source_experience_id") or "").strip()
        identity = next((item for item in identities if item.experience_id == source_id), None)
        if not identity:
            identity = _match_identity(_project_text(project), identities)
        if identity:
            project["source_experience_id"] = identity.experience_id
            coverage.setdefault(identity.experience_id, index)
    return coverage


def _apply_detail_budget(projects: list[dict], raw_input: str) -> None:
    ledger = build_experience_fact_ledger(raw_input)
    prepared: list[list[str]] = []
    for project in projects:
        details = [str(item).strip() for item in project.get("details", []) if str(item).strip()]
        unique: list[str] = []
        for detail in details:
            # Reconciliation must not perform aggressive semantic deduplication;
            # the fact-aware dedup service handles that with source_fact_ids.
            if not any(_similar(detail, existing) >= 0.94 for existing in unique):
                unique.append(detail)
        source_id = str(project.get("source_experience_id") or "")
        local_facts = ledger.for_experience(source_id)

        def priority(item: tuple[int, str]) -> tuple[int, int]:
            index, detail = item
            ranked = sorted(((fact, fact_match_score(detail, fact)) for fact in local_facts), key=lambda pair: pair[1], reverse=True)
            if ranked and ranked[0][1] >= 0.45:
                importance = {"high": 0, "medium": 1, "low": 2}[ranked[0][0].importance]
            else:
                importance = 3
            if is_generic_detail(detail):
                importance = 4
            return importance, index

        ordered = [detail for _, detail in sorted(enumerate(unique), key=priority)]
        prepared.append(ordered[:MAX_PROJECT_DETAILS])

    allocations = [min(3, len(items)) for items in prepared]
    remaining = max(0, MAX_TOTAL_DETAILS - sum(allocations))
    while remaining:
        changed = False
        for index, items in enumerate(prepared):
            if allocations[index] < len(items) and allocations[index] < MAX_PROJECT_DETAILS:
                allocations[index] += 1
                remaining -= 1
                changed = True
                if not remaining:
                    break
        if not changed:
            break
    for project, items, limit in zip(projects, prepared, allocations):
        project["details"] = items[:limit]


def _write_log(stats: ReconciliationStats) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "generation_result_id": stats.generation_result_id,
            "stage": stats.stage,
            "total_experiences": stats.total_experiences,
            "projects_before": stats.projects_before,
            "projects_after": stats.projects_after,
            "comprehensive_projects_found": stats.comprehensive_projects_found,
            "comprehensive_projects_removed": stats.comprehensive_projects_removed,
            "details_recovered": stats.details_recovered,
            "details_deduplicated": stats.details_deduplicated,
            "unmatched_details": stats.unmatched_details,
            "uncovered_experience_ids": stats.uncovered_experience_ids,
            "project_names": [name[:40] for name in stats.project_names],
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def reconcile_resume_projects(
    payload: schemas.GenerationPayload,
    raw_input: str,
    stage: str = "generation",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    identities = build_experience_identities(raw_input)
    projects = [deepcopy(item) for item in updated.resume_sections.projects if isinstance(item, dict)]
    stats = ReconciliationStats(generation_result_id=generation_result_id, stage=stage)
    stats.total_experiences = len(identities)
    stats.projects_before = len(projects)

    comprehensive = [item for item in projects if _is_comprehensive(item)]
    concrete = [item for item in projects if not _is_comprehensive(item)]
    stats.comprehensive_projects_found = len(comprehensive)

    if comprehensive and not concrete and len(identities) == 1:
        project = comprehensive[0]
        identity = identities[0]
        project["name"] = identity.title or identity.experience_type
        project["meta"] = identity.experience_type
        project["source_experience_id"] = identity.experience_id
        concrete = [project]
        comprehensive = []

    coverage = _assign_project_sources(concrete, identities)
    for generic_project in comprehensive:
        for detail in generic_project.get("details", []) or []:
            detail_text = str(detail).strip()
            identity = _match_identity(detail_text, identities)
            if not identity or identity.experience_id not in coverage:
                stats.unmatched_details += 1
                continue
            target = concrete[coverage[identity.experience_id]]
            if _contains_equivalent(target, detail_text):
                stats.details_deduplicated += 1
                continue
            if _is_valuable(detail_text, identity):
                target.setdefault("details", []).append(detail_text)
                stats.details_recovered += 1
            else:
                stats.unmatched_details += 1

    if comprehensive and concrete:
        stats.comprehensive_projects_removed = len(comprehensive)

    concrete = merge_parent_child_projects(
        concrete,
        raw_input,
        stage=f"{stage}_reconciliation",
        generation_result_id=generation_result_id,
        write_log=write_log,
    )
    _apply_detail_budget(concrete, raw_input)
    coverage = _assign_project_sources(concrete, identities)
    stats.uncovered_experience_ids = [item.experience_id for item in identities if item.experience_id not in coverage]
    stats.projects_after = len(concrete)
    stats.project_names = [str(item.get("name") or "") for item in concrete]
    updated.resume_sections.projects = concrete
    updated = deduplicate_resume_experience_entities(
        updated,
        raw_input,
        stage=f"{stage}_reconciliation",
        generation_result_id=generation_result_id,
        write_log=write_log,
        apply_hierarchy=False,
    )
    stats.projects_after = len(updated.resume_sections.projects)
    if write_log:
        _write_log(stats)
    return updated
