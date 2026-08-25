import re
from dataclasses import dataclass

from .experience_segmentation_service import ExperienceSegment, split_experience_segments


TECH_TERMS = [
    "React",
    "Vue",
    "TypeScript",
    "JavaScript",
    "Python",
    "FastAPI",
    "Flask",
    "Spring",
    "SQLite",
    "MySQL",
    "Redis",
    "Docker",
    "Nginx",
    "systemd",
    "RAG",
    "Agent",
    "LangChain",
    "LangGraph",
    "Embedding",
    "BAAI",
    "bge-m3",
    "FAISS",
    "Chroma",
    "Pandas",
    "NumPy",
    "Matplotlib",
    "PyTorch",
    "TensorFlow",
]

EVIDENCE_TERMS = ["上线", "部署", "公网", "域名", "日志", "用户", "star", "GitHub", "访问记录", "测试集", "评测指标", "奖", "排名", "立项", "答辩", "证书"]
RISK_TERMS = ["高并发", "企业级", "生产级", "核心算法", "模型训练", "微调", "SFT", "RLHF", "DPO", "LoRA", "实时并发"]


@dataclass
class LongInputContext:
    long_input_mode: bool
    raw_input_length: int
    line_count: int
    segment_count: int
    compact_context: str
    raw_input_for_prompt: str
    estimated_token_saving_hint: str
    segments: list[ExperienceSegment]


def extract_terms(text: str, terms: list[str]) -> list[str]:
    found: list[str] = []
    for term in terms:
        if re.search(re.escape(term), text, re.IGNORECASE) and term not in found:
            found.append(term)
    return found


def compact_text(text: str, limit: int = 200) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip("，,。；; ") + "..."


def _line_count(raw_input: str) -> int:
    return len([line for line in raw_input.splitlines() if line.strip()])


def build_compact_context(segments: list[ExperienceSegment]) -> str:
    lines = [f"系统本地预处理识别到 {len(segments)} 段主要经历。以下摘要只来自用户原文，不包含编造信息："]
    for index, segment in enumerate(segments, start=1):
        tech_terms = extract_terms(segment.content, TECH_TERMS)
        evidence_terms = extract_terms(segment.content, EVIDENCE_TERMS)
        risk_terms = extract_terms(segment.content, RISK_TERMS)
        lines.extend(
            [
                f"{index}. 类型/标题：{segment.label}｜{segment.title}",
                f"   摘要：{compact_text(segment.content, 210)}",
                f"   技术词：{'、'.join(tech_terms) if tech_terms else '未识别'}",
                f"   结果/证据词：{'、'.join(evidence_terms) if evidence_terms else '未识别'}",
                f"   风险词：{'、'.join(risk_terms) if risk_terms else '未识别'}",
            ]
        )
    return "\n".join(lines)


def analyze_long_input(raw_input: str) -> LongInputContext:
    raw_input = raw_input or ""
    segments = split_experience_segments(raw_input)
    raw_input_length = len(raw_input)
    line_count = _line_count(raw_input)
    segment_count = len(segments)
    long_input_mode = raw_input_length > 1800 or segment_count >= 3 or line_count > 25
    compact_context = build_compact_context(segments)
    if long_input_mode:
        raw_input_for_prompt = compact_context
        saving = "长输入模式：prompt 使用本地摘要，避免把完整长原文重复发送给模型。"
    else:
        raw_input_for_prompt = raw_input
        saving = "短输入模式：保留原始输入。"
    return LongInputContext(
        long_input_mode=long_input_mode,
        raw_input_length=raw_input_length,
        line_count=line_count,
        segment_count=segment_count,
        compact_context=compact_context,
        raw_input_for_prompt=raw_input_for_prompt,
        estimated_token_saving_hint=saving,
        segments=segments,
    )
