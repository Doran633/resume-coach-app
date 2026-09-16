import re
from dataclasses import dataclass

from .semantic_experience_segmentation_service import (
    ExplicitExperienceBoundary,
    SemanticSegmentationResult,
    segment_semantic_experiences,
)


@dataclass
class ExperienceSegment:
    label: str
    title: str
    content: str
    declared_experience_type: str = ""
    boundary_source: str = "semantic"
    source_span: tuple[int, int] = (0, 0)
    source_boundary: ExplicitExperienceBoundary | None = None


def split_experience_segments(
    raw_input: str,
    max_segments: int | None = None,
    *,
    segmentation_result: SemanticSegmentationResult | None = None,
) -> list[ExperienceSegment]:
    """Adapt one partition; explicit legacy limits fail instead of losing input."""
    semantic = segmentation_result if segmentation_result is not None else segment_semantic_experiences(raw_input)
    if max_segments is not None and len(semantic.segments) > max_segments:
        raise ValueError("Experience partition exceeds the caller's explicit segment limit")
    return [ExperienceSegment(
        label=item.source_label or item.declared_experience_type or item.experience_type,
        title=item.title,
        content=item.raw_text,
        declared_experience_type=item.declared_experience_type,
        boundary_source=item.boundary_source,
        source_span=(item.start_offset, item.end_offset),
        source_boundary=item.source_boundary,
    ) for item in semantic.segments]


def build_experience_context(raw_input: str) -> str:
    segments = split_experience_segments(raw_input)
    if not segments:
        return "未识别到有效经历内容。"

    lines = [
        f"系统预解析到 {len(segments)} 段主要经历。该结果只用于帮助分段，不得替代用户事实：",
        "以下为系统内部检索摘要，长度裁剪不代表用户原文缺失。不得将省略号或截断提示写入正式简历。",
    ]
    for index, segment in enumerate(segments, start=1):
        preview = re.sub(r"\s+", " ", segment.content).strip()
        if len(preview) > 180:
            boundaries = [match.end() for match in re.finditer(r"[。！？；;.!?]", preview[:181])]
            end = boundaries[-1] if boundaries and boundaries[-1] >= 90 else 180
            preview = preview[:end].rstrip("，、：: ") + "（内部摘要结束）"
        lines.append(f"{index}. {segment.label}：{segment.title}；内容摘要：{preview}")
    lines.append("生成时请尽量让每段主要经历分别进入正式简历结构，不要因为输入较长而随意合并或删除。")
    return "\n".join(lines)
