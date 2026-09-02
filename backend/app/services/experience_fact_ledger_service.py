import re
from dataclasses import dataclass, field
from typing import Sequence

from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .input_semantic_role_service import (
    InputSemanticAnalysis,
    InputSemanticUnit,
    RESUME_FACT,
    analyze_experience_semantics,
)
from .input_claim_resolution_service import (
    ClaimResolution,
    ELIGIBLE,
    InputClaim,
    resolve_experience_claims,
)


HIGH_VALUE_TERMS = [
    "部署", "上线", "公网", "域名", "数据隔离", "权限", "邀请码", "日志", "健康检查",
    "Smoke Test", "测试集", "评测", "指标", "Groundedness", "Citation", "Retrieval",
    "Fallback", "Experience Dilution", "CORS", "端口冲突", "问题", "优化", "提升", "降低",
]
TECH_PATTERN = re.compile(
    r"React|TypeScript|JavaScript|Python|FastAPI|SQLite|Nginx|systemd|VPS|RAG|Agent|Embedding|"
    r"BAAI/?bge-m3|Top-K|Citation|Retrieval|Groundedness|Smoke Test|CORS|JSON Schema|DOCX|token|"
    r"CodeBuddy|虚拟机|LoRa|地磁传感器|地图\s*API|SSL|回归分析|线性回归|多项式回归|"
    r"模型效果对比|数据可视化|智能制图|路线规划",
    re.IGNORECASE,
)
METRIC_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:%|ms|s|秒|次|人|用户|star|stars|token)?", re.IGNORECASE)
GENERIC_DETAIL_MARKERS = [
    "围绕真实使用场景梳理需求", "将原始经历整理为可投递", "基于已有事实提炼",
    "优先保留用户已经提供", "为每个强表达准备", "围绕用户提供的真实经历",
]
NEGATIVE_BODY_MARKERS = [
    "没有实习", "无实习", "没实习", "没有上线", "未上线", "没有真实用户", "没有用户",
    "没有获奖", "未获奖", "只是课程作业", "只是作业", "简单小项目", "没什么经验",
]


@dataclass
class ExperienceFact:
    experience_id: str
    fact_id: str
    fact_type: str
    fact_text: str
    importance: str
    explicit: bool
    resume_ready_text: str
    source_span: tuple[int, int]
    semantic_unit_id: str = ""
    related_fact_ids: list[str] = field(default_factory=list)
    clause_role: str = "action"
    completeness: str = "complete"
    immutable_experience_id: str = ""
    semantic_role: str = RESUME_FACT
    polarity: str = "positive"
    certainty: str = "certain"
    resume_eligible: bool = True
    claim_id: str = ""
    eligibility: str = ELIGIBLE
    temporal_status: str = "unknown"
    evidence_type: str = "explicit"


@dataclass
class ExperienceFactLedger:
    facts: list[ExperienceFact] = field(default_factory=list)
    constraints: list[InputSemanticUnit] = field(default_factory=list)
    uncertain_facts: list[InputSemanticUnit] = field(default_factory=list)
    excluded_units: list[InputSemanticUnit] = field(default_factory=list)
    claims: list[InputClaim] = field(default_factory=list)
    withheld_claims: list[InputClaim] = field(default_factory=list)
    excluded_claims: list[InputClaim] = field(default_factory=list)

    def for_experience(self, experience_id: str) -> list[ExperienceFact]:
        return [fact for fact in self.facts if fact.experience_id == experience_id]


def normalize_fact_text(text: str) -> str:
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", text or "").lower()


def split_atomic_facts(text: str) -> list[str]:
    # Semicolons often connect one problem/solution or action/result unit in resume input.
    # Keep them together and only split at strong sentence boundaries or explicit lines.
    strong_parts = re.split(r"(?<=[。！？])\s*|\n+|(?<=，)(?=(?:最终|工程侧|目前|根据|实现|完成|解决))", text or "")
    parts: list[str] = []
    for strong_part in strong_parts:
        clauses = re.split(r"[；;]", strong_part)
        cursor = 0
        while cursor < len(clauses):
            current = clauses[cursor].strip()
            if cursor + 1 < len(clauses):
                following = clauses[cursor + 1].strip()
                problem_solution = bool(
                    re.search(r"问题|异常|失败|为空|不足|风险|冲突", current, re.I)
                    and re.match(r"^(?:针对|因此|从而|为此|于是|通过|引入)", following, re.I)
                )
                if problem_solution:
                    current = current.rstrip("，,") + "；" + following
                    cursor += 1
            parts.append(current)
            cursor += 1
    # Claim Resolution has already removed headings, instructions and other
    # non-resume roles. Keep short but complete facts such as “参与接口测试”.
    return [part.strip(" \t\r\n，、；;。") for part in parts if len(normalize_fact_text(part)) >= 4]


def _clause_role(text: str) -> str:
    if re.search(r"提升|降低|达到|获奖|上线|用户|\d+(?:\.\d+)?", text, re.I):
        return "result"
    if re.search(r"问题|异常|失败|冲突|不足|风险|空值", text, re.I):
        return "problem"
    if re.search(r"日志|测试集|指标|记录|仓库|证据", text, re.I):
        return "evidence"
    if re.search(r"选择|权衡|实验|阈值|方案", text, re.I):
        return "decision"
    return "action"


def _completeness(text: str) -> str:
    value = str(text or "").strip()
    if re.search(r"(?:并|同时|以及|从而|因此|其中|包括|例如|通过|针对|基于|围绕)[，,:：;；-]?$", value):
        return "fragment"
    if re.search(r"^(?:针对该问题|在此基础上|预处理阶段|进一步|同时|因此)[，,:：]?", value):
        return "dependent"
    return "complete"


def _fact_type(text: str) -> str:
    if METRIC_PATTERN.search(text) and any(term in text.lower() for term in ["提升", "降低", "从", "用户", "star", "token"]):
        return "指标"
    if any(term in text for term in ["部署", "上线", "公网", "域名", "Nginx", "systemd", "VPS"]):
        return "部署"
    if any(term in text for term in ["日志", "健康检查", "Smoke Test", "CORS", "端口冲突", "数据隔离", "权限", "邀请码"]):
        return "工程实践"
    if any(term in text for term in ["解决", "修复", "冲突", "配置", "问题", "排查"]):
        return "问题排查"
    if any(term in text for term in ["负责", "主导", "独立", "参与"]):
        return "职责"
    if any(term in text for term in ["测试集", "评测", "指标", "反馈", "记录", "仓库"]):
        return "证据"
    if TECH_PATTERN.search(text):
        return "技术"
    return "功能"


def _importance(text: str, fact_type: str) -> str:
    if any(marker in text for marker in NEGATIVE_BODY_MARKERS):
        return "low"
    if fact_type in {"指标", "部署", "问题排查"} or any(term.lower() in text.lower() for term in HIGH_VALUE_TERMS):
        return "high"
    if fact_type in {"技术", "工程实践", "证据", "职责"}:
        return "medium"
    return "low"


def _resume_ready(text: str) -> str:
    if any(marker in text for marker in NEGATIVE_BODY_MARKERS):
        return ""
    value = text.strip().rstrip("。；;")
    replacements = [("工程侧完成", "完成"), ("最终通过", "通过"), ("目前进一步发现", "识别并推进解决")]
    for old, new in replacements:
        if value.startswith(old):
            value = new + value[len(old):]
    return value


def build_experience_fact_ledger_from_components(
    raw_input: str,
    *,
    identities: Sequence[ExperienceIdentity],
    semantic_analyses: Sequence[InputSemanticAnalysis],
    claim_resolutions: Sequence[ClaimResolution],
) -> ExperienceFactLedger:
    """Assemble the existing ledger from one already-compiled semantic request."""
    if not (len(identities) == len(semantic_analyses) == len(claim_resolutions)):
        raise ValueError("Semantic compilation components must have matching experience counts.")

    facts: list[ExperienceFact] = []
    constraints: list[InputSemanticUnit] = []
    uncertain_facts: list[InputSemanticUnit] = []
    excluded_units: list[InputSemanticUnit] = []
    claims: list[InputClaim] = []
    withheld_claims: list[InputClaim] = []
    excluded_claims: list[InputClaim] = []
    for identity, analysis, resolution in zip(
        identities,
        semantic_analyses,
        claim_resolutions,
        strict=True,
    ):
        constraints.extend(analysis.constraints)
        uncertain_facts.extend(analysis.uncertain_facts)
        excluded_units.extend(unit for unit in analysis.units if not unit.resume_eligible)
        claims.extend(resolution.claims)
        withheld_claims.extend(resolution.withheld_claims)
        excluded_claims.extend(resolution.excluded_claims)
        fact_index = 0
        for claim in resolution.eligible_claims:
            for text in split_atomic_facts(claim.text):
                fact_index += 1
                local = raw_input.find(text, claim.source_span[0], claim.source_span[1] + 1)
                if local < 0:
                    local = claim.source_span[0]
                fact_type = _fact_type(text)
                resume_ready = _resume_ready(text)
                if not resume_ready:
                    continue
                facts.append(ExperienceFact(
                    experience_id=identity.experience_id,
                    immutable_experience_id=identity.immutable_experience_id or identity.experience_id,
                    fact_id=f"{identity.experience_id}-F{fact_index:03d}",
                    fact_type=fact_type,
                    fact_text=text,
                    importance=_importance(text, fact_type),
                    explicit=True,
                    resume_ready_text=resume_ready,
                    source_span=(local, local + len(text)),
                    semantic_unit_id=claim.claim_id,
                    clause_role=_clause_role(text),
                    completeness=_completeness(text),
                    semantic_role=claim.semantic_role,
                    polarity=claim.polarity,
                    certainty=claim.certainty,
                    resume_eligible=claim.resume_eligible,
                    claim_id=claim.claim_id,
                    eligibility=claim.eligibility,
                    temporal_status=claim.temporal_status,
                    evidence_type=claim.evidence_type,
                ))
    grouped: dict[str, list[ExperienceFact]] = {}
    for fact in facts:
        grouped.setdefault(fact.experience_id, []).append(fact)
    for rows in grouped.values():
        for index, fact in enumerate(rows):
            related: list[str] = []
            if fact.completeness != "complete" and index + 1 < len(rows):
                related.append(rows[index + 1].fact_id)
            if fact.clause_role in {"result", "action"} and index and rows[index - 1].clause_role == "problem":
                related.append(rows[index - 1].fact_id)
            fact.related_fact_ids = related
    return ExperienceFactLedger(
        facts=facts,
        constraints=constraints,
        uncertain_facts=uncertain_facts,
        excluded_units=excluded_units,
        claims=claims,
        withheld_claims=withheld_claims,
        excluded_claims=excluded_claims,
    )


def build_experience_fact_ledger(raw_input: str) -> ExperienceFactLedger:
    """Backward-compatible ledger builder for callers outside semantic compilation."""
    identities = build_experience_identities(raw_input)
    semantic_analyses = [
        analyze_experience_semantics(identity.experience_id, identity.raw_text, identity.source_span[0])
        for identity in identities
    ]
    claim_resolutions = [
        resolve_experience_claims(identity.experience_id, identity.raw_text, identity.source_span[0])
        for identity in identities
    ]
    return build_experience_fact_ledger_from_components(
        raw_input,
        identities=identities,
        semantic_analyses=semantic_analyses,
        claim_resolutions=claim_resolutions,
    )


def build_fact_ledger_context(raw_input: str) -> str:
    ledger = build_experience_fact_ledger(raw_input)
    lines = ["内部事实账本：每条事实只能用于对应 experience_id，source_span 不提供给模型。"]
    grouped: dict[str, list[ExperienceFact]] = {}
    for fact in ledger.facts:
        grouped.setdefault(fact.experience_id, []).append(fact)
    for experience_id, facts in grouped.items():
        ranked = sorted(facts, key=lambda fact: {"high": 0, "medium": 1, "low": 2}[fact.importance])[:8]
        lines.append(experience_id + "：")
        lines.extend(
            f"- {fact.fact_id}｜claim:{fact.claim_id}｜{fact.importance}｜{fact.fact_type}｜"
            f"{fact.temporal_status}｜{fact.resume_ready_text[:140]}"
            for fact in ranked
        )
    return "\n".join(lines)


def fact_match_score(text: str, fact: ExperienceFact) -> float:
    left = normalize_fact_text(text)
    right = normalize_fact_text(fact.fact_text)
    if not left or not right:
        return 0.0
    if min(len(left), len(right)) >= 10 and (left in right or right in left):
        return 1.0
    terms = set(TECH_PATTERN.findall(text)) | set(re.findall(r"\d+(?:\.\d+)?", text))
    term_hits = sum(1 for term in terms if term and term.lower() in fact.fact_text.lower())
    char_hits = len(set(left) & set(right)) / max(1, len(set(right)))
    return min(0.95, char_hits * 0.55 + min(0.4, term_hits * 0.15))


def fact_signature_terms(fact: ExperienceFact) -> set[str]:
    terms = {term.lower() for term in TECH_PATTERN.findall(fact.fact_text) if term}
    terms.update(term.lower() for term in HIGH_VALUE_TERMS if term.lower() in fact.fact_text.lower())
    terms.update(re.findall(r"\d+(?:\.\d+)?", fact.fact_text))
    return terms


def is_generic_detail(text: str) -> bool:
    return any(marker in text for marker in GENERIC_DETAIL_MARKERS)
