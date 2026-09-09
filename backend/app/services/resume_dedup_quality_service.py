import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import TECH_PATTERN
from .resume_fact_dedup_service import (
    DetailRecord,
    _detail_records,
    _preserve_project_aggregates,
    _provenance_is_mergeable,
    information_score,
    same_fact_action,
    similarity,
)


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_dedup_quality.jsonl"


@dataclass
class DedupQualityStats:
    stage: str
    generation_result_id: int | None
    project_count: int = 0
    duplicate_candidate_count: int = 0
    duplicate_cluster_count: int = 0
    removed_duplicate_count: int = 0
    merged_duplicate_count: int = 0
    cross_field_duplicate_count: int = 0
    preserved_independent_fact_count: int = 0
    fact_coverage_before: float = 1.0
    fact_coverage_after: float = 1.0
    dedup_precision_warning_count: int = 0
    affected_experience_ids: list[str] = field(default_factory=list)
    source_fact_ids: list[str] = field(default_factory=list)


def _metric_terms(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?(?:%|ms|s|秒|次|人|token)?", str(text or ""), re.I))


def _tech_terms(text: str) -> set[str]:
    return {term.lower() for term in TECH_PATTERN.findall(str(text or "")) if term}


def _protected_facets(text: str) -> set[str]:
    lowered = str(text or "").lower()
    groups = {
        "evaluation": ["测试集", "评测", "groundedness", "retrieval", "recall"],
        "citation": ["citation", "来源展示", "答案溯源"],
        "deployment": ["部署", "vps", "nginx", "systemd", "公网"],
        "observability": ["日志", "健康检查", "smoke test", "trace"],
        "isolation": ["数据隔离", "权限隔离", "用户隔离"],
        "problem_solving": ["cors", "端口冲突", "配置问题", "排查", "修复"],
        "optimization": ["top-k", "阈值", "参数实验", "调优"],
    }
    return {name for name, terms in groups.items() if any(term in lowered for term in terms)}


def _adds_independent_information(left: str, right: str) -> bool:
    left_metrics, right_metrics = _metric_terms(left), _metric_terms(right)
    if left_metrics and right_metrics and not (left_metrics <= right_metrics or right_metrics <= left_metrics):
        return True
    left_tech, right_tech = _tech_terms(left), _tech_terms(right)
    if bool(left_tech) != bool(right_tech):
        return True
    if left_tech and right_tech and not (left_tech <= right_tech or right_tech <= left_tech):
        return True
    left_facets, right_facets = _protected_facets(left), _protected_facets(right)
    if bool(left_facets) != bool(right_facets):
        return True
    return bool(left_facets and right_facets and not (left_facets <= right_facets or right_facets <= left_facets))


def _same_fact_ids_are_mergeable(left: DetailRecord, right: DetailRecord) -> bool:
    if not _provenance_is_mergeable(left, right):
        return False
    left_metrics, right_metrics = _metric_terms(left.text), _metric_terms(right.text)
    # One ledger fact can contain several independent metrics. Shared provenance alone
    # must not collapse distinct quantified outcomes.
    if _adds_independent_information(left.text, right.text):
        return False
    return similarity(left.text, right.text) >= 0.62 or not left_metrics or not right_metrics


def _write_log(stats: DedupQualityStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def ensure_dedup_quality(
    payload: schemas.GenerationPayload,
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    stats = DedupQualityStats(stage=stage, generation_result_id=generation_result_id)
    stats.project_count = len(updated.resume_sections.projects)
    before_ids: set[str] = set()
    after_ids: set[str] = set()

    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        intro = str(project.get("intro") or "")
        role = str(project.get("role") or "")
        original_records = _detail_records(project, include_empty=True)
        incoming = [record for record in original_records if record.text]
        before_ids.update(fact_id for record in incoming for fact_id in record.source_fact_ids)
        retained: list[DetailRecord] = []

        for candidate in incoming:
            detail = candidate.text
            ids = candidate.source_fact_ids
            cross_field_match = None
            for field_name, field_text in (("intro", intro), ("role", role)):
                if not field_text:
                    continue
                field_record = DetailRecord(
                    text=field_text,
                    source_fact_ids=(
                        [str(value) for value in project.get("role_source_fact_ids", [])]
                        if field_name == "role" and isinstance(project.get("role_source_fact_ids"), list)
                        else []
                    ),
                    source_claim_ids=(
                        [str(value) for value in project.get("role_source_claim_ids", [])]
                        if field_name == "role" and isinstance(project.get("role_source_claim_ids"), list)
                        else []
                    ),
                )
                # A project aggregate does not prove that intro carries this fact.
                if not _provenance_is_mergeable(field_record, candidate):
                    continue
                if _adds_independent_information(field_text, detail):
                    continue
                score = similarity(field_text, detail)
                if score >= 0.90 or same_fact_action(field_text, detail):
                    cross_field_match = (field_name, field_text, score)
                    break
            if cross_field_match:
                stats.duplicate_candidate_count += 1
                stats.duplicate_cluster_count += 1
                stats.cross_field_duplicate_count += 1
                if information_score(detail, ids) <= information_score(cross_field_match[1]):
                    stats.removed_duplicate_count += 1
                    if source_id:
                        stats.affected_experience_ids.append(source_id)
                    continue

            duplicate_index = -1
            for kept_index, kept in enumerate(retained):
                if not _provenance_is_mergeable(kept, candidate):
                    continue
                if _adds_independent_information(kept.text, detail):
                    continue
                same_ids = _same_fact_ids_are_mergeable(kept, candidate)
                score = similarity(kept.text, detail)
                if same_ids or score >= 0.92 or same_fact_action(kept.text, detail):
                    duplicate_index = kept_index
                    stats.duplicate_candidate_count += 1
                    break
            if duplicate_index < 0:
                retained.append(candidate)
                continue

            stats.duplicate_cluster_count += 1
            current = retained[duplicate_index]
            if information_score(detail, ids) > information_score(current.text, current.source_fact_ids):
                retained[duplicate_index] = candidate
            stats.merged_duplicate_count += 1
            if source_id:
                stats.affected_experience_ids.append(source_id)

        # A quality pass never pads details. It only caps after preserving source order.
        retained = retained[:8]
        project["details"] = [record.text for record in retained]
        project["detail_fact_ids"] = [record.source_fact_ids for record in retained]
        project["detail_claim_ids"] = [record.source_claim_ids for record in retained]
        _preserve_project_aggregates(project, retained, original_records)
        after_ids.update(fact_id for record in retained for fact_id in record.source_fact_ids)
        stats.preserved_independent_fact_count += len(retained)

    if before_ids:
        stats.fact_coverage_before = 1.0
        stats.fact_coverage_after = len(after_ids & before_ids) / len(before_ids)
        if stats.fact_coverage_after < stats.fact_coverage_before:
            stats.dedup_precision_warning_count += 1
    stats.affected_experience_ids = list(dict.fromkeys(stats.affected_experience_ids))
    stats.source_fact_ids = sorted(after_ids)
    if write_log:
        _write_log(stats)
    return updated
