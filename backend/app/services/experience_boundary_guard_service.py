import re
from copy import deepcopy
from typing import Any

from .. import schemas
from .long_input_service import analyze_long_input


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _contains_term(text: str, term: str) -> bool:
    return bool(re.search(re.escape(term), text or "", re.IGNORECASE))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _match_project_to_segment(project: dict[str, Any], segments: list, index: int):
    project_text = _normalize(" ".join(str(project.get(key, "")) for key in ["name", "meta", "intro", "role"]))
    for segment in segments:
        title = _normalize(segment.title)
        label = _normalize(segment.label)
        if title and (title in project_text or project_text in title):
            return segment
        if label and label in project_text:
            return segment
    if index < len(segments):
        return segments[index]
    return segments[0] if segments else None


def _split_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[。！？；;])\s*|\n+", text or "") if item.strip()]


def _remove_contaminated_sentences(text: str, blocked_terms: set[str]) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return text
    cleaned = [sentence for sentence in sentences if not any(_contains_term(sentence, term) for term in blocked_terms)]
    if not cleaned:
        return ""
    return "".join(cleaned)


def _has_metric_contamination(text: str, segment_content: str) -> bool:
    metric_patterns = [
        r"\d+\s*(?:\+|余|多)?\s*(?:用户|人|访问|UV|PV)",
        r"\d+\s*(?:\+|余|多)?\s*(?:star|stars)",
        r"(?:公网|域名|上线|部署|访问记录)",
    ]
    return any(re.search(pattern, text or "", re.IGNORECASE) and not re.search(pattern, segment_content or "", re.IGNORECASE) for pattern in metric_patterns)


def _allowed_terms(segment) -> set[str]:
    return set(segment.tech_terms + segment.evidence_terms + segment.risk_terms + segment.supported_resume_terms)


def _global_terms(segments: list) -> set[str]:
    result: set[str] = set()
    for segment in segments:
        result.update(segment.tech_terms)
        result.update(term for term in segment.evidence_terms if term not in {"用户", "奖"})
        result.update(segment.risk_terms)
        for term in ["论文", "实验结果", "科研", "排名", "立项", "证书"]:
            if _contains_term(segment.content, term):
                result.add(term)
    return result


def guard_experience_boundaries(payload: schemas.GenerationPayload, raw_input: str) -> schemas.GenerationPayload:
    context = analyze_long_input(raw_input)
    segments = context.segments
    if len(segments) <= 1:
        return payload

    updated = payload.model_copy(deep=True)
    all_terms = _global_terms(segments)
    guarded_projects: list[dict[str, Any]] = []

    for index, project in enumerate(updated.resume_sections.projects):
        guarded = deepcopy(project)
        segment = _match_project_to_segment(guarded, segments, index)
        if not segment:
            guarded_projects.append(guarded)
            continue

        blocked_terms = all_terms - _allowed_terms(segment)
        for key in ["intro", "role"]:
            cleaned = _remove_contaminated_sentences(str(guarded.get(key, "")), blocked_terms)
            if _has_metric_contamination(cleaned, segment.content):
                cleaned = ""
            if cleaned:
                guarded[key] = cleaned
            elif key == "intro":
                guarded[key] = segment.summary
            else:
                guarded[key] = "围绕该段经历完成相关任务，具体职责以用户原文提供的信息为准。"
        details = []
        for detail in guarded.get("details", []) or []:
            detail_text = str(detail)
            if any(_contains_term(detail_text, term) for term in blocked_terms):
                continue
            if _has_metric_contamination(detail_text, segment.content):
                continue
            details.append(detail_text)
        guarded["details"] = _dedupe(details) or guarded.get("details", [])[:1]
        guarded_projects.append(guarded)

    updated.resume_sections.projects = guarded_projects
    return updated
