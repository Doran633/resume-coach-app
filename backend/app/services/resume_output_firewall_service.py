import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .input_content_classification_service import strip_non_fact_fragments


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_output_firewall.jsonl"
FORBIDDEN = [
    "想投", "希望投", "希望包装", "帮我包装", "帮我优化", "提高匹配度", "岗位匹配度",
    "不要写成", "不要写得", "不要夸张", "无法解释", "面试别", "哪些地方想重点放大",
    "建议补充", "如有", "如果会", "需要学习", "用户提供的真实经历", "根据现有经历",
    "围绕用户输入", "系统将", "模型生成", "我匹配度", "准备面试", "降级表达",
]
DROP_WHOLE_MARKERS = [
    "围绕已有任务拆解项目目标", "准备面试中的降级表达", "梳理项目不足和后续优化方向",
    "把课程项目讲成完整项目", "解释缺少实战经历时",
]
TEMPLATE_FIELD = re.compile(r"^(?:summary|project|projects|my_role|role|details|intro|meta|name|time)\s*[:：=]\s*", re.I)


@dataclass
class FirewallStats:
    stage: str
    generation_result_id: int | None
    contamination_detected_count: int = 0
    contamination_removed_count: int = 0
    partial_sentence_repaired_count: int = 0
    coach_instruction_removed_count: int = 0
    template_residue_removed_count: int = 0
    unsupported_text_removed_count: int = 0
    affected_experience_ids: list[str] = field(default_factory=list)
    affected_fields: list[str] = field(default_factory=list)


def _write_log(stats: FirewallStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **stats.__dict__}
        entry["affected_experience_ids"] = sorted(set(entry["affected_experience_ids"]))
        entry["affected_fields"] = sorted(set(entry["affected_fields"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _clean_text(value, stats: FirewallStats, field_name: str, experience_id: str = "") -> str:
    original = str(value or "").strip()
    if not original:
        return ""
    if any(marker in original for marker in DROP_WHOLE_MARKERS):
        stats.contamination_detected_count += 1
        stats.contamination_removed_count += 1
        stats.unsupported_text_removed_count += 1
        stats.affected_fields.append(field_name)
        if experience_id:
            stats.affected_experience_ids.append(experience_id)
        return ""
    has_contamination = any(term in original for term in FORBIDDEN) or bool(TEMPLATE_FIELD.search(original))
    cleaned = TEMPLATE_FIELD.sub("", original)
    if cleaned != original:
        stats.template_residue_removed_count += 1
    cleaned, removed = strip_non_fact_fragments(cleaned)
    if has_contamination or removed:
        stats.contamination_detected_count += 1
        stats.coach_instruction_removed_count += len(removed)
        if cleaned:
            stats.partial_sentence_repaired_count += 1
        else:
            stats.unsupported_text_removed_count += 1
        stats.affected_fields.append(field_name)
        if experience_id:
            stats.affected_experience_ids.append(experience_id)
    for term in FORBIDDEN:
        cleaned = cleaned.replace(term, "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,、；;：:。")
    if original and not cleaned:
        stats.contamination_removed_count += 1
    elif cleaned != original:
        stats.contamination_removed_count += 1
    return cleaned


def _clean_list(values, stats: FirewallStats, field_name: str, experience_id: str = "") -> list[str]:
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        cleaned = _clean_text(value, stats, field_name, experience_id)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def guard_resume_output(
    payload: schemas.GenerationPayload | dict,
    raw_input: str = "",
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    data = deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)
    stats = FirewallStats(stage=stage, generation_result_id=generation_result_id)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    sections["summary"] = _clean_list(sections.get("summary"), stats, "summary")
    sections["skills"] = _clean_list(sections.get("skills"), stats, "skills")
    projects: list[dict] = []
    for raw_project in sections.get("projects", []):
        if not isinstance(raw_project, dict):
            continue
        project = dict(raw_project)
        experience_id = str(project.get("source_experience_id", ""))
        for key in ("name", "meta", "intro", "role"):
            project[key] = _clean_text(project.get(key), stats, f"projects.{key}", experience_id)
        project["details"] = _clean_list(project.get("details"), stats, "projects.details", experience_id)
        projects.append(project)
    sections["projects"] = projects
    data["resume_sections"] = sections
    if write_log:
        _write_log(stats)
    return schemas.GenerationPayload.model_validate(data)
