import re
from copy import deepcopy
from difflib import SequenceMatcher

from .. import schemas
from .experience_identity_service import build_experience_identities


LOW_LEVEL_UPGRADES = [
    ("写页面", "负责核心页面开发、交互状态流转与接口联调"),
    ("写了几个页面", "负责核心页面开发、交互状态流转与接口联调"),
    ("调接口", "围绕核心接口链路完成联调、异常定位与数据流转校验"),
    ("调了一些接口", "围绕核心接口链路完成联调、异常定位与数据流转校验"),
    ("调了接口", "围绕核心接口链路完成联调、异常定位与数据流转校验"),
    ("修 bug", "定位并修复关键流程异常，提升功能稳定性"),
    ("修bug", "定位并修复关键流程异常，提升功能稳定性"),
    ("写文档", "沉淀项目说明、使用文档和复盘材料，提升项目可维护性"),
    ("做了 RAG", "围绕文档解析、切块、Embedding、向量检索和回答生成构建 RAG 应用链路"),
    ("做了RAG", "围绕文档解析、切块、Embedding、向量检索和回答生成构建 RAG 应用链路"),
]

def _as_payload_dict(payload: schemas.GenerationPayload | dict) -> dict:
    return deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _similarity(left: str, right: str) -> float:
    a = _normalize(left)
    b = _normalize(right)
    if not a or not b:
        return 0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a[:1200], b[:1200]).ratio()


def _soft_upgrades_from_raw(raw_input: str) -> list[str]:
    upgrades: list[str] = []
    for needle, upgrade in LOW_LEVEL_UPGRADES:
        if needle.lower() in raw_input.lower() and upgrade not in upgrades:
            upgrades.append(upgrade)
    if "RAG" in raw_input or "rag" in raw_input.lower():
        rag_upgrade = "围绕文档解析、切块、Embedding、向量检索和回答生成梳理 RAG 应用链路。"
        if rag_upgrade not in upgrades:
            upgrades.append(rag_upgrade)
    return upgrades


def _project_summary(project: dict, index: int) -> str:
    name = project.get("name") or f"项目经历 {index}"
    intro = project.get("intro") or "围绕用户提供的真实经历进行项目化表达。"
    role = project.get("role") or "负责项目核心功能梳理、实现与交付。"
    details = project.get("details") if isinstance(project.get("details"), list) else []
    detail_text = "；".join(details[:3])
    return f"{name}：{intro} 我的职责：{role} 技术动作：{detail_text}"


def _build_recommended_from_projects(projects: list[dict], target_role: str, raw_input: str) -> str:
    parts = [
        f"推荐版本：面向{target_role or '目标岗位'}，建议将经历组织为“项目目标、个人职责、技术动作、结果证据、面试承接”的简历表达，而不是直接复述原始描述。"
    ]
    for index, project in enumerate(projects[:3], start=1):
        parts.append(_project_summary(project, index))
    upgrades = _soft_upgrades_from_raw(raw_input)
    if upgrades:
        parts.append("表达增强：" + "；".join(upgrades[:4]))
    parts.append("使用提醒：以上表达只强化职责组织和技术动作，不新增未提供的专业、公司、用户数、并发、奖项或模型训练事实。")
    return "\n".join(parts)


def _enhance_project_details(project: dict, raw_input: str, source_text: str = "") -> dict:
    enhanced = dict(project)
    local_input = source_text or raw_input
    details = [str(item).strip() for item in project.get("details", []) if str(item).strip()] if isinstance(project.get("details"), list) else []
    rewritten: list[str] = []
    for detail in details:
        if _similarity(detail, local_input) > 0.92 and len(detail) > 40:
            rewritten.append("技术动作：" + detail[:160])
        else:
            rewritten.append(detail)

    for upgrade in _soft_upgrades_from_raw(local_input):
        if upgrade not in rewritten:
            rewritten.append(upgrade)

    enhanced["details"] = rewritten[:8]
    if _similarity(enhanced.get("intro", ""), local_input) > 0.9 and source_text:
        enhanced["intro"] = re.split(r"[。；;]", source_text, maxsplit=1)[0].strip()
    if not enhanced.get("role"):
        enhanced["role"] = "基于已有事实梳理个人职责边界，突出技术实现、联调排查和结果交付。"
    return enhanced


def ensure_packaging_gain(
    payload: schemas.GenerationPayload | dict,
    raw_input: str,
    target_role: str = "",
) -> schemas.GenerationPayload:
    data = _as_payload_dict(payload)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    projects = sections.get("projects") if isinstance(sections.get("projects"), list) else []
    identities = {item.experience_id: item for item in build_experience_identities(raw_input)}
    enhanced_projects = [
        _enhance_project_details(
            project,
            raw_input,
            identities.get(str(project.get("source_experience_id") or "")).raw_text
            if identities.get(str(project.get("source_experience_id") or "")) else "",
        )
        for project in projects
    ]
    sections["projects"] = enhanced_projects

    recommended = str(data.get("recommended_version") or "")
    if _similarity(recommended, raw_input) > 0.78 or len(recommended.strip()) < 80:
        data["recommended_version"] = _build_recommended_from_projects(enhanced_projects, target_role, raw_input)

    for key in ["normal_version", "bold_version"]:
        text = str(data.get(key) or "")
        if _similarity(text, raw_input) > 0.82 or len(text.strip()) < 60:
            data[key] = _build_recommended_from_projects(enhanced_projects, target_role, raw_input)

    data["resume_sections"] = sections
    return schemas.GenerationPayload.model_validate(data)
