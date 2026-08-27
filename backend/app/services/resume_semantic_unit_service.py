import re

from .. import schemas
from .experience_fact_ledger_service import ExperienceFact, build_experience_fact_ledger


TRAILING_DEPENDENCY = re.compile(r"(?:并|同时|以及|从而|因此|其中|包括|例如|通过|针对|基于|围绕)[，,:：;；\-—]?\s*$", re.I)
LEADING_DEPENDENCY = re.compile(r"^(?:针对该问题|在此基础上|预处理阶段|进一步|同时|因此|随后)[，,:：]?", re.I)
TRAILING_SEPARATOR = re.compile(r"[，,:：;；\-—]\s*$")
ACTION = re.compile(r"设计|实现|构建|搭建|接入|优化|建立|拆分|定位|解决|修复|联调|部署|评测|迭代|参与|负责|完成|记录|分析|支持")
METRIC = re.compile(r"\d+(?:\.\d+)?(?:%|ms|秒|次|人|token)?", re.I)


def fragment_reasons(text: str) -> set[str]:
    value = str(text or "").strip()
    reasons: set[str] = set()
    if not value:
        return {"empty"}
    if TRAILING_DEPENDENCY.search(value) or TRAILING_SEPARATOR.search(value):
        reasons.add("trailing_dependency")
    if LEADING_DEPENDENCY.search(value):
        reasons.add("leading_dependency")
    if re.search(r"从[^，。；]{1,40}(?:提升|降低|变化)到?$", value):
        reasons.add("incomplete_range")
    if re.search(r"(?:提升|降低)$", value) or (METRIC.search(value) and not re.search(r"提升|降低|达到|从|至|减少|增加|优化", value)):
        reasons.add("metric_without_relation")
    tech_tokens = re.findall(r"[A-Za-z][A-Za-z0-9+_.\-/ ]{1,30}", value)
    if len(tech_tokens) >= 2 and not ACTION.search(value):
        reasons.add("term_list_without_action")
    return reasons


def is_semantically_complete(text: str) -> bool:
    return not fragment_reasons(text)


def _merge_facts(facts: list[ExperienceFact]) -> str:
    values = [fact.resume_ready_text.strip(" ，,；;。") for fact in facts if fact.resume_ready_text]
    return "，".join(dict.fromkeys(values)).strip(" ，,；;")


def ensure_semantic_units(
    payload: schemas.GenerationPayload,
    raw_input: str,
    stats: dict | None = None,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    ledger = build_experience_fact_ledger(raw_input)
    fact_by_id = {fact.fact_id: fact for fact in ledger.facts}
    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        details = [str(item).strip() for item in project.get("details", []) if str(item).strip()]
        fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        kept: list[tuple[str, list[str]]] = []
        for index, detail in enumerate(details):
            ids = [str(item) for item in fact_rows[index]] if index < len(fact_rows) and isinstance(fact_rows[index], list) else []
            reasons = fragment_reasons(detail)
            if not reasons:
                kept.append((detail, ids))
                continue
            if stats is not None:
                stats["fragment_detected_count"] = stats.get("fragment_detected_count", 0) + 1
            source_facts = [fact_by_id[item] for item in ids if item in fact_by_id and fact_by_id[item].experience_id == source_id]
            related_ids = [related for fact in source_facts for related in fact.related_fact_ids]
            related_facts = [fact_by_id[item] for item in related_ids if item in fact_by_id and fact_by_id[item].experience_id == source_id]
            recovered = _merge_facts([*source_facts, *related_facts])
            recovered_ids = list(dict.fromkeys([*ids, *related_ids]))
            if recovered and is_semantically_complete(recovered):
                kept.append((recovered, recovered_ids))
                if stats is not None:
                    stats["fragment_recovered_count"] = stats.get("fragment_recovered_count", 0) + 1
                    stats["adjacent_units_merged_count"] = stats.get("adjacent_units_merged_count", 0) + bool(related_facts)
            elif len(detail) >= 12 and not TRAILING_DEPENDENCY.search(detail) and not TRAILING_SEPARATOR.search(detail):
                kept.append((detail, ids))
            elif stats is not None:
                stats["fragment_removed_count"] = stats.get("fragment_removed_count", 0) + 1
        project["details"] = [item[0] for item in kept]
        project["detail_fact_ids"] = [item[1] for item in kept]
        project["source_fact_ids"] = list(dict.fromkeys(fact_id for _, ids in kept for fact_id in ids))
    return updated
