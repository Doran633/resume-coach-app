import re

from .. import schemas
from .experience_fact_ledger_service import TECH_PATTERN, is_generic_detail
from .resume_fact_dedup_service import information_score, same_fact_action, similarity, _detail_records, _preserve_project_aggregates


ACTION_PATTERN = re.compile(r"设计|实现|构建|搭建|接入|优化|建立|拆分|定位|解决|修复|联调|部署|评测|迭代|组织|协调|分析")
RESULT_PATTERN = re.compile(r"提升|降低|上线|交付|获奖|用户|指标|结果|验证|反馈|\d+(?:\.\d+)?")
OBJECT_PATTERN = re.compile(r"文档|接口|组件|检索|模型|测试集|日志|用户|数据|权限|Citation|Embedding|RAG|Agent", re.I)


def information_terms(text: str) -> set[str]:
    value = str(text or "")
    terms = {item.lower() for item in TECH_PATTERN.findall(value) if item}
    terms.update(ACTION_PATTERN.findall(value))
    terms.update(RESULT_PATTERN.findall(value))
    terms.update(re.findall(r"日志|健康检查|测试集|数据隔离|权限|接口|组件|检索|切块|部署|答辩|协作", value, re.I))
    return terms


def information_gain_components(text: str) -> dict[str, set[str]]:
    value = str(text or "")
    return {
        "tech_actions": set(ACTION_PATTERN.findall(value)),
        "objects": set(OBJECT_PATTERN.findall(value)),
        "metrics_results": set(RESULT_PATTERN.findall(value)),
        "engineering_measures": set(re.findall(r"日志|健康检查|Smoke Test|部署|隔离|权限|监控|测试", value, re.I)),
        "evidence": set(re.findall(r"测试集|指标|仓库|截图|记录|用户反馈|证书", value, re.I)),
        "decisions": set(re.findall(r"选择|权衡|实验|阈值|Top-K|方案|排序", value, re.I)),
    }


def _covered_by_header(detail: str, intro: str, role: str, fact_ids: list[str]) -> bool:
    if information_score(detail, fact_ids) > max(information_score(intro), information_score(role)) + 3:
        return False
    return any(similarity(detail, value) >= 0.92 or same_fact_action(detail, value) for value in [intro, role] if value)


def ensure_information_gain(payload: schemas.GenerationPayload, stats: dict | None = None) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        intro, role = str(project.get("intro") or ""), str(project.get("role") or "")
        original_records = _detail_records(project, include_empty=True)
        kept = []
        for record in original_records:
            detail, ids = record.text, record.source_fact_ids
            if not detail:
                continue
            if is_generic_detail(detail) or (not ids and not record.source_claim_ids and _covered_by_header(detail, intro, role, ids)):
                if stats is not None:
                    stats["low_information_gain_count"] = stats.get("low_information_gain_count", 0) + 1
                continue
            duplicate_index = -1
            for pos, previous in enumerate(kept):
                existing, existing_ids = previous.text, previous.source_fact_ids
                if not ids or not record.source_claim_ids or set(ids) != set(existing_ids) or set(record.source_claim_ids) != set(previous.source_claim_ids):
                    continue
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
                kept.append(record)
                continue
            existing, existing_ids = kept[duplicate_index].text, kept[duplicate_index].source_fact_ids
            existing_terms, current_terms = information_terms(existing), information_terms(detail)
            if existing_terms - current_terms and current_terms - existing_terms:
                kept.append(record)
                continue
            if information_score(detail, ids) > information_score(existing, existing_ids):
                kept[duplicate_index] = record
            if stats is not None:
                stats["merged_detail_count"] = stats.get("merged_detail_count", 0) + 1
        project["details"] = [row.text for row in kept]
        project["detail_fact_ids"] = [row.source_fact_ids for row in kept]
        project["detail_claim_ids"] = [row.source_claim_ids for row in kept]
        _preserve_project_aggregates(project, kept, original_records)
    return updated
