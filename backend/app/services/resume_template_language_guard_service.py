import re

from .. import schemas
from .canonical_consumer_view_service import (
    CanonicalConsumerViewAccessStats,
    CanonicalPresentationView,
)


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
GENERIC_ROLE_PATTERNS = [
    re.compile(r"^(?:负责相关工作|参与相关任务|完成相关任务|围绕项目目标完成工作|根据现有经历整理职责|推进项目相关事项)[。.]?$"),
    re.compile(r".*(?:以用户原文|以用户提供的信息|以用户已提供内容).*为准[。.]?$"),
]


def professionalize_sentence(text: str) -> str:
    value = str(text or "").strip()
    for pattern, replacement in PREFIX_REPLACEMENTS:
        value = pattern.sub(replacement, value)
    value = re.sub(r"^(围绕项目目标|围绕真实使用场景)[，,]?\s*", "", value)
    return value.strip(" ，,；;")


def guard_template_language(
    payload: schemas.GenerationPayload,
    stats: dict | None = None,
    *,
    presentation_view: CanonicalPresentationView | None = None,
    access_stats: CanonicalConsumerViewAccessStats | None = None,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        intro_permitted = presentation_view is None or presentation_view.permits_project_field(
            project, "intro", access_stats=access_stats,
        )
        role_permitted = presentation_view is None or presentation_view.permits_project_field(
            project, "role", access_stats=access_stats,
        )
        if intro_permitted:
            project["intro"] = professionalize_sentence(str(project.get("intro") or ""))
        if role_permitted:
            project["role"] = professionalize_sentence(str(project.get("role") or ""))
        if role_permitted and any(pattern.fullmatch(str(project.get("role") or "")) for pattern in GENERIC_ROLE_PATTERNS):
            project["role"] = ""
        original_details = [str(item) for item in project.get("details", [])]
        cleaned_details = [
            professionalize_sentence(item)
            if presentation_view is None or presentation_view.permits_project_field(
                project, "details", index, access_stats=access_stats,
            )
            else item
            for index, item in enumerate(original_details)
        ]
        project["details"] = [after or before for before, after in zip(original_details, cleaned_details) if before]
        if stats is not None:
            stats["removed_template_detail_count"] = stats.get("removed_template_detail_count", 0) + sum(
                before != after for before, after in zip(original_details, cleaned_details)
            )
    return updated
