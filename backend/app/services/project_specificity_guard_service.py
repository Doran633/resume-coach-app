import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from .. import schemas
from .long_input_service import analyze_long_input, compact_text


TEMPLATE_PHRASES = [
    ["文档解析", "切块", "Embedding", "向量检索", "回答生成"],
    ["Top-K", "Retrieval", "Chunk", "Embedding"],
    ["接口联调", "异常处理", "数据流转"],
    ["组件化", "状态管理", "表单校验"],
]


@dataclass
class TextItem:
    project_index: int
    field: str
    text: str
    detail_index: int | None = None


def _normalize(text: str) -> str:
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", text or "").lower()


def _contains(text: str, keyword: str) -> bool:
    return bool(re.search(re.escape(keyword), text or "", re.IGNORECASE))


def _split_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[。！？；;])\s*|\n+", text or "") if item.strip()]


def _phrase_hit(text: str) -> str | None:
    normalized = _normalize(text)
    for phrase in TEMPLATE_PHRASES:
        hits = [term for term in phrase if _normalize(term) in normalized]
        if len(hits) >= min(3, len(phrase)):
            return "|".join(phrase)
    return None


def _is_duplicate(left: str, right: str) -> bool:
    left_norm = _normalize(left)
    right_norm = _normalize(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm and min(len(left_norm), len(right_norm)) >= 10:
        return True
    if min(len(left_norm), len(right_norm)) >= 18 and SequenceMatcher(None, left_norm, right_norm).ratio() >= 0.86:
        return True
    left_phrase = _phrase_hit(left)
    return bool(left_phrase and left_phrase == _phrase_hit(right))


def _fallback_detail(project: dict[str, Any], segment) -> str:
    meta = str(project.get("meta", ""))
    name = str(project.get("name", "") or (segment.title if segment else ""))
    content = "\n".join(filter(None, [segment.title, segment.content])) if segment else ""
    if _contains(content, "RAG") or _contains(content, "检索") or _contains(content, "文档问答") or _contains(content, "知识库"):
        if any(_contains(content, keyword) for keyword in ["测试集", "评测", "Benchmark", "Recall", "Groundedness"]):
            return "围绕测试样例、Top-K、Recall 和 Groundedness 指标整理 RAG 效果验证思路。"
        if any(_contains(content, keyword) for keyword in ["部署", "公网", "域名", "Nginx", "systemd", "上线"]):
            return "围绕服务部署、访问链路、日志排查和健康检查完善 RAG 应用上线验证。"
        return "围绕资料解析、向量检索、上下文组织和回答依据完善 RAG 问答流程。"
    if "实习" in meta:
        return f"围绕{name or '实习任务'}参与功能开发、接口联调、缺陷修复和需求验收。"
    if "科研" in meta or "研究" in meta or "论文" in meta:
        return f"围绕{name or '研究主题'}参与资料整理、实验记录、结果分析和阶段汇报。"
    if "竞赛" in meta or "比赛" in meta:
        return f"围绕{name or '赛题目标'}参与方案设计、材料整理、展示答辩和结果复盘。"
    if "开源" in meta:
        return f"围绕{name or '开源项目'}参与问题修复、文档完善、提交记录和协作流程。"
    if "校园" in meta or "社团" in meta or "志愿" in meta:
        return f"围绕{name or '活动目标'}参与组织执行、材料沉淀和结果复盘。"
    return f"围绕{name or '项目目标'}完成核心功能拆解、技术实现和结果验证。"


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


def _relevance_score(item: TextItem, project: dict[str, Any], segment) -> int:
    text = item.text
    segment_content = segment.content if segment else ""
    score = 0
    for term in ["RAG", "检索", "文档问答", "Embedding", "向量", "接口", "联调", "React", "Vue", "表单", "测试集", "评测", "部署", "Nginx", "systemd"]:
        if _contains(text, term) and _contains(segment_content, term):
            score += 3
        elif _contains(text, term) and not _contains(segment_content, term):
            score -= 3
    name = str(project.get("name", ""))
    if name and any(part and part in text for part in re.split(r"\s+|[｜|:：\-—–]", name)):
        score += 1
    if item.field == "details":
        score += 1
    return score


def _collect_items(projects: list[dict[str, Any]]) -> list[TextItem]:
    items: list[TextItem] = []
    for project_index, project in enumerate(projects):
        for field in ["intro", "role"]:
            for sentence in _split_sentences(str(project.get(field, ""))):
                if len(_normalize(sentence)) >= 18 or _phrase_hit(sentence):
                    items.append(TextItem(project_index, field, sentence))
        for detail_index, detail in enumerate(project.get("details", []) or []):
            text = str(detail).strip()
            if text and (len(_normalize(text)) >= 10 or _phrase_hit(text)):
                items.append(TextItem(project_index, "details", text, detail_index))
    return items


def _duplicate_groups(items: list[TextItem]) -> list[list[int]]:
    groups: list[list[int]] = []
    used: set[int] = set()
    for index, item in enumerate(items):
        if index in used:
            continue
        group = [index]
        for other_index in range(index + 1, len(items)):
            if items[other_index].project_index == item.project_index:
                continue
            if _is_duplicate(item.text, items[other_index].text):
                group.append(other_index)
        if len(group) > 1:
            groups.append(group)
            used.update(group)
    return groups


def _remove_text_from_project(project: dict[str, Any], item: TextItem) -> None:
    if item.field == "details":
        details = [str(detail) for detail in project.get("details", []) or []]
        project["details"] = [detail for detail in details if detail != item.text]
        return

    sentences = _split_sentences(str(project.get(item.field, "")))
    remaining = [sentence for sentence in sentences if sentence != item.text]
    project[item.field] = "".join(remaining)


def _ensure_minimum_details(project: dict[str, Any], segment) -> None:
    details = [str(detail).strip() for detail in project.get("details", []) or [] if str(detail).strip()]
    if details:
        project["details"] = details
        return
    if segment and segment.summary:
        project["details"] = [compact_text(segment.summary, 140)]
    else:
        project["details"] = [_fallback_detail(project, segment)]


def guard_project_specificity(payload: schemas.GenerationPayload, raw_input: str) -> schemas.GenerationPayload:
    projects = payload.resume_sections.projects
    if len(projects) <= 1:
        return payload

    updated = payload.model_copy(deep=True)
    context = analyze_long_input(raw_input)
    segments = [_match_project_to_segment(project, context.segments, index) for index, project in enumerate(updated.resume_sections.projects)]
    items = _collect_items(updated.resume_sections.projects)

    for group in _duplicate_groups(items):
        best_index = max(
            group,
            key=lambda item_index: _relevance_score(items[item_index], updated.resume_sections.projects[items[item_index].project_index], segments[items[item_index].project_index]),
        )
        for item_index in group:
            if item_index == best_index:
                continue
            item = items[item_index]
            project = updated.resume_sections.projects[item.project_index]
            detail_count = len(project.get("details", []) or [])
            _remove_text_from_project(project, item)
            if item.field == "details" and detail_count <= 1:
                fallback = _fallback_detail(project, segments[item.project_index])
                if fallback not in project.get("details", []):
                    project.setdefault("details", []).append(fallback)

    for index, project in enumerate(updated.resume_sections.projects):
        _ensure_minimum_details(project, segments[index] if index < len(segments) else None)

    return updated
