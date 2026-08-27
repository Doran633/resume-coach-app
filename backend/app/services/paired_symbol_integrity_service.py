import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "paired_symbol_integrity.jsonl"
PAIRS = {"“": "”", "‘": "’", "（": "）", "(": ")", "《": "》", "【": "】", "[": "]"}
SPECIAL_REGRESSION = re.compile(r"如何在[^。；\n]{0,24}表达更强\s*和\s*面试能够真实承接[^。；\n]{0,12}之间找到边界")


@dataclass
class SymbolStats:
    stage: str
    generation_result_id: int | None
    checked_text_count: int = 0
    unmatched_symbol_count: int = 0
    empty_quote_count: int = 0
    malformed_quote_sequence_count: int = 0
    fixed_symbol_count: int = 0
    removed_symbol_count: int = 0
    affected_fields: list[str] = field(default_factory=list)


def _balanced_cleanup(text: str, stats: SymbolStats | None = None) -> str:
    value = str(text or "")
    value, regression_count = SPECIAL_REGRESSION.subn("围绕“表达强度”与“面试可承接性”设计经历定位和风险判断机制", value)
    if stats and regression_count:
        stats.malformed_quote_sequence_count += regression_count
        stats.fixed_symbol_count += regression_count
    value, empty_count = re.subn(r"“\s*”|‘\s*’|《\s*》|【\s*】|\(\s*\)", "", value)
    if stats:
        stats.empty_quote_count += empty_count
        stats.removed_symbol_count += empty_count * 2
    value, malformed = re.subn(r"(?:“\s*){2,}|(?:”\s*){2,}", "“", value)
    if stats:
        stats.malformed_quote_sequence_count += malformed
        stats.fixed_symbol_count += malformed

    stack: list[tuple[str, int]] = []
    chars = list(value)
    reverse = {right: left for left, right in PAIRS.items()}
    protected_ranges = [(match.start(), match.end()) for match in re.finditer(r"\[待填写\]", value)]
    protected = lambda index: any(start <= index < end for start, end in protected_ranges)
    remove: set[int] = set()
    for index, char in enumerate(chars):
        if protected(index):
            continue
        if char in PAIRS:
            stack.append((char, index))
        elif char in reverse:
            if stack and stack[-1][0] == reverse[char]:
                stack.pop()
            else:
                remove.add(index)
                if stats:
                    stats.unmatched_symbol_count += 1
                    stats.removed_symbol_count += 1
    for _, index in stack:
        remove.add(index)
        if stats:
            stats.unmatched_symbol_count += 1
            stats.removed_symbol_count += 1
    value = "".join(char for index, char in enumerate(chars) if index not in remove)

    # Markdown markers and backticks are symmetric; unmatched markers are safer removed.
    if value.count("`") % 2:
        value = value.replace("`", "")
        if stats:
            stats.unmatched_symbol_count += 1
            stats.removed_symbol_count += 1
    if value.count("**") % 2:
        value = value.replace("**", "")
        if stats:
            stats.unmatched_symbol_count += 1
            stats.removed_symbol_count += 2
    return re.sub(r"\s+", " ", value).strip()


def has_unbalanced_symbols(text: str) -> bool:
    probe = SymbolStats(stage="evaluate", generation_result_id=None)
    _balanced_cleanup(text, probe)
    return bool(probe.unmatched_symbol_count or probe.empty_quote_count or probe.malformed_quote_sequence_count)


def _write_log(stats: SymbolStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        entry["affected_fields"] = sorted(set(entry["affected_fields"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def ensure_paired_symbol_integrity(
    payload: schemas.GenerationPayload,
    *, stage: str = "unknown", generation_result_id: int | None = None, write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = SymbolStats(stage=stage, generation_result_id=generation_result_id)

    def clean(value: str, field_name: str) -> str:
        before = str(value or "")
        stats.checked_text_count += 1
        after = _balanced_cleanup(before, stats)
        if before != after:
            stats.affected_fields.append(field_name)
        return after

    for key in ["normal_version", "bold_version", "boundary_version", "recommended_version"]:
        setattr(updated, key, clean(getattr(updated, key), key))
    for key in ["confirmed_facts", "missing_questions", "interview_plan", "knowledge_checklist"]:
        setattr(updated, key, [clean(item, f"{key}.{i}") for i, item in enumerate(getattr(updated, key))])
    updated.resume_sections.summary = [clean(item, f"summary.{i}") for i, item in enumerate(updated.resume_sections.summary)]
    updated.resume_sections.skills = [clean(item, f"skills.{i}") for i, item in enumerate(updated.resume_sections.skills)]
    for p_index, project in enumerate(updated.resume_sections.projects):
        for key in ["name", "position", "meta", "time", "intro", "role"]:
            if key in project:
                project[key] = clean(project.get(key, ""), f"projects.{p_index}.{key}")
        project["details"] = [clean(item, f"projects.{p_index}.details.{i}") for i, item in enumerate(project.get("details", []))]
    for c_index, claim in enumerate(updated.claims):
        for key in ["claim", "evidence", "risk_reason", "downgrade_wording"]:
            setattr(claim, key, clean(getattr(claim, key), f"claims.{c_index}.{key}"))
        claim.interview_questions = [clean(item, f"claims.{c_index}.interview_questions.{i}") for i, item in enumerate(claim.interview_questions)]
        claim.knowledge_to_prepare = [clean(item, f"claims.{c_index}.knowledge.{i}") for i, item in enumerate(claim.knowledge_to_prepare)]
    if write_log:
        _write_log(stats)
    return updated
