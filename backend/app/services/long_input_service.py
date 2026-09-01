import re
from dataclasses import dataclass

from .experience_segmentation_service import ExperienceSegment, split_experience_segments
from .supported_inference_service import build_supported_inference_context


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
    "CodeBuddy",
    "虚拟机",
    "LoRa",
    "地磁传感器",
    "地图 API",
    "SSL",
    "Token",
    "回归分析",
    "线性回归",
    "多项式回归",
    "模型效果对比",
    "数据可视化",
    "智能制图",
    "地图API",
    "路线规划",
]

EVIDENCE_TERMS = ["上线", "部署", "公网", "域名", "日志", "用户", "star", "GitHub", "访问记录", "测试集", "评测指标", "奖", "排名", "立项", "答辩", "证书"]
RISK_TERMS = ["高并发", "企业级", "生产级", "核心算法", "模型训练", "微调", "SFT", "RLHF", "DPO", "LoRA", "实时并发"]


@dataclass
class LongInputSegment:
    experience_id: str
    label: str
    title: str
    content: str
    summary: str
    tech_terms: list[str]
    evidence_terms: list[str]
    risk_terms: list[str]
    supported_resume_terms: list[str]
    supported_interview_terms: list[str]
    supported_wordings: list[str]
    declared_experience_type: str = ""
    boundary_source: str = "semantic"
    source_span: tuple[int, int] = (0, 0)


@dataclass
class LongInputContext:
    long_input_mode: bool
    raw_input_length: int
    line_count: int
    segment_count: int
    compact_context: str
    raw_input_for_prompt: str
    estimated_token_saving_hint: str
    segments: list[LongInputSegment]


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


def enrich_segments(segments: list[ExperienceSegment]) -> list[LongInputSegment]:
    enriched: list[LongInputSegment] = []
    for index, segment in enumerate(segments, start=1):
        inference = build_supported_inference_context(segment.content)
        enriched.append(
            LongInputSegment(
                experience_id=f"EXP-{index:03d}",
                label=segment.label,
                title=segment.title,
                content=segment.content,
                summary=compact_text(segment.content, 210),
                tech_terms=extract_terms(segment.content, TECH_TERMS),
                evidence_terms=extract_terms(segment.content, EVIDENCE_TERMS),
                risk_terms=extract_terms(segment.content, RISK_TERMS),
                supported_resume_terms=inference.resume_terms,
                supported_interview_terms=inference.interview_terms,
                supported_wordings=inference.wordings,
                declared_experience_type=segment.declared_experience_type,
                boundary_source=segment.boundary_source,
                source_span=segment.source_span,
            )
        )
    return enriched


def build_compact_context(segments: list[LongInputSegment]) -> str:
    lines = [f"系统本地预处理识别到 {len(segments)} 段主要经历。以下摘要只来自用户原文，不包含编造信息："]
    lines.append("经历边界规则：每段经历只能使用本段 experience_id 下的事实；禁止把其他 experience_id 的技术、数据、成果写入本段经历。")
    for segment in segments:
        lines.extend(
            [
                f"{segment.experience_id}. 类型/标题：{segment.declared_experience_type or segment.label}｜{segment.title}",
                f"   边界来源：{segment.boundary_source}",
                f"   摘要：{segment.summary}",
                f"   本段明确技术词：{'、'.join(segment.tech_terms) if segment.tech_terms else '未识别'}",
                f"   本段结果/证据词：{'、'.join(segment.evidence_terms) if segment.evidence_terms else '未识别'}",
                f"   本段风险词：{'、'.join(segment.risk_terms) if segment.risk_terms else '未识别'}",
                f"   本段可写入简历的自然承接知识：{'、'.join(segment.supported_resume_terms) if segment.supported_resume_terms else '无'}",
                f"   本段需要面试补齐的承接知识：{'、'.join(segment.supported_interview_terms) if segment.supported_interview_terms else '无'}",
            ]
        )
    return "\n".join(lines)


def analyze_long_input(raw_input: str, write_segmentation_log: bool = False, stage: str = "unknown") -> LongInputContext:
    raw_input = raw_input or ""
    if write_segmentation_log:
        from .semantic_experience_segmentation_service import segment_semantic_experiences

        segment_semantic_experiences(raw_input, write_log=True, stage=stage)
    segments = enrich_segments(split_experience_segments(raw_input))
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
