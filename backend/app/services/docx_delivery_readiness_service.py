import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .project_hierarchy_service import is_heading_detail
from .resume_experience_validity_service import is_forbidden_experience_name


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "docx_delivery_readiness.jsonl"
COACHING_MARKERS = (
    "面试准备", "面试问题", "回答要点", "知识补齐", "证据准备", "降级表达",
    "Claim 风险", "当前还缺什么", "建议补充", "建议继续学习", "面试时可以",
    "如果被问到", "准备降级表达", "当前信息不足", "系统建议", "用户需要补充",
    "围绕该段经历完成相关任务", "具体职责以用户原文提供的信息为准",
    "具体职责以用户已提供内容为准", "以用户原文为准", "以用户提供的信息为准",
    "根据用户原文", "根据用户输入", "待用户确认", "待用户进一步确认职责",
    "技术动作：",
)
INTERNAL_MARKERS = (
    "source_experience_id", "source_fact_ids", "detail_fact_ids", "fact_id",
    "section summary", "summary chunk", "section 个人优势 chunk",
)
INVALID_INCOMPLETE_MARKERS = (
    "原文截断", "需补充原文", "内容被截断", "文本不完整", "因长度限制省略",
)
ALLOWED_PLACEHOLDER = "[待填写]"


def _write_log(entry: dict) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _clean_formal_text(value: object, stats: dict, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _contains_any(text, INVALID_INCOMPLETE_MARKERS):
        stats["invalid_incomplete_text_count"] += 1
        stats["affected_fields"].append(field_name)
        return ""
    coaching = _contains_any(text, COACHING_MARKERS)
    internal = _contains_any(text, INTERNAL_MARKERS)
    if coaching:
        stats["coaching_text_detected_count"] += 1
        stats["coaching_text_removed_count"] += 1
    if internal:
        stats["internal_marker_detected_count"] += 1
    if coaching or internal:
        stats["affected_fields"].append(field_name)
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _is_renderable_project(project: dict) -> bool:
    """Reject only empty shells; DOCX must not reinterpret saved semantics."""
    if not str(project.get("name") or "").strip() or is_forbidden_experience_name(project.get("name")):
        return False
    rows = [
        str(project.get(key) or "").strip()
        for key in ("intro", "role")
    ] + [str(item or "").strip() for item in project.get("details", []) or []]
    rows = [item for item in rows if item]
    return bool(rows) and not all(is_heading_detail(item) for item in rows)


def prepare_docx_delivery(
    payload: schemas.GenerationPayload | dict,
    *,
    generation_result_id: int | None = None,
) -> schemas.GenerationPayload:
    """Return a formal-resume-safe payload without touching coaching delivery data."""
    data = deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    stats = {
        "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "generation_result_id": generation_result_id,
        "formal_section_count": 0,
        "experience_count": 0,
        "placeholder_count": 0,
        "coaching_text_detected_count": 0,
        "coaching_text_removed_count": 0,
        "internal_marker_detected_count": 0,
        "invalid_incomplete_text_count": 0,
        "interview_content_excluded_count": 0,
        "delivery_ready": False,
        "affected_fields": [],
    }

    sections["summary"] = [
        cleaned for index, value in enumerate(sections.get("summary", []))
        if (cleaned := _clean_formal_text(value, stats, f"summary.{index}"))
    ]
    sections["skills"] = [
        cleaned for index, value in enumerate(sections.get("skills", []))
        if (cleaned := _clean_formal_text(value, stats, f"skills.{index}"))
    ]
    projects: list[dict] = []
    for project_index, raw_project in enumerate(sections.get("projects", [])):
        if not isinstance(raw_project, dict):
            continue
        if not _is_renderable_project(raw_project):
            stats["invalid_incomplete_text_count"] += 1
            stats["affected_fields"].append(f"projects.{project_index}")
            continue
        project = dict(raw_project)
        for key in ("name", "meta", "time", "intro", "role"):
            project[key] = _clean_formal_text(project.get(key), stats, f"projects.{project_index}.{key}")
        project["details"] = [
            cleaned for detail_index, value in enumerate(project.get("details", []))
            if (cleaned := _clean_formal_text(value, stats, f"projects.{project_index}.details.{detail_index}"))
        ]
        if project.get("name") and (project.get("intro") or project.get("role") or project.get("details")):
            projects.append(project)
    sections["projects"] = projects

    interview_sources = (
        sections.get("interview_preparation", []),
        data.get("interview_plan", []),
        data.get("knowledge_checklist", []),
    )
    stats["interview_content_excluded_count"] = sum(len(items) for items in interview_sources if isinstance(items, list))
    for claim in data.get("claims", []):
        if isinstance(claim, dict):
            stats["interview_content_excluded_count"] += len(claim.get("interview_questions", []))
            stats["interview_content_excluded_count"] += len(claim.get("knowledge_to_prepare", []))
            stats["interview_content_excluded_count"] += int(bool(claim.get("downgrade_wording")))

    sections["personal_info"] = sections.get("personal_info") or {}
    sections["education"] = sections.get("education") or {}
    data["resume_sections"] = sections
    visible_values = json.dumps(
        {key: sections.get(key) for key in ("personal_info", "education", "summary", "skills", "projects")},
        ensure_ascii=False,
    )
    stats["placeholder_count"] = visible_values.count(ALLOWED_PLACEHOLDER)
    stats["experience_count"] = len(projects)
    stats["formal_section_count"] = sum(bool(sections.get(key)) for key in ("personal_info", "education", "summary", "skills", "projects"))
    stats["delivery_ready"] = bool(sections["summary"] and sections["skills"] and projects)
    stats["affected_fields"] = sorted(set(stats["affected_fields"]))
    _write_log(stats)
    return schemas.GenerationPayload.model_validate(data)
