import re
from dataclasses import dataclass, field

from .experience_fact_ledger_service import build_experience_fact_ledger
from .input_content_classification_service import strip_non_fact_fragments
from .long_input_service import TECH_TERMS
from .uncertain_expression_cleanup_service import INFERENCE_TERMS


SKILL_TERMS = list(dict.fromkeys([
    *TECH_TERMS, *INFERENCE_TERMS, "Git", "Linux", "Pydantic", "SQLAlchemy",
    "python-docx", "PyPDF2", "Nginx", "systemd", "Vite", "Zustand", "Ant Design",
    "pytest", "Smoke Test", "JMeter", "Groundedness", "Citation", "Retrieval", "Debug Trace",
]))
PYTHON_ECOSYSTEM_TERMS = ("FastAPI", "SQLAlchemy", "Pydantic", "pytest", "Django", "Flask")


@dataclass
class AggregatedSkillEvidence:
    term: str
    evidence_type: str
    confidence: float
    source_experience_ids: list[str] = field(default_factory=list)
    source_fact_ids: list[str] = field(default_factory=list)
    inferred_from: list[str] = field(default_factory=list)


def contains_skill_term(text: str, term: str) -> bool:
    return bool(re.search(rf"(?<![A-Za-z0-9.#-]){re.escape(term)}(?![A-Za-z0-9.#-])", text, re.I))


def extract_skill_terms(text: str) -> list[str]:
    return [term for term in SKILL_TERMS if contains_skill_term(text, term)]


def canonical_skill_term(term: str) -> str:
    aliases = {
        "codebuddy": "CodeBuddy", "lora": "LoRa", "地图api": "地图 API",
        "token": "Token", "ssl": "SSL", "智能制图": "数据可视化",
    }
    return aliases.get(re.sub(r"\s+", "", term).lower(), term)


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _add_evidence(
    grouped: dict[str, AggregatedSkillEvidence],
    *,
    term: str,
    evidence_type: str,
    confidence: float,
    experience_id: str,
    fact_id: str,
    inferred_from: str = "",
) -> None:
    canonical = canonical_skill_term(term)
    key = canonical.lower()
    row = grouped.get(key)
    if row is None:
        row = AggregatedSkillEvidence(
            term=canonical,
            evidence_type=evidence_type,
            confidence=confidence,
        )
        grouped[key] = row
    elif evidence_type == "explicit":
        row.evidence_type = "explicit"
        row.confidence = 1.0
    else:
        row.confidence = max(row.confidence, confidence)
    _append_unique(row.source_experience_ids, experience_id)
    _append_unique(row.source_fact_ids, fact_id)
    _append_unique(row.inferred_from, inferred_from)


def aggregate_skill_evidence(raw_input: str) -> list[AggregatedSkillEvidence]:
    """Aggregate global skills without relaxing project-level fact boundaries."""
    grouped: dict[str, AggregatedSkillEvidence] = {}
    for fact in build_experience_fact_ledger(raw_input).facts:
        fact_text, _ = strip_non_fact_fragments(fact.fact_text)
        if not fact_text:
            continue
        explicit_terms = extract_skill_terms(fact_text)
        for term in explicit_terms:
            _add_evidence(
                grouped,
                term=term,
                evidence_type="explicit",
                confidence=1.0,
                experience_id=fact.experience_id,
                fact_id=fact.fact_id,
            )
        python_sources = [
            term for term in PYTHON_ECOSYSTEM_TERMS
            if contains_skill_term(fact_text, term)
        ]
        for source_term in python_sources:
            _add_evidence(
                grouped,
                term="Python",
                evidence_type="deterministic_inference",
                confidence=0.98,
                experience_id=fact.experience_id,
                fact_id=fact.fact_id,
                inferred_from=source_term,
            )
    return list(grouped.values())


def aggregate_historical_project_skill_evidence(payload: object) -> list[AggregatedSkillEvidence]:
    """Recover skills from persisted project bodies only when raw input is unavailable."""
    grouped: dict[str, AggregatedSkillEvidence] = {}
    sections = getattr(payload, "resume_sections", None)
    projects = getattr(sections, "projects", []) if sections is not None else []
    for project in projects:
        if not isinstance(project, dict):
            continue
        experience_id = str(project.get("source_experience_id") or "")
        project_fact_ids = [str(item) for item in project.get("source_fact_ids", []) if item]
        detail_fact_rows = project.get("detail_fact_ids", [])
        body_rows = [
            (str(project.get("intro") or ""), project_fact_ids),
            (str(project.get("role") or ""), project_fact_ids),
        ]
        for index, detail in enumerate(project.get("details", []) or []):
            fact_ids = (
                [str(item) for item in detail_fact_rows[index] if item]
                if index < len(detail_fact_rows) and isinstance(detail_fact_rows[index], list)
                else project_fact_ids
            )
            body_rows.append((str(detail or ""), fact_ids))
        for body_text, fact_ids in body_rows:
            for term in extract_skill_terms(body_text):
                _add_evidence(
                    grouped,
                    term=term,
                    evidence_type="deterministic_inference",
                    confidence=0.8,
                    experience_id=experience_id,
                    fact_id=fact_ids[0] if fact_ids else "",
                    inferred_from="historical_project_body",
                )
            for source_term in PYTHON_ECOSYSTEM_TERMS:
                if contains_skill_term(body_text, source_term):
                    _add_evidence(
                        grouped,
                        term="Python",
                        evidence_type="deterministic_inference",
                        confidence=0.8,
                        experience_id=experience_id,
                        fact_id=fact_ids[0] if fact_ids else "",
                        inferred_from=source_term,
                    )
    return list(grouped.values())
