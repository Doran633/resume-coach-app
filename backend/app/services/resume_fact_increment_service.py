from .. import schemas
from .experience_fact_ledger_service import is_generic_detail
from .resume_fact_dedup_service import information_score, similarity
from .resume_information_gain_service import information_gain_components


def _components(text: str) -> set[str]:
    rows = information_gain_components(text)
    return {f"{name}:{item.lower()}" for name, values in rows.items() for item in values}


def _high_value(text: str) -> bool:
    value = str(text or "")
    return any(term.lower() in value.lower() for term in [
        "上线", "部署", "测试集", "评测", "指标", "数据隔离", "权限", "日志",
        "健康检查", "Smoke Test", "Citation", "Groundedness", "用户反馈",
    ]) or any(char.isdigit() for char in value)


def ensure_resume_fact_increment(payload: schemas.GenerationPayload, stats: dict | None = None) -> schemas.GenerationPayload:
    """Remove details that add no fact beyond headers or preceding details."""
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        details = [str(item).strip() for item in project.get("details", []) if str(item).strip()]
        fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        covered = _components(str(project.get("intro") or "")) | _components(str(project.get("role") or ""))
        seen_fact_ids: set[str] = set()
        kept: list[tuple[str, list[str]]] = []
        for index, detail in enumerate(details):
            ids = [str(item) for item in fact_rows[index]] if index < len(fact_rows) and isinstance(fact_rows[index], list) else []
            components = _components(detail)
            new_components = components - covered
            new_fact_ids = set(ids) - seen_fact_ids
            duplicate = any(similarity(detail, existing) >= 0.91 for existing, _ in kept)
            no_increment = not new_components and not new_fact_ids
            if is_generic_detail(detail) or (duplicate and no_increment) or (no_increment and not _high_value(detail)):
                if stats is not None:
                    stats["details_without_increment_count"] = stats.get("details_without_increment_count", 0) + 1
                continue
            if duplicate and kept:
                position = next((i for i, (existing, _) in enumerate(kept) if similarity(detail, existing) >= 0.91), -1)
                if position >= 0 and information_score(detail, ids) > information_score(kept[position][0], kept[position][1]):
                    previous_ids = kept[position][1]
                    kept[position] = (detail, list(dict.fromkeys([*previous_ids, *ids])))
                continue
            kept.append((detail, ids))
            covered.update(components)
            seen_fact_ids.update(ids)
        project["details"] = [text for text, _ in kept[:8]]
        project["detail_fact_ids"] = [ids for _, ids in kept[:8]]
        project["source_fact_ids"] = list(dict.fromkeys(fact_id for _, ids in kept[:8] for fact_id in ids))
    return updated
