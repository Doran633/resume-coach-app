import re
from dataclasses import dataclass
from typing import Any, Iterable

from .. import schemas


VISIBLE_VERSION_FIELDS = (
    "normal_version",
    "bold_version",
    "boundary_version",
    "recommended_version",
)
VISIBLE_PROJECT_FIELDS = (
    "name",
    "position",
    "meta",
    "time",
    "intro",
    "role",
)

# Longer identifiers must be checked before their component names.
INTERNAL_FIELD_REPLACEMENTS = (
    ("source_experience_id", "经历来源标识"),
    ("source_fact_ids", "事实来源标识"),
    ("detail_fact_ids", "详情事实来源"),
    ("related_claim_ids", "关联声明标识"),
    ("claim_id", "声明来源标识"),
    ("fact_id", "事实来源标识"),
    ("raw_text", "原始经历文本"),
    ("explicit_metrics", "明确指标事实"),
    ("retrieved_count", "检索结果数量"),
)
INTERNAL_DEBUG_MARKERS = (
    "section summary chunk",
    "section 个人优势 chunk",
    "debug payload",
    "traceback",
)
INTERNAL_MARKERS = tuple(marker for marker, _ in INTERNAL_FIELD_REPLACEMENTS) + INTERNAL_DEBUG_MARKERS


@dataclass(frozen=True)
class VisibleOutputField:
    field_path: str
    value: str


@dataclass(frozen=True)
class VisibleOutputLeak:
    field_path: str
    marker: str


def _payload_dict(payload: schemas.GenerationPayload | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, schemas.GenerationPayload):
        return payload.model_dump()
    return payload if isinstance(payload, dict) else {}


def iter_visible_output_fields(
    payload: schemas.GenerationPayload | dict[str, Any],
) -> Iterable[VisibleOutputField]:
    data = _payload_dict(payload)
    for key in VISIBLE_VERSION_FIELDS:
        yield VisibleOutputField(key, str(data.get(key) or ""))

    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    for key in ("summary", "skills"):
        values = sections.get(key) if isinstance(sections.get(key), list) else []
        for index, value in enumerate(values):
            yield VisibleOutputField(f"resume_sections.{key}.{index}", str(value or ""))

    projects = sections.get("projects") if isinstance(sections.get("projects"), list) else []
    for project_index, project in enumerate(projects):
        if not isinstance(project, dict):
            continue
        for key in VISIBLE_PROJECT_FIELDS:
            yield VisibleOutputField(
                f"resume_sections.projects.{project_index}.{key}",
                str(project.get(key) or ""),
            )
        details = project.get("details") if isinstance(project.get("details"), list) else []
        for detail_index, value in enumerate(details):
            yield VisibleOutputField(
                f"resume_sections.projects.{project_index}.details.{detail_index}",
                str(value or ""),
            )


def visible_output_text(payload: schemas.GenerationPayload | dict[str, Any]) -> str:
    return "\n".join(field.value for field in iter_visible_output_fields(payload) if field.value)


def _identifier_pattern(marker: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![A-Za-z0-9_]){re.escape(marker)}(?![A-Za-z0-9_])",
        re.IGNORECASE,
    )


def find_internal_field_leaks(
    payload: schemas.GenerationPayload | dict[str, Any],
) -> list[VisibleOutputLeak]:
    leaks: list[VisibleOutputLeak] = []
    seen: set[tuple[str, str]] = set()
    for field in iter_visible_output_fields(payload):
        for marker, _ in INTERNAL_FIELD_REPLACEMENTS:
            key = (field.field_path, marker)
            if key not in seen and _identifier_pattern(marker).search(field.value):
                leaks.append(VisibleOutputLeak(field.field_path, marker))
                seen.add(key)
        lowered = field.value.lower()
        for marker in INTERNAL_DEBUG_MARKERS:
            key = (field.field_path, marker)
            if key not in seen and marker.lower() in lowered:
                leaks.append(VisibleOutputLeak(field.field_path, marker))
                seen.add(key)
    return leaks


def sanitize_internal_field_text(value: object) -> tuple[str, list[str]]:
    cleaned = str(value or "").strip()
    if not cleaned:
        return "", []
    matched: list[str] = []
    for marker, replacement in INTERNAL_FIELD_REPLACEMENTS:
        pattern = _identifier_pattern(marker)
        if pattern.search(cleaned):
            cleaned = pattern.sub(replacement, cleaned)
            matched.append(marker)
    for marker in INTERNAL_DEBUG_MARKERS:
        pattern = re.compile(re.escape(marker), re.IGNORECASE)
        if pattern.search(cleaned):
            cleaned = pattern.sub("", cleaned)
            matched.append(marker)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*([，。；、])\s*\1+", r"\1", cleaned)
    return cleaned.strip(" ，,、；;：:"), list(dict.fromkeys(matched))
