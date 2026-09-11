import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .canonical_consumer_view_service import (
    CanonicalConsumerViewAccessStats,
    CanonicalPresentationView,
)


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_language_quality.jsonl"
LABEL_PATTERN = re.compile(r"^(?:技术动作|项目动作|主要做了|具体包括)\s*[:：]\s*")
PACKAGING_LEVELS = {"稳妥", "大胆", "极限"}
NON_FINAL_EXPRESSION_PATTERN = re.compile(r"(?:没有|并未|未曾|不确定|计划|打算|准备|希望|想要)")
SOFT_DERIVATIONS = (
    (
        re.compile(r"(?:我)?写了?几个?页面"),
        {
            "稳妥": "参与前端页面开发与交互实现",
            "大胆": "参与前端架构设计与完整交互流程建设",
            "极限": "参与前端架构设计与完整交互流程建设，完善功能交付与后续迭代基础",
        },
    ),
    (
        re.compile(r"(?:我)?做了?数据整理"),
        {
            "稳妥": "完成数据整理与基础校验",
            "大胆": "负责数据清洗、结构化整理与分析流程建设",
            "极限": "负责数据清洗、结构化整理与分析流程建设，支撑分析交付与后续迭代",
        },
    ),
    (
        re.compile(r"(?:我)?写了?几个?接口"),
        {
            "稳妥": "参与接口开发与功能实现",
            "大胆": "参与接口设计与服务端功能实现",
            "极限": "参与接口设计、服务端功能实现与联调验证，完善接口交付流程",
        },
    ),
    (
        re.compile(r"(?:我)?帮忙测试"),
        {
            "稳妥": "参与功能测试与结果核验",
            "大胆": "参与功能验证、问题定位与交付质量保障",
            "极限": "参与功能验证、问题定位与交付质量保障，支撑功能稳定交付",
        },
    ),
    (
        re.compile(r"(?:我)?做了?用户调研"),
        {
            "稳妥": "开展用户调研与反馈整理",
            "大胆": "负责用户需求调研、反馈归纳与产品优化分析",
            "极限": "负责用户需求调研、反馈归纳与产品优化分析，支撑产品迭代决策",
        },
    ),
)


@dataclass
class LanguageStats:
    stage: str
    generation_result_id: int | None
    packaging_level: str = "大胆"
    colloquial_expression_count: int = 0
    professionalized_expression_count: int = 0
    soft_derivation_count: int = 0
    insufficient_provenance_skip_count: int = 0
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


def _professionalize_text(value: str, packaging_level: str) -> tuple[str, bool, bool, int]:
    original = str(value or "").strip()
    if not original:
        return "", False, False, 0
    cleaned = LABEL_PATTERN.sub("", original)
    label_removed = cleaned != original
    soft_derivation_count = 0
    level = packaging_level if packaging_level in PACKAGING_LEVELS else "大胆"
    if not NON_FINAL_EXPRESSION_PATTERN.search(cleaned):
        for pattern, replacements in SOFT_DERIVATIONS:
            cleaned, count = pattern.subn(replacements[level], cleaned)
            soft_derivation_count += count
    replacements = [
        (r"^我独立完成", "独立完成"), (r"^我负责", "负责"), (r"^我参与", "参与"),
        (r"^我做过一个?", "完成"), (r"^我做了", "完成"),
        (r"我调了一些接口", "完成接口联调、数据流转校验与异常排查"),
        (r"我修了一些\s*(?:bug|Bug|BUG)", "定位并修复关键流程异常"),
        (r"我写了文档", "沉淀项目说明、使用文档与复盘材料"),
        (r"^我用了", "使用"), (r"^用了", "使用"),
    ]
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = cleaned.replace("技术动作", "技术实现")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,、；;：:。")
    return cleaned, cleaned != original, label_removed, soft_derivation_count


def professionalize_text(value: str, packaging_level: str = "大胆") -> tuple[str, bool, bool]:
    text, changed, label_removed, _ = _professionalize_text(value, packaging_level)
    return text, changed, label_removed


def field_has_professionalization_authority(
    project: dict,
    field_name: str,
    detail_index: int | None,
    presentation_view: CanonicalPresentationView,
    access_stats: CanonicalConsumerViewAccessStats | None = None,
) -> bool:
    if not presentation_view.permits_project_field(
        project, field_name, detail_index, access_stats=access_stats,
    ):
        return False
    owner = presentation_view.owner_for_project(project)
    fact_ids = presentation_view.fact_ids_for_field(project, field_name, detail_index)
    if not owner or not fact_ids:
        return False
    eligible_facts = {fact.fact_id: fact for fact in presentation_view.eligible_facts(owner)}
    expected_claim_ids = {
        eligible_facts[fact_id].claim_id
        for fact_id in fact_ids
        if fact_id in eligible_facts and eligible_facts[fact_id].claim_id
    }
    if field_name == "role":
        if "role_source_claim_ids" not in project:
            return True
        raw_claim_ids = project.get("role_source_claim_ids")
    elif field_name == "details" and detail_index is not None:
        if "detail_claim_ids" not in project:
            return True
        rows = project.get("detail_claim_ids")
        if not isinstance(rows, list) or detail_index >= len(rows):
            return False
        raw_claim_ids = rows[detail_index]
    else:
        return False
    if not isinstance(raw_claim_ids, (list, tuple, set)):
        return False
    attached_claim_ids = {str(item) for item in raw_claim_ids if str(item or "")}
    return attached_claim_ids == expected_claim_ids


def professionalize_resume_language(
    payload: schemas.GenerationPayload,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
    presentation_view: CanonicalPresentationView | None = None,
    access_stats: CanonicalConsumerViewAccessStats | None = None,
    packaging_level: str = "大胆",
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    level = packaging_level if packaging_level in PACKAGING_LEVELS else "大胆"
    stats = LanguageStats(stage=stage, generation_result_id=generation_result_id, packaging_level=level)

    def clean(value: str, field_name: str, experience_id: str = "") -> str:
        text, changed, label_removed, derivation_count = _professionalize_text(value, level)
        if changed:
            stats.colloquial_expression_count += 1
            stats.professionalized_expression_count += 1
            stats.affected_fields.append(field_name)
            if experience_id:
                stats.affected_experience_ids.append(experience_id)
        if label_removed:
            stats.removed_label_count += 1
        stats.soft_derivation_count += derivation_count
        return text

    updated.resume_sections.summary = [
        clean(item, f"summary.{index}")
        if presentation_view is None or presentation_view.supports_global_text(item)
        else item
        for index, item in enumerate(updated.resume_sections.summary)
        if item
    ]
    projects: list[dict] = []
    for raw_project in updated.resume_sections.projects:
        project = dict(raw_project)
        experience_id = str(project.get("immutable_source_experience_id") or project.get("source_experience_id") or "")
        for field_name in ("intro", "role"):
            original = str(project.get(field_name, ""))
            permitted = presentation_view is None or field_has_professionalization_authority(
                project, field_name, None, presentation_view, access_stats,
            )
            if presentation_view is not None and not permitted and original.strip():
                stats.insufficient_provenance_skip_count += 1
            candidate = clean(original, f"projects.{field_name}", experience_id) if permitted else original
            project[field_name] = candidate or original
        details: list[str] = []
        for detail_index, item in enumerate(project.get("details", [])):
            original = str(item).strip()
            if not original:
                continue
            permitted = presentation_view is None or field_has_professionalization_authority(
                project, "details", detail_index, presentation_view, access_stats,
            )
            if presentation_view is not None and not permitted:
                stats.insufficient_provenance_skip_count += 1
            candidate = clean(original, "projects.details", experience_id) if permitted else original
            details.append(candidate or original)
        project["details"] = details
        projects.append(project)
    updated.resume_sections.projects = projects
    if write_log:
        _write_log(stats)
    return updated
