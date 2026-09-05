"""Read-only Semantic Commit mutation tracing.

This module deliberately observes presentation payloads without participating in
generation, repair, or validation decisions.  It writes identifiers, paths, and
fingerprints only; user-provided text never leaves process memory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .. import schemas
from .canonical_semantic_state_service import CanonicalSemanticBuild
from .experience_fact_ledger_service import fact_match_score, normalize_fact_text
from .resume_skill_evidence_aggregation_service import AggregatedSkillEvidence, contains_skill_term
from .structured_log_service import stable_hash


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "semantic_mutation_trace.jsonl"
_WITHHELD_ROLES = {"USER_INSTRUCTION", "NEGATIVE_CONSTRAINT", "UNCERTAIN_FACT"}
_VISIBLE_PROJECT_FIELDS = ("name", "position", "meta", "time", "intro", "role")


@dataclass(frozen=True)
class SemanticCommitSnapshot:
    experience_ids: tuple[str, ...]
    type_by_experience: dict[str, str]
    fact_owner_by_id: dict[str, str]
    claim_owner_by_id: dict[str, str]
    eligible_fact_ids: frozenset[str]
    eligible_claim_ids: frozenset[str]
    withheld_claim_ids: frozenset[str]
    canonical_skill_keys: frozenset[str]
    fingerprint: str


@dataclass(frozen=True)
class VisibleField:
    path: str
    owner: str
    fact_ids: tuple[str, ...]
    value_fingerprint: str
    supported: bool
    foreign: bool
    withheld: bool
    unbound: bool


@dataclass(frozen=True)
class PayloadProjection:
    projects: dict[str, dict[str, Any]]
    fields: dict[str, VisibleField]
    skill_keys: frozenset[str]
    fingerprint: str


@dataclass(frozen=True)
class SemanticMutation:
    mutation_code: str
    severity: str
    field_path: str
    internal_ids: tuple[str, ...] = ()
    before_fingerprint: str = ""
    after_fingerprint: str = ""


def _fingerprint(value: object, *, purpose: str) -> str:
    return stable_hash(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")), purpose=purpose)


def _ids(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item or "")]
    return []


def _project_fact_ids(project: dict[str, Any]) -> list[str]:
    values = _ids(project.get("source_fact_ids")) + _ids(project.get("role_source_fact_ids"))
    for row in project.get("detail_fact_ids", []) if isinstance(project.get("detail_fact_ids"), list) else []:
        values.extend(_ids(row))
    return list(dict.fromkeys(values))


def _field_fact_ids(project: dict[str, Any], field: str, detail_index: int | None = None) -> tuple[str, ...]:
    if field == "role":
        values = _ids(project.get("role_source_fact_ids")) or _ids(project.get("source_fact_ids"))
    elif detail_index is not None:
        rows = project.get("detail_fact_ids", [])
        values = _ids(rows[detail_index]) if isinstance(rows, list) and detail_index < len(rows) else []
    else:
        values = _ids(project.get("source_fact_ids"))
    return tuple(dict.fromkeys(values))


def build_semantic_commit_snapshot(
    build: CanonicalSemanticBuild,
    skill_evidence: list[AggregatedSkillEvidence] | None = None,
) -> SemanticCommitSnapshot:
    """Project canonical IDs and skill evidence without retaining semantic text."""
    decisions = build.canonical_type_by_experience_id
    ownership = build.ownership_index
    withheld = {
        claim.claim_id
        for claim in build.ledger.withheld_claims + build.ledger.excluded_claims
        if claim.semantic_role in _WITHHELD_ROLES or not claim.resume_eligible
    }
    skills = {
        stable_hash(row.term.lower(), purpose="semantic_mutation_skill")
        for row in skill_evidence or []
        if row.term
    }
    source = {
        "experience_ids": sorted(decisions),
        "types": {key: decisions[key].canonical_experience_type for key in sorted(decisions)},
        "fact_owner": ownership.fact_owner_by_id,
        "claim_owner": ownership.claim_owner_by_id,
        "eligible_facts": sorted(ownership.fact_owner_by_id),
        "eligible_claims": sorted(claim.claim_id for claim in build.ledger.claims if claim.resume_eligible),
        "withheld_claims": sorted(withheld),
        "skill_keys": sorted(skills),
    }
    return SemanticCommitSnapshot(
        experience_ids=tuple(sorted(decisions)),
        type_by_experience={key: decisions[key].canonical_experience_type for key in decisions},
        fact_owner_by_id=dict(ownership.fact_owner_by_id),
        claim_owner_by_id=dict(ownership.claim_owner_by_id),
        eligible_fact_ids=frozenset(ownership.fact_owner_by_id),
        eligible_claim_ids=frozenset(claim.claim_id for claim in build.ledger.claims if claim.resume_eligible),
        withheld_claim_ids=frozenset(withheld),
        canonical_skill_keys=frozenset(skills),
        fingerprint=_fingerprint(source, purpose="semantic_mutation_commit"),
    )


def _text_supported(value: str, owner: str, build: CanonicalSemanticBuild) -> tuple[bool, bool, bool]:
    """Return local support, foreign support, withheld-claim match.

    Text is inspected only in memory. Provenance IDs are preferred by the
    caller; lexical score is a deliberately secondary signal for unbound text.
    """
    if not value:
        return True, False, False
    local = False
    foreign = False
    for fact in build.ledger.facts:
        score = fact_match_score(value, fact)
        if score < 0.82:
            continue
        if owner and fact.experience_id == owner:
            local = True
        elif owner and fact.experience_id != owner:
            foreign = True
        elif not owner:
            local = True
    normalized_value = normalize_fact_text(value)
    withheld = any(
        normalized_value and normalize_fact_text(claim.text) and (
            normalized_value in normalize_fact_text(claim.text)
            or normalize_fact_text(claim.text) in normalized_value
        )
        for resolution in build.claim_resolutions
        for claim in resolution.withheld_claims + resolution.excluded_claims
        if claim.semantic_role in _WITHHELD_ROLES or not claim.resume_eligible
    )
    return local, foreign, withheld


def _project_payload(
    payload: schemas.GenerationPayload,
    build: CanonicalSemanticBuild,
    snapshot: SemanticCommitSnapshot,
) -> PayloadProjection:
    fields: dict[str, VisibleField] = {}
    projects: dict[str, dict[str, Any]] = {}
    for index, project in enumerate(payload.resume_sections.projects):
        owner = str(project.get("immutable_source_experience_id") or project.get("source_experience_id") or "")
        fact_ids = _project_fact_ids(project)
        # Owner is deliberately excluded: a changed owner must retain the same
        # comparison key so the trace can report OWNER_CHANGED.
        key = _fingerprint({"index": index, "facts": sorted(fact_ids)}, purpose="semantic_mutation_project")
        projects[key] = {"owner": owner, "type": str(project.get("meta") or ""), "facts": tuple(fact_ids)}
        records: list[tuple[str, object, int | None]] = [(field, project.get(field), None) for field in _VISIBLE_PROJECT_FIELDS]
        records.extend(("details", value, detail_index) for detail_index, value in enumerate(project.get("details", []) or []))
        for field, value, detail_index in records:
            text = str(value or "").strip()
            if not text:
                continue
            path = f"resume_sections.projects.{index}.{field}" + (f".{detail_index}" if detail_index is not None else "")
            row_fact_ids = _field_fact_ids(project, field, detail_index)
            id_owners = {snapshot.fact_owner_by_id.get(fact_id, "") for fact_id in row_fact_ids}
            foreign = bool(owner and any(item and item != owner for item in id_owners))
            supported = bool(row_fact_ids and all(item in snapshot.eligible_fact_ids for item in row_fact_ids) and not foreign)
            local_text, foreign_text, withheld = _text_supported(text, owner, build)
            fields[path] = VisibleField(
                path=path,
                owner=owner,
                fact_ids=row_fact_ids,
                value_fingerprint=stable_hash(text, purpose="semantic_mutation_visible"),
                supported=supported or local_text,
                foreign=foreign or foreign_text,
                withheld=withheld,
                unbound=not row_fact_ids and not local_text,
            )
    skill_keys: set[str] = set()
    from .resume_skill_evidence_aggregation_service import extract_skill_terms
    for line in payload.resume_sections.skills:
        text = str(line or "")
        for term in extract_skill_terms(text):
            if contains_skill_term(text, term):
                skill_keys.add(stable_hash(term.lower(), purpose="semantic_mutation_skill"))
    digest = {
        "projects": {key: {"owner": value["owner"], "type": value["type"], "facts": value["facts"]} for key, value in projects.items()},
        "fields": {key: {"owner": value.owner, "facts": value.fact_ids, "text": value.value_fingerprint} for key, value in fields.items()},
        "skills": sorted(skill_keys),
    }
    return PayloadProjection(projects=projects, fields=fields, skill_keys=frozenset(skill_keys), fingerprint=_fingerprint(digest, purpose="semantic_mutation_payload"))


@dataclass
class SemanticMutationTracer:
    build: CanonicalSemanticBuild
    snapshot: SemanticCommitSnapshot
    request_id: str = ""
    attempt_id: str = ""
    generation_result_id: int | None = None
    sequence: int = 0
    previous: PayloadProjection | None = None
    seen: set[tuple[str, str]] = field(default_factory=set)
    events: list[dict[str, Any]] = field(default_factory=list)

    def checkpoint(self, payload: schemas.GenerationPayload, stage: str, *, parent_stage: str = "") -> None:
        current = _project_payload(payload, self.build, self.snapshot)
        previous = self.previous
        mutations: list[SemanticMutation] = []
        for key, project in current.projects.items():
            canonical_type = self.snapshot.type_by_experience.get(project["owner"], "")
            if project["owner"] and project["owner"] not in self.snapshot.experience_ids:
                mutations.append(SemanticMutation("NEW_EXPERIENCE", "warning", f"resume_sections.projects.{key}", (project["owner"],)))
            if canonical_type and project["type"] and project["type"] != canonical_type:
                mutations.append(SemanticMutation("TYPE_CHANGED", "warning", f"resume_sections.projects.{key}.meta", (project["owner"],)))
            if previous and key in previous.projects and previous.projects[key]["owner"] != project["owner"]:
                mutations.append(SemanticMutation("OWNER_CHANGED", "critical", f"resume_sections.projects.{key}", (project["owner"],)))
        for path, field in current.fields.items():
            if field.foreign:
                mutations.append(SemanticMutation("FOREIGN_FACT_VISIBLE", "critical", path, field.fact_ids))
            if field.withheld:
                mutations.append(SemanticMutation("WITHHELD_OR_NEGATIVE_CLAIM_VISIBLE", "critical", path, field.fact_ids))
            if field.unbound:
                mutations.append(SemanticMutation("VISIBLE_FIELD_WITHOUT_PROVENANCE", "warning", path))
                if not previous or path not in previous.fields:
                    mutations.append(SemanticMutation("NEW_UNBOUND_CLAIM_CANDIDATE", "warning", path))
            if previous and path in previous.fields and previous.fields[path].fact_ids and not field.fact_ids:
                mutations.append(SemanticMutation("FACT_BINDING_DROPPED", "warning", path))
        unsupported = current.skill_keys - self.snapshot.canonical_skill_keys
        if unsupported:
            mutations.append(SemanticMutation("SKILL_WITHOUT_CANONICAL_EVIDENCE", "critical", "resume_sections.skills", tuple(sorted(unsupported))))
            mutations.append(SemanticMutation("UNSUPPORTED_SKILL_VISIBLE", "critical", "resume_sections.skills", tuple(sorted(unsupported))))
        if previous:
            for path, field in current.fields.items():
                older = previous.fields.get(path)
                if older and older.value_fingerprint != field.value_fingerprint and field.supported and not field.foreign:
                    mutations.append(SemanticMutation("SUPPORTED_PRESENTATION_REWRITE", "observe", path, field.fact_ids))

        self.sequence += 1
        aggregate: dict[str, int] = {}
        for mutation in mutations:
            aggregate[mutation.mutation_code] = aggregate.get(mutation.mutation_code, 0) + 1
            marker = (mutation.mutation_code, mutation.field_path)
            if marker in self.seen:
                continue
            self.seen.add(marker)
            self.events.append({
                "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                "event_type": "mutation",
                "request_id": self.request_id,
                "attempt_id": self.attempt_id,
                "generation_result_id": self.generation_result_id,
                "stage": stage,
                "parent_stage": parent_stage,
                "sequence": self.sequence,
                "mutation_code": mutation.mutation_code,
                "severity": mutation.severity,
                "field_path": mutation.field_path,
                "internal_ids": list(mutation.internal_ids),
                "before_fingerprint": previous.fingerprint if previous else self.snapshot.fingerprint,
                "after_fingerprint": current.fingerprint,
                "aggregate_counts": aggregate,
                "project_count": len(current.projects),
                "visible_field_count": len(current.fields),
                "unbound_visible_field_count": sum(field.unbound for field in current.fields.values()),
                "semantic_commit_fingerprint": self.snapshot.fingerprint,
            })
        self.events.append({
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "event_type": "checkpoint",
            "request_id": self.request_id,
            "attempt_id": self.attempt_id,
            "generation_result_id": self.generation_result_id,
            "stage": stage,
            "parent_stage": parent_stage,
            "sequence": self.sequence,
            "mutation_code": "",
            "severity": "observe",
            "field_path": "",
            "internal_ids": [],
            "before_fingerprint": previous.fingerprint if previous else self.snapshot.fingerprint,
            "after_fingerprint": current.fingerprint,
            "aggregate_counts": aggregate,
            "project_count": len(current.projects),
            "visible_field_count": len(current.fields),
            "unbound_visible_field_count": sum(field.unbound for field in current.fields.values()),
            "semantic_commit_fingerprint": self.snapshot.fingerprint,
        })
        self.previous = current

    def flush(self, generation_result_id: int | None = None) -> None:
        if generation_result_id is not None:
            self.generation_result_id = generation_result_id
        if not self.events:
            return
        try:
            LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                for event in self.events:
                    event["generation_result_id"] = self.generation_result_id
                    handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            return
