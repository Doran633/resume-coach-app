import re
from dataclasses import dataclass, field

from .experience_identity_service import build_experience_identities


HIGH_VALUE_TERMS = [
    "部署", "上线", "公网", "域名", "数据隔离", "权限", "邀请码", "日志", "健康检查",
    "Smoke Test", "测试集", "评测", "指标", "Groundedness", "Citation", "Retrieval",
    "Fallback", "Experience Dilution", "CORS", "端口冲突", "问题", "优化", "提升", "降低",
]
TECH_PATTERN = re.compile(
    r"React|TypeScript|JavaScript|Python|FastAPI|SQLite|Nginx|systemd|VPS|RAG|Agent|Embedding|"
    r"BAAI/?bge-m3|Top-K|Citation|Retrieval|Groundedness|Smoke Test|CORS|JSON Schema|DOCX|token",
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


@dataclass
class ExperienceFactLedger:
    facts: list[ExperienceFact] = field(default_factory=list)

    def for_experience(self, experience_id: str) -> list[ExperienceFact]:
        return [fact for fact in self.facts if fact.experience_id == experience_id]


def normalize_fact_text(text: str) -> str:
    return re.sub(r"[\s，,。；;：:、/\\|｜（）()\[\]【】《》“”\"'`~\-—–_]+", "", text or "").lower()


def split_atomic_facts(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；;])\s*|\n+|(?<=，)(?=(?:并|同时|最终|工程侧|目前|根据|通过|实现|完成|解决))", text or "")
    return [part.strip(" \t\r\n，、；;。") for part in parts if len(normalize_fact_text(part)) >= 8]


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


def build_experience_fact_ledger(raw_input: str) -> ExperienceFactLedger:
    facts: list[ExperienceFact] = []
    for identity in build_experience_identities(raw_input):
        offset = raw_input.find(identity.raw_text)
        cursor = max(0, offset)
        for index, text in enumerate(split_atomic_facts(identity.raw_text), start=1):
            local = raw_input.find(text, cursor)
            if local < 0:
                local = cursor
            fact_type = _fact_type(text)
            facts.append(ExperienceFact(
                experience_id=identity.experience_id,
                fact_id=f"{identity.experience_id}-F{index:03d}",
                fact_type=fact_type,
                fact_text=text,
                importance=_importance(text, fact_type),
                explicit=True,
                resume_ready_text=_resume_ready(text),
                source_span=(local, local + len(text)),
            ))
            cursor = local + len(text)
    return ExperienceFactLedger(facts=facts)


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
            f"- {fact.fact_id}｜{fact.importance}｜{fact.fact_type}｜{fact.resume_ready_text[:140]}"
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
