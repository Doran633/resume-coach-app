import html
import json
import math
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import build_experience_fact_ledger, fact_match_score
from .experience_identity_service import build_experience_identities
from .fact_coverage_guard_service import guard_fact_coverage
from .fact_guard_service import guard_hard_facts
from .paired_symbol_integrity_service import ensure_paired_symbol_integrity, has_unbalanced_symbols
from .resume_experience_validity_service import classify_experience_project, ensure_resume_experience_validity
from .resume_fact_dedup_service import same_fact_action, similarity
from .resume_output_firewall_service import guard_resume_output
from .resume_semantic_unit_service import ensure_semantic_units, fragment_reasons
from .resume_skill_evidence_guard_service import _skill_terms, evaluate_skill_evidence, guard_resume_skill_evidence
from .resume_summary_quality_service import ensure_resume_summary_quality
from .resume_typography_quality_service import clean_typography, ensure_typography_quality
from .resume_whitespace_quality_service import ensure_resume_whitespace_quality, normalize_resume_whitespace


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_delivery_quality_gate.jsonl"

ISSUE_CODES = (
    "EMPTY_VISIBLE_SECTION",
    "EMPTY_PROJECT_BODY",
    "INVALID_EXPERIENCE_ENTITY",
    "CROSS_EXPERIENCE_FACT",
    "UNSUPPORTED_HARD_FACT",
    "DUPLICATE_FACT",
    "LOW_INFORMATION_GAIN",
    "INCOMPLETE_SENTENCE",
    "SEMANTIC_ROLE_CONFUSION",
    "INVALID_CHARACTER",
    "INTERNAL_FIELD_LEAK",
    "COACH_LANGUAGE_LEAK",
    "SKILL_WITHOUT_EVIDENCE",
    "LOW_HIGH_VALUE_FACT_COVERAGE",
)

INTERNAL_FIELD_REPLACEMENTS = {
    "source_experience_id": "经历来源标识",
    "source_fact_ids": "事实来源标识",
    "detail_fact_ids": "详情事实来源",
    "fact_id": "事实来源标识",
    "raw_text": "原始经历文本",
    "explicit_metrics": "明确指标事实",
    "retrieved_count": "检索结果数量",
}
INTERNAL_MARKERS = tuple(INTERNAL_FIELD_REPLACEMENTS) + (
    "section summary chunk", "section 个人优势 chunk", "debug payload", "traceback",
)
INTERNAL_DEBUG_MARKERS = (
    "section summary chunk", "section 个人优势 chunk", "debug payload", "traceback",
)
COACH_MARKERS = (
    "如果被问到", "建议补充", "可面试承接", "准备降级表达", "面试时可以",
    "用户提供的真实经历", "根据用户原文", "具体职责以", "以用户原文为准",
    "希望包装", "帮我包装", "完全无法解释", "岗位匹配度",
)
INVALID_CHAR_PATTERN = re.compile(
    r"&(?:#x?[0-9a-f]+|nbsp);|[\u200b-\u200f\u202a-\u202e\u2060\ufeff\ufffd]|"
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]",
    re.IGNORECASE,
)
MARKDOWN_RESIDUE = re.compile(r"(?:```(?:\w+)?|```)|^\s*#{1,6}\s+", re.MULTILINE)


@dataclass
class ResumeQualityIssue:
    issue_code: str
    severity: str
    field_path: str
    source_experience_id: str = ""
    source_fact_ids: list[str] = field(default_factory=list)
    confidence: float = 1.0
    repair_action: str = ""


@dataclass
class DeliveryGateStats:
    created_at: str
    generation_result_id: int | None
    stage: str
    issue_count_by_code: dict[str, int]
    critical_issue_count: int = 0
    repaired_issue_count: int = 0
    unresolved_issue_count: int = 0
    projects_before: int = 0
    projects_after: int = 0
    details_removed_count: int = 0
    facts_recovered_count: int = 0
    high_value_coverage_before: float = 1.0
    high_value_coverage_after: float = 1.0
    internal_leak_count: int = 0
    invalid_character_count: int = 0
    gate_passed: bool = True
    issues: list[ResumeQualityIssue] = field(default_factory=list)


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalized(value: object) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9+#./-]", "", _text(value)).lower()


def _source_ids(project: dict) -> set[str]:
    values: set[str] = set()
    for key in ("source_experience_id", "source_experience_ids", "merged_source_experience_ids"):
        raw = project.get(key)
        rows = raw if isinstance(raw, list) else [raw]
        values.update(_text(item) for item in rows if _text(item))
    return values


def _fact_ids(project: dict, detail_index: int | None = None) -> list[str]:
    if detail_index is not None:
        rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        if detail_index < len(rows) and isinstance(rows[detail_index], list):
            return [str(item) for item in rows[detail_index] if str(item)]
        return []
    values = [str(item) for item in project.get("source_fact_ids", []) or [] if str(item)]
    return list(dict.fromkeys(values))


def _visible_text(payload: schemas.GenerationPayload) -> str:
    sections = payload.resume_sections
    rows = [*map(str, sections.summary), *map(str, sections.skills)]
    for project in sections.projects:
        rows.extend(_text(project.get(key)) for key in ("name", "position", "meta", "time", "intro", "role"))
        rows.extend(_text(item) for item in project.get("details", []) or [])
    return "\n".join(row for row in rows if row)


def _project_text(project: dict) -> str:
    return "\n".join([
        _text(project.get("intro")), _text(project.get("role")),
        *[_text(item) for item in project.get("details", []) or []],
    ])


def _high_value_coverage(payload: schemas.GenerationPayload, raw_input: str) -> tuple[float, set[str]]:
    high_facts = [
        fact for fact in build_experience_fact_ledger(raw_input).facts
        if fact.importance == "high" and fact.resume_ready_text
    ]
    if not high_facts:
        return 1.0, set()
    projects_by_source: dict[str, list[dict]] = {}
    for project in payload.resume_sections.projects:
        for source_id in _source_ids(project):
            projects_by_source.setdefault(source_id, []).append(project)
    covered: set[str] = set()
    for fact in high_facts:
        visible = "\n".join(_project_text(project) for project in projects_by_source.get(fact.experience_id, []))
        if fact_match_score(visible, fact) >= 0.48:
            covered.add(fact.fact_id)
    return len(covered) / len(high_facts), covered


def measure_high_value_fact_coverage(payload: schemas.GenerationPayload, raw_input: str) -> float:
    return _high_value_coverage(payload, raw_input)[0]


def _add_issue(
    issues: list[ResumeQualityIssue],
    code: str,
    severity: str,
    path: str,
    project: dict | None = None,
    *,
    confidence: float = 1.0,
    repair_action: str = "",
    fact_ids: list[str] | None = None,
) -> None:
    issues.append(ResumeQualityIssue(
        issue_code=code,
        severity=severity,
        field_path=path,
        source_experience_id=_text((project or {}).get("source_experience_id")),
        source_fact_ids=list(dict.fromkeys(fact_ids or _fact_ids(project or {}))),
        confidence=round(confidence, 3),
        repair_action=repair_action,
    ))


def _clean_visible_text(value: object) -> tuple[str, set[str]]:
    original = _text(value)
    if not original:
        return "", set()
    reasons: set[str] = set()
    cleaned = original
    if INVALID_CHAR_PATTERN.search(cleaned):
        cleaned = html.unescape(cleaned).replace("\ufffd", "")
        cleaned = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", cleaned)
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", cleaned)
        reasons.add("invalid_character")
    if MARKDOWN_RESIDUE.search(cleaned):
        cleaned = MARKDOWN_RESIDUE.sub("", cleaned)
        reasons.add("markdown_residue")
    for internal, replacement in INTERNAL_FIELD_REPLACEMENTS.items():
        if re.search(re.escape(internal), cleaned, re.IGNORECASE):
            cleaned = re.sub(re.escape(internal), replacement, cleaned, flags=re.IGNORECASE)
            reasons.add("internal_field")
    if any(marker.lower() in cleaned.lower() for marker in INTERNAL_DEBUG_MARKERS):
        return "", reasons | {"internal_field"}
    for marker in COACH_MARKERS:
        if marker not in cleaned:
            continue
        prefix = cleaned.split(marker, 1)[0].rstrip(" ，,、；;：:")
        cleaned = prefix if len(_normalized(prefix)) >= 12 else ""
        reasons.add("coach_language")
        break
    cleaned = re.sub(r"、\s*、+", "、", cleaned)
    cleaned = re.sub(r"，\s*，+", "，", cleaned)
    cleaned = re.sub(r"。\s*。+", "。", cleaned)
    cleaned = normalize_resume_whitespace(clean_typography(cleaned))
    return cleaned.strip(), reasons


def _fragment_severity(reasons: set[str]) -> str:
    """Only deterministic sentence breakage blocks delivery.

    A technical term list can still be a complete resume sentence. Ambiguous
    semantic-unit signals remain observable without triggering destructive repair.
    """
    critical_reasons = {"empty", "trailing_dependency", "incomplete_range", "trailing_separator"}
    warning_reasons = {"leading_dependency", "metric_without_relation"}
    if reasons & critical_reasons:
        return "critical"
    if reasons & warning_reasons:
        return "warning"
    return "observe"


def _clean_visible_fields(payload: schemas.GenerationPayload, issues: list[ResumeQualityIssue]) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    sections = updated.resume_sections
    for field_name in ("summary", "skills"):
        cleaned_rows = []
        for index, value in enumerate(getattr(sections, field_name)):
            cleaned, reasons = _clean_visible_text(value)
            if reasons:
                code = (
                    "COACH_LANGUAGE_LEAK" if "coach_language" in reasons
                    else "INTERNAL_FIELD_LEAK" if "internal_field" in reasons
                    else "INVALID_CHARACTER"
                )
                _add_issue(issues, code, "critical", f"resume_sections.{field_name}.{index}", repair_action="normalize_visible_text")
            if cleaned and cleaned not in cleaned_rows:
                cleaned_rows.append(cleaned)
        setattr(sections, field_name, cleaned_rows)
    for project_index, project in enumerate(sections.projects):
        for key in ("name", "position", "meta", "time", "intro", "role"):
            cleaned, reasons = _clean_visible_text(project.get(key))
            if reasons:
                code = (
                    "COACH_LANGUAGE_LEAK" if "coach_language" in reasons
                    else "INTERNAL_FIELD_LEAK" if "internal_field" in reasons
                    else "INVALID_CHARACTER"
                )
                _add_issue(issues, code, "critical", f"resume_sections.projects.{project_index}.{key}", project, repair_action="normalize_visible_text")
            project[key] = cleaned
        details = []
        fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        kept_fact_rows = []
        for detail_index, value in enumerate(project.get("details", []) or []):
            cleaned, reasons = _clean_visible_text(value)
            if reasons:
                code = (
                    "COACH_LANGUAGE_LEAK" if "coach_language" in reasons
                    else "INTERNAL_FIELD_LEAK" if "internal_field" in reasons
                    else "INVALID_CHARACTER"
                )
                _add_issue(
                    issues, code, "critical", f"resume_sections.projects.{project_index}.details.{detail_index}",
                    project, repair_action="normalize_visible_text", fact_ids=_fact_ids(project, detail_index),
                )
            if cleaned and cleaned not in details:
                details.append(cleaned)
                kept_fact_rows.append(fact_rows[detail_index] if detail_index < len(fact_rows) else [])
        project["details"] = details
        project["detail_fact_ids"] = kept_fact_rows
    return updated


def _recover_projects_when_empty(payload: schemas.GenerationPayload, raw_input: str, issues: list[ResumeQualityIssue]) -> tuple[schemas.GenerationPayload, int]:
    if payload.resume_sections.projects:
        return payload, 0
    updated = payload.model_copy(deep=True)
    ledger = build_experience_fact_ledger(raw_input)
    recovered = 0
    for identity in build_experience_identities(raw_input)[:5]:
        facts = [fact for fact in ledger.for_experience(identity.experience_id) if fact.resume_ready_text]
        if not facts:
            continue
        facts.sort(key=lambda fact: {"high": 0, "medium": 1, "low": 2}[fact.importance])
        intro = facts[0].resume_ready_text
        details = [fact.resume_ready_text for fact in facts[1:7] if fact.resume_ready_text != intro]
        updated.resume_sections.projects.append({
            "name": identity.title,
            "meta": identity.experience_type,
            "time": "[待填写]",
            "intro": intro,
            "role": "",
            "details": details,
            "source_experience_id": identity.experience_id,
            "source_fact_ids": [fact.fact_id for fact in facts[:7]],
            "detail_fact_ids": [[fact.fact_id] for fact in facts[1:7] if fact.resume_ready_text != intro],
        })
        recovered += len(facts[:7])
    return updated, recovered


def _deduplicate_project_fields(payload: schemas.GenerationPayload, issues: list[ResumeQualityIssue]) -> tuple[schemas.GenerationPayload, int]:
    updated = payload.model_copy(deep=True)
    removed = 0
    for project_index, project in enumerate(updated.resume_sections.projects):
        intro = _text(project.get("intro"))
        role = _text(project.get("role"))
        if role and intro and similarity(role, intro) >= 0.92:
            project["role"] = ""
            removed += 1
            _add_issue(issues, "SEMANTIC_ROLE_CONFUSION", "warning", f"resume_sections.projects.{project_index}.role", project, repair_action="remove_repeated_role")

        details = [_text(item) for item in project.get("details", []) or [] if _text(item)]
        fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        semantic_budget = max(1, math.floor(len(details) * 0.25)) if details else 0
        semantic_removed = 0
        kept: list[str] = []
        kept_ids: list[list[str]] = []
        for index, detail in enumerate(details):
            ids = _fact_ids(project, index)
            exact_duplicate = any(_normalized(detail) == _normalized(existing) for existing in [intro, role, *kept] if existing)
            semantic_match_index = next((
                position for position, existing in enumerate(kept)
                if similarity(detail, existing) >= 0.94 and same_fact_action(detail, existing)
            ), -1)
            distinct_fact_ids = bool(ids and semantic_match_index >= 0 and set(ids).isdisjoint(kept_ids[semantic_match_index]))
            if exact_duplicate:
                removed += 1
                _add_issue(issues, "DUPLICATE_FACT", "critical", f"resume_sections.projects.{project_index}.details.{index}", project, repair_action="remove_exact_duplicate", fact_ids=ids)
                continue
            if semantic_match_index >= 0 and not distinct_fact_ids and semantic_removed < semantic_budget:
                removed += 1
                semantic_removed += 1
                _add_issue(issues, "DUPLICATE_FACT", "warning", f"resume_sections.projects.{project_index}.details.{index}", project, confidence=0.95, repair_action="remove_high_confidence_semantic_duplicate", fact_ids=ids)
                continue
            kept.append(detail)
            kept_ids.append(ids if index < len(fact_rows) else ids)
        project["details"] = kept
        project["detail_fact_ids"] = kept_ids
        project["source_fact_ids"] = list(dict.fromkeys([*_fact_ids(project), *[fact_id for row in kept_ids for fact_id in row]]))
    return updated, removed


def _cross_experience_count(payload: schemas.GenerationPayload, raw_input: str) -> int:
    ledger = build_experience_fact_ledger(raw_input)
    count = 0
    for project in payload.resume_sections.projects:
        local_ids = _source_ids(project)
        local_facts = [fact for fact in ledger.facts if fact.experience_id in local_ids]
        for detail in project.get("details", []) or []:
            all_scores = sorted(((fact_match_score(str(detail), fact), fact) for fact in ledger.facts), reverse=True, key=lambda row: row[0])
            local_score = max((fact_match_score(str(detail), fact) for fact in local_facts), default=0.0)
            if all_scores and all_scores[0][0] >= 0.78 and all_scores[0][1].experience_id not in local_ids and local_score < 0.35:
                count += 1
    return count


def _repair_strong_cross_experience_terms(
    payload: schemas.GenerationPayload,
    raw_input: str,
    issues: list[ResumeQualityIssue],
) -> tuple[schemas.GenerationPayload, int]:
    """Move only details carrying at least two terms unique to another experience."""
    updated = payload.model_copy(deep=True)
    identities = build_experience_identities(raw_input)
    if len(identities) < 2:
        return updated, 0
    identity_terms: dict[str, set[str]] = {
        identity.experience_id: {
            _text(term) for term in [*identity.explicit_tech_terms, *identity.evidence_terms]
            if len(_normalized(term)) >= 2
        }
        for identity in identities
    }
    term_owners: dict[str, set[str]] = {}
    for experience_id, terms in identity_terms.items():
        for term in terms:
            term_owners.setdefault(term.lower(), set()).add(experience_id)
    unique_terms = {
        experience_id: {term for term in terms if len(term_owners.get(term.lower(), set())) == 1}
        for experience_id, terms in identity_terms.items()
    }
    projects_by_source = {
        _text(project.get("source_experience_id")): project
        for project in updated.resume_sections.projects
        if _text(project.get("source_experience_id"))
    }
    moved = 0
    for project_index, project in enumerate(updated.resume_sections.projects):
        source_id = _text(project.get("source_experience_id"))
        if not source_id:
            continue
        details = list(project.get("details", []) or [])
        fact_rows = list(project.get("detail_fact_ids", []) or [])
        kept_details: list[str] = []
        kept_fact_rows: list[list[str]] = []
        for detail_index, detail in enumerate(details):
            value = _text(detail)
            local_matches = {term for term in unique_terms.get(source_id, set()) if term.lower() in value.lower()}
            foreign_ranked = sorted(
                (
                    ({term for term in terms if term.lower() in value.lower()}, experience_id)
                    for experience_id, terms in unique_terms.items()
                    if experience_id != source_id
                ),
                key=lambda item: len(item[0]),
                reverse=True,
            )
            foreign_matches, foreign_id = foreign_ranked[0] if foreign_ranked else (set(), "")
            destination = projects_by_source.get(foreign_id)
            if not local_matches and len(foreign_matches) >= 2 and destination is not None:
                destination_details = destination.setdefault("details", [])
                if value and not any(_normalized(value) == _normalized(item) for item in destination_details):
                    destination_details.append(value)
                    destination.setdefault("detail_fact_ids", []).append(
                        fact_rows[detail_index] if detail_index < len(fact_rows) else []
                    )
                moved += 1
                _add_issue(
                    issues, "CROSS_EXPERIENCE_FACT", "critical",
                    f"resume_sections.projects.{project_index}.details.{detail_index}", project,
                    confidence=0.98, repair_action="move_unique_terms_to_matching_experience",
                    fact_ids=_fact_ids(project, detail_index),
                )
                continue
            kept_details.append(value)
            kept_fact_rows.append(fact_rows[detail_index] if detail_index < len(fact_rows) else [])
        project["details"] = kept_details
        project["detail_fact_ids"] = kept_fact_rows
    return updated, moved


def evaluate_delivery_quality_issues(payload: schemas.GenerationPayload, raw_input: str) -> list[ResumeQualityIssue]:
    issues: list[ResumeQualityIssue] = []
    sections = payload.resume_sections
    if not sections.summary:
        _add_issue(issues, "EMPTY_VISIBLE_SECTION", "critical", "resume_sections.summary")
    if not sections.projects:
        _add_issue(issues, "EMPTY_VISIBLE_SECTION", "critical", "resume_sections.projects")
    explicit_skills = _skill_terms(raw_input)
    if explicit_skills and not sections.skills:
        _add_issue(issues, "EMPTY_VISIBLE_SECTION", "warning", "resume_sections.skills")
    for project_index, project in enumerate(sections.projects):
        if classify_experience_project(project, raw_input) != "valid":
            _add_issue(issues, "INVALID_EXPERIENCE_ENTITY", "critical", f"resume_sections.projects.{project_index}", project)
        if not any([_text(project.get("intro")), _text(project.get("role")), *[_text(item) for item in project.get("details", []) or []]]):
            _add_issue(issues, "EMPTY_PROJECT_BODY", "critical", f"resume_sections.projects.{project_index}", project)
        values = [_text(project.get("intro")), _text(project.get("role")), *[_text(item) for item in project.get("details", []) or []]]
        for left_index, left in enumerate(values):
            if not left:
                continue
            reasons = set(fragment_reasons(left))
            if reasons:
                severity = _fragment_severity(reasons)
                _add_issue(
                    issues, "INCOMPLETE_SENTENCE", severity,
                    f"resume_sections.projects.{project_index}.body.{left_index}", project,
                    confidence=0.9 if severity == "critical" else 0.65,
                )
            for right in values[left_index + 1:]:
                if not right:
                    continue
                score = similarity(left, right)
                if _normalized(left) == _normalized(right):
                    _add_issue(issues, "DUPLICATE_FACT", "critical", f"resume_sections.projects.{project_index}", project)
                elif score >= 0.78:
                    _add_issue(issues, "LOW_INFORMATION_GAIN", "observe", f"resume_sections.projects.{project_index}", project, confidence=score)
    cross_count = _cross_experience_count(payload, raw_input)
    for _ in range(cross_count):
        _add_issue(issues, "CROSS_EXPERIENCE_FACT", "critical", "resume_sections.projects", confidence=0.95)
    visible = _visible_text(payload)
    invalid_count = len(INVALID_CHAR_PATTERN.findall(visible))
    for _ in range(invalid_count):
        _add_issue(issues, "INVALID_CHARACTER", "critical", "resume_sections")
    for marker in INTERNAL_MARKERS:
        if marker.lower() in visible.lower():
            _add_issue(issues, "INTERNAL_FIELD_LEAK", "critical", "resume_sections")
    for marker in COACH_MARKERS:
        if marker in visible:
            _add_issue(issues, "COACH_LANGUAGE_LEAK", "critical", "resume_sections")
    fact_guarded = guard_hard_facts(payload, raw_input)
    if _visible_text(fact_guarded) != visible:
        _add_issue(
            issues, "UNSUPPORTED_HARD_FACT", "critical", "resume_sections",
            confidence=0.95,
        )
    if has_unbalanced_symbols(visible):
        _add_issue(issues, "INVALID_CHARACTER", "critical", "resume_sections", confidence=0.95)
    coverage, _ = _high_value_coverage(payload, raw_input)
    if coverage < 0.8:
        _add_issue(issues, "LOW_HIGH_VALUE_FACT_COVERAGE", "warning", "resume_sections.projects", confidence=1.0 - coverage)
    return issues


def _write_log(stats: DeliveryGateStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = asdict(stats)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def ensure_resume_delivery_quality(
    payload: schemas.GenerationPayload | dict,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = schemas.GenerationPayload.model_validate(
        deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)
    )
    issues: list[ResumeQualityIssue] = []
    projects_before = len(updated.resume_sections.projects)
    details_before = sum(len(project.get("details", []) or []) for project in updated.resume_sections.projects)
    coverage_before, covered_before = _high_value_coverage(updated, raw_input)
    visible_before = _visible_text(updated)

    if not updated.resume_sections.summary:
        _add_issue(issues, "EMPTY_VISIBLE_SECTION", "critical", "resume_sections.summary", repair_action="recover_grounded_summary")
    if not updated.resume_sections.projects:
        _add_issue(issues, "EMPTY_VISIBLE_SECTION", "critical", "resume_sections.projects", repair_action="recover_from_fact_ledger")
    if _skill_terms(raw_input) and not updated.resume_sections.skills:
        _add_issue(issues, "EMPTY_VISIBLE_SECTION", "warning", "resume_sections.skills", repair_action="recover_evidenced_skills")
    for marker in COACH_MARKERS:
        if marker in visible_before:
            _add_issue(issues, "COACH_LANGUAGE_LEAK", "critical", "resume_sections", repair_action="apply_output_firewall")
    for project_index, project in enumerate(updated.resume_sections.projects):
        if classify_experience_project(project, raw_input) != "valid":
            _add_issue(issues, "INVALID_EXPERIENCE_ENTITY", "critical", f"resume_sections.projects.{project_index}", project, repair_action="remove_or_absorb_invalid_entity")
        body_rows = [_text(project.get("intro")), _text(project.get("role")), *[_text(item) for item in project.get("details", []) or []]]
        for body_index, row in enumerate(body_rows):
            reasons = set(fragment_reasons(row)) if row else set()
            if reasons:
                severity = _fragment_severity(reasons)
                _add_issue(
                    issues, "INCOMPLETE_SENTENCE", severity,
                    f"resume_sections.projects.{project_index}.body.{body_index}", project,
                    confidence=0.9 if severity == "critical" else 0.65,
                    repair_action="recover_semantic_unit" if severity == "critical" else "",
                )

    updated = _clean_visible_fields(updated, issues)
    updated = guard_resume_output(updated, raw_input, stage=stage, generation_result_id=generation_result_id, write_log=False)

    updated, cross_repaired = _repair_strong_cross_experience_terms(updated, raw_input, issues)

    updated = ensure_resume_experience_validity(
        updated, raw_input, stage=stage, generation_result_id=generation_result_id, write_log=False,
    )
    updated, recovered_projects = _recover_projects_when_empty(updated, raw_input, issues)
    updated = ensure_resume_experience_validity(
        updated, raw_input, stage=stage, generation_result_id=generation_result_id, write_log=False,
    )
    if not updated.resume_sections.summary:
        updated = ensure_resume_summary_quality(
            updated, raw_input, stage=stage, generation_result_id=generation_result_id, write_log=False,
        )
    if not updated.resume_sections.skills and _skill_terms(raw_input):
        updated = guard_resume_skill_evidence(
            updated, raw_input, stage=stage, generation_result_id=generation_result_id, write_log=False,
        )
    if evaluate_skill_evidence(updated, raw_input) < 100:
        _add_issue(issues, "SKILL_WITHOUT_EVIDENCE", "warning", "resume_sections.skills")
    updated = ensure_semantic_units(updated, raw_input)
    updated, duplicate_removed = _deduplicate_project_fields(updated, issues)
    updated = ensure_paired_symbol_integrity(
        updated, stage=stage, generation_result_id=generation_result_id, write_log=False,
    )
    updated = ensure_resume_whitespace_quality(
        updated, stage=stage, generation_result_id=generation_result_id, write_log=False,
    )
    updated = ensure_typography_quality(
        updated, stage=stage, generation_result_id=generation_result_id, write_log=False,
    )

    coverage_mid, covered_mid = _high_value_coverage(updated, raw_input)
    facts_recovered = recovered_projects
    if coverage_mid < max(0.8, coverage_before):
        _add_issue(issues, "LOW_HIGH_VALUE_FACT_COVERAGE", "warning", "resume_sections.projects", confidence=1.0 - coverage_mid, repair_action="restore_from_fact_ledger")
        detail_count = sum(len(project.get("details", []) or []) for project in updated.resume_sections.projects)
        updated = guard_fact_coverage(
            updated, raw_input, stage=stage, generation_result_id=generation_result_id, write_log=False,
        )
        facts_recovered += max(0, sum(len(project.get("details", []) or []) for project in updated.resume_sections.projects) - detail_count)
        updated, extra_cross_repaired = _repair_strong_cross_experience_terms(updated, raw_input, issues)
        cross_repaired += extra_cross_repaired
        updated = ensure_resume_experience_validity(
            updated, raw_input, stage=stage, generation_result_id=generation_result_id, write_log=False,
        )
        updated, extra_removed = _deduplicate_project_fields(updated, issues)
        duplicate_removed += extra_removed

    updated = guard_resume_output(
        updated, raw_input, stage=stage, generation_result_id=generation_result_id, write_log=False,
    )
    updated = _clean_visible_fields(updated, issues)

    unresolved = evaluate_delivery_quality_issues(updated, raw_input)
    coverage_after, covered_after = _high_value_coverage(updated, raw_input)
    all_issues = issues + unresolved
    counts = {code: 0 for code in ISSUE_CODES}
    for issue in all_issues:
        counts[issue.issue_code] = counts.get(issue.issue_code, 0) + 1
    unresolved_critical = [issue for issue in unresolved if issue.severity == "critical"]
    repaired_count = sum(bool(issue.repair_action) for issue in issues)
    details_after = sum(len(project.get("details", []) or []) for project in updated.resume_sections.projects)
    stats = DeliveryGateStats(
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        generation_result_id=generation_result_id,
        stage=stage,
        issue_count_by_code=counts,
        critical_issue_count=sum(issue.severity == "critical" for issue in all_issues),
        repaired_issue_count=repaired_count,
        unresolved_issue_count=len(unresolved),
        projects_before=projects_before,
        projects_after=len(updated.resume_sections.projects),
        details_removed_count=max(duplicate_removed, details_before - details_after),
        facts_recovered_count=max(facts_recovered, len(covered_after - covered_mid), len(covered_after - covered_before)),
        high_value_coverage_before=round(coverage_before, 3),
        high_value_coverage_after=round(coverage_after, 3),
        internal_leak_count=sum(issue.issue_code == "INTERNAL_FIELD_LEAK" for issue in all_issues),
        invalid_character_count=sum(issue.issue_code == "INVALID_CHARACTER" for issue in all_issues),
        gate_passed=not unresolved_critical and coverage_after + 1e-9 >= min(coverage_before, 0.8),
        issues=all_issues,
    )
    if visible_before and not _visible_text(updated):
        stats.gate_passed = False
    if write_log:
        _write_log(stats)
    return updated
