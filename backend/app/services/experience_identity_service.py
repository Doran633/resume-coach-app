import re
from dataclasses import dataclass, field

from .long_input_service import LongInputContext, LongInputSegment, analyze_long_input
from .semantic_experience_segmentation_service import (
    infer_project_hierarchy_metadata,
    is_heading_only_text,
    segment_semantic_experiences,
)
from .input_semantic_role_service import analyze_experience_semantics
from .input_claim_resolution_service import resolve_experience_claims


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
    canonical_project_name: str = ""
    project_aliases: list[str] = field(default_factory=list)
    parent_project_name: str = ""
    phase_name: str = ""
    relation_type: str = "independent"
    source_span: tuple[int, int] = (0, 0)
    declared_experience_type: str = ""
    boundary_source: str = "semantic"
    immutable_experience_id: str = ""


def _experience_type(segment: LongInputSegment) -> str:
    if segment.declared_experience_type:
        return segment.declared_experience_type
    text = f"{segment.label}\n{segment.title}\n{segment.content}"
    internship_relation = re.search(
        r"(?:在[^。；\n]{2,50}(?:公司|企业|事务所|研究院)[^。；\n]{0,30}(?:实习|担任)|"
        r"担任[^。；\n]{0,30}实习生|实习期间(?:负责|参与)|作为[^。；\n]{0,40}实习生)",
        text,
    )
    if internship_relation or re.search(r"(?:^|\n)\s*实习经历(?:\s|$|[:：|｜])", text):
        return "实习经历"
    research_relation = re.search(
        r"(?:科研经历|研究经历|课题组|实验室|研究职责|实验研究|论文(?:发表|投稿)|参与课题|负责课题)",
        text,
    )
    if research_relation:
        return "科研经历"
    if any(term in text for term in ["竞赛", "比赛"]):
        return "竞赛经历"
    if "开源" in text:
        return "开源经历"
    if any(term in text for term in ["校园", "社团", "志愿"]):
        return "校园 / 社团经历"
    return "项目经历"


def build_experience_identities(
    raw_input: str,
    *,
    long_input_context: LongInputContext | None = None,
) -> list[ExperienceIdentity]:
    """Build stable identities, optionally reusing a request-scoped input analysis."""
    context = long_input_context or analyze_long_input(raw_input)
    identities: list[ExperienceIdentity] = []
    cursor = 0
    for segment in context.segments:
        if is_heading_only_text(segment.content):
            continue
        hierarchy = infer_project_hierarchy_metadata(segment.title, segment.content)
        if segment.source_span != (0, 0):
            start, end = segment.source_span
        else:
            start = raw_input.find(segment.content, cursor)
            if start < 0:
                start = raw_input.find(segment.content)
            start = max(0, start)
            end = start + len(segment.content)
        cursor = end
        identities.append(
            ExperienceIdentity(
                experience_id=f"EXP-{len(identities) + 1:03d}",
                experience_type=_experience_type(segment),
                title=segment.title,
                raw_text=segment.content,
                explicit_tech_terms=segment.tech_terms,
                explicit_metrics=segment.evidence_terms,
                evidence_terms=segment.evidence_terms,
                risk_terms=segment.risk_terms,
                supported_inference_terms=segment.supported_resume_terms,
                canonical_project_name=str(hierarchy["canonical_project_name"]),
                project_aliases=list(hierarchy["project_aliases"]),
                parent_project_name=str(hierarchy["parent_project_name"]),
                phase_name=str(hierarchy["phase_name"]),
                relation_type=str(hierarchy["relation_type"]),
                source_span=(start, end),
                declared_experience_type=segment.declared_experience_type,
                boundary_source=segment.boundary_source,
                immutable_experience_id=f"EXP-{len(identities) + 1:03d}",
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
        "以下为系统内部检索摘要，长度裁剪不代表用户原文缺失。不得将省略号或截断提示写入正式简历。",
    ]
    for item in identities:
        semantic = resolve_experience_claims(item.experience_id, item.raw_text, item.source_span[0])
        fact_preview = "；".join(claim.text for claim in semantic.eligible_claims)
        constraints = [claim.semantic_role for claim in [*semantic.excluded_claims, *semantic.withheld_claims]]
        lines.extend(
            [
                f"{item.experience_id}｜{item.declared_experience_type or item.experience_type}｜{item.title}",
                f"边界来源：{item.boundary_source}；该 ID 为固定 Slot，不得交换或重排。",
                f"项目层级：{item.relation_type}｜主项目：{item.canonical_project_name or item.title}"
                + (f"｜阶段/模块：{item.phase_name}" if item.phase_name else ""),
                f"可输出事实摘要：{_semantic_preview(fact_preview, 220)}",
                f"内部约束类型：{'、'.join(dict.fromkeys(constraints)) if constraints else '无'}（不得写入正文）",
                f"明确技术词：{'、'.join(item.explicit_tech_terms) if item.explicit_tech_terms else '未识别'}",
                f"指标/证据词：{'、'.join(item.evidence_terms) if item.evidence_terms else '未识别'}",
                f"风险词：{'、'.join(item.risk_terms) if item.risk_terms else '未识别'}",
                f"可自然承接：{'、'.join(item.supported_inference_terms) if item.supported_inference_terms else '无'}",
            ]
        )
    lines.append("生成 resume_sections.projects 时，只能填写上述固定 Slot，并保留其 source_experience_id；不得创建、交换或重排 ID。")
    return "\n".join(lines)


def _semantic_preview(text: str, limit: int) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    candidates = [match.end() for match in re.finditer(r"[。！？；;.!?]", compact[: limit + 1])]
    end = candidates[-1] if candidates and candidates[-1] >= limit // 2 else limit
    return compact[:end].rstrip("，、：: ") + "（内部摘要结束）"
