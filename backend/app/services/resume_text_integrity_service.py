import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_identity_service import ExperienceIdentity, build_experience_identities


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_text_integrity.jsonl"
INTERNAL_MARKERS = re.compile(
    r"(?:原文|内容|文本)(?:被)?截断|需补充(?:原文|内容)?|因长度限制省略|内部摘要结束",
    re.IGNORECASE,
)
TRAILING_ELLIPSIS = re.compile(r"(?:\.{3,}|…{1,})\s*(?:[（(][^）)]*[）)])?\s*$")


@dataclass
class IntegrityStats:
    stage: str
    generation_result_id: int | None = None
    type_corrections: list[str] = field(default_factory=list)
    truncated_text_detected_count: int = 0
    truncated_text_fixed_count: int = 0
    removed_incomplete_sentences: int = 0
    affected_experience_ids: list[str] = field(default_factory=list)


def _sentences(text: str) -> list[str]:
    return [item.strip(" \t\r\n，、") for item in re.split(r"(?<=[。！？；;.!?])\s*|\n+", text or "") if item.strip()]


def _clean_marker(text: str) -> str:
    cleaned = re.sub(r"\s*[（(]?(?:原文|内容|文本)(?:被)?截断[^）)]*[）)]?", "", text or "")
    cleaned = re.sub(r"\s*[（(]?需补充(?:原文|内容)?[）)]?", "", cleaned)
    cleaned = re.sub(r"\s*[（(]?因长度限制省略[）)]?", "", cleaned)
    return TRAILING_ELLIPSIS.sub("", cleaned).strip(" \t\r\n，、；;：:")


def _overlap_score(candidate: str, broken: str) -> int:
    terms = set(re.findall(r"[A-Za-z][A-Za-z0-9+_.\-/]*|[\u4e00-\u9fff]{2,8}", broken or ""))
    return sum(1 for term in terms if term.lower() in candidate.lower())


def _recover(text: str, identity: ExperienceIdentity | None) -> tuple[list[str], bool]:
    if not INTERNAL_MARKERS.search(text or "") and not TRAILING_ELLIPSIS.search(text or ""):
        return [text.strip()] if text.strip() else [], False
    cleaned = _clean_marker(text)
    if identity:
        candidates = _sentences(identity.raw_text)
        ranked = sorted(candidates, key=lambda item: _overlap_score(item, cleaned), reverse=True)
        if ranked and _overlap_score(ranked[0], cleaned) > 0:
            return [ranked[0]], True
    return ([cleaned] if len(cleaned) >= 12 else []), True


def _write_log(stats: IntegrityStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "stage": stats.stage,
            "generation_result_id": stats.generation_result_id,
            "type_corrections": stats.type_corrections,
            "truncated_text_detected_count": stats.truncated_text_detected_count,
            "truncated_text_fixed_count": stats.truncated_text_fixed_count,
            "removed_incomplete_sentences": stats.removed_incomplete_sentences,
            "affected_experience_ids": list(dict.fromkeys(stats.affected_experience_ids)),
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def ensure_resume_text_integrity(
    payload: schemas.GenerationPayload,
    raw_input: str,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    identities = {item.experience_id: item for item in build_experience_identities(raw_input)}
    stats = IntegrityStats(stage=stage, generation_result_id=generation_result_id)

    summary: list[str] = []
    for item in updated.resume_sections.summary:
        recovered, changed = _recover(str(item), None)
        if changed:
            stats.truncated_text_detected_count += 1
            stats.truncated_text_fixed_count += bool(recovered)
            stats.removed_incomplete_sentences += not bool(recovered)
        summary.extend(recovered)
    updated.resume_sections.summary = summary

    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        identity = identities.get(source_id)
        affected = False
        if identity:
            current_meta = str(project.get("meta") or "").strip()
            expected_meta = identity.experience_type
            if expected_meta == "项目经历":
                corrected_meta = "项目经历" if "实习" in current_meta else current_meta or "项目经历"
            else:
                corrected_meta = expected_meta
            if corrected_meta != current_meta:
                project["meta"] = corrected_meta
                stats.type_corrections.append(f"{source_id}:{current_meta or 'empty'}->{corrected_meta}")
        for key in ("name", "intro", "role"):
            recovered, changed = _recover(str(project.get(key) or ""), identity)
            if changed:
                stats.truncated_text_detected_count += 1
                stats.truncated_text_fixed_count += bool(recovered)
                stats.removed_incomplete_sentences += not bool(recovered)
                project[key] = recovered[0] if recovered else ""
                affected = True
        details: list[str] = []
        for detail in project.get("details", []) or []:
            recovered, changed = _recover(str(detail), identity)
            if changed:
                stats.truncated_text_detected_count += 1
                stats.truncated_text_fixed_count += bool(recovered)
                stats.removed_incomplete_sentences += not bool(recovered)
                affected = True
            for item in recovered:
                if item and item not in details:
                    details.append(item)
        project["details"] = details
        if affected and source_id:
            stats.affected_experience_ids.append(source_id)

    if write_log:
        _write_log(stats)
    return updated
