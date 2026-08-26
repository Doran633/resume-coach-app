import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import TECH_PATTERN, normalize_fact_text


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_fact_dedup.jsonl"
WEAK_PREFIXES = ["之后", "进一步", "同时", "随后", "在多段经历输入中", "在多段经历中", "目前"]


@dataclass
class DedupStats:
    stage: str
    generation_result_id: int | None
    compared_pair_count: int = 0
    exact_duplicate_count: int = 0
    semantic_duplicate_count: int = 0
    merged_count: int = 0
    removed_count: int = 0
    retained_unique_fact_count: int = 0
    affected_experience_ids: list[str] = field(default_factory=list)
    merged_source_fact_ids: list[str] = field(default_factory=list)
    dedup_confidence_distribution: dict[str, int] = field(default_factory=lambda: {"high": 0, "medium": 0, "low": 0})


def _core(text: str) -> str:
    value = str(text or "")
    for prefix in WEAK_PREFIXES:
        value = value.replace(prefix, "")
    return normalize_fact_text(value)


def _terms(text: str) -> set[str]:
    values = {item.lower() for item in TECH_PATTERN.findall(text or "") if item}
    values.update(re.findall(r"\d+(?:\.\d+)?", text or ""))
    values.update(term for term in ["发现", "识别", "解决", "推进", "优化", "部署", "测试", "评估"] if term in (text or ""))
    return values


def similarity(left: str, right: str) -> float:
    a, b = _core(left), _core(right)
    if not a or not b:
        return 0.0
    if min(len(a), len(b)) >= 12 and (a in b or b in a):
        return 0.96
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = _terms(left), _terms(right)
    overlap = len(ta & tb) / max(1, len(ta | tb))
    return ratio * 0.7 + overlap * 0.3


def _merge(left: str, right: str) -> str:
    if _core(left) in _core(right):
        return right
    if _core(right) in _core(left):
        return left
    return right if len(right) > len(left) else left


def _write_log(stats: DedupStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **stats.__dict__}
        entry["affected_experience_ids"] = sorted(set(entry["affected_experience_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def deduplicate_resume_facts(payload: schemas.GenerationPayload, *, stage: str = "unknown", generation_result_id: int | None = None, write_log: bool = True) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = DedupStats(stage=stage, generation_result_id=generation_result_id)
    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        intro = str(project.get("intro") or "")
        unique: list[str] = []
        for detail in [str(item).strip() for item in project.get("details", []) if str(item).strip()]:
            if similarity(intro, detail) >= 0.9:
                stats.removed_count += 1
                stats.affected_experience_ids.append(source_id)
                continue
            merged = False
            for index, existing in enumerate(unique):
                stats.compared_pair_count += 1
                score = similarity(existing, detail)
                if score >= 0.88:
                    stats.semantic_duplicate_count += 1
                    stats.dedup_confidence_distribution["high"] += 1
                    unique[index] = _merge(existing, detail)
                    stats.merged_count += 1
                    stats.affected_experience_ids.append(source_id)
                    merged = True
                    break
                if score >= 0.72:
                    stats.dedup_confidence_distribution["medium"] += 1
                else:
                    stats.dedup_confidence_distribution["low"] += 1
            if not merged:
                unique.append(detail)
        project["details"] = unique
        stats.retained_unique_fact_count += len(unique)
    if write_log:
        _write_log(stats)
    return updated
