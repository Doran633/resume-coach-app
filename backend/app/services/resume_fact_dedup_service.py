import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import HIGH_VALUE_TERMS, TECH_PATTERN, normalize_fact_text


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_fact_dedup.jsonl"
WEAK_PREFIXES = ["之后", "进一步", "同时", "随后", "在多段经历输入中", "在多段经历中", "目前"]
EXPERIMENT_TERMS = {"chunk size", "chunk overlap", "top-k", "score threshold", "retrieval ranking"}
RAG_CHAIN_TERMS = {"文档解析", "切块", "embedding", "向量检索", "回答生成"}
DISTINCT_FACETS = {
    "project_positioning": ["面向", "目标", "定位", "场景", "解决"],
    "ownership": ["负责", "主导", "独立", "owner", "承担"],
    "implementation": ["实现", "开发", "构建", "接入", "功能", "链路"],
    "retrieval_pipeline": ["切块", "embedding", "向量检索", "回答生成", "rag"],
    "evaluation": ["评测", "测试集", "groundedness", "retrieval", "指标", "质量"],
    "citation": ["citation", "来源", "source cards", "溯源"],
    "deployment": ["部署", "上线", "nginx", "systemd", "公网", "健康检查"],
    "observability": ["日志", "健康检查", "smoke test", "trace", "监控"],
    "isolation": ["数据隔离", "权限隔离", "课程隔离", "用户隔离"],
    "optimization": ["实验", "调优", "参数", "top-k", "score threshold", "ranking", "优化"],
    "result": ["提升", "降低", "用户", "奖项", "一等奖", "相关度", "%"],
    "product_iteration": ["用户反馈", "版本迭代", "架构调整", "重构", "迭代"],
    "problem_solving": ["定位", "排查", "修复", "cors", "端口冲突", "配置问题"],
}
ACTION_TERMS = ["实现", "构建", "设计", "开发", "优化", "部署", "定位", "修复", "建立", "拆分", "识别", "解决", "负责", "主导"]
RESULT_TERMS = ["提升", "降低", "上线", "交付", "获奖", "一等奖", "验证", "支持", "完成"]
EVIDENCE_TERMS = ["日志", "测试集", "指标", "用户反馈", "仓库", "文档", "截图", "记录", "证书"]
WEAK_WORDING = ["进一步发现", "持续优化", "围绕项目目标", "完成相关工作", "提升项目质量", "具备相关能力", "技术动作", "之后", "同时"]


@dataclass
class DedupStats:
    stage: str
    generation_result_id: int | None
    compared_pair_count: int = 0
    exact_duplicate_count: int = 0
    semantic_duplicate_count: int = 0
    merged_count: int = 0
    removed_count: int = 0
    retained_unique_fact_count: int = 0
    affected_experience_ids: list[str] = field(default_factory=list)
    merged_source_fact_ids: list[str] = field(default_factory=list)
    dedup_confidence_distribution: dict[str, int] = field(default_factory=lambda: {"high": 0, "medium": 0, "low": 0})
    source_experience_id: str = ""
    details_before: int = 0
    details_after: int = 0
    containment_duplicate_count: int = 0
    merged_detail_count: int = 0
    removed_detail_count: int = 0
    preserved_high_value_fact_count: int = 0
    duplicate_groups: list[dict] = field(default_factory=list)
    decision_reason: list[str] = field(default_factory=list)
    similarity_score: list[float] = field(default_factory=list)
    source_fact_ids: list[str] = field(default_factory=list)


def _core(text: str) -> str:
    value = str(text or "")
    for prefix in WEAK_PREFIXES:
        value = value.replace(prefix, "")
    return normalize_fact_text(value)


def _terms(text: str) -> set[str]:
    values = {item.lower() for item in TECH_PATTERN.findall(text or "") if item}
    values.update(re.findall(r"\d+(?:\.\d+)?", text or ""))
    values.update(term for term in ["发现", "识别", "解决", "推进", "优化", "部署", "测试", "评估"] if term in (text or ""))
    return values


def similarity(left: str, right: str) -> float:
    a, b = _core(left), _core(right)
    if not a or not b:
        return 0.0
    if min(len(a), len(b)) >= 12 and (a in b or b in a):
        return 0.96
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = _terms(left) | _normalized_terms(left), _terms(right) | _normalized_terms(right)
    overlap = len(ta & tb) / max(1, len(ta | tb))
    return ratio * 0.7 + overlap * 0.3


def _merge(left: str, right: str) -> str:
    if _core(left) in _core(right):
        return right
    if _core(right) in _core(left):
        return left
    return right if len(right) > len(left) else left


@dataclass
class DetailRecord:
    text: str
    source_fact_ids: list[str] = field(default_factory=list)
    original_index: int = 0


def _normalized_terms(text: str) -> set[str]:
    lowered = str(text or "").lower().replace("top k", "top-k")
    values = {item.lower() for item in TECH_PATTERN.findall(lowered) if item}
    values.update(re.findall(r"\d+(?:\.\d+)?(?:%|ms|s|秒|次|人|token)?", lowered))
    for term in EXPERIMENT_TERMS | RAG_CHAIN_TERMS:
        if term in lowered:
            values.add(term)
    return values


def _facets(text: str) -> set[str]:
    lowered = str(text or "").lower()
    return {name for name, markers in DISTINCT_FACETS.items() if any(marker in lowered for marker in markers)}


def information_score(text: str, source_fact_ids: list[str] | None = None) -> float:
    value = str(text or "")
    tech_count = len(_normalized_terms(value))
    action_count = sum(term in value for term in ACTION_TERMS)
    result_count = sum(term in value for term in RESULT_TERMS)
    evidence_count = sum(term.lower() in value.lower() for term in EVIDENCE_TERMS)
    metric_count = len(re.findall(r"\d+(?:\.\d+)?(?:%|ms|s|秒|次|人|token)?", value, re.I))
    problem_count = sum(term.lower() in value.lower() for term in DISTINCT_FACETS["problem_solving"])
    weak_count = sum(term in value for term in WEAK_WORDING)
    completeness = 2 if re.search(r"[。！？]$", value.strip()) else 0
    return (
        tech_count * 3 + action_count * 2 + result_count * 2 + evidence_count * 2
        + metric_count * 3 + problem_count * 2 + len(source_fact_ids or []) * 2
        + min(len(value), 120) / 30 + completeness - weak_count * 2
    )


def same_fact_action(left: str, right: str) -> bool:
    left_core, right_core = _core(left), _core(right)
    if "experiencedilution" in left_core and "experiencedilution" in right_core:
        return bool({"发现", "识别", "解决"} & _terms(left)) and bool({"发现", "识别", "解决"} & _terms(right))
    facets = _facets(left) & _facets(right)
    terms_left, terms_right = _normalized_terms(left), _normalized_terms(right)
    term_overlap = len(terms_left & terms_right) / max(1, min(len(terms_left), len(terms_right)))
    return bool(facets) and term_overlap >= 0.75 and similarity(left, right) >= 0.82


def _same_experiment(left: str, right: str) -> bool:
    left_terms = _normalized_terms(left) & EXPERIMENT_TERMS
    right_terms = _normalized_terms(right) & EXPERIMENT_TERMS
    return len(left_terms & right_terms) >= 3 and bool(re.search(r"实验|优化|调优", left, re.I)) and bool(re.search(r"实验|优化|调优", right, re.I))


def _merge_records(left: DetailRecord, right: DetailRecord) -> DetailRecord:
    left_core, right_core = _core(left.text), _core(right.text)
    if left_core in right_core:
        text = right.text
    elif right_core in left_core:
        text = left.text
    else:
        left_score = information_score(left.text, left.source_fact_ids)
        right_score = information_score(right.text, right.source_fact_ids)
        text = right.text if right_score > left_score else left.text
    return DetailRecord(
        text=text,
        source_fact_ids=list(dict.fromkeys([*left.source_fact_ids, *right.source_fact_ids])),
        original_index=min(left.original_index, right.original_index),
    )


def _generic_rag_summary_covered(record: DetailRecord, others: list[DetailRecord]) -> bool:
    terms = _normalized_terms(record.text) & RAG_CHAIN_TERMS
    if len(terms) < 4 or not re.search(r"梳理|应用链路|完整链路|全链路", record.text, re.I):
        return False
    covered: set[str] = set()
    supporting_count = 0
    for other in others:
        hits = _normalized_terms(other.text) & terms
        if hits:
            covered.update(hits)
            supporting_count += 1
    return supporting_count >= 2 and covered >= terms


def _is_high_value(text: str) -> bool:
    if re.search(r"\d+(?:\.\d+)?%|上线|部署|测试集|评测|指标|数据隔离|权限|日志|健康检查|Smoke Test|Citation|Groundedness", text, re.I):
        return True
    return any(term.lower() in text.lower() for term in HIGH_VALUE_TERMS)


def _detail_records(project: dict) -> list[DetailRecord]:
    details = [str(item).strip() for item in project.get("details", []) if str(item).strip()]
    fact_ids = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
    records: list[DetailRecord] = []
    for index, text in enumerate(details):
        ids = fact_ids[index] if index < len(fact_ids) and isinstance(fact_ids[index], list) else []
        records.append(DetailRecord(text=text, source_fact_ids=[str(item) for item in ids], original_index=index))
    return records


def _write_log(stats: DedupStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **stats.__dict__}
        entry["affected_experience_ids"] = sorted(set(entry["affected_experience_ids"]))
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def deduplicate_resume_facts(payload: schemas.GenerationPayload, *, stage: str = "unknown", generation_result_id: int | None = None, write_log: bool = True) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        stats = DedupStats(stage=stage, generation_result_id=generation_result_id, source_experience_id=source_id)
        incoming = _detail_records(project)
        stats.details_before = len(incoming)
        intro_role = [str(project.get("intro") or ""), str(project.get("role") or "")]
        unique: list[DetailRecord] = []
        for candidate in incoming:
            if any(similarity(value, candidate.text) >= 0.94 for value in intro_role if value):
                stats.containment_duplicate_count += 1
                stats.removed_detail_count += 1
                stats.removed_count += 1
                stats.decision_reason.append("covered_by_intro_or_role")
                continue
            matched_index = -1
            matched_reason = ""
            matched_score = 0.0
            for index, existing in enumerate(unique):
                stats.compared_pair_count += 1
                score = similarity(existing.text, candidate.text)
                left_core, right_core = _core(existing.text), _core(candidate.text)
                exact = left_core == right_core
                containment = min(len(left_core), len(right_core)) >= 12 and (left_core in right_core or right_core in left_core)
                same_fact_ids = bool(set(existing.source_fact_ids) & set(candidate.source_fact_ids)) and score >= 0.68
                same_experiment = _same_experiment(existing.text, candidate.text)
                same_action = same_fact_action(existing.text, candidate.text)
                semantic = score >= 0.90 and bool(_facets(existing.text) & _facets(candidate.text))
                if exact or containment or same_fact_ids or same_experiment or same_action or semantic:
                    matched_index = index
                    matched_score = score
                    matched_reason = "exact" if exact else "containment" if containment else "same_source_fact_ids" if same_fact_ids else "same_experiment" if same_experiment else "same_fact_action" if same_action else "high_semantic_similarity"
                    break
                stats.dedup_confidence_distribution["medium" if score >= 0.72 else "low"] += 1
            if matched_index < 0:
                unique.append(candidate)
                continue
            previous = unique[matched_index]
            unique[matched_index] = _merge_records(previous, candidate)
            if matched_reason == "exact":
                stats.exact_duplicate_count += 1
            elif matched_reason == "containment":
                stats.containment_duplicate_count += 1
            else:
                stats.semantic_duplicate_count += 1
            stats.dedup_confidence_distribution["high"] += 1
            stats.merged_count += 1
            stats.merged_detail_count += 1
            stats.removed_count += 1
            stats.removed_detail_count += 1
            stats.affected_experience_ids.append(source_id)
            stats.decision_reason.append(matched_reason)
            stats.similarity_score.append(round(matched_score, 3))
            stats.duplicate_groups.append({"kept_index": previous.original_index, "merged_index": candidate.original_index, "reason": matched_reason, "score": round(matched_score, 3)})

        filtered: list[DetailRecord] = []
        for record in unique:
            if _generic_rag_summary_covered(record, [item for item in unique if item is not record]):
                stats.containment_duplicate_count += 1
                stats.removed_count += 1
                stats.removed_detail_count += 1
                stats.decision_reason.append("generic_summary_covered_by_details")
                continue
            filtered.append(record)

        filtered = filtered[:8]
        project["details"] = [record.text for record in filtered]
        project["detail_fact_ids"] = [record.source_fact_ids for record in filtered]
        project["source_fact_ids"] = list(dict.fromkeys(fact_id for record in filtered for fact_id in record.source_fact_ids))
        stats.details_after = len(filtered)
        stats.retained_unique_fact_count = len(filtered)
        stats.preserved_high_value_fact_count = sum(_is_high_value(record.text) for record in filtered)
        stats.source_fact_ids = project["source_fact_ids"]
        stats.merged_source_fact_ids = stats.source_fact_ids
        if write_log:
            _write_log(stats)
    return updated
