import json
import re
from collections import OrderedDict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "resume_skill_taxonomy.jsonl"
CATEGORIES = OrderedDict([
    ("编程语言", ["Python", "Java", "JavaScript", "TypeScript", "SQL", "C++", "Go"]),
    ("AI / 大模型应用", ["RAG", "Agent", "Embedding", "向量检索", "rerank", "LangChain", "LangGraph", "Prompt", "LLM"]),
    ("前端开发", ["React", "Vue", "Vite", "Ant Design", "Zustand", "dayjs"]),
    ("后端开发", ["FastAPI", "Flask", "Django", "Spring", "Spring Boot", "Pydantic", "SQLAlchemy", "python-multipart"]),
    ("数据库与存储", ["SQLite", "MySQL", "PostgreSQL", "Redis", "FAISS", "Chroma", "Pinecone", "向量数据库", "向量索引"]),
    ("测试与评测", ["pytest", "Smoke Test", "JMeter", "Groundedness", "Citation", "Retrieval", "Debug Trace"]),
    ("工程化与部署", ["Git", "Docker", "Nginx", "systemd", "Linux", "VPS", "CI", "CORS"]),
    ("数据分析与机器学习", ["Pandas", "NumPy", "Scikit-learn", "Matplotlib", "PyTorch", "TensorFlow"]),
    ("其他工具", []),
])
LEVEL_PREFIX = re.compile(r"^(?:掌握|精通|熟悉|了解|具备)\s*")


@dataclass
class SkillTaxonomyStats:
    stage: str
    generation_result_id: int | None
    skills_before_count: int = 0
    skills_after_count: int = 0
    duplicate_skills_removed: int = 0
    category_corrections: int = 0
    unsupported_skills_removed: int = 0


def _category(term: str) -> str:
    for category, terms in CATEGORIES.items():
        if any(term.lower() == item.lower() for item in terms):
            return category
    return "其他工具"


def _terms(text: str) -> list[str]:
    candidates = [item for values in CATEGORIES.values() for item in values]
    candidates.sort(key=len, reverse=True)
    found: list[str] = []
    for term in candidates:
        if re.search(rf"(?<![A-Za-z0-9.+#-]){re.escape(term)}(?![A-Za-z0-9.+#-])", text, re.I):
            found.append(term)
    return found


def _write_log(stats: SkillTaxonomyStats) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **asdict(stats)}
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def calibrate_resume_skill_taxonomy(
    payload: schemas.GenerationPayload,
    target_role: str = "",
    *,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    """Categorize only skills already admitted by the evidence guard."""
    updated = payload.model_copy(deep=True)
    stats = SkillTaxonomyStats(stage=stage, generation_result_id=generation_result_id)
    stats.skills_before_count = len(updated.resume_sections.skills)
    grouped: dict[str, list[str]] = {name: [] for name in CATEGORIES}
    seen: set[str] = set()
    for raw_line in updated.resume_sections.skills:
        line = LEVEL_PREFIX.sub("", str(raw_line or "").strip())
        old_label = re.match(r"^([^：:]{1,18})[：:]", line)
        for term in _terms(line):
            key = term.lower()
            if key in seen:
                stats.duplicate_skills_removed += 1
                continue
            seen.add(key)
            category = _category(term)
            if old_label and old_label.group(1).strip() != category:
                stats.category_corrections += 1
            grouped[category].append(term)
    for category, values in grouped.items():
        order = {term.lower(): index for index, term in enumerate(CATEGORIES[category])}
        values.sort(key=lambda item: order.get(item.lower(), len(order)))
    updated.resume_sections.skills = [f"{name}：{'、'.join(values)}" for name, values in grouped.items() if values]
    stats.skills_after_count = len(updated.resume_sections.skills)
    if write_log:
        _write_log(stats)
    return updated
