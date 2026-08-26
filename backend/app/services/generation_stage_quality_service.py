import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .resume_section_schema_service import ALLOWED_SECTION_KEYS


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "generation_stage_quality.jsonl"
CONTAMINATION = re.compile(r"section\s+(?:个人优势|summary)|summary\s+chunk", re.I)


def log_generation_stage(payload: schemas.GenerationPayload | dict, stage_name: str, generation_result_id: int | None = None) -> None:
    try:
        data = payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload
        sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
        projects = sections.get("projects") if isinstance(sections.get("projects"), list) else []
        texts = []
        for project in projects:
            if isinstance(project, dict):
                texts.extend(str(project.get(key, "")) for key in ("name", "intro", "role"))
                texts.extend(str(item) for item in project.get("details", []) if item)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "generation_result_id": generation_result_id,
            "stage_name": stage_name, "project_count": len(projects),
            "experience_ids": [str(item.get("source_experience_id")) for item in projects if isinstance(item, dict) and item.get("source_experience_id")],
            "project_types": [str(item.get("meta")) for item in projects if isinstance(item, dict)],
            "section_keys": list(sections.keys()), "illegal_section_keys": [key for key in sections if key not in ALLOWED_SECTION_KEYS],
            "duplicate_fact_count": 0, "contamination_count": sum(1 for text in texts if CONTAMINATION.search(text)),
            "type_conflict_count": 0,
            "project_type_lineage": [
                {
                    "experience_id": str(item.get("source_experience_id") or ""),
                    "current_type": str(item.get("meta") or ""),
                    "resolved_type": str(item.get("resolved_experience_type") or ""),
                    "type_locked": bool(item.get("type_locked")),
                    "resolver_version": str(item.get("type_resolution_version") or ""),
                }
                for item in projects if isinstance(item, dict)
            ],
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except (OSError, TypeError, AttributeError):
        pass
