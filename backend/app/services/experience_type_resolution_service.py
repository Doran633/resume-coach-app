import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_identity_service import ExperienceIdentity, build_experience_identities


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "experience_type_resolution.jsonl"
STANDARD_TYPES = {"项目经历", "实习经历", "科研经历", "竞赛经历", "竞赛获奖", "开源经历", "校园 / 社团经历"}


@dataclass
class TypeResolution:
    experience_id: str
    resolved_type: str
    confidence: float
    positive_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)
    source_title: str = ""
    local_raw_text: str = ""
    resolution_method: str = "local_semantics"
    conflict_detected: bool = False


def resolve_identity_type(identity: ExperienceIdentity) -> TypeResolution:
    title = identity.title or ""
    local = identity.raw_text or ""
    header = f"{title}\n{local[:100]}"
    signals: list[tuple[str, str, float]] = []
    explicit_rules = [
        ("实习经历", r"实习经历|在[^。；\n]{2,40}(?:公司|企业|事务所|研究院)[^。；\n]{0,30}实习|担任[^。；\n]{0,30}实习生"),
        ("科研经历", r"科研经历|研究经历|论文经历|课题研究"),
        ("竞赛获奖", r"竞赛获奖|比赛获奖|(?:一等奖|二等奖|三等奖|金奖|银奖|铜奖)"),
        ("竞赛经历", r"竞赛经历|比赛经历|参加[^。；\n]{0,30}(?:竞赛|比赛)"),
        ("开源经历", r"开源经历|开源贡献|Pull Request|\bPR\b"),
        ("校园 / 社团经历", r"校园经历|社团经历|学生工作|志愿经历|协会|学生会"),
        ("项目经历", r"项目[一二三四五六七八九十\d]*\s*[|｜:：]|项目经历|个人项目|课程项目"),
    ]
    for type_name, pattern in explicit_rules:
        if re.search(pattern, header, re.IGNORECASE):
            signals.append((type_name, pattern, 0.92 if re.search(pattern, title, re.IGNORECASE) else 0.82))
    if not signals:
        inferred = identity.experience_type if identity.experience_type in STANDARD_TYPES else "项目经历"
        signals.append((inferred, "identity_local_type", 0.62 if inferred != "项目经历" else 0.55))
    signals.sort(key=lambda item: item[2], reverse=True)
    resolved, signal, confidence = signals[0]
    negatives = [item[0] for item in signals[1:] if item[0] != resolved]
    return TypeResolution(
        experience_id=identity.experience_id, resolved_type=resolved, confidence=confidence,
        positive_signals=[signal], negative_signals=negatives, source_title=title,
        local_raw_text=local, resolution_method="explicit_local_signal" if confidence >= 0.8 else "local_semantics",
        conflict_detected=bool(negatives),
    )


def build_type_resolutions(raw_input: str) -> dict[str, TypeResolution]:
    return {item.experience_id: resolve_identity_type(item) for item in build_experience_identities(raw_input)}


def _write_log(resolution: TypeResolution, llm_meta: str, final_section: str, stage: str, generation_result_id: int | None) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "generation_result_id": generation_result_id,
            "stage": stage, "experience_id": resolution.experience_id, "original_type": "",
            "llm_meta": llm_meta, "resolved_type": resolution.resolved_type, "confidence": resolution.confidence,
            "positive_signal_types": resolution.positive_signals, "negative_signal_types": resolution.negative_signals,
            "conflict_detected": llm_meta != resolution.resolved_type, "correction_applied": llm_meta != final_section,
            "final_section": final_section,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def resolve_project_types(payload: schemas.GenerationPayload, raw_input: str, *, stage: str = "unknown", generation_result_id: int | None = None, write_log: bool = True) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    resolutions = build_type_resolutions(raw_input)
    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        resolution = resolutions.get(source_id)
        if not resolution:
            continue
        llm_meta = str(project.get("meta") or "项目经历")
        if resolution.confidence >= 0.8:
            final_type = resolution.resolved_type
        elif resolution.confidence >= 0.55 and llm_meta in STANDARD_TYPES and not (llm_meta == "实习经历" and resolution.resolved_type == "项目经历"):
            final_type = llm_meta
        else:
            final_type = "项目经历"
        project["meta"] = final_type
        if write_log:
            _write_log(resolution, llm_meta, final_type, stage, generation_result_id)
    return updated
