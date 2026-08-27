import re

from .. import schemas
from .experience_fact_ledger_service import TECH_PATTERN, is_generic_detail
from .resume_fact_dedup_service import information_score, same_fact_action, similarity


ACTION_PATTERN = re.compile(r"设计|实现|构建|搭建|接入|优化|建立|拆分|定位|解决|修复|联调|部署|评测|迭代|组织|协调|分析")
RESULT_PATTERN = re.compile(r"提升|降低|上线|交付|获奖|用户|指标|结果|验证|反馈|\d+(?:\.\d+)?")


def information_terms(text: str) -> set[str]:
    value = str(text or "")
    terms = {item.lower() for item in TECH_PATTERN.findall(value) if item}
    terms.update(ACTION_PATTERN.findall(value))
    terms.update(RESULT_PATTERN.findall(value))
    terms.update(re.findall(r"日志|健康检查|测试集|数据隔离|权限|接口|组件|检索|切块|部署|答辩|协作", value, re.I))
    return terms


def _covered_by_header(detail: str, intro: str, role: str, fact_ids: list[str]) -> bool:
    if information_score(detail, fact_ids) > max(information_score(intro), information_score(role)) + 3:
        return False
    return any(similarity(detail, value) >= 0.92 or same_fact_action(detail, value) for value in [intro, role] if value)


def ensure_information_gain(payload: schemas.GenerationPayload, stats: dict | None = None) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        intro, role = str(project.get("intro") or ""), str(project.get("role") or "")
        details = [str(item).strip() for item in project.get("details", []) if str(item).strip()]
        fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        kept: list[tuple[str, list[str]]] = []
        for index, detail in enumerate(details):
            ids = [str(item) for item in fact_rows[index]] if index < len(fact_rows) and isinstance(fact_rows[index], list) else []
            if is_generic_detail(detail) or _covered_by_header(detail, intro, role, ids):
                if stats is not None:
                    stats["low_information_gain_count"] = stats.get("low_information_gain_count", 0) + 1
                continue
            duplicate_index = -1
            for pos, (existing, existing_ids) in enumerate(kept):
                existing_terms, current_terms = information_terms(existing), information_terms(detail)
                shared_source = bool(set(existing_ids) & set(ids))
                source_containment = shared_source and bool(existing_terms) and (
                    existing_terms <= current_terms or current_terms <= existing_terms
                )
                if similarity(existing, detail) >= 0.91 or source_containment or (
                    shared_source and same_fact_action(existing, detail)
                ):
                    duplicate_index = pos
                    break
            if duplicate_index < 0:
                kept.append((detail, ids))
                continue
            existing, existing_ids = kept[duplicate_index]
            existing_terms, current_terms = information_terms(existing), information_terms(detail)
            if existing_terms - current_terms and current_terms - existing_terms:
                kept.append((detail, ids))
                continue
            if information_score(detail, ids) > information_score(existing, existing_ids):
                kept[duplicate_index] = (detail, list(dict.fromkeys([*existing_ids, *ids])))
            else:
                kept[duplicate_index] = (existing, list(dict.fromkeys([*existing_ids, *ids])))
            if stats is not None:
                stats["merged_detail_count"] = stats.get("merged_detail_count", 0) + 1
        project["details"] = [item[0] for item in kept]
        project["detail_fact_ids"] = [item[1] for item in kept]
        project["source_fact_ids"] = list(dict.fromkeys(fact_id for _, ids in kept for fact_id in ids))
    return updated
