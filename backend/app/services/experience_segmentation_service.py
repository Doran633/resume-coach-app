import re
from dataclasses import dataclass


SEGMENT_PATTERN = re.compile(
    r"(^|\n)\s*(?:#{1,6}\s*)?"
    r"(?P<label>项目[一二三四五六七八九十\d]*|经历[一二三四五六七八九十\d]*|开源经历|实习经历|比赛经历|校园经历)"
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


def split_experience_segments(raw_input: str, max_segments: int = 8) -> list[ExperienceSegment]:
    text = raw_input.strip()
    if not text:
        return []

    matches = list(SEGMENT_PATTERN.finditer(text))
    if not matches:
        return [ExperienceSegment(label="经历一", title="综合经历", content=text)]

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
    return segments


def build_experience_context(raw_input: str) -> str:
    segments = split_experience_segments(raw_input)
    if not segments:
        return "未识别到有效经历内容。"

    lines = [
        f"系统预解析到 {len(segments)} 段主要经历。该结果只用于帮助分段，不得替代用户事实：",
    ]
    for index, segment in enumerate(segments, start=1):
        preview = re.sub(r"\s+", " ", segment.content).strip()
        if len(preview) > 180:
            preview = preview[:180] + "..."
        lines.append(f"{index}. {segment.label}：{segment.title}；内容摘要：{preview}")
    lines.append("生成时请尽量让每段主要经历分别进入正式简历结构，不要因为输入较长而随意合并或删除。")
    return "\n".join(lines)
