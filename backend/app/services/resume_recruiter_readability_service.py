import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .resume_fact_dedup_service import similarity
from .recruiter_language_service import internal_field_count


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_recruiter_readability.jsonl"
SERVICE_FILE = re.compile(r"\b[a-z][a-z0-9_]*(?:_service)?\.py\b", re.I)
ACTION_OR_VALUE = re.compile(
    r"设计|实现|建立|引入|优化|修复|解决|定位|完成|支持|形成|监控|降低|提升|避免|保障|"
    r"暴露|发现|验证|交付|部署|重构|治理|校验|抽取|拆分|维护|记录",
    re.I,
)


@dataclass
class RecruiterReadabilityStats:
    stage: str
    generation_result_id: int | None
    checked_detail_count: int = 0
    developer_log_expression_count: int = 0
    developer_log_expression_removed_count: int = 0
    intro_duplicate_removed_count: int = 0
    unsupported_internal_enumeration_count: int = 0
    recruiter_readability_score: int = 100
    affected_experience_ids: list[str] = field(default_factory=list)


def _is_low_value(text: str, intro: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    if SERVICE_FILE.search(value):
        return True
    if internal_field_count(value) >= 3:
        return True
    if intro and similarity(value, intro) >= 0.88:
        return True
    if re.search(r"^(?:新增|修改|更新)\s+[\w/.-]+(?:文件|脚本)?$", value, re.I):
        return True
    if re.search(r"(?:发现|优化)了?(?:问题|系统)?[。]?$", value) and not ACTION_OR_VALUE.search(value[2:]):
        return True
    return False


def _write_log(stats: RecruiterReadabilityStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        entry["affected_experience_ids"] = sorted(set(entry["affected_experience_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def ensure_recruiter_readability(
    payload: schemas.GenerationPayload,
    *, stage: str = "unknown", generation_result_id: int | None = None, write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = RecruiterReadabilityStats(stage=stage, generation_result_id=generation_result_id)
    for project in updated.resume_sections.projects:
        intro = str(project.get("intro") or "")
        source_id = str(project.get("source_experience_id") or "")
        kept: list[str] = []
        for raw_detail in project.get("details", []) or []:
            detail = str(raw_detail or "").strip()
            stats.checked_detail_count += 1
            low_value = _is_low_value(detail, intro)
            if low_value:
                stats.developer_log_expression_count += 1
                if intro and similarity(detail, intro) >= 0.88:
                    stats.intro_duplicate_removed_count += 1
                if internal_field_count(detail) >= 3:
                    stats.unsupported_internal_enumeration_count += 1
                # Keep unique technical content unless the sentence is only residue or repetition.
                if SERVICE_FILE.search(detail) or similarity(detail, intro) >= 0.88 or len(detail) < 18:
                    stats.developer_log_expression_removed_count += 1
                    stats.affected_experience_ids.append(source_id)
                    continue
            if detail and detail not in kept:
                kept.append(detail)
        project["details"] = kept
    stats.recruiter_readability_score = max(
        0, round(100 - stats.developer_log_expression_count / max(1, stats.checked_detail_count) * 100)
    )
    if write_log:
        _write_log(stats)
    return updated


def recruiter_readability_score(payload: schemas.GenerationPayload) -> int:
    checked = bad = 0
    for project in payload.resume_sections.projects:
        intro = str(project.get("intro") or "")
        for detail in project.get("details", []) or []:
            checked += 1
            bad += _is_low_value(str(detail), intro)
    return max(0, round(100 - bad / max(1, checked) * 100))
