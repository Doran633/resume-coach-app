import re
from dataclasses import dataclass

from .semantic_experience_segmentation_service import segment_semantic_experiences


SEGMENT_PATTERN = re.compile(
    r"(^|\n)\s*(?:#{1,6}\s*)?"
    r"(?P<label>项目[一二三四五六七八九十\d]*|项目经历|经历[一二三四五六七八九十\d]*|实习经历|科研经历|研究经历|论文经历|竞赛经历|比赛经历|开源经历|校园经历|社团经历|志愿经历)"
    r"\s*(?:[:：|｜\-—–]\s*)",
    re.MULTILINE,
)


@dataclass
class ExperienceSegment:
    label: str
    title: str
    content: str


def _clean_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" #|-—–｜:：\t")


def _infer_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        title = _clean_line(line)
        if 2 <= len(title) <= 60:
            return title
    return fallback


def _title_subject(text: str) -> str:
    value = re.sub(
        r"^(?:我(?:曾经)?做过(?:一个)?|我做了(?:一个)?|我独立(?:完成|开发|设计)了?|"
        r"独立(?:完成|开发|设计)|设计并开发|项目[一二三四五六七八九十\d]+)\s*",
        "", _clean_line(text), flags=re.IGNORECASE,
    )
    value = re.sub(r"(?:个人项目|课程项目|项目经历|项目)\s*$", "", value).strip()
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", value).lower()


def _redistribute_explicit_title_mentions(segments: list[ExperienceSegment]) -> list[ExperienceSegment]:
    """Move a detached supplement only when it names another full project title."""
    if len(segments) < 2:
        return segments
    subjects = [_title_subject(segment.title) for segment in segments]
    additions: dict[int, list[str]] = {}
    for current_index, segment in enumerate(segments):
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n+", segment.content) if item.strip()]
        kept: list[str] = []
        for paragraph_index, paragraph in enumerate(paragraphs):
            normalized = _title_subject(paragraph)
            matches = [
                index for index, subject in enumerate(subjects)
                if index != current_index and len(subject) >= 5 and subject in normalized
            ]
            if paragraph_index > 0 and len(matches) == 1 and subjects[current_index] not in normalized:
                additions.setdefault(matches[0], []).append(paragraph)
            else:
                kept.append(paragraph)
        segment.content = "\n\n".join(kept)
    for index, rows in additions.items():
        segments[index].content = "\n\n".join([segments[index].content, *rows]).strip()
    return segments


def split_experience_segments(raw_input: str, max_segments: int = 8) -> list[ExperienceSegment]:
    text = raw_input.strip()
    if not text:
        return []

    matches = list(SEGMENT_PATTERN.finditer(text))
    if not matches:
        semantic = segment_semantic_experiences(text)
        return [
            ExperienceSegment(label=item.experience_type, title=item.title, content=item.raw_text)
            for item in semantic.segments[:max_segments]
        ]

    segments: list[ExperienceSegment] = []
    for index, match in enumerate(matches[:max_segments]):
        label = match.group("label")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if not content:
            continue
        title = _infer_title(content, label)
        segments.append(ExperienceSegment(label=label, title=title, content=content))
    return _redistribute_explicit_title_mentions(segments)


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
