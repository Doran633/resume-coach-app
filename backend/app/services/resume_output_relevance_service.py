import json
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .resume_skill_evidence_guard_service import _canonical_term, _skill_terms
from .technical_term_disambiguation_service import best_resolution, resolve_technical_terms


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_output_relevance.jsonl"
CONFIDENCE_THRESHOLD = 0.65
TOKEN_QUESTION = "请确认 Token 指大模型调用消耗、上下文长度，还是接口鉴权令牌。"


@dataclass
class OutputRelevanceStats:
    stage: str
    generation_result_id: int | None
    checked_skill_count: int = 0
    moved_skill_count: int = 0
    removed_ambiguous_skill_count: int = 0
    unsupported_category_count: int = 0
    repair_count: int = 0
    source_experience_ids: list[str] = field(default_factory=list)
    source_fact_ids: list[str] = field(default_factory=list)
    resolved_terms: list[dict] = field(default_factory=list)


def _display_term(term: str, meaning: str) -> str:
    if term.lower() != "token":
        return term
    if meaning == "authentication_token":
        return "Token 鉴权"
    if meaning in {"prompt_token_cost", "context_token"}:
        return "上下文 Token 管理"
    if meaning == "llm_token_cost":
        return "Token 成本控制"
    return term


def _ordered_skill_terms(line: str) -> list[str]:
    terms = _skill_terms(line)
    lowered = line.lower()
    return sorted(terms, key=lambda term: lowered.find(term.lower()))


def _write_log(stats: OutputRelevanceStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        entry["source_experience_ids"] = sorted(set(entry["source_experience_ids"]))
        entry["source_fact_ids"] = sorted(set(entry["source_fact_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def guard_resume_output_relevance(
    payload: schemas.GenerationPayload,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = OutputRelevanceStats(stage=stage, generation_result_id=generation_result_id)
    resolutions = resolve_technical_terms(raw_input)
    grouped: OrderedDict[str, list[str]] = OrderedDict()
    unresolved_token = any(
        item.term.lower() == "token"
        and (not item.category or item.confidence < CONFIDENCE_THRESHOLD)
        for item in resolutions
    )

    for raw_line in updated.resume_sections.skills:
        line = str(raw_line or "").strip()
        label_match = re.match(r"^([^：:]{1,24})[：:]", line)
        current_category = label_match.group(1).strip() if label_match else "其他技术"
        for raw_term in _ordered_skill_terms(line):
            term = _canonical_term(raw_term)
            stats.checked_skill_count += 1
            target_category = current_category
            if term.lower() == "token":
                resolution = best_resolution(resolutions, "Token")
                if not resolution or not resolution.category or resolution.confidence < CONFIDENCE_THRESHOLD:
                    stats.removed_ambiguous_skill_count += 1
                    stats.repair_count += 1
                    unresolved_token = True
                    continue
                target_category = resolution.category
                stats.source_experience_ids.append(resolution.experience_id)
                stats.source_fact_ids.append(resolution.fact_id)
                stats.resolved_terms.append({
                    "term": resolution.term,
                    "meaning": resolution.meaning,
                    "category": resolution.category,
                    "confidence": resolution.confidence,
                    "experience_id": resolution.experience_id,
                    "fact_id": resolution.fact_id,
                })
                if target_category != current_category:
                    stats.moved_skill_count += 1
                    stats.unsupported_category_count += 1
                    stats.repair_count += 1
                term = _display_term(term, resolution.meaning)
            values = grouped.setdefault(target_category, [])
            if term.lower() not in {item.lower() for item in values}:
                values.append(term)

    updated.resume_sections.skills = [
        f"{category}：{'、'.join(terms)}" for category, terms in grouped.items() if terms
    ]
    if unresolved_token and TOKEN_QUESTION not in updated.missing_questions:
        updated.missing_questions.append(TOKEN_QUESTION)
    if write_log:
        _write_log(stats)
    return updated
