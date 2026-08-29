import json
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .resume_skill_evidence_guard_service import _skill_terms
from .technical_term_disambiguation_service import best_resolution, resolve_technical_terms


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_skill_presentation.jsonl"

CATEGORY_TERMS = OrderedDict([
    ("编程语言", ["Python", "Java", "JavaScript", "TypeScript", "C++", "Go"]),
    ("前端技术", ["React", "Vue", "Vite", "Ant Design", "Zustand", "dayjs"]),
    ("后端技术", ["FastAPI", "Flask", "Spring", "Spring Boot", "Pydantic", "SQLAlchemy", "python-multipart"]),
    ("数据库与存储", ["SQLite", "MySQL", "PostgreSQL", "Redis", "FAISS", "Chroma", "Pinecone", "向量数据库", "向量索引"]),
    ("AI / 大模型应用", ["RAG", "Agent", "Embedding", "向量检索", "rerank", "LangChain", "LangGraph", "Prompt", "LLM"]),
    ("数据分析与机器学习", ["Pandas", "NumPy", "Matplotlib", "Scikit-learn", "PyTorch", "TensorFlow"]),
    ("数据分析与建模", ["回归分析", "线性回归", "多项式回归", "模型效果对比"]),
    ("数据可视化", ["数据可视化"]),
    ("物联网与通信", ["LoRa", "地磁传感器"]),
    ("地图与路线服务", ["地图 API", "路线规划"]),
    ("安全机制", ["SSL"]),
    ("大模型工程与成本优化", ["Token"]),
    ("Prompt 工程与上下文管理", []),
    ("开发工具与环境", ["CodeBuddy", "虚拟机"]),
    ("工程化与部署", ["Git", "Linux", "Docker", "Nginx", "systemd", "VPS", "CI", "CORS"]),
    ("测试与质量保障", ["pytest", "Smoke Test", "JMeter", "Groundedness", "Citation", "Retrieval", "Debug Trace"]),
])

CATEGORY_ALIASES = {
    "语言": "编程语言", "开发语言": "编程语言", "前端": "前端技术", "前端框架": "前端技术",
    "后端": "后端技术", "后端框架": "后端技术", "数据库": "数据库与存储", "存储": "数据库与存储",
    "ai技术": "AI / 大模型应用", "ai应用技术": "AI / 大模型应用", "大模型": "AI / 大模型应用",
    "大模型应用": "AI / 大模型应用", "工具": "工程化与部署", "工程化": "工程化与部署",
    "部署": "工程化与部署", "测试": "测试与质量保障", "质量保障": "测试与质量保障",
}

ROLE_ORDERS = {
    "ai": ["编程语言", "AI / 大模型应用", "后端技术", "数据库与存储", "前端技术", "工程化与部署", "测试与质量保障", "数据分析与机器学习", "其他技术"],
    "frontend": ["编程语言", "前端技术", "工程化与部署", "后端技术", "数据库与存储", "AI / 大模型应用", "测试与质量保障", "数据分析与机器学习", "其他技术"],
    "backend": ["编程语言", "后端技术", "数据库与存储", "工程化与部署", "测试与质量保障", "前端技术", "AI / 大模型应用", "数据分析与机器学习", "其他技术"],
}
DEFAULT_ORDER = [*CATEGORY_TERMS.keys(), "其他技术"]


@dataclass
class SkillPresentationStats:
    stage: str
    generation_result_id: int | None
    skill_lines_before: int = 0
    skill_lines_after: int = 0
    verified_skill_count: int = 0
    categorized_skill_count: int = 0
    uncategorized_skill_count: int = 0
    duplicate_removed_count: int = 0
    unsupported_skill_removed_count: int = 0
    category_distribution: dict[str, int] = field(default_factory=dict)


def _normalized_category(label: str) -> str | None:
    compact = re.sub(r"[\s：:]", "", label).lower()
    for category in DEFAULT_ORDER:
        if compact == re.sub(r"[\s/：:]", "", category).lower():
            return category
    return CATEGORY_ALIASES.get(compact)


def _category_for(term: str, preferred: str | None = None) -> str:
    if preferred:
        return preferred
    lowered = term.lower()
    for category, terms in CATEGORY_TERMS.items():
        if any(lowered == candidate.lower() for candidate in terms):
            return category
    return "其他技术"


def _role_order(target_role: str) -> list[str]:
    lowered = str(target_role or "").lower()
    if any(token in lowered for token in ["ai", "agent", "大模型"]):
        return ROLE_ORDERS["ai"]
    if "前端" in lowered:
        return ROLE_ORDERS["frontend"]
    if "后端" in lowered:
        return ROLE_ORDERS["backend"]
    return DEFAULT_ORDER


def _write_log(stats: SkillPresentationStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def organize_resume_skills(
    payload: schemas.GenerationPayload,
    target_role: str = "",
    raw_input: str = "",
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    """Group already-verified skill terms without inventing new technologies."""
    updated = payload.model_copy(deep=True)
    stats = SkillPresentationStats(stage=stage, generation_result_id=generation_result_id)
    stats.skill_lines_before = len(updated.resume_sections.skills)
    grouped: dict[str, list[str]] = {category: [] for category in DEFAULT_ORDER}
    seen: set[str] = set()
    resolutions = resolve_technical_terms(raw_input) if raw_input else []

    for raw_line in updated.resume_sections.skills:
        line = str(raw_line or "").strip()
        if not line:
            continue
        label_match = re.match(r"^([^：:]{1,18})[：:]", line)
        preferred = _normalized_category(label_match.group(1)) if label_match else None
        terms = _skill_terms(line)
        for term in terms:
            key = term.lower()
            if key in seen:
                stats.duplicate_removed_count += 1
                continue
            seen.add(key)
            category = _category_for(term, preferred)
            if term.lower() == "token" and raw_input:
                resolution = best_resolution(resolutions, "Token")
                if not resolution or not resolution.category or resolution.confidence < 0.65:
                    stats.unsupported_skill_removed_count += 1
                    continue
                category = resolution.category
            grouped[category].append(term)
            stats.categorized_skill_count += category != "其他技术"
            stats.uncategorized_skill_count += category == "其他技术"

    lines = [f"{category}：{'、'.join(grouped[category])}" for category in _role_order(target_role) if grouped[category]]
    updated.resume_sections.skills = lines
    stats.skill_lines_after = len(lines)
    stats.verified_skill_count = len(seen)
    stats.category_distribution = {category: len(terms) for category, terms in grouped.items() if terms}
    if write_log:
        _write_log(stats)
    return updated


def evaluate_skill_presentation(payload: schemas.GenerationPayload) -> tuple[int, list[str]]:
    skills = [str(item or "").strip() for item in payload.resume_sections.skills if str(item or "").strip()]
    warnings: list[str] = []
    if len(skills) >= 3 and sum("：" not in line and ":" not in line for line in skills) / len(skills) >= 0.6:
        warnings.append("FLAT_SKILL_LIST")
    if any(("：" not in line and ":" not in line) for line in skills):
        warnings.append("SKILL_CATEGORY_LOSS")
    terms = [term.lower() for line in skills for term in _skill_terms(line)]
    if len(terms) != len(set(terms)):
        warnings.append("DUPLICATE_SKILL")
    score = max(0, 100 - len(set(warnings)) * 25)
    return score, list(dict.fromkeys(warnings))
