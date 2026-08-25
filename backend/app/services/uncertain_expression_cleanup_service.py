import re
from typing import Any

from .. import schemas
from .long_input_service import TECH_TERMS


UNCERTAIN_MARKERS = ["如有", "如使用", "可补充", "建议掌握", "建议了解", "待补充", "可以学习", "需要学习", "可进一步补齐"]
INFERENCE_TERMS = [
    "Top-K",
    "Retrieval",
    "Chunk",
    "Embedding",
    "Recall",
    "Precision",
    "Groundedness",
    "Citation",
    "Rerank",
    "RESTful API",
    "参数校验",
    "异常处理",
    "接口日志",
    "组件化",
    "状态管理",
    "表单校验",
    "Benchmark",
    "误差分析",
    "Nginx",
    "systemd",
]
KNOWN_TERMS = TECH_TERMS + INFERENCE_TERMS
BODY_FORBIDDEN_UNLESS_EXPLICIT = ["Rerank", "LangGraph", "SFT", "RLHF", "DPO", "LoRA"]


def _has_uncertain_marker(text: str) -> bool:
    return any(marker in (text or "") for marker in UNCERTAIN_MARKERS)


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(re.escape(term), text or "", re.IGNORECASE))


def _extract_terms(text: str) -> list[str]:
    return [term for term in KNOWN_TERMS if _contains_term(text, term)]


def _explicit_terms(raw_input: str) -> set[str]:
    return {term for term in KNOWN_TERMS if _contains_term(raw_input, term)}


def _add_unique(values: list[str], item: str) -> None:
    if item and item not in values:
        values.append(item)


def _strip_uncertain_parentheses(text: str, explicit: set[str], moved: list[str]) -> str:
    cleaned = text or ""
    for term in KNOWN_TERMS:
        pattern = re.compile(rf"{re.escape(term)}\s*[（(][^）)]*(?:{'|'.join(map(re.escape, UNCERTAIN_MARKERS))})[^）)]*[）)]", re.IGNORECASE)
        if pattern.search(cleaned):
            _add_unique(moved, term)
            replacement = term if term in explicit else ""
            cleaned = pattern.sub(replacement, cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip(" ，,、；;")


def _clean_text(text: str, explicit: set[str], moved: list[str]) -> str:
    if not text:
        return ""
    cleaned = _strip_uncertain_parentheses(text, explicit, moved)
    sentences = [item.strip() for item in re.split(r"(?<=[。！？；;])\s*|\n+", cleaned) if item.strip()]
    if not sentences:
        terms = _extract_terms(cleaned)
        for term in terms:
            _add_unique(moved, term)
        forbidden = [term for term in BODY_FORBIDDEN_UNLESS_EXPLICIT if _contains_term(cleaned, term) and term not in explicit]
        return "" if (_has_uncertain_marker(cleaned) and terms) or forbidden else cleaned

    kept: list[str] = []
    for sentence in sentences:
        forbidden_terms = [term for term in BODY_FORBIDDEN_UNLESS_EXPLICIT if _contains_term(sentence, term) and term not in explicit]
        if forbidden_terms:
            for term in forbidden_terms:
                _add_unique(moved, term)
            continue
        if _has_uncertain_marker(sentence):
            for term in _extract_terms(sentence):
                _add_unique(moved, term)
            continue
        kept.append(sentence)
    return "".join(kept)


def _clean_string_list(items: list[str], explicit: set[str], moved: list[str]) -> list[str]:
    result: list[str] = []
    for item in items or []:
        cleaned = _clean_text(str(item), explicit, moved)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _merge_preparation(payload: schemas.GenerationPayload, moved_terms: list[str]) -> None:
    for term in moved_terms:
        _add_unique(payload.knowledge_checklist, term)
        _add_unique(payload.interview_plan, f"补齐 {term} 的基本概念、使用边界和面试解释口径。")
        _add_unique(payload.resume_sections.interview_preparation, f"补齐 {term} 的基本概念、使用边界和面试解释口径。")


def cleanup_uncertain_expressions(payload: schemas.GenerationPayload, raw_input: str) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    explicit = _explicit_terms(raw_input)
    moved_terms: list[str] = []

    updated.normal_version = _clean_text(updated.normal_version, explicit, moved_terms)
    updated.bold_version = _clean_text(updated.bold_version, explicit, moved_terms)
    updated.recommended_version = _clean_text(updated.recommended_version, explicit, moved_terms)
    updated.resume_sections.summary = _clean_string_list(updated.resume_sections.summary, explicit, moved_terms)
    updated.resume_sections.skills = _clean_string_list(updated.resume_sections.skills, explicit, moved_terms)

    cleaned_projects: list[dict[str, Any]] = []
    for project in updated.resume_sections.projects:
        cleaned = dict(project)
        for key in ["intro", "role"]:
            cleaned[key] = _clean_text(str(cleaned.get(key, "")), explicit, moved_terms)
        cleaned["details"] = _clean_string_list([str(item) for item in cleaned.get("details", [])], explicit, moved_terms)
        cleaned_projects.append(cleaned)
    updated.resume_sections.projects = cleaned_projects
    _merge_preparation(updated, moved_terms)
    return updated
