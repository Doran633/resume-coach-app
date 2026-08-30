import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_typography_quality.jsonl"
REPEATED = [(r"、{2,}", "、"), (r"，{2,}", "，"), (r"。{2,}", "。"), (r"；{2,}", "；"), (r"：{2,}", "："), (r"！{2,}", "！"), (r"？{2,}", "？")]
MIXED = [(r"、\s*,+|,+\s*、", "、"), (r"，\s*,+|,+\s*，", "，")]
ABNORMAL_PATTERN = re.compile(r"、、|，，|。。|；；|：：|！！|？？|、[ \t]*,|,[ \t]*、|，[ \t]*,|,[ \t]*，|[ \t]{2,}")
LEADING_STRUCTURE_PATTERNS = (
    re.compile(r"^\s*[-*+]\s*\[[ xX]\]\s+", re.MULTILINE),
    re.compile(r"^\s*[•▪◦‣●○·]+\s*", re.MULTILINE),
    re.compile(r"^\s*[-*+]\s+", re.MULTILINE),
    re.compile(r"^\s*#{1,6}\s+", re.MULTILINE),
    re.compile(r"^\s*>\s+", re.MULTILINE),
    re.compile(r"^\s*\d{1,3}[.)、]\s+", re.MULTILINE),
)


@dataclass
class TypographyStats:
    stage: str
    generation_result_id: int | None
    abnormal_punctuation_count: int = 0
    repeated_punctuation_fixed_count: int = 0
    mixed_punctuation_fixed_count: int = 0
    trailing_punctuation_fixed_count: int = 0
    spacing_fixed_count: int = 0
    leading_markup_detected_count: int = 0
    leading_markup_removed_count: int = 0
    affected_fields: list[str] = field(default_factory=list)
    affected_experience_ids: list[str] = field(default_factory=list)


def count_typography_issues(text: str) -> int:
    value = str(text or "")
    return (
        len(ABNORMAL_PATTERN.findall(value))
        + int(bool(re.search(r"[、，,；;]+\s*$", value)))
        + sum(len(pattern.findall(value)) for pattern in LEADING_STRUCTURE_PATTERNS)
    )


def has_leading_structure_marker(text: str) -> bool:
    value = str(text or "")
    return any(pattern.search(value) for pattern in LEADING_STRUCTURE_PATTERNS)


def strip_leading_structure_markers(
    text: str,
    stats: TypographyStats | None = None,
) -> str:
    value = str(text or "")
    total = 0
    # Re-run because pasted LLM text may contain nested markers such as ` -`.
    for _ in range(8):
        pass_count = 0
        for pattern in LEADING_STRUCTURE_PATTERNS:
            value, count = pattern.subn("", value)
            pass_count += count
        total += pass_count
        if not pass_count:
            break
    if stats and total:
        stats.leading_markup_detected_count += total
        stats.leading_markup_removed_count += total
    return value


def clean_typography(text: str, stats: TypographyStats | None = None) -> str:
    value = str(text or "")
    original = value
    if stats:
        stats.abnormal_punctuation_count += count_typography_issues(value)
    value = strip_leading_structure_markers(value, stats)
    for pattern, replacement in REPEATED:
        value, count = re.subn(pattern, replacement, value)
        if stats:
            stats.repeated_punctuation_fixed_count += count
    for pattern, replacement in MIXED:
        value, count = re.subn(pattern, replacement, value)
        if stats:
            stats.mixed_punctuation_fixed_count += count
    value, spacing = re.subn(r"[ \t]{2,}", " ", value)
    value = re.sub(r"\s+([、，。；：！？])", r"\1", value)
    value = re.sub(r"([、，。；：！？])\s+", r"\1", value)
    if stats:
        stats.spacing_fixed_count += spacing
    stripped, trailing = re.subn(r"[、，,；;]+\s*$", "", value)
    if trailing:
        value = stripped
        if stats:
            stats.trailing_punctuation_fixed_count += trailing
    return value.strip() if original != value else value.strip()


def _write_log(stats: TypographyStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def ensure_typography_quality(
    payload: schemas.GenerationPayload,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = TypographyStats(stage=stage, generation_result_id=generation_result_id)

    def clean(value: str, field_name: str, experience_id: str = "") -> str:
        before = str(value or "")
        after = clean_typography(before, stats)
        if before != after:
            stats.affected_fields.append(field_name)
            if experience_id:
                stats.affected_experience_ids.append(experience_id)
        return after

    updated.resume_sections.summary = [clean(item, f"summary.{index}") for index, item in enumerate(updated.resume_sections.summary)]
    updated.resume_sections.skills = [clean(item, f"skills.{index}") for index, item in enumerate(updated.resume_sections.skills)]
    for project_index, project in enumerate(updated.resume_sections.projects):
        source_id = str(project.get("source_experience_id") or "")
        for key in ["name", "position", "meta", "time", "intro", "role"]:
            if key in project:
                project[key] = clean(project.get(key, ""), f"projects.{project_index}.{key}", source_id)
        project["details"] = [
            clean(item, f"projects.{project_index}.details.{index}", source_id)
            for index, item in enumerate(project.get("details", []))
        ]
    stats.affected_fields = list(dict.fromkeys(stats.affected_fields))
    stats.affected_experience_ids = list(dict.fromkeys(stats.affected_experience_ids))
    if write_log:
        _write_log(stats)
    return updated
