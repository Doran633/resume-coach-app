import re

from .. import schemas
from .long_input_service import EVIDENCE_TERMS, RISK_TERMS, TECH_TERMS, LongInputContext, compact_text, extract_terms


def _infer_meta(label: str, content: str) -> str:
    text = f"{label}\n{content}"
    if "实习" in text:
        return "实习经历"
    if "科研" in text or "研究" in text or "论文" in text:
        return "科研经历"
    if "竞赛" in text or "比赛" in text:
        return "竞赛经历"
    if "开源" in text:
        return "开源经历"
    if "校园" in text or "社团" in text or "志愿" in text:
        return "校园 / 社团经历"
    return "项目经历"


def _split_details(content: str, limit: int = 5) -> list[str]:
    normalized = re.sub(r"\s+", " ", content).strip()
    parts = re.split(r"(?<=[。！？；])\s*|[，,]\s*", normalized)
    details: list[str] = []
    for part in parts:
        item = part.strip(" -•\t")
        if len(item) >= 8 and item not in details:
            details.append(item)
        if len(details) >= limit:
            break
    return details or [compact_text(content, 160)]


def _role_for_meta(meta: str) -> str:
    if meta == "实习经历":
        return "围绕实习任务参与功能开发、联调排查、文档整理或需求验收，具体职责以用户已提供内容为准。"
    if meta == "科研经历":
        return "围绕研究目标参与资料整理、方案设计、实验记录或报告撰写，突出方法理解和过程沉淀。"
    if meta == "竞赛经历":
        return "围绕竞赛目标参与方案设计、材料整理、展示答辩或功能实现，突出个人贡献与交付结果。"
    if meta == "开源经历":
        return "围绕开源项目参与问题修复、文档完善、功能贡献或工具沉淀，突出可核验贡献。"
    return "围绕项目目标参与功能设计、技术实现、联调排查和结果交付。"


def _build_claims(risk_terms: list[str], evidence_terms: list[str]) -> list[schemas.ClaimResult]:
    claims: list[schemas.ClaimResult] = []
    for term in risk_terms[:4]:
        claims.append(
            schemas.ClaimResult(
                claim=term,
                risk_level="yellow" if term in evidence_terms else "red",
                evidence="用户原文中出现相关风险词，需结合事实证据判断使用强度。",
                risk_reason="该表达在面试中容易被追问具体实现、指标口径或个人贡献边界。",
                interview_questions=[f"{term} 的事实依据是什么？", "你具体负责了哪些部分？"],
                knowledge_to_prepare=[term, "证据材料", "降级表达"],
                downgrade_wording=f"准备不足时建议降低为与 {term} 相关的参与或探索经历。",
            )
        )
    if not claims:
        claims.append(
            schemas.ClaimResult(
                claim="职责边界与结果证据",
                risk_level="yellow",
                evidence="长输入稳定模式基于用户原文生成，需要用户补充更明确的证据材料。",
                risk_reason="职责和结果表达可以增强，但需要能讲清个人贡献、证据和项目边界。",
                interview_questions=["你具体负责了哪些模块？", "有哪些日志、截图、仓库或文档可以证明？"],
                knowledge_to_prepare=["项目结构", "职责边界", "证据口径"],
                downgrade_wording="参与相关模块开发、联调或材料整理。",
            )
        )
    return claims[:8]


def build_stable_generation_fallback(request: schemas.GenerateRequest, context: LongInputContext) -> schemas.GenerationPayload:
    all_tech: list[str] = []
    all_evidence: list[str] = []
    all_risks: list[str] = []
    projects: list[dict] = []

    for segment in context.segments[:5]:
        tech_terms = extract_terms(segment.content, TECH_TERMS)
        evidence_terms = extract_terms(segment.content, EVIDENCE_TERMS)
        risk_terms = extract_terms(segment.content, RISK_TERMS)
        for target, values in [(all_tech, tech_terms), (all_evidence, evidence_terms), (all_risks, risk_terms)]:
            for value in values:
                if value not in target:
                    target.append(value)
        meta = _infer_meta(segment.label, segment.content)
        projects.append(
            {
                "name": segment.title,
                "meta": meta,
                "time": "[待填写]",
                "intro": compact_text(segment.content, 180),
                "role": _role_for_meta(meta),
                "details": _split_details(segment.content, limit=5),
            }
        )

    if not projects:
        projects.append(
            {
                "name": "综合经历",
                "meta": "综合经历",
                "time": "[待填写]",
                "intro": compact_text(request.raw_input, 180),
                "role": "基于用户原始经历整理项目目标、职责边界和技术动作。",
                "details": _split_details(request.raw_input, limit=5),
            }
        )

    project_names = "、".join(project["name"] for project in projects[:3])
    normal = f"稳定模式已根据用户原文识别并保留主要经历：{project_names}。建议围绕目标岗位整理项目定位、个人职责、技术动作和结果证据。"
    bold = f"可将这些经历包装为面向{request.target_role}的连续实践：突出多段经历中的技术链路、问题排查、交付结果和可面试承接的证据材料。"
    boundary = "边界参考：未提供的学校、专业、用户数、并发、奖项、模型训练等硬事实不能补写；缺少证据的强表达应降级。"
    recommended = f"{normal}\n{bold}"

    return schemas.GenerationPayload(
        completeness_score=72 if context.long_input_mode else 64,
        confirmed_facts=["系统基于用户原文识别出主要经历", f"识别到 {context.segment_count} 段经历"],
        missing_questions=["每段经历的时间、个人贡献边界和证据材料可以继续补充。"],
        normal_version=normal,
        bold_version=bold,
        boundary_version=boundary,
        recommended_version=recommended,
        claims=_build_claims(all_risks, all_evidence),
        interview_plan=[
            "准备每段经历的背景、目标、个人职责和交付结果。",
            "为强表达准备截图、日志、仓库、文档或证书等证据。",
            "准备一段真实问题排查或方案取舍案例。",
        ][:6],
        knowledge_checklist=(all_tech + ["职责边界", "证据材料", "面试降级表达"])[:10],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]", "邮箱": "[待填写]", "手机号": "[待填写]", "求职意向": request.target_role},
            summary=["具备多段真实经历，可围绕目标岗位整理为项目、实习、科研或竞赛实践。"],
            skills=all_tech[:10],
            projects=projects,
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            interview_preparation=["逐段准备职责边界、技术细节、证据材料和降级表达。"],
        ),
    )
