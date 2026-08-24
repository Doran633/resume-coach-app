import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_PATH = LOG_DIR / "result_cleanup.jsonl"

ALLOWED_RISK_LEVELS = {"green", "yellow", "red", "black"}
DEFAULT_TEXT = "暂未生成，建议补充更多经历细节后重新生成。"

REPLACEMENTS: dict[str, str] = {
    "interview_preparation": "面试准备",
    "responsibilities": "我的职责",
    "project_intro": "项目简介",
    "project_name": "项目名称",
    "answer_points": "回答要点",
    "tech_details": "技术细节",
    "achievements": "项目成果",
    "my_role": "我的职责",
    "projects": "项目经历",
    "project": "项目经历",
    "question": "面试问题",
    "details": "技术细节",
    "summary": "个人优势",
    "skills": "技能栈",
    "education": "教育经历",
    "intro": "项目简介",
    "role": "我的职责",
    "meta": "项目类型",
    "name": "项目名称",
    "time": "项目时间",
    "degree": "学历",
    "school": "学校",
    "major": "专业",
}


class CleanupStats:
    def __init__(self, source: str | None = None):
        self.source = source
        self.replacements: dict[str, int] = {}
        self.fallback_fields: list[str] = []
        self.risk_level_fixed_count = 0

    @property
    def changed(self) -> bool:
        return bool(self.replacements or self.fallback_fields or self.risk_level_fixed_count)

    def add_replacement(self, key: str, count: int):
        if count > 0:
            self.replacements[key] = self.replacements.get(key, 0) + count

    def add_fallback(self, field_path: str):
        self.fallback_fields.append(field_path)


def _write_cleanup_log(stats: CleanupStats):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "changed": stats.changed,
            "replacements": stats.replacements,
            "fallback_fields": stats.fallback_fields,
            "risk_level_fixed_count": stats.risk_level_fixed_count,
            "source": stats.source,
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(log, ensure_ascii=False) + "\n")
    except Exception:
        return


def _replacement_items():
    return sorted(REPLACEMENTS.items(), key=lambda item: len(item[0]), reverse=True)


def _replace_field_markers(text: str, stats: CleanupStats) -> str:
    cleaned = text
    for marker, replacement in _replacement_items():
        label_pattern = re.compile(
            rf"(^|[\s{{\[\(,，。;；])(?:[-*]\s*)?[\"']?{re.escape(marker)}[\"']?\s*[:：=]",
            re.IGNORECASE,
        )
        cleaned, label_count = label_pattern.subn(lambda match: f"{match.group(1)}{replacement}：", cleaned)

        standalone_pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(marker)}(?![A-Za-z0-9_])", re.IGNORECASE)
        cleaned, standalone_count = standalone_pattern.subn(replacement, cleaned)
        stats.add_replacement(marker, label_count + standalone_count)
    return cleaned


def _clean_markdown_json_wrapping(text: str) -> str:
    cleaned = text.replace("```json", "").replace("```JSON", "").replace("```", "")
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s+([，。！？、；：])", r"\1", cleaned)
    return cleaned.strip()


def _clean_text(value, stats: CleanupStats, field_path: str, fallback: str | None = DEFAULT_TEXT) -> str:
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)

    cleaned = _replace_field_markers(text, stats)
    cleaned = _clean_markdown_json_wrapping(cleaned)
    if not cleaned and fallback is not None:
        stats.add_fallback(field_path)
        return fallback
    return cleaned


def _clean_list(values, stats: CleanupStats, field_path: str, limit: int | None = None) -> list[str]:
    if not isinstance(values, list):
        stats.add_fallback(field_path)
        return []
    cleaned = []
    for index, item in enumerate(values):
        text = _clean_text(item, stats, f"{field_path}[{index}]", fallback=None)
        if text:
            cleaned.append(text)
    return cleaned[:limit] if limit is not None else cleaned


def _clean_string_dict(values, stats: CleanupStats, field_path: str) -> dict[str, str]:
    if not isinstance(values, dict):
        stats.add_fallback(field_path)
        return {}
    cleaned = {}
    for key, value in values.items():
        key_text = str(key)
        clean_key = REPLACEMENTS.get(key_text.lower(), key_text)
        if clean_key != key_text:
            stats.add_replacement(key_text.lower(), 1)
        clean_key = _clean_text(clean_key, stats, f"{field_path}.{key}.key", fallback=str(key))
        cleaned[clean_key] = _clean_text(value, stats, f"{field_path}.{key}")
    return cleaned


def _clean_claims(claims, stats: CleanupStats) -> list[dict]:
    if not isinstance(claims, list):
        stats.add_fallback("claims")
        return []

    cleaned_claims = []
    for index, claim in enumerate(claims[:12]):
        if not isinstance(claim, dict):
            claim = {"claim": claim}

        risk_level = str(claim.get("risk_level", "yellow")).lower()
        if risk_level not in ALLOWED_RISK_LEVELS:
            risk_level = "yellow"
            stats.risk_level_fixed_count += 1

        claim_text = _clean_text(claim.get("claim"), stats, f"claims[{index}].claim", fallback=None)
        if not claim_text:
            stats.add_fallback(f"claims[{index}].claim")
            claim_text = "待确认表达"

        risk_reason = _clean_text(claim.get("risk_reason"), stats, f"claims[{index}].risk_reason", fallback=None)
        if not risk_reason:
            stats.add_fallback(f"claims[{index}].risk_reason")
            risk_reason = "该表达需要结合事实证据和面试准备判断使用强度。"

        downgrade = _clean_text(claim.get("downgrade_wording"), stats, f"claims[{index}].downgrade_wording", fallback=None)
        if not downgrade:
            stats.add_fallback(f"claims[{index}].downgrade_wording")
            downgrade = "准备不足时建议降低职责强度，改为参与或协助相关工作。"

        cleaned_claims.append(
            {
                "claim": claim_text,
                "risk_level": risk_level,
                "evidence": _clean_text(claim.get("evidence"), stats, f"claims[{index}].evidence"),
                "risk_reason": risk_reason,
                "interview_questions": _clean_list(claim.get("interview_questions"), stats, f"claims[{index}].interview_questions"),
                "knowledge_to_prepare": _clean_list(claim.get("knowledge_to_prepare"), stats, f"claims[{index}].knowledge_to_prepare"),
                "downgrade_wording": downgrade,
            }
        )
    return cleaned_claims


def _clean_projects(projects, stats: CleanupStats) -> list[dict]:
    if not isinstance(projects, list):
        stats.add_fallback("resume_sections.projects")
        return []

    cleaned_projects = []
    for index, project in enumerate(projects[:3]):
        if not isinstance(project, dict):
            project = {"name": "项目经历", "intro": project}
        cleaned_projects.append(
            {
                "name": _clean_text(project.get("name"), stats, f"resume_sections.projects[{index}].name"),
                "meta": _clean_text(project.get("meta"), stats, f"resume_sections.projects[{index}].meta"),
                "time": _clean_text(project.get("time"), stats, f"resume_sections.projects[{index}].time"),
                "intro": _clean_text(project.get("intro"), stats, f"resume_sections.projects[{index}].intro"),
                "role": _clean_text(project.get("role"), stats, f"resume_sections.projects[{index}].role"),
                "details": _clean_list(project.get("details"), stats, f"resume_sections.projects[{index}].details", limit=6),
            }
        )
    return cleaned_projects


def cleanup_generation_payload(payload: schemas.GenerationPayload | dict, source: str | None = None) -> schemas.GenerationPayload:
    stats = CleanupStats(source=source)
    data = deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)

    data["confirmed_facts"] = _clean_list(data.get("confirmed_facts"), stats, "confirmed_facts", limit=8)
    data["missing_questions"] = _clean_list(data.get("missing_questions"), stats, "missing_questions", limit=8)
    data["normal_version"] = _clean_text(data.get("normal_version"), stats, "normal_version")
    data["bold_version"] = _clean_text(data.get("bold_version"), stats, "bold_version")
    data["boundary_version"] = _clean_text(data.get("boundary_version"), stats, "boundary_version")
    data["recommended_version"] = _clean_text(data.get("recommended_version"), stats, "recommended_version")
    data["claims"] = _clean_claims(data.get("claims"), stats)
    data["interview_plan"] = _clean_list(data.get("interview_plan"), stats, "interview_plan", limit=10)
    data["knowledge_checklist"] = _clean_list(data.get("knowledge_checklist"), stats, "knowledge_checklist", limit=12)

    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    if not sections:
        stats.add_fallback("resume_sections")
    sections["personal_info"] = _clean_string_dict(sections.get("personal_info"), stats, "resume_sections.personal_info")
    sections["summary"] = _clean_list(sections.get("summary"), stats, "resume_sections.summary")
    sections["skills"] = _clean_list(sections.get("skills"), stats, "resume_sections.skills")
    sections["projects"] = _clean_projects(sections.get("projects"), stats)
    sections["education"] = _clean_string_dict(sections.get("education"), stats, "resume_sections.education")
    sections["interview_preparation"] = _clean_list(sections.get("interview_preparation"), stats, "resume_sections.interview_preparation")
    data["resume_sections"] = sections

    cleaned_payload = schemas.GenerationPayload.model_validate(data)
    _write_cleanup_log(stats)
    return cleaned_payload
