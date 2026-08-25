import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_PATH = LOG_DIR / "experience_segmentation.jsonl"

AUTO_SPLIT_THRESHOLD = 0.72
CAUTIOUS_SPLIT_THRESHOLD = 0.48

BACKGROUND_PATTERNS = [
    r"我是(?:一名)?(?:大[一二三四五]|研[一二三]|本科|硕士|博士)(?:学生)?",
    r"目前是(?:大[一二三四五]|研[一二三])",
]
INTENT_PATTERNS = [
    r"希望(?:包装得)?更?适合[^。；;]+(?:岗位|方向)",
    r"想投[^。；;]+(?:岗位|方向)",
    r"目标岗位是[^。；;]+",
]
START_PATTERNS = [
    r"(?:利用|使用).{0,8}(?:AI|人工智能).{0,8}(?:做过|开发过|设计过)",
    r"(?:做过|开发过|设计了|设计过|完成过)",
    r"(?:参加过|参与了|参与过|深度参与|加入)",
    r"(?:担任|作为).{0,28}(?:成员|负责人|干事|宣传|开发者)",
]
CONTINUATION_PREFIXES = (
    "可以", "包含", "支持", "实现", "能够", "并", "以及", "同时", "其中", "根据", "主要功能", "技术上",
)

TYPE_KEYWORDS = {
    "实习经历": ["实习", "公司", "岗位"],
    "科研经历": ["科研", "研究", "论文", "课题", "实验室"],
    "开源经历": ["开源", "GitHub", "PR", "commit"],
    "社团经历": ["协会", "社团", "足球协会"],
    "社会实践经历": ["实践队", "社会实践", "实践落地"],
    "竞赛获奖": ["竞赛", "比赛", "路演", "一等奖", "二等奖", "三等奖", "获奖"],
    "校园活动经历": ["校庆", "晚会", "演出", "节目安排", "梦拓计划"],
    "学生工作经历": ["学生会", "干事", "班委", "组织协调"],
    "课程项目": ["课程项目", "课程作业", "大作业", "课设"],
    "项目经历": ["系统", "平台", "计算器", "工具", "项目", "应用"],
}

THEME_KEYWORDS = {
    "ai_data": ["AI", "回归分析", "函数选择", "数据合理性", "生成图像", "数据分析"],
    "campus_event": ["校庆", "活动策划", "晚会", "演出", "节目安排", "审核", "表演", "梦拓计划"],
    "practice": ["实践队", "实践落地", "宣传干事", "联系"],
    "media": ["足球协会", "拍摄", "剪辑", "宣传"],
    "parking": ["停车场", "停车指引", "路线", "天气", "车流", "路演"],
}


@dataclass
class SemanticExperienceSegment:
    experience_id: str
    experience_type: str
    title: str
    raw_text: str
    start_offset: int
    end_offset: int
    segmentation_confidence: float
    segmentation_reasons: list[str] = field(default_factory=list)
    explicit_tech_terms: list[str] = field(default_factory=list)
    explicit_metrics: list[str] = field(default_factory=list)
    evidence_terms: list[str] = field(default_factory=list)
    risk_terms: list[str] = field(default_factory=list)
    supported_inference_terms: list[str] = field(default_factory=list)


@dataclass
class SemanticSegmentationResult:
    segments: list[SemanticExperienceSegment]
    discarded_context_count: int = 0
    semantic_boundary_count: int = 0
    merged_segment_count: int = 0
    low_confidence_segment_count: int = 0
    clarification_questions: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip(" ，,。；;：:")


def _strip_context(text: str) -> tuple[str, int]:
    cleaned = text
    count = 0
    for pattern in BACKGROUND_PATTERNS + INTENT_PATTERNS:
        cleaned, replacements = re.subn(pattern, "", cleaned, flags=re.IGNORECASE)
        count += replacements
    return _normalize(cleaned), count


def _themes(text: str) -> set[str]:
    lowered = text.lower()
    return {
        theme
        for theme, keywords in THEME_KEYWORDS.items()
        if any(keyword.lower() in lowered for keyword in keywords)
    }


def _infer_type(text: str) -> str:
    negative_internship = any(term in text for term in ["没有实习", "无实习", "没实习"])
    for experience_type, keywords in TYPE_KEYWORDS.items():
        if experience_type == "实习经历" and negative_internship:
            continue
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return experience_type
    return "其他经历"


def _infer_title(text: str, experience_type: str) -> str:
    title_rules = [
        (r"(?:做过|开发过|设计了|设计过)?(?:一个|一套)?([^，。；;]{2,24}(?:计算器|系统|平台|工具|助手))", 1),
        (r"(智能停车场(?:系统)?)", 1),
        (r"(回归分析计算器)", 1),
        (r"(学校?足球协会)", 1),
        (r"(校庆活动)", 1),
        (r"([^，。；;]{2,18}实践队)", 1),
        (r"(梦拓计划|学院晚会)", 1),
    ]
    for pattern, group in title_rules:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _normalize(match.group(group))[:60]
    return experience_type


def _has_start_signal(text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in START_PATTERNS) or bool(
        re.search(r"^是.{0,24}实践队", text)
    )


def _boundary_score(previous: str, current: str, punctuation: str) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if punctuation in {"；", ";", "。", "\n"}:
        score += 0.15
        reasons.append("完整标点边界")
    if _has_start_signal(current):
        score += 0.20
        reasons.append("出现新经历动作")
    previous_type = _infer_type(previous)
    current_type = _infer_type(current)
    if previous_type != current_type and "其他经历" not in {previous_type, current_type}:
        score += 0.25
        reasons.append("经历类型变化")
    previous_themes = _themes(previous)
    current_themes = _themes(current)
    if previous_themes and current_themes and previous_themes.isdisjoint(current_themes):
        score += 0.20
        reasons.append("主题明显变化")
    if any(term in current for term in ["协会", "实践队", "学院", "校庆", "团队核心成员"]):
        score += 0.20
        reasons.append("出现新组织或角色")
    if any(term in current for term in ["一等奖", "二等奖", "三等奖", "获奖", "路演", "GitHub", "上线"]):
        score += 0.15
        reasons.append("出现独立结果或证据")
    if len(previous) >= 12 and len(current) >= 12 and _has_start_signal(previous) and _has_start_signal(current):
        score += 0.15
        reasons.append("前后均可形成独立经历")
    if current.startswith(CONTINUATION_PREFIXES) and not _has_start_signal(current):
        score -= 0.35
        reasons.append("后句是功能或技术补充")
    if len(current) < 10 and not _has_start_signal(current):
        score -= 0.25
        reasons.append("片段过短")
    return max(0.0, min(1.0, score)), reasons


def _candidate_clauses(text: str) -> list[tuple[str, int, int, str]]:
    clauses: list[tuple[str, int, int, str]] = []
    start = 0
    boundary_pattern = re.compile(
        r"[；;。\n]+|[，,](?=(?:参加过|参与了|参与过|参与学校|深度参与|担任|作为团队|是.{0,24}实践队))"
    )
    preceding_punctuation = ""
    for match in boundary_pattern.finditer(text):
        chunk = _normalize(text[start:match.start()])
        if chunk:
            clauses.append((chunk, start, match.start(), preceding_punctuation))
        preceding_punctuation = match.group(0)[0]
        start = match.end()
    tail = _normalize(text[start:])
    if tail:
        clauses.append((tail, start, len(text), preceding_punctuation))
    return clauses


def _merge_related_campus_segments(segments: list[dict]) -> tuple[list[dict], int]:
    result: list[dict] = []
    merged = 0
    mergeable_types = {"校园活动经历", "学生工作经历"}
    for segment in segments:
        if (
            result
            and segment["experience_type"] in mergeable_types
            and result[-1]["experience_type"] in mergeable_types
            and len(segment["raw_text"]) < 45
            and len(result[-1]["raw_text"]) < 100
        ):
            result[-1]["raw_text"] = f"{result[-1]['raw_text']}；{segment['raw_text']}"
            result[-1]["end_offset"] = segment["end_offset"]
            result[-1]["title"] = "校园活动与组织经历"
            result[-1]["segmentation_reasons"].append("相邻短校园经历谨慎合并")
            merged += 1
        else:
            result.append(segment)
    return result, merged


def segment_semantic_experiences(raw_input: str, write_log: bool = False, stage: str = "unknown") -> SemanticSegmentationResult:
    source = raw_input or ""
    cleaned, discarded = _strip_context(source)
    if not cleaned:
        return SemanticSegmentationResult(segments=[], discarded_context_count=discarded)

    clauses = _candidate_clauses(cleaned)
    grouped: list[dict] = []
    semantic_boundaries = 0
    low_confidence = 0
    questions: list[str] = []
    for clause, start, end, punctuation in clauses:
        if not grouped:
            grouped.append({
                "raw_text": clause,
                "start_offset": start,
                "end_offset": end,
                "segmentation_confidence": 1.0,
                "segmentation_reasons": ["首段经历"],
                "experience_type": _infer_type(clause),
            })
            continue
        previous = grouped[-1]["raw_text"]
        score, reasons = _boundary_score(previous, clause, punctuation)
        should_split = score >= AUTO_SPLIT_THRESHOLD or (
            score >= CAUTIOUS_SPLIT_THRESHOLD
            and _has_start_signal(clause)
            and bool(_themes(previous).isdisjoint(_themes(clause)))
        )
        if should_split:
            grouped.append({
                "raw_text": clause,
                "start_offset": start,
                "end_offset": end,
                "segmentation_confidence": score,
                "segmentation_reasons": reasons,
                "experience_type": _infer_type(clause),
            })
            semantic_boundaries += 1
            if score < AUTO_SPLIT_THRESHOLD:
                low_confidence += 1
        else:
            grouped[-1]["raw_text"] = f"{grouped[-1]['raw_text']}；{clause}"
            grouped[-1]["end_offset"] = end
            if CAUTIOUS_SPLIT_THRESHOLD <= score < AUTO_SPLIT_THRESHOLD:
                low_confidence += 1
                questions.append(f"“{_infer_title(clause, _infer_type(clause))}”是否需要作为单独经历展示？")

    grouped, merged_count = _merge_related_campus_segments(grouped)
    segments: list[SemanticExperienceSegment] = []
    for index, item in enumerate(grouped, start=1):
        experience_type = _infer_type(item["raw_text"])
        segments.append(
            SemanticExperienceSegment(
                experience_id=f"EXP-{index:03d}",
                experience_type=experience_type,
                title=_infer_title(item["raw_text"], experience_type),
                raw_text=item["raw_text"],
                start_offset=item["start_offset"],
                end_offset=item["end_offset"],
                segmentation_confidence=item["segmentation_confidence"],
                segmentation_reasons=item["segmentation_reasons"],
            )
        )

    result = SemanticSegmentationResult(
        segments=segments,
        discarded_context_count=discarded,
        semantic_boundary_count=semantic_boundaries,
        merged_segment_count=merged_count,
        low_confidence_segment_count=low_confidence,
        clarification_questions=list(dict.fromkeys(questions))[:4],
    )
    if write_log:
        write_segmentation_log(result, len(source), stage=stage)
    return result


def write_segmentation_log(result: SemanticSegmentationResult, raw_input_length: int, stage: str = "unknown", generation_result_id: int | None = None) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "raw_input_length": raw_input_length,
            "explicit_boundary_count": 0,
            "semantic_boundary_count": result.semantic_boundary_count,
            "total_segments": len(result.segments),
            "discarded_context_count": result.discarded_context_count,
            "merged_segment_count": result.merged_segment_count,
            "low_confidence_segment_count": result.low_confidence_segment_count,
            "segments": [
                {
                    "experience_id": item.experience_id,
                    "experience_type": item.experience_type,
                    "title": item.title[:40],
                    "confidence": round(item.segmentation_confidence, 3),
                    "reasons": item.segmentation_reasons,
                    "raw_text_length": len(item.raw_text),
                }
                for item in result.segments
            ],
            "generation_result_id": generation_result_id,
            "stage": stage,
        }
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return
