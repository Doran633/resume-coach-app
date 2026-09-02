import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .project_hierarchy_service import is_heading_detail, merge_parent_child_projects
from .resume_fact_dedup_service import information_score, similarity
from .resume_experience_validity_service import classify_experience_project, is_forbidden_experience_name
from .canonical_semantic_state_service import CanonicalScopedFactAccessStats
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .canonical_semantic_state_service import CanonicalFactOwnershipIndex, CanonicalSemanticBuild


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_experience_entity_dedup.jsonl"
TITLE_PREFIX = re.compile(
    r"^(?:项目[一二三四五六七八九十\d]+\s*[:：|｜\-—]?\s*|"
    r"我(?:曾经)?做过(?:一个)?|我做了(?:一个)?|我独立(?:完成|开发|设计)了?|"
    r"独立(?:完成|开发|设计)|设计并开发|个人项目\s*[:：|｜\-—]?\s*|"
    r"课程项目\s*[:：|｜\-—]?\s*|项目经历\s*[:：|｜\-—]?\s*)+",
    re.IGNORECASE,
)
GENERIC_TITLE = {"项目", "项目经历", "个人项目", "课程项目", "综合经历", "综合经历项目"}
INTERNAL_MARKERS = ["source_experience_id", "source_fact_ids", "fact_id", "技术动作", "希望包装", "原文截断"]
ANCHOR_TERMS = [
    "回归", "智能制图", "最优模型", "停车", "路线", "天气", "车流", "RAG", "Citation",
    "Embedding", "测试集", "部署", "Nginx", "systemd", "用户反馈", "Fallback", "Fact Ledger",
    "Experience ID", "数据隔离", "健康检查", "Smoke Test", "一等奖", "相关度", "Token",
]


@dataclass
class EntityDedupStats:
    created_at: str
    stage: str
    generation_result_id: int | None
    project_count_before: int = 0
    project_count_after: int = 0
    duplicate_entity_count: int = 0
    duplicate_source_id_count: int = 0
    normalized_title_duplicate_count: int = 0
    fact_fingerprint_duplicate_count: int = 0
    possible_duplicate_count: int = 0
    merged_project_count: int = 0
    recovered_unique_fact_count: int = 0
    removed_duplicate_detail_count: int = 0
    affected_experience_ids: list[str] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    provenance_conflict_count: int = 0
    inferred_id_collision_count: int = 0


@dataclass
class DuplicateDecision:
    duplicate: bool
    reason: str
    confidence: float
    possible: bool = False


def normalize_project_title(value: object) -> str:
    text = str(value or "").strip()
    text = TITLE_PREFIX.sub("", text).strip()
    text = re.sub(r"(?:个人项目|课程项目|项目经历)\s*$", "", text).strip()
    text = re.sub(r"(?:系统|平台|工具|项目)\s*$", "", text).strip()
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", text).lower()


def _literal_title(value: object) -> str:
    text = TITLE_PREFIX.sub("", str(value or "").strip()).strip()
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", text).lower()


def clean_project_title(value: object) -> str:
    text = TITLE_PREFIX.sub("", str(value or "").strip()).strip(" ：:|｜-—")
    return text or str(value or "").strip()


def _project_text(project: dict) -> str:
    return "\n".join([
        str(project.get("name") or ""), str(project.get("meta") or ""),
        str(project.get("intro") or ""), str(project.get("role") or ""),
        *[str(item) for item in project.get("details", []) or []],
    ])


def _detail_text(project: dict) -> str:
    return "\n".join(str(item) for item in project.get("details", []) or [])


def _source_ids(project: dict) -> set[str]:
    values = set()
    source_id = str(project.get("source_experience_id") or "").strip()
    if source_id:
        values.add(source_id)
    for key in ["source_fact_ids", "role_source_fact_ids"]:
        for fact_id in project.get(key, []) if isinstance(project.get(key), list) else []:
            match = re.match(r"(EXP-\d+)-F\d+", str(fact_id))
            if match:
                values.add(match.group(1))
    return values


def _fact_ids(project: dict) -> set[str]:
    values = {str(item) for item in project.get("source_fact_ids", []) if str(item)} if isinstance(project.get("source_fact_ids"), list) else set()
    rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
    for row in rows:
        if isinstance(row, list):
            values.update(str(item) for item in row if str(item))
    return values


def _anchors(text: str) -> set[str]:
    lowered = str(text or "").lower()
    values = {term.lower() for term in ANCHOR_TERMS if term.lower() in lowered}
    values.update(re.findall(r"\d+(?:\.\d+)?(?:%|token|人|次|ms|秒)?", lowered, re.I))
    values.update(re.findall(r"[A-Za-z][A-Za-z0-9+./_-]{2,}", lowered))
    return values


def _overlap(left: set[str], right: set[str]) -> float:
    return len(left & right) / max(1, min(len(left), len(right)))


def _title_similarity(left: dict, right: dict) -> float:
    a, b = normalize_project_title(left.get("name")), normalize_project_title(right.get("name"))
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 5 and (a in b or b in a):
        return 0.96
    return SequenceMatcher(None, a, b).ratio()


def _is_comprehensive_project(project: dict) -> bool:
    title = normalize_project_title(project.get("name"))
    meta = normalize_project_title(project.get("meta"))
    return "综合经历" in str(project.get("name") or "") or title in {"综合经历", "综合经历项目"} or meta == "综合经历"


def _heading_shell_points_to(shell: dict, target: dict) -> bool:
    kind = classify_experience_project(shell)
    if kind not in {"heading_residue_shell", "generic_name_shell", "empty_fact_shell"}:
        return False
    target_title = normalize_project_title(target.get("name"))
    if len(target_title) < 4:
        return False
    heading_rows = [
        str(value or "") for value in [
            shell.get("intro"), shell.get("role"), *(shell.get("details", []) or []),
        ] if str(value or "").strip() and is_heading_detail(str(value))
    ]
    return any(target_title in normalize_project_title(row) for row in heading_rows)


def _duplicate_decision(left: dict, right: dict) -> DuplicateDecision:
    # A title residue may receive a different source id during segmentation.
    # Resolve this narrow shell relation before the normal source-id boundary;
    # ordinary projects still keep the strict distinct-id rule below.
    if _heading_shell_points_to(left, right) or _heading_shell_points_to(right, left):
        return DuplicateDecision(True, "heading_residue_alias", 1.0)
    # A comprehensive fallback row is a temporary fact container. Reconciliation
    # must distribute its details before entity-level deduplication can be safe.
    if _is_comprehensive_project(left) != _is_comprehensive_project(right):
        return DuplicateDecision(False, "defer_comprehensive_reconciliation", 1.0)
    left_sources, right_sources = _source_ids(left), _source_ids(right)
    left_facts, right_facts = _fact_ids(left), _fact_ids(right)
    fact_overlap = _overlap(left_facts, right_facts) if left_facts and right_facts else 0.0
    if left_sources and right_sources:
        if left_sources & right_sources:
            title_score = _title_similarity(left, right)
            detail_anchors = _overlap(_anchors(_detail_text(left)), _anchors(_detail_text(right)))
            trusted = bool(left.get("source_binding_locked") and right.get("source_binding_locked"))
            if fact_overlap >= 0.5:
                return DuplicateDecision(True, "fact_fingerprint_duplicate", 0.99)
            if title_score >= 0.88 and (trusted or detail_anchors >= 0.25):
                return DuplicateDecision(True, "exact_source_duplicate", 0.98)
            if title_score >= 0.88 and not left.get("source_binding_origin") and not right.get("source_binding_origin"):
                return DuplicateDecision(True, "exact_source_duplicate", 0.94)
            return DuplicateDecision(False, "provenance_conflict", 0.96, possible=True)
        return DuplicateDecision(False, "distinct_source_experience_id", 1.0)
    if fact_overlap >= 0.5:
        return DuplicateDecision(True, "fact_fingerprint_duplicate", 0.98)

    title_score = _title_similarity(left, right)
    left_title = normalize_project_title(left.get("name"))
    anchors = _overlap(_anchors(_project_text(left)), _anchors(_project_text(right)))
    detail_anchors = _overlap(_anchors(_detail_text(left)), _anchors(_detail_text(right)))
    if title_score == 1.0 and len(left_title) >= 4:
        literal_match = _literal_title(left.get("name")) == _literal_title(right.get("name"))
        if literal_match or detail_anchors >= 0.35:
            return DuplicateDecision(True, "normalized_title_duplicate", 0.97 if literal_match else 0.93)
        return DuplicateDecision(False, "possible_duplicate", 0.72, possible=True)
    if title_score >= 0.88 and detail_anchors >= 0.5:
        return DuplicateDecision(True, "fact_fingerprint_duplicate", round((title_score + detail_anchors) / 2, 3))
    if title_score >= 0.75 and anchors >= 0.3:
        return DuplicateDecision(False, "possible_duplicate", round((title_score + anchors) / 2, 3), possible=True)
    return DuplicateDecision(False, "distinct_experience", max(title_score, anchors))


def _identity_title_match(project: dict, identities: list[ExperienceIdentity]) -> str:
    title = normalize_project_title(project.get("name"))
    if not title:
        return ""
    ranked = []
    for identity in identities:
        identity_title = normalize_project_title(identity.title)
        score = 1.0 if title == identity_title else SequenceMatcher(None, title, identity_title).ratio()
        if min(len(title), len(identity_title)) >= 5 and (title in identity_title or identity_title in title):
            score = max(score, 0.96)
        ranked.append((identity.experience_id, score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    if ranked and ranked[0][1] >= 0.9 and (len(ranked) == 1 or ranked[0][1] > ranked[1][1] + 0.08):
        return ranked[0][0]
    return ""


def _project_score(project: dict) -> float:
    title = str(project.get("name") or "")
    details = [str(item) for item in project.get("details", []) or []]
    score = information_score(str(project.get("intro") or "")) + information_score(str(project.get("role") or ""))
    score += sum(information_score(item) for item in details)
    score += len(_fact_ids(project)) * 4 + bool(project.get("source_experience_id")) * 6
    score -= sum(marker.lower() in _project_text(project).lower() for marker in INTERNAL_MARKERS) * 15
    score -= bool(TITLE_PREFIX.match(title)) * 8
    score -= (normalize_project_title(title) in GENERIC_TITLE) * 8
    return score


def _choose_text(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    if similarity(left, right) >= 0.88:
        return right if information_score(right) > information_score(left) else left
    return right if information_score(right) > information_score(left) * 1.25 else left


def _merge_details(primary: dict, secondary: dict, stats: EntityDedupStats) -> tuple[list[str], list[list[str]]]:
    records: list[tuple[str, list[str]]] = []
    for project in [primary, secondary]:
        details = [str(item).strip() for item in project.get("details", []) or [] if str(item).strip()]
        fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        for index, detail in enumerate(details):
            ids = [str(item) for item in fact_rows[index]] if index < len(fact_rows) and isinstance(fact_rows[index], list) else []
            matched = next((position for position, (existing, existing_ids) in enumerate(records)
                            if similarity(existing, detail) >= 0.88 or bool(set(existing_ids) & set(ids))), -1)
            if matched < 0:
                records.append((detail, ids))
                continue
            existing, existing_ids = records[matched]
            chosen = detail if information_score(detail, ids) > information_score(existing, existing_ids) else existing
            records[matched] = (chosen, list(dict.fromkeys([*existing_ids, *ids])))
            stats.removed_duplicate_detail_count += 1
    records.sort(key=lambda item: information_score(item[0], item[1]), reverse=True)
    records = records[:8]
    return [item[0] for item in records], [item[1] for item in records]


def _merge_projects(left: dict, right: dict, stats: EntityDedupStats) -> dict:
    primary, secondary = (left, right) if _project_score(left) >= _project_score(right) else (right, left)
    merged = deepcopy(primary)
    left_title, right_title = clean_project_title(left.get("name")), clean_project_title(right.get("name"))
    left_was_spoken = bool(TITLE_PREFIX.match(str(left.get("name") or "")))
    right_was_spoken = bool(TITLE_PREFIX.match(str(right.get("name") or "")))
    if is_forbidden_experience_name(left.get("name")) != is_forbidden_experience_name(right.get("name")):
        merged["name"] = right_title if is_forbidden_experience_name(left.get("name")) else left_title
    elif left_was_spoken != right_was_spoken:
        merged["name"] = right_title if left_was_spoken else left_title
    else:
        merged["name"] = left_title if len(left_title) <= len(right_title) else right_title
    if not merged["name"]:
        merged["name"] = "项目经历"
    merged["intro"] = _choose_text(str(primary.get("intro") or ""), str(secondary.get("intro") or ""))
    merged["role"] = _choose_text(str(primary.get("role") or ""), str(secondary.get("role") or ""))
    details, detail_fact_ids = _merge_details(primary, secondary, stats)
    merged["details"] = details
    merged["detail_fact_ids"] = detail_fact_ids
    all_fact_ids = list(dict.fromkeys([
        *[str(item) for item in primary.get("source_fact_ids", []) or []],
        *[str(item) for item in secondary.get("source_fact_ids", []) or []],
        *[fact_id for row in detail_fact_ids for fact_id in row],
    ]))
    merged["source_fact_ids"] = all_fact_ids
    source_id = str(primary.get("source_experience_id") or secondary.get("source_experience_id") or "")
    if source_id:
        merged["source_experience_id"] = source_id
    primary_fact_ids = _fact_ids(primary)
    stats.recovered_unique_fact_count += len(set(all_fact_ids) - primary_fact_ids)
    return merged


def analyze_duplicate_experience_entities(payload: schemas.GenerationPayload) -> dict[str, int]:
    projects = payload.resume_sections.projects
    duplicate_entities = duplicate_sources = normalized_titles = fingerprints = possible = 0
    for left_index in range(len(projects)):
        for right_index in range(left_index + 1, len(projects)):
            decision = _duplicate_decision(projects[left_index], projects[right_index])
            if decision.possible:
                possible += 1
            if not decision.duplicate:
                continue
            duplicate_entities += 1
            duplicate_sources += decision.reason == "exact_source_duplicate"
            normalized_titles += decision.reason == "normalized_title_duplicate"
            fingerprints += decision.reason == "fact_fingerprint_duplicate"
    return {
        "experience_entity_count": len(projects),
        "unique_source_experience_id_count": len({str(item.get("source_experience_id")) for item in projects if item.get("source_experience_id")}),
        "duplicate_experience_entity_count": duplicate_entities,
        "duplicate_source_experience_id_count": duplicate_sources,
        "normalized_title_duplicate_count": normalized_titles,
        "fact_fingerprint_duplicate_count": fingerprints,
        "possible_duplicate_count": possible,
    }


def _write_log(stats: EntityDedupStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(stats), ensure_ascii=False) + "\n")
    except OSError:
        pass


def deduplicate_resume_experience_entities(
    payload: schemas.GenerationPayload,
    raw_input: str,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
    apply_hierarchy: bool = True,
    semantic_build: "CanonicalSemanticBuild | None" = None,
    ownership_index: "CanonicalFactOwnershipIndex | None" = None,
    scoped_access_stats: CanonicalScopedFactAccessStats | None = None,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    projects = [deepcopy(item) for item in updated.resume_sections.projects if isinstance(item, dict)]
    canonical_mode = semantic_build is not None or ownership_index is not None
    ownership = ownership_index or (semantic_build.ownership_index if semantic_build is not None else None)
    identities = list(semantic_build.identities) if semantic_build is not None else (build_experience_identities(raw_input) if raw_input else [])
    stats = EntityDedupStats(
        created_at=datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        stage=stage,
        generation_result_id=generation_result_id,
        project_count_before=len(projects),
    )

    if apply_hierarchy:
        projects = merge_parent_child_projects(
            projects,
            "" if canonical_mode else raw_input,
            stage=f"{stage}_entity_dedup",
            generation_result_id=generation_result_id,
            write_log=write_log,
            identities=identities if canonical_mode else None,
            require_same_frozen_owner=canonical_mode,
        )

    for project in projects:
        project["name"] = clean_project_title(project.get("name")) or "项目经历"
        if not canonical_mode and not project.get("source_experience_id"):
            matched_id = _identity_title_match(project, identities)
            if matched_id:
                project["source_experience_id"] = matched_id
                project["immutable_source_experience_id"] = matched_id
                project["source_binding_origin"] = "entity_dedup_title_inference"
                project["source_binding_confidence"] = 0.9
                project["source_binding_locked"] = False

    unique: list[dict] = []
    for incoming_index, project in enumerate(projects):
        matched_index = -1
        matched_decision = None
        for index, existing in enumerate(unique):
            if canonical_mode:
                left_owner = str(existing.get("immutable_source_experience_id") or "")
                right_owner = str(project.get("immutable_source_experience_id") or "")
                if left_owner != right_owner:
                    decision = DuplicateDecision(False, "distinct_frozen_source_experience_id", 1.0)
                    if scoped_access_stats is not None:
                        scoped_access_stats.rejected_cross_owner_access_count += 1
                else:
                    decision = _duplicate_decision(existing, project)
            else:
                decision = _duplicate_decision(existing, project)
            if decision.possible:
                stats.possible_duplicate_count += 1
                if decision.reason == "provenance_conflict":
                    stats.provenance_conflict_count += 1
                    stats.inferred_id_collision_count += 1
                stats.decisions.append({
                    "left_index": index, "right_index": incoming_index,
                    "source_experience_id": str(project.get("source_experience_id") or ""),
                    "decision": decision.reason, "confidence": decision.confidence, "result": "kept_separate",
                })
            if decision.duplicate:
                matched_index, matched_decision = index, decision
                break
        if matched_index < 0:
            unique.append(project)
            continue

        stats.duplicate_entity_count += 1
        stats.merged_project_count += 1
        if matched_decision.reason == "exact_source_duplicate":
            stats.duplicate_source_id_count += 1
        elif matched_decision.reason == "normalized_title_duplicate":
            stats.normalized_title_duplicate_count += 1
        else:
            stats.fact_fingerprint_duplicate_count += 1
        source_ids = _source_ids(unique[matched_index]) | _source_ids(project)
        stats.affected_experience_ids.extend(sorted(source_ids))
        stats.decisions.append({
            "left_index": matched_index, "right_index": incoming_index,
            "source_experience_id": sorted(source_ids)[0] if len(source_ids) == 1 else "",
            "decision": matched_decision.reason, "confidence": matched_decision.confidence, "result": "merged",
        })
        unique[matched_index] = _merge_projects(unique[matched_index], project, stats)

    stats.project_count_after = len(unique)
    stats.affected_experience_ids = sorted(set(stats.affected_experience_ids))
    updated.resume_sections.projects = unique
    if write_log:
        _write_log(stats)
    return updated
