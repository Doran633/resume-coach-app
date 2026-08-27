import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_fact_ledger_service import (
    TECH_PATTERN,
    ExperienceFact,
    build_experience_fact_ledger,
    fact_match_score,
)
from .experience_identity_service import build_experience_identities


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_summary_quality.jsonl"
COACH_LANGUAGE = [
    "候选人", "爱好者", "适合将", "整理为可面试", "可面试承接", "可投递表达", "简历表达",
    "包装经历", "课程项目、小项目", "缺少实习", "履历薄弱", "建议补充", "持续补齐",
    "准备降级表达", "面试时可以", "如果被问到", "需要学习", "降级表达", "求职教练",
]
EXPERT_OVERCLAIMS = ["经验丰富", "行业专家", "资深", "精通"]
SUMMARY_MAX_COUNT = 2
OWNERSHIP_TERMS = ["独立", "主导", "负责", "从零", "核心成员"]
PROBLEM_TERMS = ["解决", "排查", "修复", "优化", "复盘", "冲突", "调试"]
COLLABORATION_TERMS = ["团队", "协作", "沟通", "组织", "推进", "参与", "汇报", "答辩", "活动执行"]


@dataclass
class SummaryCandidate:
    text: str
    dimension: str
    source_experience_ids: list[str]
    source_fact_ids: list[str]


@dataclass
class SummaryStats:
    stage: str
    generation_result_id: int | None = None
    summary_count_before: int = 0
    summary_count_after: int = 0
    coach_language_removed_count: int = 0
    unsupported_summary_removed_count: int = 0
    fact_grounded_summary_count: int = 0
    source_experience_ids: list[str] = field(default_factory=list)
    source_fact_ids: list[str] = field(default_factory=list)


def _facts_with_terms(facts: list[ExperienceFact], terms: list[str]) -> list[ExperienceFact]:
    return [fact for fact in facts if any(term.lower() in fact.fact_text.lower() for term in terms)]


def _candidate(text: str, dimension: str, facts: list[ExperienceFact]) -> SummaryCandidate:
    return SummaryCandidate(
        text=text,
        dimension=dimension,
        source_experience_ids=list(dict.fromkeys(fact.experience_id for fact in facts)),
        source_fact_ids=list(dict.fromkeys(fact.fact_id for fact in facts)),
    )


def build_grounded_summary_candidates(raw_input: str) -> list[SummaryCandidate]:
    ledger = build_experience_fact_ledger(raw_input)
    facts = [fact for fact in ledger.facts if fact.resume_ready_text]
    identities = build_experience_identities(raw_input)
    candidates: list[SummaryCandidate] = []

    ownership = _facts_with_terms(facts, OWNERSHIP_TERMS)
    if ownership:
        candidates.append(_candidate(
            "具备独立推进任务的实践能力，能够围绕目标完成需求拆解、功能实现和结果验证。",
            "ownership", ownership[:3]))

    technical = [fact for fact in facts if fact.fact_type in {"技术", "部署", "工程实践"} or TECH_PATTERN.search(fact.fact_text)]
    tech_terms = list(dict.fromkeys(term for fact in technical for term in TECH_PATTERN.findall(fact.fact_text)))[:5]
    if technical:
        tech_label = "、".join(tech_terms)
        wording = f"具备技术方案落地能力，能够运用{tech_label}完成具体功能开发与实现验证。" if tech_label else "具备技术方案落地能力，能够完成具体功能开发与实现验证。"
        candidates.append(_candidate(wording, "technical_delivery", technical[:4]))

    problem = _facts_with_terms(facts, PROBLEM_TERMS)
    if problem:
        candidates.append(_candidate(
            "具备问题拆解与工程排查能力，能够结合测试、日志或结果反馈定位问题并持续优化。",
            "problem_solving", problem[:4]))

    quantified = [fact for fact in facts if fact.fact_type == "指标"]
    if quantified:
        candidates.append(_candidate(
            "具备结果验证意识，能够通过明确指标记录优化前后的变化并支撑方案迭代。",
            "quantified_result", quantified[:3]))

    collaboration = _facts_with_terms(facts, COLLABORATION_TERMS)
    if collaboration:
        candidates.append(_candidate(
            "具备协作与交付意识，能够参与任务推进、材料沉淀、展示汇报和结果复盘。",
            "collaboration", collaboration[:3]))

    experience_types = {identity.experience_type for identity in identities}
    explicit_transfer = any(term in raw_input for term in ["迁移", "跨场景", "应用到不同", "综合运用"])
    if len(experience_types) >= 2 or explicit_transfer:
        candidates.append(_candidate(
            "具备跨场景学习迁移能力，能够将已有方法应用到不同实践任务并完成落地验证。",
            "learning_transfer", facts[:4]))

    if any(term in raw_input for term in ("课程项目", "课设", "大作业", "个人项目", "项目")) and facts:
        candidates.append(_candidate(
            "具备项目实践能力，能够围绕任务目标完成需求理解、功能实现与成果展示。",
            "project_delivery", facts[:4]))

    if any(term in raw_input for term in ("页面", "接口", "功能", "系统", "开发", "实现")) and facts:
        candidates.append(_candidate(
            "具备功能开发与联调实践，能够围绕页面、接口或系统功能推进实现与验证。",
            "implementation", facts[:4]))

    functional = [fact for fact in facts if fact.fact_type in {"功能", "职责", "证据"}]
    execution_facts = functional or facts[:4]
    if execution_facts:
        candidates.append(_candidate(
            "具备任务落地与结果验证意识，能够围绕具体目标推进功能实现并检查交付结果。",
            "execution", execution_facts[:4]))
    return candidates


def _has_coach_language(text: str) -> bool:
    return any(term in text for term in COACH_LANGUAGE + EXPERT_OVERCLAIMS)


def _best_support(text: str, facts: list[ExperienceFact]) -> tuple[ExperienceFact | None, float]:
    ranked = sorted(((fact, fact_match_score(text, fact)) for fact in facts), key=lambda item: item[1], reverse=True)
    return ranked[0] if ranked else (None, 0.0)


def _summary_dimension(text: str) -> str:
    checks = [
        ("ownership", ["独立", "主导", "负责", "推进"]),
        ("problem_solving", ["问题", "排查", "调试", "优化", "复盘"]),
        ("quantified_result", ["指标", "量化", "提升", "降低"]),
        ("collaboration", ["协作", "沟通", "组织", "汇报", "答辩"]),
        ("learning_transfer", ["学习迁移", "跨场景"]),
        ("project_delivery", ["项目实践", "需求理解", "成果展示"]),
        ("implementation", ["功能开发", "联调实践", "页面、接口"]),
        ("technical_delivery", ["技术落地", "技术方案", "开发", "实现"]),
    ]
    for dimension, terms in checks:
        if any(term in text for term in terms):
            return dimension
    return "execution"


def _compact_summary(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    clauses = [item.strip(" ，；。") for item in re.split(r"[；;。]", cleaned) if item.strip(" ，；。")]
    if len(clauses) > 2:
        clauses = clauses[:2]
    compacted = "，".join(clauses)
    if compacted and compacted[-1] not in "。！？":
        compacted += "。"
    return compacted


def _summary_similarity(left: str, right: str) -> float:
    def tokens(text: str) -> set[str]:
        normalized = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9+#./-]", "", text).lower()
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
        bigrams = {chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))}
        english = set(re.findall(r"[a-z][a-z0-9+#./-]*", normalized))
        return bigrams | english

    left_tokens = tokens(left)
    right_tokens = tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def _write_log(stats: SummaryStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "generation_result_id": stats.generation_result_id,
            "stage": stats.stage,
            "summary_count_before": stats.summary_count_before,
            "summary_count_after": stats.summary_count_after,
            "coach_language_removed_count": stats.coach_language_removed_count,
            "unsupported_summary_removed_count": stats.unsupported_summary_removed_count,
            "fact_grounded_summary_count": stats.fact_grounded_summary_count,
            "source_experience_ids": list(dict.fromkeys(stats.source_experience_ids)),
            "source_fact_ids": list(dict.fromkeys(stats.source_fact_ids)),
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return


def ensure_resume_summary_quality(
    payload: schemas.GenerationPayload,
    raw_input: str,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    facts = [fact for fact in build_experience_fact_ledger(raw_input).facts if fact.resume_ready_text]
    stats = SummaryStats(stage=stage, generation_result_id=generation_result_id)
    stats.summary_count_before = len(updated.resume_sections.summary)
    kept: list[str] = []
    used_dimensions: set[str] = set()

    for raw_summary in updated.resume_sections.summary:
        summary = _compact_summary(raw_summary)
        if not summary:
            continue
        if _has_coach_language(summary):
            stats.coach_language_removed_count += 1
            continue
        support, score = _best_support(summary, facts)
        explicit_terms = [term for term in TECH_PATTERN.findall(summary) if term]
        explicit_supported = bool(explicit_terms) and all(term.lower() in raw_input.lower() for term in explicit_terms)
        ability_supported = any(term in summary for term in ["独立", "技术落地", "问题", "优化", "协作", "交付", "结果验证"]) and bool(facts)
        if not support or (score < 0.32 and not explicit_supported and not ability_supported):
            stats.unsupported_summary_removed_count += 1
            continue
        if summary not in kept and not any(_summary_similarity(summary, item) >= 0.65 for item in kept):
            kept.append(summary)
            used_dimensions.add(_summary_dimension(summary))
            stats.source_experience_ids.append(support.experience_id)
            stats.source_fact_ids.append(support.fact_id)

    for candidate in build_grounded_summary_candidates(raw_input):
        if len(kept) >= SUMMARY_MAX_COUNT:
            break
        candidate_text = _compact_summary(candidate.text)
        if (
            candidate.dimension not in used_dimensions
            and candidate_text not in kept
            and not any(_summary_similarity(candidate_text, item) >= 0.65 for item in kept)
        ):
            kept.append(candidate_text)
            used_dimensions.add(candidate.dimension)
            stats.source_experience_ids.extend(candidate.source_experience_ids)
            stats.source_fact_ids.extend(candidate.source_fact_ids)

    if not kept:
        candidates = build_grounded_summary_candidates(raw_input)
        if candidates:
            kept.append(_compact_summary(candidates[0].text))
            stats.source_experience_ids.extend(candidates[0].source_experience_ids)
            stats.source_fact_ids.extend(candidates[0].source_fact_ids)

    updated.resume_sections.summary = kept[:SUMMARY_MAX_COUNT]
    stats.summary_count_after = len(updated.resume_sections.summary)
    stats.fact_grounded_summary_count = stats.summary_count_after
    if write_log:
        _write_log(stats)
    return updated
