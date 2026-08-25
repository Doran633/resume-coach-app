import re
from copy import deepcopy

from .. import schemas


PLACEHOLDER = "[待填写]"

TECH_TERMS = [
    "RAG",
    "React",
    "TypeScript",
    "FastAPI",
    "SQLite",
    "Python",
    "Vue",
    "LangChain",
    "LangGraph",
    "Embedding",
    "BAAI",
    "bge-m3",
    "Nginx",
    "systemd",
    "Docker",
    "Pandas",
    "NumPy",
    "Matplotlib",
]

EDUCATION_KEYS = {
    "学校": ["学校", "大学", "学院"],
    "专业": ["专业"],
    "学历": ["本科", "硕士", "博士", "专科", "学历"],
    "时间": ["20", "大一", "大二", "大三", "大四", "研一", "研二", "研三"],
}

FORBIDDEN_IF_MISSING = {
    "major": [
        ("计算机相关专业", "具备工程实践能力"),
        ("软件工程专业", "具备工程实践能力"),
        ("计算机专业训练", "项目实践积累"),
        ("专业课程基础扎实", "项目实践基础较扎实"),
        ("科班背景", "项目实践积累"),
        ("计算机专业背景", "工程实践背景"),
    ],
    "company": [
        ("企业级实战", "真实项目实践"),
        ("公司级项目", "项目实践"),
        ("生产级业务系统", "可部署项目"),
        ("真实业务团队协作", "项目协作与交付实践"),
        ("企业级生产系统", "可公网访问的项目"),
        ("企业级经验", "项目实践经验"),
    ],
    "training": [
        ("模型训练经验", "AI 应用开发经验"),
        ("训练模型", "调用或应用模型"),
        ("微调模型", "模型应用与调试"),
        ("SFT", "模型训练相关知识准备"),
        ("RLHF", "模型训练相关知识准备"),
        ("DPO", "模型训练相关知识准备"),
        ("LoRA", "模型训练相关知识准备"),
    ],
    "concurrency": [
        ("高并发", "多用户访问"),
        ("实时高并发", "多用户访问"),
        ("高并发访问", "多用户访问"),
    ],
}


def _as_payload_dict(payload: schemas.GenerationPayload | dict) -> dict:
    return deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)


def _raw_has_any(raw_input: str, keywords: list[str]) -> bool:
    raw_lower = raw_input.lower()
    return any(keyword.lower() in raw_lower for keyword in keywords)


def _provided_facts(raw_input: str) -> dict[str, bool]:
    raw = raw_input.strip()
    return {
        "school": bool(re.search(r"(大学|学院|学校)", raw)),
        "major": bool(re.search(r"(专业是|专业为|就读.*专业|[^，。；\s]{2,20}专业)", raw)),
        "degree": _raw_has_any(raw, ["本科", "硕士", "博士", "专科", "学历"]),
        "company": _raw_has_any(raw, ["公司", "企业", "实习", "工作", "岗位", "业务团队"]),
        "users": bool(re.search(r"\d+\s*(人|用户|UV|PV|访问|在线)", raw, re.IGNORECASE)),
        "stars": bool(re.search(r"\d+\s*(star|stars|星)", raw, re.IGNORECASE)),
        "online": _raw_has_any(raw, ["上线", "部署", "公网", "域名", "VPS", "Nginx", "systemd"]),
        "concurrency": _raw_has_any(raw, ["并发", "同时在线", "QPS", "吞吐"]),
        "performance": _raw_has_any(raw, ["性能提升", "提升", "降低", "优化了", "%"]),
        "award": _raw_has_any(raw, ["奖", "排名", "名次", "一等奖", "二等奖", "三等奖"]),
        "training": _raw_has_any(raw, ["模型训练", "训练模型", "微调", "SFT", "RLHF", "DPO", "LoRA", "QLoRA"]),
        "tech": _raw_has_any(raw, TECH_TERMS),
    }


def _replace_missing_fact_phrases(text: str, facts: dict[str, bool]) -> str:
    cleaned = text
    if not facts["major"]:
        for src, dst in FORBIDDEN_IF_MISSING["major"]:
            cleaned = cleaned.replace(src, dst)
    if not facts["company"]:
        for src, dst in FORBIDDEN_IF_MISSING["company"]:
            cleaned = cleaned.replace(src, dst)
    if not facts["training"]:
        for src, dst in FORBIDDEN_IF_MISSING["training"]:
            cleaned = cleaned.replace(src, dst)
    if not facts["concurrency"]:
        for src, dst in FORBIDDEN_IF_MISSING["concurrency"]:
            cleaned = cleaned.replace(src, dst)
    if not facts["online"]:
        cleaned = cleaned.replace("已部署上线", "具备部署实践")
        cleaned = cleaned.replace("上线运行", "完成本地或测试环境运行")
    return cleaned


def _clean_text(value, facts: dict[str, bool]) -> str:
    if value is None:
        return ""
    return _replace_missing_fact_phrases(str(value), facts).strip()


def _clean_list(values, facts: dict[str, bool]) -> list[str]:
    if not isinstance(values, list):
        return []
    return [text for item in values if (text := _clean_text(item, facts))]


def _guard_education(education: dict, raw_input: str, facts: dict[str, bool]) -> dict[str, str]:
    guarded = education if isinstance(education, dict) else {}
    result: dict[str, str] = {}
    for key in ["学校", "专业", "学历", "时间"]:
        value = _clean_text(guarded.get(key), facts) or PLACEHOLDER
        if key == "学校" and not facts["school"]:
            value = PLACEHOLDER
        if key == "专业" and not facts["major"]:
            value = PLACEHOLDER
        if key == "学历" and not facts["degree"]:
            value = PLACEHOLDER
        if key == "时间" and not _raw_has_any(raw_input, EDUCATION_KEYS["时间"]):
            value = PLACEHOLDER
        result[key] = value
    return result


def _clean_claims(claims, facts: dict[str, bool]) -> list[dict]:
    cleaned = []
    for claim in claims if isinstance(claims, list) else []:
        item = claim if isinstance(claim, dict) else {"claim": claim}
        cleaned.append(
            {
                "claim": _clean_text(item.get("claim"), facts),
                "risk_level": item.get("risk_level", "yellow"),
                "evidence": _clean_text(item.get("evidence"), facts),
                "risk_reason": _clean_text(item.get("risk_reason"), facts),
                "interview_questions": _clean_list(item.get("interview_questions"), facts),
                "knowledge_to_prepare": _clean_list(item.get("knowledge_to_prepare"), facts),
                "downgrade_wording": _clean_text(item.get("downgrade_wording"), facts),
            }
        )
    return cleaned


def _clean_projects(projects, facts: dict[str, bool]) -> list[dict]:
    cleaned_projects = []
    for project in projects if isinstance(projects, list) else []:
        item = project if isinstance(project, dict) else {"name": "项目经历", "intro": project}
        cleaned_projects.append(
            {
                "name": _clean_text(item.get("name"), facts) or "项目经历",
                "meta": _clean_text(item.get("meta"), facts) or "项目经历",
                "time": _clean_text(item.get("time"), facts) or PLACEHOLDER,
                "intro": _clean_text(item.get("intro"), facts),
                "role": _clean_text(item.get("role"), facts),
                "details": _clean_list(item.get("details"), facts),
            }
        )
    return cleaned_projects


def guard_hard_facts(payload: schemas.GenerationPayload | dict, raw_input: str) -> schemas.GenerationPayload:
    facts = _provided_facts(raw_input)
    data = _as_payload_dict(payload)

    for key in ["normal_version", "bold_version", "boundary_version", "recommended_version"]:
        data[key] = _clean_text(data.get(key), facts)

    for key in ["confirmed_facts", "missing_questions", "interview_plan", "knowledge_checklist"]:
        data[key] = _clean_list(data.get(key), facts)

    data["claims"] = _clean_claims(data.get("claims"), facts)

    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    sections["summary"] = _clean_list(sections.get("summary"), facts)
    sections["skills"] = _clean_list(sections.get("skills"), facts)
    sections["projects"] = _clean_projects(sections.get("projects"), facts)
    sections["education"] = _guard_education(sections.get("education"), raw_input, facts)
    sections["interview_preparation"] = _clean_list(sections.get("interview_preparation"), facts)
    sections["personal_info"] = sections.get("personal_info") if isinstance(sections.get("personal_info"), dict) else {}
    data["resume_sections"] = sections

    return schemas.GenerationPayload.model_validate(data)
