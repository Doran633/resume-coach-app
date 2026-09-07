"""Deterministic, owner-scoped repairs after read-only delivery validation.

This router intentionally has no access to raw input, LLMs, fallbacks, or
semantic compilers.  It may only remove an already-visible field when its
existing local Fact bindings prove it contributes no new information.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .canonical_consumer_view_service import CanonicalRepairView
from .resume_delivery_quality_gate_service import ResumeQualityIssue
from .structured_log_service import stable_hash


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_quality_repair_router.jsonl"
EXACT_DUPLICATE_FIELD = "EXACT_DUPLICATE_FIELD"


def _normalized(value: object) -> str:
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9+#./-]", "", str(value or "").strip()).lower()


def _ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(dict.fromkeys(str(item) for item in value if str(item or "")))


def _field_fact_ids(project: dict, field: str, detail_index: int | None = None) -> tuple[str, ...]:
    if field == "role":
        return _ids(project.get("role_source_fact_ids")) or _ids(project.get("source_fact_ids"))
    if detail_index is not None:
        rows = project.get("detail_fact_ids")
        return _ids(rows[detail_index]) if isinstance(rows, list) and detail_index < len(rows) else ()
    return _ids(project.get("source_fact_ids"))


@dataclass(frozen=True)
class QualityRepairAction:
    action_code: str
    project_index: int
    field: str
    detail_index: int | None
    source_experience_id: str
    source_fact_ids: tuple[str, ...]

    @property
    def field_path(self) -> str:
        suffix = f".{self.detail_index}" if self.detail_index is not None else ""
        return f"resume_sections.projects.{self.project_index}.{self.field}{suffix}"


@dataclass
class QualityRepairStats:
    created_at: str
    generation_result_id: int | None
    stage: str
    issue_count: int
    planned_action_count: int = 0
    applied_action_count: int = 0
    skipped_action_count: int = 0
    fields_removed_count: int = 0
    action_count_by_code: dict[str, int] = field(default_factory=dict)
    changed: bool = False
    high_value_fact_count_before: int = 0
    high_value_fact_count_after: int = 0
    view_fingerprint: str = ""


@dataclass(frozen=True)
class QualityRepairResult:
    actions: tuple[QualityRepairAction, ...]
    stats: QualityRepairStats


def _is_locally_repairable(
    project: dict,
    owner: str,
    fact_ids: tuple[str, ...],
    repair_view: CanonicalRepairView,
) -> bool:
    return bool(
        owner
        and project.get("source_binding_locked") is True
        and project.get("immutable_source_experience_id") == owner
        and fact_ids
        and all(repair_view.permits_fact(owner, fact_id) for fact_id in fact_ids)
    )


def build_quality_repair_plan(
    payload: schemas.GenerationPayload,
    issues: tuple[ResumeQualityIssue, ...] | list[ResumeQualityIssue],
    repair_view: CanonicalRepairView,
) -> tuple[QualityRepairAction, ...]:
    """Plan only same-owner, same-Fact exact duplicate removals."""
    duplicate_project_paths = {
        issue.field_path
        for issue in issues
        if issue.issue_code == "DUPLICATE_FACT"
    }
    actions: list[QualityRepairAction] = []
    for project_index, project in enumerate(payload.resume_sections.projects):
        project_path = f"resume_sections.projects.{project_index}"
        if project_path not in duplicate_project_paths:
            continue
        owner = str(project.get("immutable_source_experience_id") or "")
        records: list[tuple[str, int | None, str, tuple[str, ...], int]] = []
        for field, priority in (("intro", 0), ("role", 2)):
            value = _normalized(project.get(field))
            fact_ids = _field_fact_ids(project, field)
            if value and _is_locally_repairable(project, owner, fact_ids, repair_view):
                records.append((field, None, value, fact_ids, priority))
        for detail_index, detail in enumerate(project.get("details", []) or []):
            value = _normalized(detail)
            fact_ids = _field_fact_ids(project, "details", detail_index)
            if value and _is_locally_repairable(project, owner, fact_ids, repair_view):
                records.append(("details", detail_index, value, fact_ids, 1))

        kept: list[tuple[str, tuple[str, ...]]] = []
        for field, detail_index, value, fact_ids, _ in sorted(records, key=lambda row: row[4]):
            if any(value == prior_value and fact_ids == prior_fact_ids for prior_value, prior_fact_ids in kept):
                actions.append(QualityRepairAction(
                    action_code=EXACT_DUPLICATE_FIELD,
                    project_index=project_index,
                    field=field,
                    detail_index=detail_index,
                    source_experience_id=owner,
                    source_fact_ids=fact_ids,
                ))
                continue
            kept.append((value, fact_ids))
    return tuple(actions)


def _remove_detail(project: dict, detail_index: int) -> bool:
    details = project.get("details")
    if not isinstance(details, list) or detail_index >= len(details):
        return False
    details.pop(detail_index)
    for key in ("detail_fact_ids", "detail_claim_ids"):
        rows = project.get(key)
        if isinstance(rows, list) and detail_index < len(rows):
            rows.pop(detail_index)
    return True


def apply_quality_repair_plan(
    payload: schemas.GenerationPayload,
    actions: tuple[QualityRepairAction, ...],
    repair_view: CanonicalRepairView,
) -> tuple[int, int]:
    """Apply an already-scoped plan without creating or moving semantics."""
    applied = 0
    skipped = 0
    ordered = sorted(
        actions,
        key=lambda action: (action.project_index, action.field == "details", action.detail_index or -1),
        reverse=True,
    )
    for action in ordered:
        projects = payload.resume_sections.projects
        if action.project_index >= len(projects):
            skipped += 1
            continue
        project = projects[action.project_index]
        owner = str(project.get("immutable_source_experience_id") or "")
        if not _is_locally_repairable(project, owner, action.source_fact_ids, repair_view):
            skipped += 1
            continue
        if action.field == "role" and action.detail_index is None:
            if not _normalized(project.get("role")):
                skipped += 1
                continue
            project["role"] = ""
            applied += 1
        elif action.field == "details" and action.detail_index is not None:
            if _remove_detail(project, action.detail_index):
                applied += 1
            else:
                skipped += 1
        else:
            skipped += 1
    return applied, skipped


def _high_value_fact_count(payload: schemas.GenerationPayload, repair_view: CanonicalRepairView) -> int:
    projected: set[tuple[str, str]] = set()
    for project in payload.resume_sections.projects:
        owner = str(project.get("immutable_source_experience_id") or "")
        bindings = [
            _field_fact_ids(project, "intro"),
            _field_fact_ids(project, "role"),
            *[
                _field_fact_ids(project, "details", index)
                for index, _ in enumerate(project.get("details", []) or [])
            ],
        ]
        for fact_ids in bindings:
            projected.update((owner, fact_id) for fact_id in fact_ids if repair_view.permits_fact(owner, fact_id))
    high_value = {
        (owner, fact.fact_id)
        for owner in {owner for owner, _ in projected}
        for fact in repair_view.eligible_facts(owner)
        if fact.importance == "high"
    }
    return len(projected & high_value)


def route_quality_repairs(
    payload: schemas.GenerationPayload,
    issues: tuple[ResumeQualityIssue, ...] | list[ResumeQualityIssue],
    repair_view: CanonicalRepairView,
    *,
    stage: str,
    generation_result_id: int | None = None,
    request_id: str = "",
    attempt_id: str = "",
    write_log: bool = True,
) -> QualityRepairResult:
    """Apply the narrowly-authorized repair plan and write aggregate telemetry."""
    before = payload.model_dump(mode="json")
    actions = build_quality_repair_plan(payload, issues, repair_view)
    high_value_before = _high_value_fact_count(payload, repair_view)
    applied, skipped = apply_quality_repair_plan(payload, actions, repair_view)
    high_value_after = _high_value_fact_count(payload, repair_view)
    if high_value_after < high_value_before:
        raise RuntimeError("quality repair would lower high-value Fact coverage")
    stats = QualityRepairStats(
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        generation_result_id=generation_result_id,
        stage=stage,
        issue_count=len(issues),
        planned_action_count=len(actions),
        applied_action_count=applied,
        skipped_action_count=skipped,
        fields_removed_count=applied,
        action_count_by_code={EXACT_DUPLICATE_FIELD: applied} if applied else {},
        changed=before != payload.model_dump(mode="json"),
        high_value_fact_count_before=high_value_before,
        high_value_fact_count_after=high_value_after,
        view_fingerprint=repair_view.fingerprint,
    )
    result = QualityRepairResult(actions=actions, stats=stats)
    if write_log:
        write_quality_repair_router_log(result, request_id=request_id, attempt_id=attempt_id)
    return result


def write_quality_repair_router_log(
    result: QualityRepairResult,
    *,
    request_id: str,
    attempt_id: str,
    generation_result_id: int | None = None,
    stage: str | None = None,
) -> None:
    """Persist an aggregate-only repair record, optionally after result save."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        row = asdict(result.stats)
        if generation_result_id is not None:
            row["generation_result_id"] = generation_result_id
        if stage is not None:
            row["stage"] = stage
        row.update({
            "request_id": request_id,
            "attempt_id": attempt_id,
            "action_fingerprint": stable_hash(
                json.dumps([
                    (action.action_code, action.project_index, action.field, action.detail_index, action.source_experience_id, action.source_fact_ids)
                    for action in result.actions
                ], ensure_ascii=False, sort_keys=True),
                purpose="resume_quality_repair_router",
            ),
        })
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        return
