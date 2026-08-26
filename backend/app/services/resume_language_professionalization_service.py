import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_language_quality.jsonl"
LABEL_PATTERN = re.compile(r"^(?:技术动作|项目动作|主要做了|具体包括)\s*[:：]\s*")


@dataclass
class LanguageStats:
    stage: str
    generation_result_id: int | None
    colloquial_expression_count: int = 0
    professionalized_expression_count: int = 0
    removed_label_count: int = 0
    affected_experience_ids: list[str] = field(default_factory=list)
    affected_fields: list[str] = field(default_factory=list)


def _write_log(stats: LanguageStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **stats.__dict__}
        entry["affected_experience_ids"] = sorted(set(entry["affected_experience_ids"]))
        entry["affected_fields"] = sorted(set(entry["affected_fields"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def professionalize_text(value: str) -> tuple[str, bool, bool]:
    original = str(value or "").strip()
    if not original:
        return "", False, False
    cleaned = LABEL_PATTERN.sub("", original)
    label_removed = cleaned != original
    replacements = [
        (r"^我独立完成", "独立完成"), (r"^我负责", "负责"), (r"^我参与", "参与"),
        (r"^我做过一个?", "完成"), (r"^我做了", "完成"),
        (r"我写了几个页面", "负责相关页面开发与交互流程实现"),
        (r"我调了一些接口", "完成接口联调、数据流转校验与异常排查"),
        (r"我修了一些\s*(?:bug|Bug|BUG)", "定位并修复关键流程异常"),
        (r"我写了文档", "沉淀项目说明、使用文档与复盘材料"),
        (r"^我用了", "使用"), (r"^用了", "使用"),
    ]
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = cleaned.replace("技术动作", "技术实现")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,、；;：:。")
    return cleaned, cleaned != original, label_removed


def professionalize_resume_language(
    payload: schemas.GenerationPayload,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = LanguageStats(stage=stage, generation_result_id=generation_result_id)

    def clean(value: str, field_name: str, experience_id: str = "") -> str:
        text, changed, label_removed = professionalize_text(value)
        if changed:
            stats.colloquial_expression_count += 1
            stats.professionalized_expression_count += 1
            stats.affected_fields.append(field_name)
            if experience_id:
                stats.affected_experience_ids.append(experience_id)
        if label_removed:
            stats.removed_label_count += 1
        return text

    updated.resume_sections.summary = [clean(item, "summary") for item in updated.resume_sections.summary if item]
    projects: list[dict] = []
    for raw_project in updated.resume_sections.projects:
        project = dict(raw_project)
        experience_id = str(project.get("source_experience_id", ""))
        project["intro"] = clean(str(project.get("intro", "")), "projects.intro", experience_id)
        project["role"] = clean(str(project.get("role", "")), "projects.role", experience_id)
        project["details"] = [clean(str(item), "projects.details", experience_id) for item in project.get("details", []) if str(item).strip()]
        projects.append(project)
    updated.resume_sections.projects = projects
    if write_log:
        _write_log(stats)
    return updated
