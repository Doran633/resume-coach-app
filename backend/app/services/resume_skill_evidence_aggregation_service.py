import re
from dataclasses import dataclass, field

from .experience_fact_ledger_service import ExperienceFactLedger, build_experience_fact_ledger
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
    declarations: list[dict] = field(default_factory=list)


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


_SKILL_DECLARATION = re.compile(
    r"^\s*(?:(?:技能(?:与能力)?|基本信息|个人信息)[ \t]*(?:[:：]|\r?\n)\s*)?"
    r"(?:(?P<prefix>(?:(?:我|本人|平时|目前|主要|也|还|但|仅|只|做项目时)\s*)*"
    r"(?P<restriction>不太|不|尚未|没有|未曾)?\s*"
    r"(?:能够使用|接触过|会使用|会用|熟悉|了解|掌握|使用过|用过|使用|用))"
    r"|(?P<label>技能(?:与能力)?[ \t]*(?:[:：]|\r?\n)))"
    r"(?P<items>.+)$", re.S,
)
_TECH_NAME = re.compile(r"\.?[A-Za-z][A-Za-z0-9+#.\-]*(?:[ \t]+[A-Z][A-Za-z0-9+#.\-]*)*")


def _skill_declarations(text: str, base_offset: int = 0) -> list[tuple[str, dict]]:
    """Local self-declarations, not a new experience or Claim classifier."""
    result = []
    previous = []
    carry = None
    for clause in re.finditer(r"[^，,。；;！？]+", text):
        if clause.start() and text[clause.start() - 1] not in '，,':
            previous, carry = [], None
        value = clause.group().strip()
        if previous and not _TECH_NAME.search(value) and re.match(r'^(?:但|不过)?(?:仅|只)(?:用于|用来|在|做过)|^(?:但|不过)(?:尚未|没有|不确定)', value):
            for _, proof in previous:
                proof['source_span'] = (proof['source_span'][0], base_offset + clause.end())
                proof['display_text'] += '，' + value
            carry = None
            continue
        match = _SKILL_DECLARATION.fullmatch(clause.group())
        if not match:
            if carry and re.fullmatch(r'\s*\.?[A-Za-z][A-Za-z0-9+#.\-]*(?:[ \t]+[A-Z][A-Za-z0-9+#.\-]*)*(?:\s*[、和及与/]\s*\.?[A-Za-z][A-Za-z0-9+#.\-]*)*\s*', clause.group()):
                prefix, qualified, source_start = carry
                items, items_start = clause.group(), 0
            else:
                previous, carry = [], None
                continue
        else:
            previous = []
            prefix = match.group('prefix') or ''
            qualified = not bool(match.group('restriction'))
            source_start = clause.start()
            items, items_start = match.group('items'), match.start('items')
        clause_rows = []
        carry = (prefix, qualified, source_start)
        # Conditions and alternatives do not prove an individual's current skill.
        if re.search(r"(?:如果|若|可能|不确定|计划|打算|建议|岗位要求|者优先|的同学|还是|或者)", items):
            carry = None
            continue
        for item in re.finditer(r"[^、和及与/]+", items):
            item_text = item.group()
            candidates = list(_TECH_NAME.finditer(item_text))
            if not candidates:
                candidates = [m for term in sorted(SKILL_TERMS, key=len, reverse=True)
                              if re.search(r'[\u4e00-\u9fff]', term)
                              for m in re.finditer(re.escape(term), item_text)]
                if candidates:
                    candidates = candidates[:1]
            if len(candidates) != 1:
                continue
            term_match = candidates[0]
            start = clause.start() + items_start + item.start() + term_match.start()
            end = start + len(term_match.group())
            # Preserve scope such as '基础', '命令', or '仅用于课程练习'.
            display = re.sub(r"\s+", " ", prefix + item_text).strip()
            clause_rows.append((canonical_skill_term(term_match.group()), {
                'source_span': (base_offset + source_start, base_offset + clause.end()),
                'term_span': (base_offset + start, base_offset + end),
                'display_text': display,
                'qualified': qualified,
            }))
        previous.extend(clause_rows)
        result.extend(clause_rows)
    return result


def skill_evidence_display(row: AggregatedSkillEvidence) -> str:
    """Keep distinct local qualifications; never pick the strongest wording."""
    values = list(dict.fromkeys(d['display_text'] for d in row.declarations))
    return '；'.join(values) if values else row.term


def aggregate_skill_evidence_from_ledger(
    ledger: ExperienceFactLedger,
    *,
    non_experience_context: tuple[tuple[tuple[int, int], str], ...] | None = None,
) -> list[AggregatedSkillEvidence]:
    """Aggregate global skills from the already-compiled request ledger."""
    grouped: dict[str, AggregatedSkillEvidence] = {}
    for fact in ledger.facts:
        fact_text, _ = strip_non_fact_fragments(fact.fact_text)
        if not fact_text:
            continue
        explicit_terms = extract_skill_terms(fact_text)
        if non_experience_context is not None:
            # Already eligible usage facts can name a tool absent from legacy dictionaries.
            usage = [
                row
                for match in re.finditer(r"(?:使用|用过|会用)", fact.fact_text)
                for row in _skill_declarations(fact.fact_text[match.start():])
            ]
            local_terms = [term for term, proof in usage if proof['qualified']]
            explicit_terms = [term for term in explicit_terms if not any(
                term.lower() != other.lower() and contains_skill_term(other, term)
                for other in local_terms
            )] + local_terms
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
    if non_experience_context is not None:
        declarations = []
        for (start, end), text in non_experience_context:
            if end - start != len(text):
                raise ValueError('Background skill source range does not match its original slice')
            declarations.extend(_skill_declarations(text, start))
        for term, proof in declarations:
            proof['source_kind'] = 'background_declaration'
            if not proof['qualified']:
                continue
            key = term.lower()
            if key not in grouped:
                grouped[key] = AggregatedSkillEvidence(term, 'explicit_background', 1.0)
        for term, proof in declarations:
            row = grouped.get(term.lower())
            if row is not None and proof not in row.declarations:
                row.declarations.append(proof)
    return list(grouped.values())


def aggregate_skill_evidence(raw_input: str) -> list[AggregatedSkillEvidence]:
    """Aggregate global skills without relaxing project-level fact boundaries."""
    return aggregate_skill_evidence_from_ledger(build_experience_fact_ledger(raw_input))


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
