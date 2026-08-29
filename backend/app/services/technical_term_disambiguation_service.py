import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .experience_fact_ledger_service import build_experience_fact_ledger


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "technical_term_disambiguation.jsonl"


@dataclass(frozen=True)
class ResolvedTechnicalTerm:
    term: str
    meaning: str
    category: str | None
    confidence: float
    experience_id: str
    fact_id: str


def _resolve_token(text: str) -> tuple[str, str | None, float]:
    lowered = text.lower()
    auth = re.search(
        r"jwt|bearer|access\s*token|refresh\s*token|鉴权|认证|登录态|权限|令牌|"
        r"token\s*(?:校验|验证|认证)|(?:ssl|https)[^。；\n]{0,20}token|token[^。；\n]{0,20}(?:加密|鉴权)",
        lowered,
        re.I,
    )
    prompt_context = re.search(r"prompt|上下文|context|输入\s*token|输出\s*token", lowered, re.I)
    cost = re.search(
        r"token[^。；\n]{0,24}(?:消耗|成本|用量|预算|降低|减少|压缩|节省)|"
        r"(?:消耗|成本|用量|预算|降低|减少|压缩|节省)[^。；\n]{0,24}token|"
        r"\d+(?:\.\d+)?[^。；\n]{0,12}token|token[^。；\n]{0,12}\d+(?:\.\d+)?",
        lowered,
        re.I,
    )
    if auth:
        return "authentication_token", "安全机制", 0.98
    if prompt_context and cost:
        return "prompt_token_cost", "Prompt 工程与上下文管理", 0.97
    if cost:
        return "llm_token_cost", "大模型工程与成本优化", 0.97
    if prompt_context:
        return "context_token", "Prompt 工程与上下文管理", 0.88
    return "ambiguous_token", None, 0.20


def _resolve_model(text: str) -> tuple[str, str | None, float]:
    if re.search(r"sft|rlhf|dpo|lora|微调|训练模型|模型训练", text, re.I):
        return "model_training", "AI / 大模型应用", 0.96
    if re.search(r"回归|分类|聚类|预测|scikit|pandas|数据分析|拟合", text, re.I):
        return "statistical_model", "数据分析与建模", 0.92
    if re.search(r"大模型|llm|rag|agent|embedding|语言模型|生成模型", text, re.I):
        return "ai_model", "AI / 大模型应用", 0.90
    return "ambiguous_model", None, 0.30


def _resolve_training(text: str) -> tuple[str, str | None, float]:
    if re.search(r"sft|rlhf|dpo|lora|微调|训练模型|模型训练|训练数据", text, re.I):
        return "model_training", "AI / 大模型应用", 0.96
    if re.search(r"课程|培训|练习|体能|活动训练", text, re.I):
        return "non_technical_training", None, 0.90
    return "ambiguous_training", None, 0.30


def _resolve_deployment(text: str) -> tuple[str, str | None, float]:
    if re.search(r"公网|上线|域名|nginx|systemd|vps|服务器|云主机|容器|docker", text, re.I):
        return "service_deployment", "工程化与部署", 0.95
    if re.search(r"本地|课堂|演示|虚拟机", text, re.I):
        return "local_runtime", "开发工具与环境", 0.82
    return "generic_deployment", "工程化与部署", 0.68


def _resolve_user(text: str) -> tuple[str, str | None, float]:
    if re.search(r"\d+\s*(?:名|个|位)?用户|真实用户|访问记录|用户反馈|日活|月活", text, re.I):
        return "user_evidence", None, 0.93
    if re.search(r"目标用户|面向用户|用户需求|用户场景", text, re.I):
        return "product_audience", None, 0.88
    return "ambiguous_user", None, 0.35


def _resolve_test(text: str) -> tuple[str, str | None, float]:
    if re.search(r"rag|检索|groundedness|citation|recall|top-?k|评测|测试集", text, re.I):
        return "ai_evaluation", "测试与评测", 0.94
    if re.search(r"pytest|smoke\s*test|接口测试|功能测试|自动化测试|单元测试|集成测试", text, re.I):
        return "software_testing", "测试与评测", 0.94
    return "ambiguous_test", None, 0.35


RESOLVERS = {
    "Token": (re.compile(r"(?<![A-Za-z0-9])token(?![A-Za-z0-9])", re.I), _resolve_token),
    "模型": (re.compile(r"模型|(?<![A-Za-z])model(?![A-Za-z])", re.I), _resolve_model),
    "训练": (re.compile(r"训练|微调|(?<![A-Za-z])train(?:ing)?(?![A-Za-z])", re.I), _resolve_training),
    "部署": (re.compile(r"部署|(?<![A-Za-z])deploy(?:ment|ed)?(?![A-Za-z])", re.I), _resolve_deployment),
    "用户": (re.compile(r"用户|(?<![A-Za-z])users?(?![A-Za-z])", re.I), _resolve_user),
    "测试": (re.compile(r"测试|评测|(?<![A-Za-z])tests?(?:ing)?(?![A-Za-z])", re.I), _resolve_test),
}


def resolve_technical_terms(raw_input: str) -> list[ResolvedTechnicalTerm]:
    resolutions: list[ResolvedTechnicalTerm] = []
    for fact in build_experience_fact_ledger(raw_input).facts:
        for term, (pattern, resolver) in RESOLVERS.items():
            if not pattern.search(fact.fact_text):
                continue
            meaning, category, confidence = resolver(fact.fact_text)
            resolutions.append(ResolvedTechnicalTerm(
                term=term,
                meaning=meaning,
                category=category,
                confidence=confidence,
                experience_id=fact.experience_id,
                fact_id=fact.fact_id,
            ))
    return resolutions


def best_resolution(
    resolutions: list[ResolvedTechnicalTerm], term: str,
) -> ResolvedTechnicalTerm | None:
    candidates = [item for item in resolutions if item.term.lower() == term.lower()]
    return max(candidates, key=lambda item: item.confidence, default=None)


def write_disambiguation_log(
    resolutions: list[ResolvedTechnicalTerm], *, stage: str,
    generation_result_id: int | None = None,
) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "stage": stage,
            "generation_result_id": generation_result_id,
            "term_count": len(resolutions),
            "ambiguous_term_count": sum(item.category is None for item in resolutions),
            "terms": [asdict(item) for item in resolutions],
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
