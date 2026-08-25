from dataclasses import dataclass

from .long_input_service import LongInputSegment, analyze_long_input
from .semantic_experience_segmentation_service import segment_semantic_experiences


@dataclass
class ExperienceIdentity:
    experience_id: str
    experience_type: str
    title: str
    raw_text: str
    explicit_tech_terms: list[str]
    explicit_metrics: list[str]
    evidence_terms: list[str]
    risk_terms: list[str]
    supported_inference_terms: list[str]


def _experience_type(segment: LongInputSegment) -> str:
    text = f"{segment.label}\n{segment.title}\n{segment.content}"
    if "实习" in text and not any(pattern in text for pattern in ["没有实习", "无实习", "没实习"]):
        return "实习经历"
    if any(term in text for term in ["科研", "研究", "论文"]):
        return "科研经历"
    if any(term in text for term in ["竞赛", "比赛"]):
        return "竞赛经历"
    if "开源" in text:
        return "开源经历"
    if any(term in text for term in ["校园", "社团", "志愿"]):
        return "校园 / 社团经历"
    return "项目经历"


def build_experience_identities(raw_input: str) -> list[ExperienceIdentity]:
    context = analyze_long_input(raw_input)
    identities: list[ExperienceIdentity] = []
    for segment in context.segments:
        identities.append(
            ExperienceIdentity(
                experience_id=segment.experience_id,
                experience_type=_experience_type(segment),
                title=segment.title,
                raw_text=segment.content,
                explicit_tech_terms=segment.tech_terms,
                explicit_metrics=segment.evidence_terms,
                evidence_terms=segment.evidence_terms,
                risk_terms=segment.risk_terms,
                supported_inference_terms=segment.supported_resume_terms,
            )
        )
    return identities


def build_segmentation_questions(raw_input: str) -> list[str]:
    return segment_semantic_experiences(raw_input).clarification_questions


def build_experience_identity_context(raw_input: str) -> str:
    identities = build_experience_identities(raw_input)
    if not identities:
        return "未识别到有效经历身份。"

    lines = [
        "内部 experience_id 边界表：以下信息只来自用户原文和本地预处理，不得跨 experience_id 借用事实。",
    ]
    for item in identities:
        lines.extend(
            [
                f"{item.experience_id}｜{item.experience_type}｜{item.title}",
                f"原文摘要：{item.raw_text[:220].strip()}",
                f"明确技术词：{'、'.join(item.explicit_tech_terms) if item.explicit_tech_terms else '未识别'}",
                f"指标/证据词：{'、'.join(item.evidence_terms) if item.evidence_terms else '未识别'}",
                f"风险词：{'、'.join(item.risk_terms) if item.risk_terms else '未识别'}",
                f"可自然承接：{'、'.join(item.supported_inference_terms) if item.supported_inference_terms else '无'}",
            ]
        )
    lines.append("生成 resume_sections.projects 时，每个项目必须包含内部字段 source_experience_id，例如 EXP-001。该字段不会展示给用户。")
    return "\n".join(lines)
