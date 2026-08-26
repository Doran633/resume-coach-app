from copy import deepcopy

from .. import schemas


ALLOWED_SECTION_KEYS = {"personal_info", "education", "summary", "skills", "projects", "interview_preparation"}
SUMMARY_ALIASES = {"个人优势", "section 个人优势", "summary chunk", "section summary"}


def normalize_resume_section_schema(payload: schemas.GenerationPayload | dict) -> schemas.GenerationPayload:
    data = deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)
    raw_sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    sections = {key: raw_sections.get(key) for key in ALLOWED_SECTION_KEYS if key in raw_sections}
    summary = list(sections.get("summary") or []) if isinstance(sections.get("summary"), list) else []
    for alias in SUMMARY_ALIASES:
        values = raw_sections.get(alias)
        if isinstance(values, list):
            summary.extend(str(item) for item in values if str(item).strip())
    sections["summary"] = list(dict.fromkeys(summary))
    sections.setdefault("personal_info", {})
    sections.setdefault("education", {})
    sections.setdefault("skills", [])
    sections.setdefault("projects", [])
    sections.setdefault("interview_preparation", [])
    data["resume_sections"] = sections
    return schemas.GenerationPayload.model_validate(data)
