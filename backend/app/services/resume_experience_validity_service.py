import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import build_experience_fact_ledger
from .experience_identity_service import build_experience_identities
from .project_hierarchy_service import is_heading_detail
from .semantic_experience_segmentation_service import clean_heading_title


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_experience_validity.jsonl"
FORBIDDEN_EXPERIENCE_NAMES = {
    "其他经历", "其他项目", "综合经历", "综合经历项目", "未命名经历",
}
ACTION_OR_EVIDENCE_PATTERN = re.compile(
    r"负责|参与|主导|独立|实现|开发|设计|搭建|建立|优化|调试|部署|上线|隔离|"
    r"修复|解决|测试|评测|分析|组织|执行|协调|推进|交付|复盘|获奖|提升|降低|"
    r"React|Vue|FastAPI|SQLite|RAG|Embedding|Citation|Nginx|systemd|LoRa|API|\d+(?:\.\d+)?",
    re.IGNORECASE,
)


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalized(value: object) -> str:
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", str(value or "")).lower()


def is_forbidden_experience_name(value: object) -> bool:
    text = _text(value)
    normalized = _normalized(text)
    return text in FORBIDDEN_EXPERIENCE_NAMES or normalized in {_normalized(item) for item in FORBIDDEN_EXPERIENCE_NAMES}


def _visible_rows(project: dict) -> list[str]:
    return [
        row for row in [
            _text(project.get("intro")),
            _text(project.get("role")),
            *[_text(item) for item in project.get("details", []) or []],
        ] if row
    ]


def _heading_anchor(project: dict) -> str:
    for row in _visible_rows(project):
        if is_heading_detail(row):
            anchor = clean_heading_title(row)
            if anchor:
                return anchor
    return ""


def _non_heading_fact_rows(project: dict) -> list[str]:
    return [
        row for row in _visible_rows(project)
        if not is_heading_detail(row) and ACTION_OR_EVIDENCE_PATTERN.search(row)
    ]


def has_independent_experience_fact(project: dict, raw_input: str = "") -> bool:
    if not isinstance(project, dict) or not _non_heading_fact_rows(project):
        return False
    source_id = _text(project.get("source_experience_id"))
    if not raw_input or not source_id:
        return True
    ledger = build_experience_fact_ledger(raw_input)
    source_facts = [fact for fact in ledger.for_experience(source_id) if not is_heading_detail(fact.fact_text)]
    return bool(source_facts)


def classify_experience_project(project: dict, raw_input: str = "") -> str:
    if not isinstance(project, dict):
        return "empty_fact_shell"
    rows = _visible_rows(project)
    heading_rows = [row for row in rows if is_heading_detail(row)]
    normalized_rows = {_normalized(row) for row in rows if _normalized(row)}
    if rows and len(heading_rows) == len(rows):
        return "heading_residue_shell"
    if len(rows) >= 2 and len(normalized_rows) == 1 and heading_rows:
        return "heading_residue_shell"
    if is_forbidden_experience_name(project.get("name")) or is_forbidden_experience_name(project.get("meta")):
        return "generic_name_shell" if not has_independent_experience_fact(project, raw_input) else "generic_name"
    if not has_independent_experience_fact(project, raw_input):
        return "empty_fact_shell"
    return "valid"


def is_valid_fallback_candidate(project: dict, raw_input: str = "") -> bool:
    return classify_experience_project(project, raw_input) == "valid"


def _project_aliases(project: dict) -> set[str]:
    values = {
        _text(project.get("name")),
        _text(project.get("canonical_project_name")),
        *[_text(item) for item in project.get("project_aliases", []) or []],
    }
    return {_normalized(value) for value in values if _normalized(value)}


def _matching_project_index(shell: dict, projects: list[dict]) -> int:
    anchor = _normalized(_heading_anchor(shell))
    if not anchor:
        return -1
    matches = []
    for index, project in enumerate(projects):
        if classify_experience_project(project) != "valid":
            continue
        aliases = _project_aliases(project)
        if any(len(value) >= 4 and (anchor == value or anchor in value or value in anchor) for value in aliases):
            matches.append(index)
    return matches[0] if len(matches) == 1 else -1


def _merge_internal_sources(target: dict, shell: dict) -> None:
    source_ids = []
    for project in (target, shell):
        for key in ("source_experience_id", "source_experience_ids", "merged_source_experience_ids"):
            raw = project.get(key)
            values = raw if isinstance(raw, list) else [raw]
            for value in values:
                text = _text(value)
                if text and text not in source_ids:
                    source_ids.append(text)
    if source_ids:
        target["source_experience_id"] = _text(target.get("source_experience_id")) or source_ids[0]
        target["merged_source_experience_ids"] = source_ids


def _recover_generic_project(project: dict, raw_input: str) -> bool:
    source_id = _text(project.get("source_experience_id"))
    if not source_id or not has_independent_experience_fact(project, raw_input):
        return False
    identity = next((item for item in build_experience_identities(raw_input) if item.experience_id == source_id), None)
    if not identity or is_forbidden_experience_name(identity.title) or is_heading_detail(identity.raw_text):
        return False
    title = _text(identity.title)
    if not title or title in {identity.experience_type, "项目经历"}:
        return False
    project["name"] = title
    project["meta"] = identity.experience_type
    return True


def _append_missing_question(data: dict, source_ids: list[str]) -> None:
    question = "有一段内容仅包含经历标题或元数据，已从正式简历中移除；请补充该经历的职责、技术动作或结果证据。"
    questions = data.get("missing_questions") if isinstance(data.get("missing_questions"), list) else []
    if question not in questions:
        questions.append(question)
    data["missing_questions"] = questions[:12]


def _write_log(stats: dict) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(stats, ensure_ascii=False) + "\n")
    except Exception:
        return


def ensure_resume_experience_validity(
    payload: schemas.GenerationPayload | dict,
    raw_input: str = "",
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    fallback_candidate_rejected_count: int = 0,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    data = deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    projects = [dict(item) for item in sections.get("projects", []) if isinstance(item, dict)]
    valid_projects: list[dict] = []
    pending_shells: list[tuple[dict, str]] = []
    affected_ids: list[str] = []
    stats = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "generation_result_id": generation_result_id,
        "stage": stage,
        "generic_experience_name_count": 0,
        "heading_residue_project_count": 0,
        "invalid_experience_count": 0,
        "absorbed_shell_count": 0,
        "removed_shell_count": 0,
        "fallback_candidate_rejected_count": fallback_candidate_rejected_count,
        "affected_source_experience_ids": affected_ids,
    }

    for project in projects:
        kind = classify_experience_project(project, raw_input)
        if kind == "generic_name" and _recover_generic_project(project, raw_input):
            kind = "valid"
        if kind == "valid":
            valid_projects.append(project)
            continue
        stats["invalid_experience_count"] += 1
        stats["generic_experience_name_count"] += int(
            is_forbidden_experience_name(project.get("name"))
            or is_forbidden_experience_name(project.get("meta"))
        )
        stats["heading_residue_project_count"] += int(kind == "heading_residue_shell")
        source_id = _text(project.get("source_experience_id"))
        if source_id:
            affected_ids.append(source_id)
        pending_shells.append((project, kind))

    unresolved_ids: list[str] = []
    for shell, _kind in pending_shells:
        match_index = _matching_project_index(shell, valid_projects)
        if match_index >= 0:
            _merge_internal_sources(valid_projects[match_index], shell)
            stats["absorbed_shell_count"] += 1
            continue
        stats["removed_shell_count"] += 1
        source_id = _text(shell.get("source_experience_id"))
        if source_id:
            unresolved_ids.append(source_id)

    if pending_shells and stats["absorbed_shell_count"] < len(pending_shells):
        _append_missing_question(data, unresolved_ids)
    sections["projects"] = valid_projects
    data["resume_sections"] = sections
    stats["affected_source_experience_ids"] = sorted(set(affected_ids))
    if write_log:
        _write_log(stats)
    return schemas.GenerationPayload.model_validate(data)
