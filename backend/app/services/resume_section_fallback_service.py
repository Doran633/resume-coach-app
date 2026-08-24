import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_PATH = LOG_DIR / "resume_section_fallback.jsonl"

TECH_TERMS = [
    "JavaScript",
    "TypeScript",
    "Scikit-learn",
    "LangChain",
    "LangGraph",
    "TensorFlow",
    "FastAPI",
    "Matplotlib",
    "PyTorch",
    "Python",
    "React",
    "Flask",
    "Spring",
    "SQLite",
    "MySQL",
    "Redis",
    "Docker",
    "Pandas",
    "NumPy",
    "RAG",
    "Agent",
    "Vue",
    "SQL",
    "Java",
]

PROJECT_LABELS = ["项目名称", "项目类型", "项目时间", "项目简介", "我的职责", "技术细节", "项目成果"]
PROJECT_SPLIT_PATTERN = re.compile(
    r"(^|\n)\s*(?:#{1,6}\s*)?"
    r"(?P<label>项目[一二三四五六七八九十\d]*|经历[一二三四五六七八九十\d]*|开源经历|实习经历|比赛经历|校园经历)"
    r"\s*(?:[:：|｜\-—–]\s*)",
    re.MULTILINE,
)


class FallbackStats:
    def __init__(self, generation_result_id: int | None = None, stage: str = "unknown"):
        self.generation_result_id = generation_result_id
        self.stage = stage
        self.fallback_sections: list[str] = []
        self.fallback_reasons: list[str] = []
        self.source_fields: list[str] = []

    @property
    def changed(self) -> bool:
        return bool(self.fallback_sections)

    @property
    def fallback_reason(self) -> str:
        if "structured_resume_empty" in self.fallback_reasons:
            return "structured_resume_empty"
        return self.fallback_reasons[0] if self.fallback_reasons else ""

    def fill(self, section: str, source: str):
        if section not in self.fallback_sections:
            self.fallback_sections.append(section)
        if source not in self.source_fields:
            self.source_fields.append(source)

    def add_reason(self, reason: str):
        if reason not in self.fallback_reasons:
            self.fallback_reasons.append(reason)


def _write_fallback_log(stats: FallbackStats):
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "resume_fallback_triggered": stats.changed,
            "changed": stats.changed,
            "fallback_sections": stats.fallback_sections,
            "fallback_reasons": stats.fallback_reasons,
            "fallback_reason": stats.fallback_reason,
            "source_fields": stats.source_fields,
            "generation_result_id": stats.generation_result_id,
            "stage": stats.stage,
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(log, ensure_ascii=False) + "\n")
    except Exception:
        return


def _as_payload_dict(payload: schemas.GenerationPayload | dict) -> dict:
    return deepcopy(payload.model_dump() if isinstance(payload, schemas.GenerationPayload) else payload)


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(item for item in (_text(part) for part in value) if item)
    if isinstance(value, dict):
        return "\n".join(f"{key}：{item}" for key, value in value.items() if (item := _text(value)))
    return str(value).strip()


def _has_items(value) -> bool:
    return isinstance(value, list) and any(_text(item) for item in value)


def _split_sentences(text: str, limit: int = 6) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[。！？；])\s*|\n+", normalized)
    cleaned = [part.strip(" -•\t") for part in parts if part.strip(" -•\t")]
    if len(cleaned) < min(4, limit):
        clause_parts = re.split(r"[，,]\s*", normalized)
        for part in clause_parts:
            item = part.strip(" -•\t")
            if len(item) >= 8 and item not in cleaned:
                cleaned.append(item)
            if len(cleaned) >= limit:
                break
    return cleaned[:limit]


def _source_text(data: dict) -> tuple[str, str]:
    for field in ["recommended_version", "bold_version", "normal_version"]:
        text = _text(data.get(field))
        if text:
            return text, field
    return "", ""


def _extract_between(text: str, start_label: str, end_labels: list[str]) -> str:
    start = re.search(rf"{re.escape(start_label)}\s*[:：]", text)
    if not start:
        return ""
    start_index = start.end()
    end_index = len(text)
    for label in end_labels:
        match = re.search(rf"{re.escape(label)}\s*[:：]", text[start_index:])
        if match:
            end_index = min(end_index, start_index + match.start())
    return text[start_index:end_index].strip()


def _extract_section(text: str, label: str, following_labels: list[str]) -> str:
    return _extract_between(text, label, [item for item in following_labels if item != label])


def _build_summary(data: dict, source: str, source_field: str, stats: FallbackStats) -> list[str]:
    summary_text = _extract_section(source, "个人优势", ["项目经历", "项目名称", "技能栈", "教育经历", "校园活动", "面试准备"])
    if summary_text:
        stats.fill("summary", source_field)
        return _split_sentences(summary_text, limit=4)

    facts = [item for item in (_text(item) for item in data.get("confirmed_facts", [])) if item]
    if facts:
        stats.fill("summary", "confirmed_facts")
        return facts[:4]
    return []


def _extract_skills(data: dict, source: str, source_field: str, stats: FallbackStats) -> list[str]:
    haystack = "\n".join([source, _text(data.get("knowledge_checklist"))])
    found = []
    for term in TECH_TERMS:
        if re.search(rf"(?<![A-Za-z0-9.+#-]){re.escape(term)}(?![A-Za-z0-9.+#-])", haystack, re.IGNORECASE):
            found.append(term)
    if found:
        stats.fill("skills", f"{source_field}/knowledge_checklist")
        return found[:12]

    checklist = [item for item in (_text(item) for item in data.get("knowledge_checklist", [])) if item]
    if checklist:
        stats.fill("skills", "knowledge_checklist")
        return checklist[:8]
    return []


def _field_from_project_block(block: str, label: str) -> str:
    following = [item for item in PROJECT_LABELS if item != label]
    return _extract_between(block, label, following)


def _details_from_text(*values: str, limit: int = 6) -> list[str]:
    details: list[str] = []
    for value in values:
        for sentence in _split_sentences(value, limit=limit):
            if sentence and sentence not in details:
                details.append(sentence)
            if len(details) >= limit:
                return details
    return details


def _infer_meta(label: str, block: str) -> str:
    text = f"{label}\n{block}"
    if "实习" in text:
        return "实习经历"
    if "开源" in text:
        return "开源经历"
    if "比赛" in text or "竞赛" in text:
        return "比赛经历"
    if "校园" in text or "社团" in text:
        return "校园经历"
    return "项目经历"


def _infer_name(label: str, block: str) -> str:
    explicit_name = _field_from_project_block(block, "项目名称")
    if explicit_name:
        return explicit_name

    first_line = block.strip().splitlines()[0].strip(" -•\t") if block.strip() else ""
    if first_line:
        first_line = re.split(r"[。；;]", first_line)[0].strip()
        first_line = re.sub(r"^(项目名称|项目简介|我的职责|技术细节|项目成果)\s*[:：]\s*", "", first_line)
        if 2 <= len(first_line) <= 36:
            return first_line

    if label in {"开源经历", "实习经历", "比赛经历", "校园经历"}:
        return label
    return "项目经历"


def _project_from_block(block: str, source_field: str, stats: FallbackStats, label: str = "项目经历") -> dict | None:
    block = block.strip()
    if not block:
        return None

    name = _infer_name(label, block)
    meta = _field_from_project_block(block, "项目类型") or _infer_meta(label, block)
    time = _field_from_project_block(block, "项目时间") or "[待填写]"
    intro = _field_from_project_block(block, "项目简介")
    role = _field_from_project_block(block, "我的职责")
    tech_details = _field_from_project_block(block, "技术细节")
    achievements = _field_from_project_block(block, "项目成果")
    details = _details_from_text(tech_details, achievements, role, intro, block, limit=8)

    if not (intro or role or details):
        return None

    stats.fill("projects", source_field)
    return {
        "name": name,
        "meta": meta,
        "time": time,
        "intro": intro or _split_sentences(block, limit=1)[0],
        "role": role or "围绕项目目标参与核心功能设计、实现与结果交付。",
        "details": details,
    }


def _split_project_blocks(source: str) -> list[tuple[str, str]]:
    matches = list(PROJECT_SPLIT_PATTERN.finditer(source))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        label = match.group("label")
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        block = source[start:end].strip()
        if block:
            blocks.append((label, block))
    return blocks


def _parse_projects(source: str, source_field: str, stats: FallbackStats) -> list[dict]:
    if not source:
        return []

    matches = list(re.finditer(r"项目名称\s*[:：]", source))
    projects = []
    for index, match in enumerate(matches[:5]):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        block = source[start:end].strip()
        project = _project_from_block(block, source_field, stats)
        if project:
            projects.append(project)

    if projects:
        return projects

    split_projects = []
    for label, block in _split_project_blocks(source)[:5]:
        project = _project_from_block(block, source_field, stats, label=label)
        if project:
            split_projects.append(project)
    if split_projects:
        return split_projects

    details = _details_from_text(source, limit=8)
    if details:
        stats.fill("projects", source_field)
        return [
            {
                "name": "综合经历项目",
                "meta": "综合经历",
                "time": "[待填写]",
                "intro": details[0],
                "role": "根据现有经历整理个人参与内容与项目亮点。",
                "details": details,
            }
        ]
    return []


def _build_interview_preparation(data: dict, stats: FallbackStats) -> list[str]:
    interview_plan = [item for item in (_text(item) for item in data.get("interview_plan", [])) if item]
    if interview_plan:
        stats.fill("interview_preparation", "interview_plan")
        return interview_plan[:8]

    items: list[str] = []
    for claim in data.get("claims", []):
        if not isinstance(claim, dict):
            continue
        for question in claim.get("interview_questions", []):
            text = _text(question)
            if text and text not in items:
                items.append(text)

    for item in data.get("knowledge_checklist", []):
        text = _text(item)
        if text and text not in items:
            items.append(text)

    if items:
        stats.fill("interview_preparation", "claims/knowledge_checklist")
    return items[:8]


def fill_resume_sections(
    payload: schemas.GenerationPayload | dict,
    generation_result_id: int | None = None,
    stage: str = "unknown",
    write_log: bool = True,
) -> schemas.GenerationPayload:
    stats = FallbackStats(generation_result_id=generation_result_id, stage=stage)
    data = _as_payload_dict(payload)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}

    source, source_field = _source_text(data)

    sections["personal_info"] = sections.get("personal_info") if isinstance(sections.get("personal_info"), dict) else {}
    sections["education"] = sections.get("education") if isinstance(sections.get("education"), dict) else {}

    empty_sections = [
        section
        for section in ["summary", "skills", "projects", "interview_preparation"]
        if not _has_items(sections.get(section))
    ]
    if set(empty_sections) == {"summary", "skills", "projects", "interview_preparation"}:
        stats.add_reason("structured_resume_empty")
    for section in empty_sections:
        stats.add_reason(f"{section}_empty")

    if "summary" in empty_sections:
        sections["summary"] = _build_summary(data, source, source_field, stats)

    if "skills" in empty_sections:
        sections["skills"] = _extract_skills(data, source, source_field, stats)

    if "projects" in empty_sections:
        sections["projects"] = _parse_projects(source, source_field, stats)

    if "interview_preparation" in empty_sections:
        sections["interview_preparation"] = _build_interview_preparation(data, stats)

    data["resume_sections"] = sections
    filled = schemas.GenerationPayload.model_validate(data)
    if write_log:
        _write_fallback_log(stats)
    return filled
