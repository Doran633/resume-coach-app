import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .semantic_experience_segmentation_service import clean_heading_title, is_heading_only_text, is_phase_heading


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "project_hierarchy.jsonl"
HIERARCHY_INTERNAL_FIELDS = {
    "canonical_project_name",
    "project_aliases",
    "parent_project_name",
    "phase_name",
    "source_experience_ids",
    "merged_source_experience_ids",
    "relation_type",
}
GENERIC_INTRO_PATTERNS = [
    r"^面向.{1,30}场景的?.{1,24}(?:应用|系统|产品)，?(?:旨在|用于|帮助|提供)",
    r"^围绕.{1,30}(?:需求|场景|目标).{0,24}(?:应用|系统|产品)$",
    r"^围绕用户提供的真实经历",
]
GENERIC_ROLE_PATTERNS = [
    r"^(?:独立开发者|项目负责人)，?(?:负责)?(?:整体|项目)(?:设计|开发|实现|推进|交付)",
    r"^负责(?:整体|项目)(?:设计|开发|实现|推进|交付)$",
    r"^根据现有经历整理",
]
OWNERSHIP_TERMS = ("独立开发", "独立开发者", "负责人", "主导", "核心成员", "参与")
ACTION_OR_EVIDENCE_PATTERN = re.compile(
    r"实现|开发|设计|搭建|建立|优化|调试|部署|上线|隔离|修复|解决|测试|评测|"
    r"React|FastAPI|SQLite|RAG|Embedding|Citation|Nginx|systemd|\d+(?:\.\d+)?",
    re.IGNORECASE,
)


@dataclass
class ProjectHierarchyRelation:
    parent_index: int
    child_index: int
    canonical_project_name: str
    project_aliases: list[str]
    parent_project_name: str
    phase_name: str
    source_experience_ids: list[str]
    relation_type: str
    confidence: float
    signals: list[str] = field(default_factory=list)


@dataclass
class ProjectHierarchyStats:
    created_at: str
    stage: str
    generation_result_id: int | None
    detected_shell_project_count: int = 0
    parent_child_relation_count: int = 0
    merged_project_count: int = 0
    removed_heading_detail_count: int = 0
    canonical_project_names: list[str] = field(default_factory=list)
    merged_source_experience_ids: list[list[str]] = field(default_factory=list)
    low_confidence_relation_count: int = 0
    removed_unmerged_shell_count: int = 0


def _compact(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalized(value: object) -> str:
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", str(value or "")).lower()


def _project_text(project: dict) -> str:
    return "\n".join([
        _compact(project.get("name")),
        _compact(project.get("intro")),
        _compact(project.get("role")),
        *[_compact(item) for item in project.get("details", []) or []],
    ])


def _source_ids(project: dict) -> list[str]:
    values: list[str] = []
    for key in ["source_experience_id", "source_experience_ids", "merged_source_experience_ids"]:
        raw = project.get(key)
        rows = raw if isinstance(raw, list) else [raw]
        for item in rows:
            value = _compact(item)
            if value and value not in values:
                values.append(value)
    return values


def _fact_ids(project: dict) -> set[str]:
    values = {
        _compact(item) for item in project.get("source_fact_ids", []) or [] if _compact(item)
    }
    for row in project.get("detail_fact_ids", []) or []:
        if isinstance(row, list):
            values.update(_compact(item) for item in row if _compact(item))
    return values


def is_heading_detail(text: str) -> bool:
    value = _compact(text)
    if is_heading_only_text(value):
        return True
    parts = [part.strip() for part in re.split(r"[｜|]", value) if part.strip()]
    return len(parts) >= 3 and len(value) <= 120 and bool(
        re.search(r"(?:19|20)\d{2}|至今|待填写|独立开发者|个人项目|课程项目", value)
    )


def _generic_text(value: object, patterns: list[str]) -> bool:
    text = _compact(value)
    return not text or any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _meaningful_details(project: dict) -> list[str]:
    return [
        _compact(detail)
        for detail in project.get("details", []) or []
        if _compact(detail) and not is_heading_detail(_compact(detail)) and ACTION_OR_EVIDENCE_PATTERN.search(_compact(detail))
    ]


def is_shell_project(project: dict) -> bool:
    details = [_compact(item) for item in project.get("details", []) or [] if _compact(item)]
    heading_only = not details or all(is_heading_detail(item) for item in details)
    return bool(
        len(details) <= 1
        and heading_only
        and not _meaningful_details(project)
        and _generic_text(project.get("intro"), GENERIC_INTRO_PATTERNS)
        and _generic_text(project.get("role"), GENERIC_ROLE_PATTERNS)
        and len(_fact_ids(project)) <= 1
    )


def _same_owner_and_time(left: dict, right: dict) -> bool:
    left_time, right_time = _compact(left.get("time")), _compact(right.get("time"))
    time_matches = bool(left_time and left_time == right_time and left_time != "[待填写]")
    left_role, right_role = _compact(left.get("role")), _compact(right.get("role"))
    owner_matches = any(term in left_role and term in right_role for term in OWNERSHIP_TERMS)
    return time_matches and owner_matches


def _title_reference(parent: dict, child: dict) -> bool:
    parent_title = _normalized(clean_heading_title(_compact(parent.get("name"))))
    child_text = _normalized(_project_text(child))
    return len(parent_title) >= 5 and parent_title in child_text


def _identity_relation(
    parent: dict,
    child: dict,
    identities: dict[str, ExperienceIdentity],
) -> bool:
    parent_ids, child_ids = _source_ids(parent), _source_ids(child)
    for source_id in [*parent_ids, *child_ids]:
        identity = identities.get(source_id)
        if not identity or identity.relation_type == "independent":
            continue
        aliases = [_normalized(item) for item in identity.project_aliases]
        names = [_normalized(parent.get("name")), _normalized(child.get("name"))]
        if any(alias and any(alias in name or name in alias for name in names if name) for alias in aliases):
            return True
    return False


def _phase_name(project: dict) -> str:
    title = clean_heading_title(_compact(project.get("name")))
    if not is_phase_heading(title):
        return ""
    prefix = re.split(r"[（(]", title, maxsplit=1)[0].strip()
    return prefix or title


def _relation_for_pair(
    left: dict,
    right: dict,
    left_index: int,
    right_index: int,
    identities: dict[str, ExperienceIdentity],
) -> ProjectHierarchyRelation | None:
    left_shell, right_shell = is_shell_project(left), is_shell_project(right)
    left_phase, right_phase = bool(_phase_name(left)), bool(_phase_name(right))
    if left_shell and right_phase:
        parent, child, parent_index, child_index = left, right, left_index, right_index
    elif right_shell and left_phase:
        parent, child, parent_index, child_index = right, left, right_index, left_index
    elif left_shell != right_shell:
        parent, child, parent_index, child_index = (
            (left, right, left_index, right_index) if left_shell else (right, left, right_index, left_index)
        )
    else:
        return None

    parent_sources, child_sources = set(_source_ids(parent)), set(_source_ids(child))
    signals: list[str] = []
    if parent_sources and child_sources and parent_sources & child_sources:
        signals.append("same_source_experience_id")
    if abs(parent_index - child_index) == 1:
        signals.append("adjacent_projects")
    if is_shell_project(parent):
        signals.append("shell_parent")
    if _phase_name(child):
        signals.append("phase_or_module_marker")
    if _title_reference(parent, child):
        signals.append("parent_name_reference")
    if _same_owner_and_time(parent, child):
        signals.append("same_owner_and_time")
    if len(_meaningful_details(child)) >= 3 or len(_fact_ids(child)) >= 3:
        signals.append("facts_concentrated_in_child")
    if _identity_relation(parent, child, identities):
        signals.append("identity_hierarchy_relation")

    core_relation = bool(
        "same_source_experience_id" in signals
        or "parent_name_reference" in signals
        or "identity_hierarchy_relation" in signals
        or {
            "shell_parent", "adjacent_projects", "phase_or_module_marker"
        }.issubset(signals)
    )
    if len(signals) < 2 or not core_relation:
        return None

    parent_name = clean_heading_title(_compact(parent.get("name"))) or "项目经历"
    phase_name = _phase_name(child)
    aliases = list(dict.fromkeys([
        parent_name,
        clean_heading_title(_compact(child.get("name"))),
    ]))
    source_ids = list(dict.fromkeys([*_source_ids(parent), *_source_ids(child)]))
    relation_type = "module_of" if any(term in phase_name for term in ["模块", "子系统"]) else "phase_of"
    confidence = min(0.99, 0.55 + len(signals) * 0.07)
    return ProjectHierarchyRelation(
        parent_index=parent_index,
        child_index=child_index,
        canonical_project_name=parent_name,
        project_aliases=[item for item in aliases if item],
        parent_project_name=parent_name,
        phase_name=phase_name,
        source_experience_ids=source_ids,
        relation_type=relation_type,
        confidence=round(confidence, 3),
        signals=signals,
    )


def _choose_specific_text(primary: dict, secondary: dict, key: str) -> str:
    first, second = _compact(primary.get(key)), _compact(secondary.get(key))
    if not first:
        return second
    if not second:
        return first
    if _generic_text(first, GENERIC_INTRO_PATTERNS if key == "intro" else GENERIC_ROLE_PATTERNS):
        return second
    return first if len(first) >= len(second) else second


def _merge_details(parent: dict, child: dict, stats: ProjectHierarchyStats) -> tuple[list[str], list[list[str]]]:
    records: list[tuple[str, list[str]]] = []
    for project in [child, parent]:
        details = [_compact(item) for item in project.get("details", []) or [] if _compact(item)]
        fact_rows = project.get("detail_fact_ids", []) if isinstance(project.get("detail_fact_ids"), list) else []
        for index, detail in enumerate(details):
            if is_heading_detail(detail):
                stats.removed_heading_detail_count += 1
                continue
            ids = [str(item) for item in fact_rows[index]] if index < len(fact_rows) and isinstance(fact_rows[index], list) else []
            normalized = _normalized(detail)
            match = next((
                position for position, (existing, existing_ids) in enumerate(records)
                if normalized == _normalized(existing)
                or bool(set(ids) & set(existing_ids))
                or SequenceMatcher(None, normalized, _normalized(existing)).ratio() >= 0.9
            ), -1)
            if match < 0:
                records.append((detail, ids))
            else:
                existing, existing_ids = records[match]
                chosen = detail if len(detail) > len(existing) else existing
                records[match] = (chosen, list(dict.fromkeys([*existing_ids, *ids])))
    return [item[0] for item in records], [item[1] for item in records]


def _merge_parent_child(
    parent: dict,
    child: dict,
    relation: ProjectHierarchyRelation,
    stats: ProjectHierarchyStats,
) -> dict:
    merged = deepcopy(child)
    title = relation.canonical_project_name
    if relation.phase_name and _normalized(relation.phase_name) not in _normalized(title):
        title = f"{title}（{relation.phase_name}）"
    merged["name"] = title
    merged["intro"] = _choose_specific_text(child, parent, "intro")
    merged["role"] = _choose_specific_text(child, parent, "role")
    details, detail_fact_ids = _merge_details(parent, child, stats)
    merged["details"] = details
    merged["detail_fact_ids"] = detail_fact_ids
    merged["source_fact_ids"] = list(dict.fromkeys([
        *[str(item) for item in child.get("source_fact_ids", []) or []],
        *[str(item) for item in parent.get("source_fact_ids", []) or []],
        *[fact_id for row in detail_fact_ids for fact_id in row],
    ]))
    source_ids = relation.source_experience_ids
    if source_ids:
        child_source = _compact(child.get("source_experience_id"))
        merged["source_experience_id"] = child_source or source_ids[-1]
    merged["canonical_project_name"] = relation.canonical_project_name
    merged["project_aliases"] = relation.project_aliases
    merged["parent_project_name"] = relation.parent_project_name
    merged["phase_name"] = relation.phase_name
    merged["source_experience_ids"] = source_ids
    merged["merged_source_experience_ids"] = source_ids
    merged["relation_type"] = relation.relation_type
    return merged


def _write_log(stats: ProjectHierarchyStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(stats), ensure_ascii=False) + "\n")
    except OSError:
        pass


def merge_parent_child_projects(
    projects: list[dict],
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> list[dict]:
    rows = [deepcopy(item) for item in projects if isinstance(item, dict)]
    identities = {item.experience_id: item for item in build_experience_identities(raw_input)} if raw_input else {}
    stats = ProjectHierarchyStats(
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        stage=stage,
        generation_result_id=generation_result_id,
    )
    stats.detected_shell_project_count = sum(is_shell_project(item) for item in rows)
    for left_index in range(len(rows)):
        for right_index in range(left_index + 1, len(rows)):
            relation = _relation_for_pair(rows[left_index], rows[right_index], left_index, right_index, identities)
            if relation:
                continue
            left, right = rows[left_index], rows[right_index]
            if (is_shell_project(left) or is_shell_project(right)) and (
                _phase_name(left) or _phase_name(right) or _title_reference(left, right) or _title_reference(right, left)
            ):
                stats.low_confidence_relation_count += 1

    changed = True
    while changed:
        changed = False
        for left_index in range(len(rows)):
            for right_index in range(left_index + 1, len(rows)):
                relation = _relation_for_pair(rows[left_index], rows[right_index], left_index, right_index, identities)
                if not relation:
                    continue
                stats.parent_child_relation_count += 1
                parent, child = rows[relation.parent_index], rows[relation.child_index]
                merged = _merge_parent_child(parent, child, relation, stats)
                keep_index = min(relation.parent_index, relation.child_index)
                remove_index = max(relation.parent_index, relation.child_index)
                rows[keep_index] = merged
                rows.pop(remove_index)
                stats.merged_project_count += 1
                stats.canonical_project_names.append(relation.canonical_project_name[:60])
                stats.merged_source_experience_ids.append(relation.source_experience_ids)
                changed = True
                break
            if changed:
                break

    if len(rows) > 1:
        kept: list[dict] = []
        for project in rows:
            if is_shell_project(project):
                stats.removed_unmerged_shell_count += 1
                stats.removed_heading_detail_count += sum(
                    is_heading_detail(str(item)) for item in project.get("details", []) or []
                )
                continue
            kept.append(project)
        rows = kept

    for project in rows:
        cleaned = [item for item in project.get("details", []) or [] if not is_heading_detail(str(item))]
        stats.removed_heading_detail_count += len(project.get("details", []) or []) - len(cleaned)
        project["details"] = cleaned
    if write_log:
        _write_log(stats)
    return rows


def merge_resume_project_hierarchies(
    payload: schemas.GenerationPayload,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    updated.resume_sections.projects = merge_parent_child_projects(
        updated.resume_sections.projects,
        raw_input,
        stage=stage,
        generation_result_id=generation_result_id,
        write_log=write_log,
    )
    return updated


def strip_project_hierarchy_metadata(payload: schemas.GenerationPayload) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        for key in HIERARCHY_INTERNAL_FIELDS:
            project.pop(key, None)
    return updated
