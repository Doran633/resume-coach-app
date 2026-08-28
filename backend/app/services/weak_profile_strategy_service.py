import re
from copy import deepcopy

from .. import schemas
from .resume_summary_quality_service import build_grounded_summary_candidates
from .long_input_service import EVIDENCE_TERMS, TECH_TERMS, analyze_long_input
from .experience_fact_ledger_service import build_experience_fact_ledger
from .experience_identity_service import build_experience_identities


WEAK_EXPERIENCE_TERMS = [
    "课程项目",
    "大作业",
    "课设",
    "课程设计",
    "小项目",
    "作业",
    "课堂项目",
    "学生工作",
    "学生会",
    "社团",
    "班委",
    "竞赛参与",
    "比赛参与",
]

STRONG_FACT_TERMS = [
    "实习",
    "工作",
    "公司",
    "企业",
    "上线",
    "部署",
    "公网",
    "域名",
    "用户",
    "star",
    "stars",
    "访问",
    "并发",
    "奖",
    "排名",
    "名次",
    "证书",
    "立项",
]

FORBIDDEN_STRONG_PHRASES = [
    "企业级经验",
    "企业级项目",
    "企业级实战",
    "生产经验",
    "生产级业务系统",
    "真实生产系统",
    "公司级项目",
    "大型线上系统",
    "高并发系统",
]

AWARD_PHRASES = ["一等奖", "二等奖", "三等奖", "优秀奖", "冠军", "亚军", "季军", "获奖", "排名"]

NEGATIVE_RESUME_PHRASES = [
    ("没有实习经历", ""),
    ("没有实习", ""),
    ("无实习", ""),
    ("没有上线", ""),
    ("未上线", ""),
    ("没有真实用户", ""),
    ("没有用户", ""),
    ("没有获奖", ""),
    ("未获奖", ""),
    ("没什么奖项", ""),
    ("只是课程作业", "课程项目"),
    ("只是作业", "课程项目"),
    ("简单小项目", "个人项目实践"),
    ("简单项目", "个人项目实践"),
    ("写了几个页面", "参与核心页面开发与交互流程实现"),
    ("调了一些接口", "完成接口联调与数据流转校验"),
]

WEAK_PROFILE_QUESTIONS = [
    "项目是否有课程评分、演示记录或 GitHub 仓库？",
    "是否能补充技术栈、模块分工、遇到的问题和解决过程？",
    "是否有截图、文档、答辩 PPT、实验报告或复盘材料？",
    "竞赛是否有奖项、排名、证书或立项材料？",
    "学生工作中是否有活动规模、参与人数、成果材料或复盘文档？",
]

WEAK_PROFILE_INTERVIEW_PLAN = [
    "把课程项目讲成完整项目：准备项目背景、需求目标、功能模块、个人负责部分和最终演示效果。",
    "补技术细节：至少能解释页面流程、接口数据流转、核心库的作用和一次问题排查过程。",
    "准备项目追问：说明为什么这样设计、遇到什么问题、如何定位、还有哪些不足。",
    "解释缺少实战经历时，将回答重点放在项目完整度、学习迁移能力和快速补齐能力上。",
    "准备降级表达：证据不足时用课程项目、个人项目、参与实现、协助整理等口径承接。",
]

WEAK_PROFILE_KNOWLEDGE = [
    "课程项目复盘：背景、目标、模块、职责、结果",
    "技术细节补齐：组件、接口、数据流、异常处理",
    "项目证据材料：截图、仓库、文档、PPT、实验报告",
    "面试降级表达：课程项目 / 个人项目 / 参与实现 / 协助整理",
]


def _as_payload_dict(payload: schemas.GenerationPayload | dict) -> dict:
    return deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(re.search(re.escape(keyword), text or "", re.IGNORECASE) for keyword in keywords)


def _has_positive_work_signal(text: str) -> bool:
    raw = text or ""
    if _has_any(raw, ["没有实习", "无实习", "没实习", "没有实习经历", "没有实习经验"]):
        return _has_any(raw, ["公司", "企业", "工作", "岗位"]) and not _has_any(raw, ["没有工作", "无工作"])
    return _has_any(raw, ["实习", "工作", "公司", "企业", "岗位"])


def _unique_append(target: list[str], values: list[str], limit: int) -> list[str]:
    for value in values:
        item = str(value).strip()
        if item and item not in target:
            target.append(item)
        if len(target) >= limit:
            break
    return target


def _count_terms(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if re.search(re.escape(term), text or "", re.IGNORECASE))


def _project_text(project: dict) -> str:
    details = project.get("details") if isinstance(project.get("details"), list) else []
    return " ".join(
        [
            str(project.get("name", "")),
            str(project.get("meta", "")),
            str(project.get("intro", "")),
            str(project.get("role", "")),
            " ".join(str(item) for item in details),
        ]
    )


def detect_weak_profile(raw_input: str, payload: schemas.GenerationPayload | dict) -> bool:
    raw = raw_input or ""
    data = _as_payload_dict(payload)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    projects = sections.get("projects") if isinstance(sections.get("projects"), list) else []
    context = analyze_long_input(raw)
    tech_count = _count_terms(raw, TECH_TERMS)
    evidence_count = _count_terms(raw, EVIDENCE_TERMS)

    if context.segment_count >= 3 and tech_count >= 4 and evidence_count >= 2:
        return False
    if _has_positive_work_signal(raw) and (tech_count >= 4 or evidence_count >= 2):
        return False

    score = 0
    if len(raw.strip()) < 450:
        score += 2
    if context.segment_count <= 2:
        score += 1
    if not _has_positive_work_signal(raw):
        score += 1
    if not _has_any(raw, ["上线", "部署", "公网", "域名", "用户", "star", "访问", "并发"]):
        score += 1
    if _has_any(raw, WEAK_EXPERIENCE_TERMS):
        score += 2
    if tech_count <= 3:
        score += 1
    if evidence_count <= 1:
        score += 1
    if len(projects) <= 2:
        score += 1
    if projects and all(len(project.get("details", []) or []) < 3 for project in projects if isinstance(project, dict)):
        score += 1
    return score >= 4


def _sanitize_strong_phrases(text: str, raw_input: str) -> str:
    cleaned = str(text or "")
    for source, target in NEGATIVE_RESUME_PHRASES:
        cleaned = cleaned.replace(source, target)
    if not (_has_positive_work_signal(raw_input) or _has_any(raw_input, ["生产", "上线"])):
        for phrase in FORBIDDEN_STRONG_PHRASES:
            cleaned = cleaned.replace(phrase, "项目实践")
    if not _has_any(raw_input, ["奖", "排名", "名次", "证书", "立项"]):
        for phrase in AWARD_PHRASES:
            cleaned = cleaned.replace(phrase, "参与")
    return cleaned.strip()


def _infer_weak_meta(project: dict, raw_input: str) -> str:
    text = _project_text(project)
    current = str(project.get("meta", "") or "项目经历")
    if "实习" in current:
        return current
    if _has_any(text, ["课程项目", "大作业", "课设", "课程设计", "课堂项目", "作业"]):
        return "课程项目"
    if _has_any(text, ["学生工作", "学生会", "班委", "社团"]):
        return "校园 / 社团经历"
    if _has_any(text, ["竞赛", "比赛"]):
        return "竞赛经历"
    if _has_any(text, ["小项目", "个人项目"]):
        return "个人项目"
    return current if current else "个人项目"


def _detail_candidates(project: dict, raw_input: str, use_raw_hints: bool = False) -> list[str]:
    text = f"{_project_text(project)}\n{raw_input if use_raw_hints else ''}"
    meta = str(project.get("meta", ""))
    candidates: list[str] = []

    if _has_any(text, ["写页面", "页面", "前端", "React", "Vue", "组件"]):
        candidates.append("围绕页面开发与交互流程实现，梳理核心功能、状态变化和用户操作路径。")
    if _has_any(text, ["调接口", "接口", "API", "请求", "后端"]):
        candidates.append("围绕接口联调与数据流转校验，处理请求参数、返回数据和异常提示。")
    if _has_any(text, ["写文档", "文档", "报告", "PPT", "实验报告"]):
        candidates.append("沉淀项目说明、实验报告、演示材料或复盘文档，提升经历可解释性。")
    if _has_any(text, ["展示", "答辩", "路演", "汇报"]):
        candidates.append("参与功能演示、展示答辩或阶段汇报，能够讲清方案思路和个人贡献。")
    if _has_any(text, ["竞赛", "比赛"]) or "竞赛" in meta:
        candidates.extend(
            [
                "围绕赛题目标进行问题分析、方案设计、材料整理和结果复盘。",
                "将竞赛过程整理为可面试表达的目标、分工、交付材料和复盘收获。",
            ]
        )
    if _has_any(text, ["学生工作", "学生会", "社团", "班委"]) or "社团" in meta or "校园" in meta:
        candidates.extend(
            [
                "围绕活动目标参与组织协调、沟通推进、材料沉淀和执行复盘。",
                "将学生工作经历转化为协作沟通、流程推进和结果复盘能力支撑。",
            ]
        )
    if _has_any(text, ["课程", "大作业", "课设", "课程设计", "作业"]):
        candidates.append("基于课程要求完成需求理解、功能拆解、实现验证和项目复盘。")
    if _has_any(text, ["小项目", "个人项目"]):
        candidates.append("从需求分析到功能实现独立推进项目，形成可展示、可复盘的实践经历。")

    candidates.extend(
        [
            "围绕已有任务拆解项目目标、个人职责、技术动作和可补充证据。",
            "梳理项目不足和后续优化方向，准备面试中的降级表达和改进计划。",
        ]
    )
    return candidates


def _project_experience_id(project: dict, raw_input: str) -> str:
    source_id = str(project.get("source_experience_id") or "").strip()
    if source_id:
        return source_id
    project_text = _project_text(project).lower()
    ranked: list[tuple[int, str]] = []
    for identity in build_experience_identities(raw_input):
        signals = [identity.title, *identity.explicit_tech_terms, *identity.explicit_metrics]
        score = sum(bool(signal and str(signal).lower() in project_text) for signal in signals)
        if identity.title and identity.title.lower() in project_text:
            score += 3
        ranked.append((score, identity.experience_id))
    ranked.sort(reverse=True)
    return ranked[0][1] if ranked and ranked[0][0] > 0 else ""


def _professional_fact_detail(text: str) -> str:
    value = str(text or "").strip(" ，,。；;")
    replacements = [
        (r"^我做过一个\s*", "设计并实现"),
        (r"^我独立完成(?:此|该)?项目[，,]?", "独立完成项目设计与功能实现，"),
        (r"^我主要负责\s*", "负责"),
        (r"^项目实现了\s*", "实现"),
    ]
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value, flags=re.I)
    return value.strip(" ，,。；;")


def _fact_backed_detail_candidates(project: dict, raw_input: str) -> list[str]:
    experience_id = _project_experience_id(project, raw_input)
    if not experience_id:
        return []
    candidates: list[str] = []
    for fact in build_experience_fact_ledger(raw_input).for_experience(experience_id):
        if not fact.resume_ready_text or fact.importance == "low" and fact.fact_type not in {"功能", "技术"}:
            continue
        detail = _professional_fact_detail(fact.resume_ready_text)
        if any(marker in detail for marker in ["希望包装", "目标岗位", "完全无法解释"]):
            continue
        if detail and detail not in candidates:
            candidates.append(detail)
    return candidates[:6]


def _strengthen_project(project: dict, raw_input: str, use_raw_hints: bool = False) -> dict:
    strengthened = dict(project)
    strengthened["name"] = _sanitize_strong_phrases(strengthened.get("name") or "项目实践", raw_input)
    strengthened["meta"] = _infer_weak_meta(strengthened, raw_input)
    strengthened["time"] = _sanitize_strong_phrases(strengthened.get("time") or "[待填写]", raw_input) or "[待填写]"
    strengthened["intro"] = _sanitize_strong_phrases(strengthened.get("intro") or "围绕已有经历整理项目目标、功能链路和实践价值。", raw_input)
    strengthened["role"] = _sanitize_strong_phrases(
        strengthened.get("role") or "基于已有任务参与需求理解、功能实现、材料整理和复盘优化。",
        raw_input,
    )

    details = [str(item).strip() for item in strengthened.get("details", []) or [] if str(item).strip()]
    details = [_sanitize_strong_phrases(item, raw_input) for item in details if _sanitize_strong_phrases(item, raw_input)]
    _unique_append(details, _fact_backed_detail_candidates(strengthened, raw_input), 6)
    if len(details) < 3:
        _unique_append(details, _detail_candidates(strengthened, raw_input, use_raw_hints), 4)
    strengthened["details"] = details[:8]
    return strengthened


def strengthen_weak_profile_payload(
    payload: schemas.GenerationPayload | dict,
    raw_input: str,
    target_role: str = "",
) -> schemas.GenerationPayload:
    data = _as_payload_dict(payload)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    projects = sections.get("projects") if isinstance(sections.get("projects"), list) else []
    weak_profile = detect_weak_profile(raw_input, payload)
    ledger = build_experience_fact_ledger(raw_input)
    thin_with_evidence = any(
        len(project.get("details", []) or []) < 3
        and len(ledger.for_experience(_project_experience_id(project, raw_input))) >= 3
        for project in projects
        if isinstance(project, dict)
    )
    if not weak_profile and not thin_with_evidence:
        return payload if isinstance(payload, schemas.GenerationPayload) else schemas.GenerationPayload.model_validate(payload)

    # A fact-rich profile can still have a thin generated project. Repair only the
    # affected project bodies without applying weak-profile coaching content.
    if not weak_profile:
        sections["projects"] = [_strengthen_project(project, raw_input) for project in projects]
        data["resume_sections"] = sections
        return schemas.GenerationPayload.model_validate(data)

    summary = [str(item).strip() for item in sections.get("summary", []) if str(item).strip()] if isinstance(sections.get("summary"), list) else []
    summary = [_sanitize_strong_phrases(item, raw_input) for item in summary]
    grounded_seeds = [candidate.text for candidate in build_grounded_summary_candidates(raw_input)]
    _unique_append(summary, grounded_seeds, 2)
    sections["summary"] = summary[:2]

    if not projects:
        projects = [
            {
                "name": "课程 / 个人项目实践",
                "meta": "课程项目" if _has_any(raw_input, ["课程", "大作业", "课设", "作业"]) else "个人项目",
                "time": "[待填写]",
                "intro": "围绕用户已提供经历整理项目目标、功能实现和可面试承接点。",
                "role": "参与需求理解、功能实现、材料整理和复盘优化。",
                "details": [],
            }
        ]
    use_raw_hints = len(projects) <= 1
    sections["projects"] = [_strengthen_project(project, raw_input, use_raw_hints) for project in projects]

    missing_questions = [str(item).strip() for item in data.get("missing_questions", []) if str(item).strip()] if isinstance(data.get("missing_questions"), list) else []
    _unique_append(missing_questions, WEAK_PROFILE_QUESTIONS, 8)
    data["missing_questions"] = missing_questions[:8]

    interview_plan = [str(item).strip() for item in data.get("interview_plan", []) if str(item).strip()] if isinstance(data.get("interview_plan"), list) else []
    _unique_append(interview_plan, WEAK_PROFILE_INTERVIEW_PLAN, 12)
    data["interview_plan"] = interview_plan[:12]

    knowledge_checklist = [str(item).strip() for item in data.get("knowledge_checklist", []) if str(item).strip()] if isinstance(data.get("knowledge_checklist"), list) else []
    _unique_append(knowledge_checklist, WEAK_PROFILE_KNOWLEDGE, 16)
    data["knowledge_checklist"] = knowledge_checklist[:16]

    interview_preparation = [str(item).strip() for item in sections.get("interview_preparation", []) if str(item).strip()] if isinstance(sections.get("interview_preparation"), list) else []
    _unique_append(interview_preparation, WEAK_PROFILE_INTERVIEW_PLAN[:4], 10)
    sections["interview_preparation"] = interview_preparation[:10]

    data["recommended_version"] = _sanitize_strong_phrases(str(data.get("recommended_version") or ""), raw_input)
    if len(data["recommended_version"].strip()) < 80:
        data["recommended_version"] = (
            f"建议将当前经历包装为面向{target_role or '目标岗位'}的成长型实践画像：以课程项目、个人项目、竞赛或学生工作为基础，"
            "突出需求理解、功能实现、材料沉淀、问题复盘和学习迁移能力。表达可以更正式，但不补写未提供的硬事实。"
        )

    sections["personal_info"] = sections.get("personal_info") if isinstance(sections.get("personal_info"), dict) else {}
    sections["education"] = sections.get("education") if isinstance(sections.get("education"), dict) else {"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"}
    data["resume_sections"] = sections
    return schemas.GenerationPayload.model_validate(data)
