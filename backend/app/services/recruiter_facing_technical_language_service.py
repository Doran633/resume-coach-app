import re

from .. import schemas
from .recruiter_language_service import ensure_recruiter_language


OBSERVABILITY_FIELDS = re.compile(
    r"(?:retrieved_count|retrieval_score|confidence|no_answer|token_usage|answer_policy)"
    r"(?:\s*[,，、和与及]\s*(?:retrieved_count|retrieval_score|confidence|no_answer|token_usage|answer_policy))*",
    re.I,
)
PIPELINE_FIELDS = re.compile(
    r"(?:result_cleanup|fact_guard|resume_section_fallback)"
    r"(?:\s*[,，、和与及]\s*(?:result_cleanup|fact_guard|resume_section_fallback))*",
    re.I,
)


def _convert(text: str) -> str:
    value = str(text or "")
    value = OBSERVABILITY_FIELDS.sub("检索召回、相关度评分、回答置信度、拒答策略和 Token 消耗", value)
    value = PIPELINE_FIELDS.sub("生成结果清洗、事实校验和简历结构完整性兜底机制", value)
    if re.search(r"EXP-\d+", value, re.I) and "技术、指标、证据和风险事实" in value:
        value = "将长输入拆分为独立 experience_id，并分别抽取技术、指标、证据和风险事实，建立经历级事实边界。"
    value = re.sub(r"(?:section\s+summary\s+chunk|summary\s+chunk|section\s+个人优势\s+chunk)", "", value, flags=re.I)
    value = re.sub(r"\s*[,，、]\s*[,，、]+", "、", value)
    return value.strip(" ，,、；;")


def ensure_recruiter_facing_technical_language(
    payload: schemas.GenerationPayload,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = ensure_recruiter_language(
        payload, stage=stage, generation_result_id=generation_result_id, write_log=write_log,
    )
    updated.resume_sections.summary = [_convert(item) for item in updated.resume_sections.summary if _convert(item)]
    updated.resume_sections.skills = [_convert(item) for item in updated.resume_sections.skills if _convert(item)]
    for project in updated.resume_sections.projects:
        for key in ("name", "position", "meta", "intro", "role"):
            if key in project:
                project[key] = _convert(project.get(key, ""))
        project["details"] = [_convert(item) for item in project.get("details", []) if _convert(item)]
    return updated
