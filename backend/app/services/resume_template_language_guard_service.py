import re

from .. import schemas


PREFIX_REPLACEMENTS = [
    (re.compile(r"^我做过(?:一个|一项)?"), "设计并完成"),
    (re.compile(r"^我做了"), "完成"),
    (re.compile(r"^我写了"), "开发"),
    (re.compile(r"^我调了"), "完成联调并验证"),
    (re.compile(r"^技术动作[：:]\s*"), ""),
    (re.compile(r"^(?:然后|之后又|还做了|主要就是)[，,：:]?\s*"), ""),
    (re.compile(r"^用了"), "使用"),
    (re.compile(r"^搞了"), "搭建"),
    (re.compile(r"^做了一些"), "完成"),
    (re.compile(r"^进行了相关工作[：:]?\s*"), ""),
]


def professionalize_sentence(text: str) -> str:
    value = str(text or "").strip()
    for pattern, replacement in PREFIX_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    value = re.sub(r"^(围绕项目目标|围绕真实使用场景)[，,]?\s*", "", value)
    return value.strip(" ，,；;")


def guard_template_language(payload: schemas.GenerationPayload, stats: dict | None = None) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        project["intro"] = professionalize_sentence(str(project.get("intro") or ""))
        project["role"] = professionalize_sentence(str(project.get("role") or ""))
        original_details = [str(item) for item in project.get("details", [])]
        cleaned_details = [professionalize_sentence(item) for item in original_details]
        project["details"] = [item for item in cleaned_details if item]
        if stats is not None:
            stats["removed_template_detail_count"] = stats.get("removed_template_detail_count", 0) + sum(
                before != after for before, after in zip(original_details, cleaned_details)
            )
    return updated
