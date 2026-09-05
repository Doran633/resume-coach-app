import re
from copy import deepcopy

from .. import schemas


NEGATIVE_DROP_PATTERNS = [
    r"没有实习(?:经历|经验)?",
    r"无实习(?:经历|经验)?",
    r"没有正式上线",
    r"没有上线",
    r"未上线",
    r"没有真实用户",
    r"没有用户",
    r"没有获奖",
    r"未获奖",
    r"没什么奖项",
    r"没有什么经验",
    r"不太熟",
    r"不够专业",
    r"可能不会",
    r"随便做了",
]

NEGATIVE_REPLACEMENTS = [
    ("只是课程作业", "课程项目"),
    ("只是作业", "课程项目"),
    ("简单小项目", "个人项目实践"),
    ("简单项目", "个人项目实践"),
    ("写了几个页面", "参与核心页面开发与交互流程实现"),
    ("调了一些接口", "完成接口联调与数据流转校验"),
    ("只是参与", "参与相关任务并沉淀实践过程"),
]

INTERVIEW_NOTES = [
    ("没有实习", "如被问到实践经历，可强调课程项目、个人项目和学习迁移能力。"),
    ("无实习", "如被问到实践经历，可强调课程项目、个人项目和学习迁移能力。"),
    ("没有上线", "如被问到上线情况，可说明项目展示环境和后续部署计划，避免写成已上线项目。"),
    ("未上线", "如被问到上线情况，可说明项目展示环境和后续部署计划，避免写成已上线项目。"),
    ("没有获奖", "如被问到竞赛结果，可强调方案设计、材料整理、展示答辩和复盘收获。"),
    ("未获奖", "如被问到竞赛结果，可强调方案设计、材料整理、展示答辩和复盘收获。"),
]


def _as_payload_dict(payload: schemas.GenerationPayload | dict) -> dict:
    return deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)


def _clean_text(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for source, target in NEGATIVE_REPLACEMENTS:
        text = text.replace(source, target)
    for pattern in NEGATIVE_DROP_PATTERNS:
        text = re.sub(pattern, "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[，,、；;：:。 ]+$", "", text)
    text = re.sub(r"^[，,、；;：:。 ]+", "", text)
    return text.strip()


def _clean_list(values) -> list[str]:
    cleaned: list[str] = []
    for value in values if isinstance(values, list) else []:
        text = _clean_text(value)
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned


def _clean_project(project: dict) -> dict:
    item = dict(project if isinstance(project, dict) else {"name": "项目经历", "intro": project})
    meta = _clean_text(item.get("meta")) or "项目经历"
    if meta == "简单小项目":
        meta = "个人项目"
    if meta == "只是课程作业":
        meta = "课程项目"
    cleaned = {
        "name": _clean_text(item.get("name")) or "项目实践",
        "meta": meta,
        "time": _clean_text(item.get("time")) or "[待填写]",
        "intro": _clean_text(item.get("intro")),
        "role": _clean_text(item.get("role")),
        "details": _clean_list(item.get("details")),
    }
    for key in [
        "source_experience_id", "resolved_experience_type", "type_resolution_version", "type_locked", "source_fact_ids",
        "immutable_source_experience_id", "source_binding_origin", "source_binding_confidence", "source_binding_locked",
    ]:
        if key in item:
            cleaned[key] = item[key]
    return cleaned


def _add_interview_notes(data: dict, raw_input: str) -> None:
    raw = raw_input or ""
    interview_plan = [str(item).strip() for item in data.get("interview_plan", []) if str(item).strip()] if isinstance(data.get("interview_plan"), list) else []
    for trigger, note in INTERVIEW_NOTES:
        if trigger in raw and note not in interview_plan:
            interview_plan.append(note)
    data["interview_plan"] = interview_plan[:14]


def sanitize_resume_body(payload: schemas.GenerationPayload | dict, raw_input: str = "") -> schemas.GenerationPayload:
    data = _as_payload_dict(payload)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}

    sections["summary"] = _clean_list(sections.get("summary"))
    sections["projects"] = [_clean_project(project) for project in sections.get("projects", []) if isinstance(project, dict)]
    sections["interview_preparation"] = _clean_list(sections.get("interview_preparation"))
    sections["skills"] = _clean_list(sections.get("skills"))
    sections["personal_info"] = sections.get("personal_info") if isinstance(sections.get("personal_info"), dict) else {}
    sections["education"] = sections.get("education") if isinstance(sections.get("education"), dict) else {"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"}
    data["resume_sections"] = sections

    for key in ["normal_version", "bold_version", "recommended_version"]:
        data[key] = _clean_text(data.get(key))

    _add_interview_notes(data, raw_input)
    return schemas.GenerationPayload.model_validate(data)
