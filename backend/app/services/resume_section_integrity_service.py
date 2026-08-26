import re

from .. import schemas
from .resume_section_schema_service import normalize_resume_section_schema


POLLUTION = re.compile(
    r"(?:section\s+(?:个人优势|summary)(?:\s+chunk)?|(?:个人优势|summary)\s+chunk(?:\s+内容如下)?)",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    text = str(value or "").strip()
    if POLLUTION.fullmatch(text) or POLLUTION.search(text):
        text = POLLUTION.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" ，,、；;：:。")


def ensure_resume_section_integrity(payload: schemas.GenerationPayload | dict) -> schemas.GenerationPayload:
    updated = normalize_resume_section_schema(payload)
    updated.resume_sections.summary = [cleaned for item in updated.resume_sections.summary if (cleaned := _clean(item))]
    updated.resume_sections.skills = [cleaned for item in updated.resume_sections.skills if (cleaned := _clean(item))]
    projects: list[dict] = []
    for raw_project in updated.resume_sections.projects:
        project = dict(raw_project)
        for key in ("name", "meta", "intro", "role"):
            project[key] = _clean(project.get(key, ""))
        project["details"] = [cleaned for item in project.get("details", []) if (cleaned := _clean(item))]
        projects.append(project)
    updated.resume_sections.projects = projects
    return updated
