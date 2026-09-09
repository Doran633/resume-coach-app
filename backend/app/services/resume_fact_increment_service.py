from .. import schemas
from .experience_fact_ledger_service import is_generic_detail
from .resume_fact_dedup_service import information_score, similarity, _detail_records, _preserve_project_aggregates
from .resume_information_gain_service import information_gain_components


def _components(text: str) -> set[str]:
    rows = information_gain_components(text)
    return {f"{name}:{item.lower()}" for name, values in rows.items() for item in values}


def _high_value(text: str) -> bool:
    value = str(text or "")
    return any(term.lower() in value.lower() for term in [
        "上线", "部署", "测试集", "评测", "指标", "数据隔离", "权限", "日志",
        "健康检查", "Smoke Test", "Citation", "Groundedness", "用户反馈",
        "Resume Section Fallback", "Experience ID", "Fact Ledger", "事实边界",
        "输出防火墙", "结构完整性", "业务完整性",
    ]) or any(char.isdigit() for char in value)


def ensure_resume_fact_increment(payload: schemas.GenerationPayload, stats: dict | None = None) -> schemas.GenerationPayload:
    """Remove details that add no fact beyond headers or preceding details."""
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        original_records = _detail_records(project, include_empty=True)
        covered = _components(str(project.get("intro") or "")) | _components(str(project.get("role") or ""))
        seen_fact_ids: set[str] = set()
        kept = []
        for record in original_records:
            detail, ids = record.text, record.source_fact_ids
            if not detail:
                continue
            components = _components(detail)
            new_components = components - covered
            new_fact_ids = set(ids) - seen_fact_ids
            position = next((i for i, existing in enumerate(kept)
                             if ids and record.source_claim_ids
                             and set(ids) == set(existing.source_fact_ids)
                             and set(record.source_claim_ids) == set(existing.source_claim_ids)
                             and similarity(detail, existing.text) >= 0.91), -1)
            duplicate = position >= 0
            no_increment = not new_components and not new_fact_ids
            if is_generic_detail(detail) or (duplicate and no_increment) or (no_increment and not ids and not record.source_claim_ids and not _high_value(detail)):
                if stats is not None:
                    stats["details_without_increment_count"] = stats.get("details_without_increment_count", 0) + 1
                continue
            if duplicate and kept:
                if information_score(detail, ids) > information_score(kept[position].text, kept[position].source_fact_ids):
                    kept[position] = record
                continue
            kept.append(record)
            covered.update(components)
            seen_fact_ids.update(ids)
        kept = kept[:8]
        project["details"] = [row.text for row in kept]
        project["detail_fact_ids"] = [row.source_fact_ids for row in kept]
        project["detail_claim_ids"] = [row.source_claim_ids for row in kept]
        _preserve_project_aggregates(project, kept, original_records)
    return updated
