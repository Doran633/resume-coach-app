import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import build_experience_fact_ledger
from .long_input_service import TECH_TERMS
from .technical_term_disambiguation_service import (
    best_resolution,
    resolve_technical_terms,
    write_disambiguation_log,
)
from .uncertain_expression_cleanup_service import INFERENCE_TERMS


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_skill_evidence.jsonl"
UNCERTAIN_MARKERS = (
    "如掌握", "如有", "若熟悉", "可补充", "建议学习", "建议掌握", "计划学习",
    "了解即可", "可能使用", "可考虑", "待确认", "熟悉者优先", "掌握者优先",
)
SKILL_TERMS = list(dict.fromkeys([
    *TECH_TERMS, *INFERENCE_TERMS, "Git", "Linux", "Pydantic", "SQLAlchemy",
    "python-docx", "PyPDF2", "Nginx", "systemd", "Vite", "Zustand", "Ant Design",
    "pytest", "Smoke Test", "JMeter", "Groundedness", "Citation", "Retrieval", "Debug Trace",
]))


@dataclass
class SkillEvidenceStats:
    stage: str
    generation_result_id: int | None
    skill_count_before: int = 0
    skill_count_after: int = 0
    verified_skill_count: int = 0
    explicit_skill_count: int = 0
    recovered_skill_count: int = 0
    normalized_skill_count: int = 0
    uncertain_skill_removed_count: int = 0
    uncertainty_marker_removed_count: int = 0
    unsupported_skills: list[str] = field(default_factory=list)
    source_experience_ids: list[str] = field(default_factory=list)
    source_fact_ids: list[str] = field(default_factory=list)


def _contains(text: str, term: str) -> bool:
    # `+` is also a common separator in user input (LoRa+sensor, SSL+Token),
    # so it must not block evidence recognition. Terms such as C++ remain safe
    # because the plus signs are part of the escaped term itself.
    return bool(re.search(rf"(?<![A-Za-z0-9.#-]){re.escape(term)}(?![A-Za-z0-9.#-])", text, re.I))


def _skill_terms(text: str) -> list[str]:
    return [term for term in SKILL_TERMS if _contains(text, term)]


def _canonical_term(term: str) -> str:
    aliases = {
        "codebuddy": "CodeBuddy", "lora": "LoRa", "地图api": "地图 API",
        "token": "Token", "ssl": "SSL", "智能制图": "数据可视化",
    }
    return aliases.get(re.sub(r"\s+", "", term).lower(), term)


def _has_grounded_term(text: str, term: str) -> bool:
    contexts = re.split(r"(?<=[。！？；;])\s*|\n+", str(text or ""))
    excluded = re.compile(r"目标岗位|岗位(?:需要|要求)|JD|建议(?:学习|掌握)|计划学习|希望学习|未使用|没有使用|不熟悉", re.I)
    return any(_contains(context, term) and not excluded.search(context) for context in contexts)


def _visible_evidence(payload: schemas.GenerationPayload, raw_input: str) -> str:
    sections = payload.resume_sections
    project_text = []
    for project in sections.projects:
        project_text.extend(str(project.get(key) or "") for key in ["name", "intro", "role"])
        project_text.extend(str(item) for item in project.get("details", []) or [])
    return "\n".join([raw_input, *payload.confirmed_facts, *project_text])


def _clean_marker(text: str) -> tuple[str, int]:
    cleaned = text
    count = 0
    for marker in UNCERTAIN_MARKERS:
        cleaned, changed = re.subn(rf"[（(][^）)]*{re.escape(marker)}[^）)]*[）)]", "", cleaned)
        count += changed
        cleaned, changed = re.subn(re.escape(marker), "", cleaned)
        count += changed
    cleaned = re.sub(r"\s*[,，、]\s*[,，、]+", "、", cleaned)
    return cleaned.strip(" ，,、；;：:"), count


def _rebuild_skill_line(line: str, supported: list[str]) -> str:
    label_match = re.match(r"^([^：:]{1,16}[：:])", line)
    label = label_match.group(1) if label_match else ""
    if supported:
        return f"{label}{'、'.join(dict.fromkeys(supported))}"
    # Preserve non-enumerated prose only when it contains no recognized technology.
    return line if not _skill_terms(line) else ""


def _write_log(stats: SkillEvidenceStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        entry["unsupported_skills"] = sorted(set(entry["unsupported_skills"]))
        entry["source_experience_ids"] = sorted(set(entry["source_experience_ids"]))
        entry["source_fact_ids"] = sorted(set(entry["source_fact_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def guard_resume_skill_evidence(
    payload: schemas.GenerationPayload,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = SkillEvidenceStats(stage=stage, generation_result_id=generation_result_id)
    stats.skill_count_before = len(updated.resume_sections.skills)
    evidence = _visible_evidence(updated, raw_input)
    ledger = build_experience_fact_ledger(raw_input)
    resolutions = resolve_technical_terms(raw_input)
    if write_log:
        write_disambiguation_log(
            resolutions, stage=stage, generation_result_id=generation_result_id,
        )
    supported_by_term: dict[str, list] = {}
    for fact in ledger.facts:
        for term in _skill_terms(fact.fact_text):
            if _has_grounded_term(fact.fact_text, term):
                canonical = _canonical_term(term)
                if canonical.lower() == "token":
                    resolution = best_resolution(
                        [item for item in resolutions if item.fact_id == fact.fact_id], "Token",
                    )
                    if not resolution or not resolution.category or resolution.confidence < 0.65:
                        continue
                stats.normalized_skill_count += canonical != term
                supported_by_term.setdefault(canonical.lower(), []).append(fact)
                stats.explicit_skill_count += 1

    cleaned_lines: list[str] = []
    for raw_line in updated.resume_sections.skills:
        line = str(raw_line or "").strip()
        if not line:
            continue
        terms = _skill_terms(line)
        uncertain = any(marker in line for marker in UNCERTAIN_MARKERS)
        cleaned, marker_count = _clean_marker(line)
        stats.uncertainty_marker_removed_count += marker_count
        supported: list[str] = []
        for term in terms:
            term = _canonical_term(term)
            facts = supported_by_term.get(term.lower(), [])
            explicit = _has_grounded_term(evidence, term)
            # Remove the current skill line from evidence: a generated skill cannot prove itself.
            explicit = explicit and _has_grounded_term("\n".join([raw_input, *payload.confirmed_facts, *[
                str(value) for project in payload.resume_sections.projects
                for value in [project.get("intro", ""), project.get("role", ""), *(project.get("details", []) or [])]
            ]]), term)
            if explicit or facts:
                supported.append(term)
                stats.verified_skill_count += 1
                for fact in facts:
                    stats.source_experience_ids.append(fact.experience_id)
                    stats.source_fact_ids.append(fact.fact_id)
            else:
                stats.unsupported_skills.append(term)
                if uncertain:
                    stats.uncertain_skill_removed_count += 1
        rebuilt = _rebuild_skill_line(cleaned, supported)
        if rebuilt and rebuilt not in cleaned_lines:
            cleaned_lines.append(rebuilt)

    # A structurally valid LLM response may still leave skills empty. Recover only
    # terms explicitly grounded in the experience ledger; target-role terms never
    # participate in this path.
    represented = {term.lower() for line in cleaned_lines for term in _skill_terms(line)}
    recovered = [
        _canonical_term(next(
            term for term in SKILL_TERMS
            if _canonical_term(term).lower() == key
        ))
        for key, facts in supported_by_term.items()
        if key not in represented
    ]
    recovered = list(dict.fromkeys(recovered))
    canonical_order = {
        _canonical_term(term).lower(): index
        for index, term in enumerate(SKILL_TERMS)
    }
    recovered.sort(key=lambda term: canonical_order.get(term.lower(), len(canonical_order)))
    if recovered:
        cleaned_lines.append("技能证据：" + "、".join(recovered))
        stats.recovered_skill_count = len(recovered)

    updated.resume_sections.skills = cleaned_lines
    stats.skill_count_after = len(cleaned_lines)
    if write_log:
        _write_log(stats)
    return updated


def evaluate_skill_evidence(payload: schemas.GenerationPayload, raw_input: str) -> int:
    evidence = _visible_evidence(payload, raw_input)
    terms = [term for line in payload.resume_sections.skills for term in _skill_terms(line)]
    unsupported = sum(not _has_grounded_term(evidence.replace("\n".join(payload.resume_sections.skills), ""), term) for term in terms)
    uncertainty = sum(any(marker in line for marker in UNCERTAIN_MARKERS) for line in payload.resume_sections.skills)
    return max(0, round(100 - (unsupported + uncertainty) / max(1, len(terms)) * 100))
