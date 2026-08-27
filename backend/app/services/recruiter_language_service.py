import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "recruiter_language.jsonl"
INTERNAL_FIELDS = (
    "raw_text", "experience_type", "explicit_tech_terms", "explicit_metrics", "evidence_terms",
    "risk_terms", "supported_inference_terms", "source_experience_id", "source_fact_ids", "fact_id",
    "missing_questions", "claims", "interview_preparation", "resume_sections", "normal_version",
    "bold_version", "boundary_version", "fallback_sections", "fallback_reason", "detail_fact_ids",
)
FIELD_ENUM_PATTERN = re.compile(
    r"(?:raw_text|experience_type|explicit_tech_terms|explicit_metrics|evidence_terms|risk_terms|supported_inference_terms)"
    r"(?:\s*[,，、和与及]\s*(?:raw_text|experience_type|explicit_tech_terms|explicit_metrics|evidence_terms|risk_terms|supported_inference_terms))*",
    re.I,
)


@dataclass
class RecruiterLanguageStats:
    stage: str
    generation_result_id: int | None
    checked_text_count: int = 0
    internal_field_leak_count: int = 0
    recruiter_language_conversion_count: int = 0
    removed_debug_expression_count: int = 0
    affected_fields: list[str] = field(default_factory=list)
    affected_experience_ids: list[str] = field(default_factory=list)


def internal_field_count(text: str) -> int:
    lowered = str(text or "").lower()
    return sum(lowered.count(field.lower()) for field in INTERNAL_FIELDS)


def convert_to_recruiter_language(text: str) -> tuple[str, int, int]:
    value = str(text or "").strip()
    before_count = internal_field_count(value)
    if not value or not before_count:
        return value, 0, 0

    conversions = 0
    patterns = [
        (
            r"(?:将)?用户输入拆分为\s*(?:EXP-\d+(?:\s*[,，、]\s*EXP-\d+)*)[^。；]*?(?:raw_text|experience_type|explicit_tech_terms)[^。；]*",
            "将长输入拆分为独立 experience_id，并分别抽取技术、指标、证据和风险事实，建立经历级事实边界",
        ),
        (
            r"[^。；]*?(?:missing_questions|claims|interview_preparation)[^。；]*",
            "对缺乏事实支撑的表达进行风险分级，并引导用户补充证据或准备降级表述",
        ),
        (
            r"(?:检查|校验)[^。；]*?resume_sections[^。；]*?(?:为空|完整性)[^。；]*",
            "在简历保存与导出前增加业务完整性校验，避免结构合法但正文为空的异常结果",
        ),
        (
            r"[^。；]*?(?:fallback_sections|fallback_reason)[^。；]*",
            "记录 Resume Section Fallback 的触发原因和补全范围，用于监控上游结构化输出退化",
        ),
    ]
    for pattern, replacement in patterns:
        value, count = re.subn(pattern, replacement, value, flags=re.I)
        conversions += count

    if internal_field_count(value):
        value, enum_count = FIELD_ENUM_PATTERN.subn("技术、指标、证据和风险事实", value)
        conversions += enum_count
        replacements = {
            "source_experience_id": "经历来源标识", "source_fact_ids": "事实来源标识",
            "detail_fact_ids": "详情事实来源", "fact_id": "事实标识",
            "experience_type": "经历类型", "explicit_metrics": "明确指标",
            "explicit_tech_terms": "明确技术", "evidence_terms": "证据事实", "risk_terms": "风险事实",
            "supported_inference_terms": "可承接技术", "raw_text": "原始经历",
        }
        for old, new in replacements.items():
            value, count = re.subn(re.escape(old), new, value, flags=re.I)
            conversions += count
    value = value.strip(" ，,、；;")
    return value, before_count, conversions


def _write_log(stats: RecruiterLanguageStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        entry["affected_fields"] = sorted(set(entry["affected_fields"]))
        entry["affected_experience_ids"] = sorted(set(entry["affected_experience_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def ensure_recruiter_language(
    payload: schemas.GenerationPayload,
    *, stage: str = "unknown", generation_result_id: int | None = None, write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = RecruiterLanguageStats(stage=stage, generation_result_id=generation_result_id)

    def clean(value: str, field: str, source_id: str = "") -> str:
        stats.checked_text_count += 1
        after, leaks, conversions = convert_to_recruiter_language(value)
        stats.internal_field_leak_count += leaks
        stats.recruiter_language_conversion_count += conversions
        if after != str(value or ""):
            stats.affected_fields.append(field)
            if source_id:
                stats.affected_experience_ids.append(source_id)
        return after

    updated.resume_sections.summary = [clean(item, f"summary.{i}") for i, item in enumerate(updated.resume_sections.summary)]
    updated.resume_sections.skills = [clean(item, f"skills.{i}") for i, item in enumerate(updated.resume_sections.skills)]
    for p_index, project in enumerate(updated.resume_sections.projects):
        source_id = str(project.get("source_experience_id") or "")
        for key in ["name", "position", "meta", "intro", "role"]:
            if key in project:
                project[key] = clean(project.get(key, ""), f"projects.{p_index}.{key}", source_id)
        project["details"] = [clean(item, f"projects.{p_index}.details.{i}", source_id) for i, item in enumerate(project.get("details", []))]
    if write_log:
        _write_log(stats)
    return updated


def recruiter_language_score(payload: schemas.GenerationPayload) -> int:
    text = "\n".join([
        *payload.resume_sections.summary, *payload.resume_sections.skills,
        *[str(value) for project in payload.resume_sections.projects for value in [
            project.get("intro", ""), project.get("role", ""), *(project.get("details", []) or [])
        ]],
    ])
    return max(0, 100 - internal_field_count(text) * 20)
