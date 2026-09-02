import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import schemas
from .experience_identity_service import ExperienceIdentity, build_experience_identities
from .experience_fact_ledger_service import build_experience_fact_ledger
from .resume_role_resolution_service import is_internal_or_generic_role, resolve_role_for_experience
from .resume_experience_entity_dedup_service import deduplicate_resume_experience_entities
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .canonical_semantic_state_service import CanonicalSemanticBuild
from .resume_experience_validity_service import ensure_resume_experience_validity, is_valid_fallback_candidate


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
    r"(?P<label>项目[一二三四五六七八九十\d]*|项目经历|经历[一二三四五六七八九十\d]*|实习经历|科研经历|研究经历|论文经历|竞赛经历|比赛经历|开源经历|校园经历|社团经历|志愿经历)"
    r"\s*(?:[:：|｜\-—–]\s*)",
    re.MULTILINE,
)

EXPERIENCE_META_BY_KEYWORD = [
    ("实习", "实习经历"),
    ("科研", "科研经历"),
    ("研究", "科研经历"),
    ("论文", "科研经历"),
    ("竞赛", "竞赛经历"),
    ("比赛", "竞赛经历"),
    ("开源", "开源经历"),
    ("校园", "校园 / 社团经历"),
    ("社团", "校园 / 社团经历"),
    ("志愿", "校园 / 社团经历"),
]

NEGATIVE_INTERNSHIP_PATTERNS = ["没有实习", "无实习", "没实习", "没有实习经历", "没有实习经验"]
POSITIVE_INTERNSHIP_PATTERNS = ["实习经历：", "实习经历:", "实习｜", "实习|", "前端开发实习", "后端开发实习", "测试开发实习", "产品实习", "运营实习", "在公司", "某公司", "公司实习", "企业实习"]
RESUME_BODY_NOISE_PATTERNS = [
    "我是大二学生",
    "我是大三学生",
    "我是大一学生",
    "想投",
    "没有实习",
    "无实习",
    "没实习",
    "没有上线",
    "未上线",
    "没有真实用户",
    "没有用户",
    "没有获奖",
    "未获奖",
]


class FallbackStats:
    def __init__(self, generation_result_id: int | None = None, stage: str = "unknown"):
        self.generation_result_id = generation_result_id
        self.stage = stage
        self.fallback_sections: list[str] = []
        self.fallback_reasons: list[str] = []
        self.source_fields: list[str] = []
        self.used_experience_id = False
        self.attempted_sections: list[str] = []
        self.projects_before = 0
        self.projects_after = 0
        self.projects_added = 0
        self.projects_removed = 0
        self.uncovered_experience_ids: list[str] = []
        self.role_fallback_triggered = 0
        self.role_recovered_from_fact_count = 0
        self.role_left_empty_count = 0
        self.internal_fallback_text_removed_count = 0
        self.role_source_experience_ids: list[str] = []
        self.role_source_fact_ids: list[str] = []
        self.fallback_candidate_rejected_count = 0
        self.fallback_bindings: list[dict] = []

    @property
    def changed(self) -> bool:
        return bool(
            self.fallback_sections
            or self.role_fallback_triggered
            or self.internal_fallback_text_removed_count
            or self.fallback_candidate_rejected_count
        )

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
            "attempted_sections": stats.attempted_sections,
            "actually_filled_sections": stats.fallback_sections,
            "fallback_reasons": stats.fallback_reasons,
            "fallback_reason": stats.fallback_reason,
            "source_fields": stats.source_fields,
            "used_experience_id": stats.used_experience_id,
            "projects_before": stats.projects_before,
            "projects_after": stats.projects_after,
            "projects_added": stats.projects_added,
            "projects_removed": stats.projects_removed,
            "uncovered_experience_ids": stats.uncovered_experience_ids,
            "role_fallback_triggered": stats.role_fallback_triggered,
            "role_recovered_from_fact_count": stats.role_recovered_from_fact_count,
            "role_left_empty_count": stats.role_left_empty_count,
            "internal_fallback_text_removed_count": stats.internal_fallback_text_removed_count,
            "role_source_experience_ids": sorted(set(stats.role_source_experience_ids)),
            "role_source_fact_ids": sorted(set(stats.role_source_fact_ids)),
            "fallback_candidate_rejected_count": stats.fallback_candidate_rejected_count,
            "fallback_bindings": stats.fallback_bindings,
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
    # Preparation items are not evidence that the user has used a technology.
    haystack = source
    found = []
    for term in TECH_TERMS:
        if re.search(rf"(?<![A-Za-z0-9.+#-]){re.escape(term)}(?![A-Za-z0-9.+#-])", haystack, re.IGNORECASE):
            found.append(term)
    if found:
        stats.fill("skills", source_field)
        return found[:12]
    return []


def _field_from_project_block(block: str, label: str) -> str:
    following = [item for item in PROJECT_LABELS if item != label]
    return _extract_between(block, label, following)


def _details_from_text(*values: str, limit: int = 6) -> list[str]:
    details: list[str] = []
    for value in values:
        for sentence in _split_sentences(value, limit=limit):
            if any(pattern in sentence for pattern in RESUME_BODY_NOISE_PATTERNS):
                continue
            if sentence and sentence not in details:
                details.append(sentence)
            if len(details) >= limit:
                return details
    return details


def _infer_meta(label: str, block: str) -> str:
    text = f"{label}\n{block}"
    no_internship = any(pattern in text for pattern in NEGATIVE_INTERNSHIP_PATTERNS)
    has_positive_internship = any(pattern in text for pattern in POSITIVE_INTERNSHIP_PATTERNS)
    if "实习" in text and not no_internship and has_positive_internship:
        return "实习经历"
    for keyword, meta in EXPERIENCE_META_BY_KEYWORD:
        if keyword == "实习":
            continue
        if keyword in text:
            return meta
    return "项目经历"


def _infer_name(label: str, block: str) -> str:
    explicit_name = _field_from_project_block(block, "项目名称")
    if explicit_name:
        return explicit_name

    first_line = block.strip().splitlines()[0].strip(" -•\t") if block.strip() else ""
    if first_line:
        first_line = re.split(r"[。；;]", first_line)[0].strip()
        first_line = re.sub(r"^(项目名称|项目简介|我的职责|技术细节|项目成果)\s*[:：]\s*", "", first_line)
        if 2 <= len(first_line) <= 36 and not re.search(r"我是|想投|没有实习|无实习|没实习", first_line):
            return first_line

    if label in {"开源经历", "实习经历", "科研经历", "研究经历", "论文经历", "竞赛经历", "比赛经历", "校园经历", "社团经历", "志愿经历"}:
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

    implicit_meta = _infer_meta("综合经历", source)
    if implicit_meta != "项目经历":
        project = _project_from_block(source, source_field, stats, label=implicit_meta)
        if project:
            project["meta"] = implicit_meta
            return [project]

    details = _details_from_text(source, limit=8)
    if details:
        stats.fill("projects", source_field)
        return [
            {
                "name": "综合经历项目",
                "meta": "综合经历",
                "time": "[待填写]",
                "intro": details[0],
                "role": "",
                "details": details,
            }
        ]
    return []


def _project_signature(project: dict) -> str:
    return f"{_text(project.get('name'))}|{_text(project.get('meta'))}"


def _normalize_match_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _project_text(project: dict) -> str:
    return "\n".join(_text(project.get(key)) for key in ["name", "meta", "intro", "role", "details"])


def _score_project_identity(project: dict, identity: ExperienceIdentity) -> int:
    project_text = _normalize_match_text(_project_text(project))
    raw_text = _normalize_match_text(identity.raw_text)
    score = 0
    title = _normalize_match_text(identity.title)
    if title and title in project_text:
        score += 16
    if identity.experience_type and identity.experience_type in _project_text(project):
        score += 5
    for term in identity.explicit_tech_terms:
        if re.search(re.escape(term), _project_text(project), re.IGNORECASE):
            score += 3
    for term in identity.evidence_terms + identity.risk_terms:
        if term and term in _project_text(project):
            score += 3
    if raw_text and project_text and (project_text[:18] in raw_text or raw_text[:18] in project_text):
        score += 4
    return score


def _assign_source_experience_ids(projects: list, raw_input: str, stats: FallbackStats) -> list:
    if not isinstance(projects, list) or not raw_input:
        return projects
    identities = build_experience_identities(raw_input)
    if not identities:
        return projects

    assigned: list[dict] = []
    used_ids: set[str] = set()
    for index, project in enumerate(projects):
        if not isinstance(project, dict):
            assigned.append(project)
            continue
        source_id = _text(project.get("source_experience_id"))
        valid_ids = {item.experience_id for item in identities}
        if source_id in valid_ids and project.get("source_binding_locked"):
            assigned.append(project)
            used_ids.add(source_id)
            stats.used_experience_id = True
            continue
        if len(identities) == 1 and source_id == identities[0].experience_id:
            # Historical payloads predate binding metadata. A matching ID is
            # unambiguous only in the singleton case; multi-experience payloads
            # still require strong local evidence below.
            project["source_binding_origin"] = "singleton_existing_id_candidate"
            project["source_binding_confidence"] = 1.0
            project["source_binding_locked"] = False
            assigned.append(project)
            used_ids.add(source_id)
            stats.used_experience_id = True
            continue

        ranked = sorted(identities, key=lambda item: _score_project_identity(project, item), reverse=True)
        chosen = ranked[0] if ranked else None
        best_score = _score_project_identity(project, chosen) if chosen else 0
        second_score = _score_project_identity(project, ranked[1]) if len(ranked) > 1 else -1
        # Fallback may only bind on strong local identity evidence. Shared
        # frameworks and a merely unique low score are not sufficient.
        if chosen and best_score >= 14 and best_score - second_score >= 6 and chosen.experience_id not in used_ids:
            project["source_experience_id"] = chosen.experience_id
            project["source_binding_origin"] = "fallback_strong_local_match_candidate"
            project["source_binding_confidence"] = min(1.0, best_score / 20)
            project["source_binding_locked"] = False
            used_ids.add(chosen.experience_id)
            stats.used_experience_id = True
            stats.fallback_bindings.append({
                "fallback_source_experience_id": chosen.experience_id,
                "fallback_target_experience_id": chosen.experience_id,
                "slot_binding_confidence": project["source_binding_confidence"],
                "restored_fact_ids": [],
                "rejected": False,
            })
        else:
            project.pop("source_experience_id", None)
            project.pop("immutable_source_experience_id", None)
            project["source_binding_origin"] = "fallback_rejected"
            project["source_binding_confidence"] = 0.0
            project["source_binding_locked"] = False
            stats.fallback_candidate_rejected_count += 1
            stats.fallback_bindings.append({
                "fallback_source_experience_id": "",
                "fallback_target_experience_id": "",
                "slot_binding_confidence": 0.0,
                "restored_fact_ids": [],
                "rejected": True,
                "reason": "low_confidence_or_ambiguous",
            })
        assigned.append(project)
    return assigned


def _projects_from_identities(raw_input: str, stats: FallbackStats) -> list[dict]:
    projects = []
    ledger = build_experience_fact_ledger(raw_input)
    for identity in build_experience_identities(raw_input)[:5]:
        local_facts = [
            fact for fact in ledger.for_experience(identity.experience_id)
            if fact.resume_eligible and fact.resume_ready_text
        ]
        details = [fact.resume_ready_text for fact in local_facts[:6]]
        if not details:
            stats.fallback_candidate_rejected_count += 1
            stats.fallback_bindings.append({
                "fallback_source_experience_id": identity.experience_id,
                "fallback_target_experience_id": identity.experience_id,
                "slot_binding_confidence": 1.0,
                "restored_fact_ids": [],
                "rejected": True,
                "reason": "no_local_resume_eligible_fact",
            })
            continue
        role, role_fact_ids = resolve_role_for_experience(
            raw_input, identity.experience_id, details=details, intro=details[0], ledger=ledger,
        )
        stats.role_fallback_triggered += 1
        if role:
            stats.role_recovered_from_fact_count += 1
            stats.role_source_experience_ids.append(identity.experience_id)
            stats.role_source_fact_ids.extend(role_fact_ids)
        else:
            stats.role_left_empty_count += 1
        candidate = {
                "name": identity.title or identity.experience_type,
                "meta": identity.experience_type,
                "time": "[待填写]",
                "intro": details[0],
                "role": role,
                "details": details,
                "source_experience_id": identity.experience_id,
                "source_binding_origin": "local_fact_fallback_candidate",
                "source_binding_confidence": 1.0,
                "source_binding_locked": False,
                "source_fact_ids": [fact.fact_id for fact in local_facts[:6]],
                "detail_fact_ids": [[fact.fact_id] for fact in local_facts[:6]],
                "role_source_fact_ids": role_fact_ids,
            }
        if not is_valid_fallback_candidate(candidate, raw_input):
            stats.fallback_candidate_rejected_count += 1
            continue
        stats.used_experience_id = True
        stats.fallback_bindings.append({
            "fallback_source_experience_id": identity.experience_id,
            "fallback_target_experience_id": identity.experience_id,
            "slot_binding_confidence": 1.0,
            "restored_fact_ids": [fact.fact_id for fact in local_facts[:6]],
            "rejected": False,
        })
        projects.append(candidate)
    return projects


def _merge_missing_projects(
    existing: list,
    candidates: list[dict],
    stats: FallbackStats,
    source: str,
    raw_input: str = "",
) -> list:
    merged = list(existing) if isinstance(existing, list) else []
    signatures = {_project_signature(project) for project in merged if isinstance(project, dict)}
    covered_ids = {
        _text(project.get("source_experience_id"))
        for project in merged
        if isinstance(project, dict) and _text(project.get("source_experience_id"))
    }
    for candidate in candidates:
        if not is_valid_fallback_candidate(candidate, raw_input):
            stats.fallback_candidate_rejected_count += 1
            continue
        signature = _project_signature(candidate)
        source_id = _text(candidate.get("source_experience_id"))
        if signature in signatures:
            continue
        if source_id and source_id in covered_ids:
            continue
        merged.append(candidate)
        signatures.add(signature)
        if source_id:
            covered_ids.add(source_id)
        stats.fill("projects", source)
        if len(merged) >= 5:
            break
    return merged


def _valid_fallback_projects(candidates: list, raw_input: str, stats: FallbackStats) -> list[dict]:
    valid: list[dict] = []
    for candidate in candidates if isinstance(candidates, list) else []:
        if isinstance(candidate, dict) and is_valid_fallback_candidate(candidate, raw_input):
            valid.append(candidate)
        else:
            stats.fallback_candidate_rejected_count += 1
    return valid


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
    raw_input: str = "",
    write_log: bool = True,
    return_stats: bool = False,
    semantic_build: "CanonicalSemanticBuild | None" = None,
) -> schemas.GenerationPayload | tuple[schemas.GenerationPayload, FallbackStats]:
    stats = FallbackStats(generation_result_id=generation_result_id, stage=stage)
    data = _as_payload_dict(payload)
    sections = data.get("resume_sections") if isinstance(data.get("resume_sections"), dict) else {}
    if semantic_build is not None:
        # This service may supply a candidate owner, never a frozen one.
        for project in sections.get("projects", []) if isinstance(sections.get("projects"), list) else []:
            if isinstance(project, dict):
                project.pop("immutable_source_experience_id", None)
                project["source_binding_locked"] = False

    source, source_field = _source_text(data)
    raw_source = _text(raw_input)

    sections["personal_info"] = sections.get("personal_info") if isinstance(sections.get("personal_info"), dict) else {}
    sections["education"] = sections.get("education") if isinstance(sections.get("education"), dict) else {}
    stats.projects_before = len(sections.get("projects", [])) if isinstance(sections.get("projects"), list) else 0

    identities = build_experience_identities(raw_source) if raw_source else []
    existing_projects = sections.get("projects") if isinstance(sections.get("projects"), list) else []
    if len(identities) >= 2 and len(existing_projects) == 1 and isinstance(existing_projects[0], dict):
        project_name = _text(existing_projects[0].get("name"))
        project_meta = _text(existing_projects[0].get("meta"))
        if "综合经历" in project_name or "综合经历" in project_meta:
            sections["projects"] = _projects_from_identities(raw_source, stats)
            stats.fill("projects", "experience_id/raw_input")
            stats.add_reason("combined_project_replaced")

    empty_sections = [
        section
        for section in ["summary", "skills", "projects", "interview_preparation"]
        if not _has_items(sections.get(section))
    ]
    stats.attempted_sections = list(empty_sections)
    if set(empty_sections) == {"summary", "skills", "projects", "interview_preparation"}:
        stats.add_reason("structured_resume_empty")
    for section in empty_sections:
        stats.add_reason(f"{section}_empty")

    if "summary" in empty_sections:
        sections["summary"] = _build_summary(data, source, source_field, stats)

    if "skills" in empty_sections:
        sections["skills"] = _extract_skills(data, source, source_field, stats)

    if "projects" in empty_sections:
        raw_projects = _projects_from_identities(raw_source, stats) if raw_source and identities else []
        if not raw_projects and raw_source:
            raw_projects = _parse_projects(raw_source, "raw_input", stats)
        elif raw_projects:
            stats.fill("projects", "experience_id/raw_input")
        candidates = raw_projects or _parse_projects(source, source_field, stats)
        sections["projects"] = _valid_fallback_projects(candidates, raw_source, stats)
        sections["projects"] = _assign_source_experience_ids(sections["projects"], raw_source, stats)
    elif raw_source:
        sections["projects"] = _assign_source_experience_ids(sections.get("projects"), raw_source, stats)
        identity_projects = _projects_from_identities(raw_source, stats) if identities else []
        sections["projects"] = _merge_missing_projects(
            sections.get("projects"), identity_projects, stats, "uncovered_experience_id", raw_source,
        )
        sections["projects"] = _assign_source_experience_ids(sections.get("projects"), raw_source, stats)

    if "interview_preparation" in empty_sections:
        sections["interview_preparation"] = _build_interview_preparation(data, stats)

    ledger = build_experience_fact_ledger(raw_source) if raw_source else None
    for project in sections.get("projects", []):
        if not isinstance(project, dict) or not is_internal_or_generic_role(_text(project.get("role"))):
            continue
        stats.internal_fallback_text_removed_count += 1
        stats.role_fallback_triggered += 1
        source_id = _text(project.get("source_experience_id"))
        recovered, fact_ids = resolve_role_for_experience(
            raw_source,
            source_id,
            details=project.get("details", []),
            intro=_text(project.get("intro")),
            ledger=ledger,
        ) if raw_source and source_id and ledger else ("", [])
        project["role"] = recovered
        if recovered:
            stats.role_recovered_from_fact_count += 1
            stats.role_source_experience_ids.append(source_id)
            stats.role_source_fact_ids.extend(fact_ids)
            project["role_source_fact_ids"] = fact_ids
        else:
            stats.role_left_empty_count += 1

    data["resume_sections"] = sections
    stats.projects_after = len(sections.get("projects", [])) if isinstance(sections.get("projects"), list) else 0
    stats.projects_added = max(0, stats.projects_after - stats.projects_before)
    stats.projects_removed = max(0, stats.projects_before - stats.projects_after)
    covered_ids = {
        _text(project.get("source_experience_id"))
        for project in sections.get("projects", [])
        if isinstance(project, dict) and _text(project.get("source_experience_id"))
    }
    stats.uncovered_experience_ids = [item.experience_id for item in identities if item.experience_id not in covered_ids]
    filled = schemas.GenerationPayload.model_validate(data)
    filled = deduplicate_resume_experience_entities(
        filled,
        raw_source,
        stage=f"{stage}_fallback",
        generation_result_id=generation_result_id,
        write_log=write_log,
        semantic_build=semantic_build,
        ownership_index=semantic_build.ownership_index if semantic_build is not None else None,
    )
    if stats.fallback_sections or stats.fallback_candidate_rejected_count:
        filled = ensure_resume_experience_validity(
            filled,
            raw_source,
            stage=f"{stage}_fallback",
            generation_result_id=generation_result_id,
            fallback_candidate_rejected_count=stats.fallback_candidate_rejected_count,
            write_log=write_log,
        )
    stats.projects_after = len(filled.resume_sections.projects)
    stats.projects_removed = max(0, stats.projects_before - stats.projects_after)
    if write_log:
        _write_fallback_log(stats)
    return (filled, stats) if return_stats else filled
