import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import ExperienceFactLedger, build_experience_fact_ledger, fact_match_score
from .canonical_semantic_state_service import (
    CanonicalFallbackRecoveryStats,
    canonical_fact_scope_for_owner,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .canonical_semantic_state_service import CanonicalFactOwnershipIndex, CanonicalSemanticBuild


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_role_quality.jsonl"
ACTION_PATTERN = re.compile(r"负责|独立|主导|参与|开发|设计|实现|优化|测试|部署|组织|协调|策划|联调|修复|建设|搭建|推进|写|调")
INTERNAL_ROLE_MARKERS = (
    "围绕该段经历完成相关任务", "具体职责以用户原文提供的信息为准", "具体职责以用户已提供内容为准",
    "以用户原文为准", "以用户提供的信息为准", "以用户已提供内容为准", "根据现有经历整理个人参与内容",
    "围绕用户提供的真实经历", "根据用户原文", "根据用户输入", "请结合用户信息", "待用户确认",
    "待用户进一步确认职责", "相关工作以实际情况为准", "基于用户原始经历整理",
)
GENERIC_ROLES = (
    "负责相关工作", "参与相关任务", "完成相关任务", "围绕项目目标完成工作", "推进项目相关事项",
    "围绕项目目标参与功能设计、技术实现、联调排查和结果交付",
)


@dataclass
class RoleQualityStats:
    stage: str
    generation_result_id: int | None
    role_fallback_triggered: int = 0
    role_recovered_from_fact_count: int = 0
    role_left_empty_count: int = 0
    internal_fallback_text_removed_count: int = 0
    role_source_experience_ids: list[str] = field(default_factory=list)
    role_source_fact_ids: list[str] = field(default_factory=list)


def is_internal_or_generic_role(text: str) -> bool:
    value = str(text or "").strip()
    return bool(value) and (any(marker in value for marker in INTERNAL_ROLE_MARKERS) or any(value.rstrip("。") == marker for marker in GENERIC_ROLES))


def _professionalize_role(text: str) -> str:
    value = str(text or "").strip().rstrip("。；;")
    value = re.sub(r"^(?:我|本人)(?=负责|独立|主导|参与|开发|设计|实现|优化|测试|部署|组织|协调|写|调)", "", value)
    value = re.sub(r"写了几个\s*([^，。；]*)页面", lambda match: f"负责{match.group(1).strip()}页面开发" if match.group(1).strip() else "负责页面开发", value)
    value = re.sub(r"(?:也)?调了(?:一些)?(?:后端)?接口", "完成接口联调与数据流转校验", value)
    value = re.sub(r"\s+", " ", value).strip(" ，,、；;：:")
    return value if ACTION_PATTERN.search(value) and not is_internal_or_generic_role(value) else ""


def resolve_role_for_experience(
    raw_input: str,
    experience_id: str,
    *,
    details: list[str] | None = None,
    intro: str = "",
    ledger: ExperienceFactLedger | None = None,
    facts: list | None = None,
) -> tuple[str, list[str]]:
    facts = facts if facts is not None else (ledger or build_experience_fact_ledger(raw_input)).for_experience(experience_id)
    ranked = sorted(
        [fact for fact in facts if fact.resume_ready_text and ACTION_PATTERN.search(fact.fact_text)],
        key=lambda fact: (fact.fact_type != "职责", fact.importance == "low"),
    )
    for fact in ranked:
        role = _professionalize_role(fact.resume_ready_text)
        if role:
            return role, [fact.fact_id]
    for candidate in [*(details or []), intro]:
        ranked_candidates = sorted(((fact_match_score(candidate, fact), fact) for fact in facts), reverse=True, key=lambda item: item[0])
        best_score, best_fact = ranked_candidates[0] if ranked_candidates else (0.0, None)
        if best_fact and best_score >= 0.48:
            role = _professionalize_role(candidate)
            if role:
                return role, [best_fact.fact_id]
    return "", []


def _write_log(stats: RoleQualityStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        entry["role_source_experience_ids"] = sorted(set(entry["role_source_experience_ids"]))
        entry["role_source_fact_ids"] = sorted(set(entry["role_source_fact_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def resolve_resume_roles(
    payload: schemas.GenerationPayload,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
    semantic_build: "CanonicalSemanticBuild | None" = None,
    ownership_index: "CanonicalFactOwnershipIndex | None" = None,
    recovery_stats: CanonicalFallbackRecoveryStats | None = None,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = RoleQualityStats(stage=stage, generation_result_id=generation_result_id)
    canonical_mode = semantic_build is not None or ownership_index is not None
    ownership = ownership_index or (semantic_build.ownership_index if semantic_build is not None else None)
    ledger = semantic_build.ledger if semantic_build is not None else build_experience_fact_ledger(raw_input)
    if canonical_mode and recovery_stats is not None:
        recovery_stats.raw_input_rebuild_blocked_count += 1
    experience_ids = sorted({fact.experience_id for fact in ledger.facts})
    for project in updated.resume_sections.projects:
        role = str(project.get("role") or "").strip()
        contaminated = is_internal_or_generic_role(role)
        if contaminated:
            stats.internal_fallback_text_removed_count += 1
            role = ""
        if role:
            project["role"] = role
            continue
        stats.role_fallback_triggered += 1
        source_id = str(project.get("immutable_source_experience_id") or "") if canonical_mode else str(project.get("source_experience_id") or "")
        if not canonical_mode and not source_id and len(experience_ids) == 1:
            source_id = experience_ids[0]
            project["source_experience_id"] = source_id
        scope = canonical_fact_scope_for_owner(ownership, source_id) if canonical_mode else None
        if canonical_mode and scope is None:
            if recovery_stats is not None:
                recovery_stats.unowned_project_skipped_count += 1
                recovery_stats.missing_question_count += 1
            recovered, fact_ids = "", []
        else:
            local_facts = scope.eligible_facts(ledger) if scope is not None else None
            recovered, fact_ids = resolve_role_for_experience(
                "" if canonical_mode else raw_input,
                source_id,
                details=project.get("details", []),
                intro=str(project.get("intro") or ""),
                ledger=ledger,
                facts=local_facts,
            ) if source_id else ("", [])
        project["role"] = recovered
        if recovered:
            stats.role_recovered_from_fact_count += 1
            stats.role_source_experience_ids.append(source_id)
            stats.role_source_fact_ids.extend(fact_ids)
            if fact_ids:
                project["role_source_fact_ids"] = fact_ids
            if canonical_mode and recovery_stats is not None:
                recovery_stats.local_role_recovered_count += 1
        else:
            stats.role_left_empty_count += 1
            question = "你在这段经历中具体负责哪些工作？"
            if question not in updated.missing_questions:
                updated.missing_questions.append(question)
    if write_log:
        _write_log(stats)
    return updated
