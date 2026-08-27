import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_whitespace_quality.jsonl"
HAN = r"\u3400-\u4dbf\u4e00-\u9fff"
CHINESE_PUNCTUATION = "，。；：！？、）】》”’"
OPENING_PUNCTUATION = "（【《“‘"
PROTECTED_PHRASES = (
    "AI Agent", "JSON Schema", "Resume Section Fallback", "Experience ID",
    "Experience Fact Ledger", "Claim Risk", "Smoke Test", "Debug Trace",
    "Citation Source Cards", "Groundedness Evaluation", "Retrieval Evaluation",
    "Ant Design", "Visual Studio Code", "FastAPI API",
)
BROKEN_PROTECTED = {re.sub(r"\s+", "", phrase).lower(): phrase for phrase in PROTECTED_PHRASES}
URL_OR_CODE = re.compile(
    r"https?://[^\s，。；]+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/[^\s，。；]*)?|"
    r"`[^`]+`|\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+\b"
)


@dataclass
class WhitespaceStats:
    stage: str
    generation_result_id: int | None
    checked_text_count: int = 0
    abnormal_space_count: int = 0
    repeated_space_fixed_count: int = 0
    special_space_fixed_count: int = 0
    chinese_internal_space_fixed_count: int = 0
    punctuation_space_fixed_count: int = 0
    quote_inner_space_fixed_count: int = 0
    protected_phrase_count: int = 0
    protected_phrase_restored_count: int = 0
    protected_phrase_restore_failed_count: int = 0
    affected_fields: list[str] = field(default_factory=list)
    affected_experience_ids: list[str] = field(default_factory=list)


def _protect(value: str, stats: WhitespaceStats | None) -> tuple[str, dict[str, str]]:
    protected: dict[str, str] = {}

    def store(text: str) -> str:
        token = f"WSPROTECTEDTOKEN{len(protected)}X"
        protected[token] = text
        return token

    value = URL_OR_CODE.sub(lambda match: store(match.group(0)), value)
    for phrase in sorted(PROTECTED_PHRASES, key=len, reverse=True):
        pattern = re.compile(re.escape(phrase), re.I)
        value, count = pattern.subn(lambda match: store(phrase), value)
        if stats:
            stats.protected_phrase_count += count
    return value, protected


def _restore_broken_phrases(value: str, stats: WhitespaceStats | None) -> str:
    # Repair only known multiword technical phrases that were already collapsed upstream.
    for collapsed, phrase in BROKEN_PROTECTED.items():
        pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(collapsed)}(?![A-Za-z0-9])", re.I)
        value, count = pattern.subn(phrase, value)
        if stats:
            stats.protected_phrase_restored_count += count
    return value


def normalize_resume_whitespace(text: str, stats: WhitespaceStats | None = None) -> str:
    original = str(text or "")
    value = original
    if stats:
        stats.checked_text_count += 1

    special_before = len(re.findall(r"[\u00a0\u3000\u200b\ufeff\t\r\n]", value))
    # Zero-width characters between ASCII tokens represent a likely lost separator; elsewhere remove them.
    value = re.sub(r"(?<=[A-Za-z0-9])(?:\u200b|\ufeff)(?=[A-Za-z0-9])", " ", value)
    value = re.sub(r"[\u200b\ufeff]", "", value)
    value = re.sub(r"[\u00a0\u3000\t\r\n]+", " ", value)
    if stats:
        stats.special_space_fixed_count += special_before

    value = _restore_broken_phrases(value, stats)
    value, protected = _protect(value, stats)

    value, repeated = re.subn(r" {2,}", " ", value)
    if stats:
        stats.repeated_space_fixed_count += repeated

    value, chinese_spaces = re.subn(rf"(?<=[{HAN}]) +(?=[{HAN}])", "", value)
    if stats:
        stats.chinese_internal_space_fixed_count += chinese_spaces

    punctuation_count = 0
    value, count = re.subn(rf" +(?=[{re.escape(CHINESE_PUNCTUATION)}])", "", value)
    punctuation_count += count
    value, count = re.subn(rf"(?<=[{re.escape(CHINESE_PUNCTUATION)}]) +", "", value)
    punctuation_count += count
    if stats:
        stats.punctuation_space_fixed_count += punctuation_count

    quote_count = 0
    value, count = re.subn(rf"(?<=[{re.escape(OPENING_PUNCTUATION)}]) +", "", value)
    quote_count += count
    value, count = re.subn(rf" +(?=[{re.escape(CHINESE_PUNCTUATION)}])", "", value)
    quote_count += count
    if stats:
        stats.quote_inner_space_fixed_count += quote_count

    for token, phrase in protected.items():
        if token in value:
            value = value.replace(token, phrase)
            if stats:
                stats.protected_phrase_restored_count += 1
        elif stats:
            stats.protected_phrase_restore_failed_count += 1

    value = value.strip()
    if stats and value != original:
        stats.abnormal_space_count += max(
            1, special_before + repeated + chinese_spaces + punctuation_count + quote_count,
        )
    return value


def count_whitespace_issues(text: str) -> int:
    probe = WhitespaceStats(stage="evaluate", generation_result_id=None)
    normalize_resume_whitespace(text, probe)
    return probe.abnormal_space_count + probe.protected_phrase_restore_failed_count


def count_broken_protected_phrases(text: str) -> int:
    value = str(text or "").lower()
    return sum(bool(re.search(rf"(?<![a-z0-9]){re.escape(collapsed)}(?![a-z0-9])", value)) for collapsed in BROKEN_PROTECTED)


def _write_log(stats: WhitespaceStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        entry["affected_fields"] = sorted(set(entry["affected_fields"]))
        entry["affected_experience_ids"] = sorted(set(entry["affected_experience_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def ensure_resume_whitespace_quality(
    payload: schemas.GenerationPayload,
    *, stage: str = "unknown", generation_result_id: int | None = None, write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = WhitespaceStats(stage=stage, generation_result_id=generation_result_id)

    def clean(value: str, field_name: str, source_id: str = "") -> str:
        before = str(value or "")
        after = normalize_resume_whitespace(before, stats)
        if before != after:
            stats.affected_fields.append(field_name)
            if source_id:
                stats.affected_experience_ids.append(source_id)
        return after

    for key in ["normal_version", "bold_version", "boundary_version", "recommended_version"]:
        setattr(updated, key, clean(getattr(updated, key), key))
    for key in ["confirmed_facts", "missing_questions", "interview_plan", "knowledge_checklist"]:
        setattr(updated, key, [clean(item, f"{key}.{i}") for i, item in enumerate(getattr(updated, key))])
    for key, value in list(updated.resume_sections.personal_info.items()):
        updated.resume_sections.personal_info[key] = clean(value, f"personal_info.{key}")
    for key, value in list(updated.resume_sections.education.items()):
        updated.resume_sections.education[key] = clean(value, f"education.{key}")
    updated.resume_sections.summary = [clean(item, f"summary.{i}") for i, item in enumerate(updated.resume_sections.summary)]
    updated.resume_sections.skills = [clean(item, f"skills.{i}") for i, item in enumerate(updated.resume_sections.skills)]
    for p_index, project in enumerate(updated.resume_sections.projects):
        source_id = str(project.get("source_experience_id") or "")
        for key in ["name", "position", "meta", "time", "intro", "role"]:
            if key in project:
                project[key] = clean(project.get(key, ""), f"projects.{p_index}.{key}", source_id)
        project["details"] = [clean(item, f"projects.{p_index}.details.{i}", source_id) for i, item in enumerate(project.get("details", []))]
    for c_index, claim in enumerate(updated.claims):
        for key in ["claim", "evidence", "risk_reason", "downgrade_wording"]:
            setattr(claim, key, clean(getattr(claim, key), f"claims.{c_index}.{key}"))
        claim.interview_questions = [clean(item, f"claims.{c_index}.questions.{i}") for i, item in enumerate(claim.interview_questions)]
        claim.knowledge_to_prepare = [clean(item, f"claims.{c_index}.knowledge.{i}") for i, item in enumerate(claim.knowledge_to_prepare)]
    if write_log:
        _write_log(stats)
    return updated
