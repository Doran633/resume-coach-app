import re

from .. import schemas
from .experience_identity_service import build_segmentation_questions
from .experience_fact_ledger_service import build_experience_fact_ledger
from .long_input_service import EVIDENCE_TERMS, RISK_TERMS, TECH_TERMS, LongInputContext, compact_text, extract_terms
from .resume_role_resolution_service import resolve_role_for_experience
from .resume_experience_entity_dedup_service import deduplicate_resume_experience_entities
from .resume_experience_validity_service import ensure_resume_experience_validity, is_valid_fallback_candidate


NEGATIVE_INTERNSHIP_PATTERNS = ["没有实习", "无实习", "没实习", "没有实习经历", "没有实习经验"]
POSITIVE_INTERNSHIP_PATTERNS = ["实习经历：", "实习经历:", "实习｜", "实习|", "前端开发实习", "后端开发实习", "测试开发实习", "产品实习", "运营实习", "在公司", "某公司", "公司实习", "企业实习"]
RESUME_BODY_NOISE_PATTERNS = ["我是大二学生", "我是大三学生", "我是大一学生", "想投", "没有实习", "无实习", "没实习", "没有上线", "未上线", "没有真实用户", "没有用户", "没有获奖", "未获奖"]


def _infer_meta(label: str, content: str) -> str:
    text = f"{label}\n{content}"
    no_internship = any(pattern in text for pattern in NEGATIVE_INTERNSHIP_PATTERNS)
    has_positive_internship = any(pattern in text for pattern in POSITIVE_INTERNSHIP_PATTERNS)
    if "实习" in text and not no_internship and has_positive_internship:
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
        if any(pattern in item for pattern in RESUME_BODY_NOISE_PATTERNS):
            continue
        if len(item) >= 8 and item not in details:
            details.append(item)
        if len(details) >= limit:
            break
    return details or [compact_text(content, 160)]


def _intro_from_content(content: str) -> str:
    details = _split_details(content, limit=2)
    return compact_text("。".join(details), 180)


def _wording_key(text: str) -> str:
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", text or "").lower()


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
    all_interview_terms: list[str] = []
    projects: list[dict] = []
    used_supported_wordings: set[str] = set()
    rejected_candidates = 0
    ledger = build_experience_fact_ledger(request.raw_input)

    for segment in context.segments[:5]:
        tech_terms = segment.tech_terms
        evidence_terms = segment.evidence_terms
        risk_terms = segment.risk_terms
        for target, values in [(all_tech, tech_terms), (all_evidence, evidence_terms), (all_risks, risk_terms)]:
            for value in values:
                if value not in target:
                    target.append(value)
        for value in segment.supported_interview_terms:
            if value not in all_interview_terms:
                all_interview_terms.append(value)
        meta = segment.declared_experience_type or _infer_meta(segment.label, segment.content)
        local_facts = [
            fact for fact in ledger.for_experience(segment.experience_id)
            if fact.resume_eligible and fact.resume_ready_text
        ]
        details = [fact.resume_ready_text for fact in local_facts[:5]]
        if not details:
            rejected_candidates += 1
            continue
        role, role_fact_ids = resolve_role_for_experience(
            request.raw_input, segment.experience_id, details=details, intro=details[0], ledger=ledger,
        )
        candidate = {
                "name": segment.title,
                "meta": meta,
                "time": "[待填写]",
                "intro": details[0],
                "role": role,
                "details": details[:5],
                "source_experience_id": segment.experience_id,
                "immutable_source_experience_id": segment.experience_id,
                "source_binding_origin": "stable_local_fact_fallback",
                "source_binding_confidence": 1.0,
                "source_binding_locked": True,
                "source_fact_ids": [fact.fact_id for fact in local_facts[:5]],
                "detail_fact_ids": [[fact.fact_id] for fact in local_facts[:5]],
                "role_source_fact_ids": role_fact_ids,
            }
        if is_valid_fallback_candidate(candidate, request.raw_input):
            projects.append(candidate)
        else:
            rejected_candidates += 1

    project_names = "、".join(project["name"] for project in projects[:3])
    normal = (
        f"稳定模式已识别并保留主要经历：{project_names}。建议围绕目标岗位整理项目定位、个人职责、技术动作和结果证据。"
        if project_names else "当前输入尚未形成可安全写入正式简历的完整经历，请补充职责、技术动作或结果证据。"
    )
    bold = f"可将这些经历包装为面向{request.target_role}的连续实践：突出多段经历中的技术链路、问题排查、交付结果和可面试承接的证据材料。"
    boundary = "边界参考：未提供的学校、专业、用户数、并发、奖项、模型训练等硬事实不能补写；缺少证据的强表达应降级。"
    recommended = f"{normal}\n{bold}"

    segmentation_questions = build_segmentation_questions(request.raw_input)
    payload = schemas.GenerationPayload(
        completeness_score=72 if context.long_input_mode else 64,
        confirmed_facts=["系统基于用户原文识别出主要经历", f"识别到 {context.segment_count} 段经历"],
        missing_questions=(segmentation_questions + [
            "每段经历的时间、个人贡献边界和证据材料可以继续补充。",
            *(["检测到仅含标题或元数据的片段，请补充该经历的职责、技术动作或结果证据。"] if rejected_candidates else []),
        ])[:8],
        normal_version=normal,
        bold_version=bold,
        boundary_version=boundary,
        recommended_version=recommended,
        claims=_build_claims(all_risks, all_evidence),
        interview_plan=[
            "准备每段经历的背景、目标、个人职责和交付结果。",
            "为强表达准备截图、日志、仓库、文档或证书等证据。",
            "准备一段真实问题排查或方案取舍案例。",
            f"补齐自然承接知识：{'、'.join(all_interview_terms[:8])}。" if all_interview_terms else "补齐每段经历对应的技术概念和面试解释口径。",
        ][:6],
        knowledge_checklist=(all_tech + all_interview_terms + ["职责边界", "证据材料", "面试降级表达"])[:10],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]", "邮箱": "[待填写]", "手机号": "[待填写]", "求职意向": request.target_role},
            summary=["具备多段真实经历，可围绕目标岗位整理为项目、科研、竞赛或校园实践。"],
            skills=all_tech[:10],
            projects=projects,
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
            interview_preparation=["逐段准备职责边界、技术细节、证据材料和降级表达。"],
        ),
    )
    payload = deduplicate_resume_experience_entities(
        payload,
        request.raw_input,
        stage="stable_fallback",
    )
    return ensure_resume_experience_validity(
        payload,
        request.raw_input,
        stage="stable_fallback",
        fallback_candidate_rejected_count=rejected_candidates,
    )
