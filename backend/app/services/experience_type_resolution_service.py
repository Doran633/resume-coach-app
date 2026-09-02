import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from .. import schemas
from .canonical_semantic_state_service import CanonicalExperienceTypeDecision
from .experience_identity_service import ExperienceIdentity, build_experience_identities

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "experience_type_resolution.jsonl"
RESOLVER_VERSION = "v0.9.2"
STANDARD_TYPES = ["项目经历", "实习经历", "科研经历", "竞赛获奖", "竞赛经历", "开源经历", "校园 / 社团经历"]
EXCLUDED_INTERNSHIP_CONTEXTS = [
    r"面向[^。；\n]{0,30}实习(?:生|求职者|用户)", r"服务[^。；\n]{0,20}实习用户", r"帮助用户[^。；\n]{0,30}实习",
    r"应届生和实习生", r"实习(?:招聘|岗位推荐|简历|求职平台|面试准备|经历分析|用户反馈)",
    r"(?:没有|缺少|无)实习", r"想(?:找|投)实习", r"适合实习岗位",
    r"不是实习",
]


@dataclass
class TypeResolution:
    experience_id: str
    resolved_type: str
    confidence: float
    positive_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)
    source_title: str = ""
    local_raw_text: str = ""
    resolution_method: str = "relation_score"
    conflict_detected: bool = False
    evidence_scores: dict[str, int] = field(default_factory=dict)
    excluded_context_signals: list[str] = field(default_factory=list)
    runner_up_type: str = ""
    score_margin: int = 0
    employment_relation_detected: bool = False
    project_ownership_detected: bool = False
    inherited_identity_type: str = ""
    inherited_type_used: bool = False
    type_locked: bool = True
    resolver_version: str = RESOLVER_VERSION


def _hits(pattern: str, text: str) -> list[str]:
    return [match.group(0) for match in re.finditer(pattern, text, re.IGNORECASE)]


def resolve_identity_type(identity: ExperienceIdentity) -> TypeResolution:
    title, local = identity.title or "", identity.raw_text or ""
    text = f"{title}\n{local}"
    scores = {key: 0 for key in STANDARD_TYPES}
    positive: list[str] = []
    excluded = [hit for pattern in EXCLUDED_INTERNSHIP_CONTEXTS for hit in _hits(pattern, text)]

    if identity.declared_experience_type in STANDARD_TYPES:
        declared = identity.declared_experience_type
        scores[declared] = 100
        return TypeResolution(
            experience_id=identity.experience_id,
            resolved_type=declared,
            confidence=1.0,
            positive_signals=[f"用户显式类型:{declared}"],
            negative_signals=[f"排除实习语境:{item[:50]}" for item in excluded],
            source_title=title,
            local_raw_text=local,
            resolution_method="declared_experience_type",
            conflict_detected=identity.experience_type != declared,
            evidence_scores=scores,
            excluded_context_signals=excluded,
            runner_up_type="",
            score_margin=100,
            inherited_identity_type=identity.experience_type,
            inherited_type_used=True,
        )

    explicit_rules = [
        ("实习经历", r"(?:^|\n)\s*实习经历(?:\s|$|[:：|｜])", 10),
        ("项目经历", r"(?:^|\n)\s*(?:项目经历|项目[一二三四五六七八九十\d]+)(?:\s|$|[:：|｜])", 10),
        ("科研经历", r"(?:^|\n)\s*(?:科研经历|研究经历|论文经历)(?:\s|$|[:：|｜])", 10),
        ("竞赛经历", r"(?:^|\n)\s*(?:竞赛经历|比赛经历)(?:\s|$|[:：|｜])", 10),
        ("开源经历", r"(?:^|\n)\s*开源经历(?:\s|$|[:：|｜])", 10),
    ]
    for type_name, pattern, weight in explicit_rules:
        hits = _hits(pattern, text)
        if hits:
            scores[type_name] += weight
            positive.extend(f"{type_name}:{hit[:40]}" for hit in hits)

    # The identity layer now emits internship only for an explicit heading or
    # an author-employment relation, so this inherited signal is bounded and
    # no longer represents a raw keyword match.
    if identity.experience_type == "实习经历":
        scores["实习经历"] += 10
        positive.append("实习经历:identity_strong_relation")
    elif identity.experience_type in STANDARD_TYPES and identity.experience_type != "项目经历":
        scores[identity.experience_type] += 4

    employment_patterns = [
        r"在[^。；\n]{2,50}(?:公司|企业|事务所|研究院)[^。；\n]{0,35}(?:实习|担任)",
        r"担任[^。；\n]{0,35}实习生", r"实习期间(?:负责|参与)", r"作为[^。；\n]{0,40}实习生",
    ]
    employment_hits = [hit for pattern in employment_patterns for hit in _hits(pattern, text)]
    if employment_hits:
        scores["实习经历"] += 10
        positive.extend(f"实习关系:{hit[:50]}" for hit in employment_hits)
    scores["实习经历"] -= min(16, len(excluded) * 8)

    project_patterns = [
        (r"独立(?:设计并开发|设计|开发|完成)", 8), (r"个人项目|课程项目", 8), (r"从零设计|持续迭代", 5),
        (r"项目起点|产品定位|完整工作流|系统实现|平台开发", 4), (r"公网部署|用户测试|产品反馈|版本迭代|GitHub", 3),
        (r"前端(?:使用|主要使用)|后端(?:使用|主要使用)|技术栈", 3),
    ]
    ownership_hits: list[str] = []
    for pattern, weight in project_patterns:
        hits = _hits(pattern, text)
        if hits:
            scores["项目经历"] += weight
            ownership_hits.extend(hits)
    if ownership_hits:
        positive.extend(f"项目关系:{hit[:40]}" for hit in ownership_hits[:6])

    semantic_rules = [
        ("科研经历", r"(?:参与|负责|开展|承担).{0,24}(?:课题|实验研究)|课题组|实验室|研究职责|论文(?:发表|投稿)", 6),
        ("竞赛获奖", r"一等奖|二等奖|三等奖|金奖|银奖|铜奖", 8),
        ("竞赛经历", r"参加[^。；\n]{0,40}(?:竞赛|比赛)|赛题|路演|答辩", 5),
        ("开源经历", r"开源贡献|Pull Request|\bPR\b|maintainer", 6),
        ("校园 / 社团经历", r"学生会|社团|协会|校庆|校园活动|志愿", 6),
    ]
    for type_name, pattern, weight in semantic_rules:
        hits = _hits(pattern, text)
        if hits:
            scores[type_name] += weight
            positive.extend(f"{type_name}:{hit[:40]}" for hit in hits[:3])

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    resolved, top_score = ranked[0]
    runner_up, second_score = ranked[1]
    if top_score <= 0 or top_score - second_score < 2:
        resolved = "项目经历"
    margin = top_score - second_score
    confidence = 0.55
    if top_score >= 10 and margin >= 5:
        confidence = 0.92
    elif top_score >= 8 and margin >= 3:
        confidence = 0.85
    elif top_score >= 5:
        confidence = 0.72
    elif top_score > 0:
        confidence = 0.62
    return TypeResolution(
        experience_id=identity.experience_id, resolved_type=resolved, confidence=confidence,
        positive_signals=positive, negative_signals=[f"排除实习语境:{item[:50]}" for item in excluded],
        source_title=title, local_raw_text=local, conflict_detected=identity.experience_type != resolved,
        evidence_scores=scores, excluded_context_signals=excluded, runner_up_type=runner_up, score_margin=margin,
        employment_relation_detected=bool(employment_hits), project_ownership_detected=bool(ownership_hits),
        inherited_identity_type=identity.experience_type, inherited_type_used=False,
    )


def build_type_resolutions(raw_input: str) -> dict[str, TypeResolution]:
    return {item.experience_id: resolve_identity_type(item) for item in build_experience_identities(raw_input)}


def _safe_type(value: str) -> str:
    return value if value in STANDARD_TYPES else "unrecognized"


def _signal_categories(signals: list[str]) -> list[str]:
    return sorted({item.split(":", 1)[0] for item in signals if item})


def _canonical_resolution(decision: CanonicalExperienceTypeDecision) -> TypeResolution:
    return TypeResolution(
        experience_id=decision.experience_id,
        resolved_type=decision.canonical_experience_type,
        confidence=decision.confidence,
        positive_signals=[f"canonical_type_source:{decision.type_source}"],
        resolution_method="canonical_semantic_build",
        inherited_identity_type=decision.canonical_experience_type,
        inherited_type_used=True,
    )


def _write_log(
    resolution: TypeResolution,
    llm_meta: str,
    final_section: str,
    stage: str,
    generation_result_id: int | None,
    *,
    authority_mode: str = "legacy",
    write_mode: str = "apply",
    canonical_decision: CanonicalExperienceTypeDecision | None = None,
) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "generation_result_id": generation_result_id,
            "stage": stage, "experience_id": resolution.experience_id, "original_type": _safe_type(resolution.inherited_identity_type),
            "llm_meta": _safe_type(llm_meta), "resolved_type": resolution.resolved_type, "confidence": resolution.confidence,
            "type_scores": resolution.evidence_scores, "runner_up_type": resolution.runner_up_type, "score_margin": resolution.score_margin,
            "positive_signal_categories": _signal_categories(resolution.positive_signals),
            "negative_signal_categories": _signal_categories(resolution.negative_signals),
            "excluded_context_count": len(resolution.excluded_context_signals),
            "employment_relation_detected": resolution.employment_relation_detected,
            "project_ownership_detected": resolution.project_ownership_detected,
            "inherited_identity_type": _safe_type(resolution.inherited_identity_type), "inherited_type_used": resolution.inherited_type_used,
            "conflict_detected": resolution.conflict_detected or llm_meta != resolution.resolved_type,
            "correction_applied": write_mode == "apply" and llm_meta != final_section,
            "final_section": _safe_type(final_section), "authority_mode": authority_mode,
            "write_mode": write_mode,
            "canonical_type_source": canonical_decision.type_source if canonical_decision else "",
            "canonical_type_explicit": canonical_decision.explicit if canonical_decision else False,
            "canonical_type_confidence": canonical_decision.confidence if canonical_decision else None,
            "type_locked": resolution.type_locked, "resolver_version": resolution.resolver_version,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _write_unmapped_canonical_log(
    source_id: str,
    *,
    stage: str,
    generation_result_id: int | None,
    write_mode: str,
) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "generation_result_id": generation_result_id,
            "stage": stage,
            "experience_id": source_id,
            "authority_mode": "canonical",
            "write_mode": write_mode,
            "canonical_mapping_found": False,
            "correction_applied": False,
            "resolver_version": RESOLVER_VERSION,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass


def resolve_project_types(
    payload: schemas.GenerationPayload,
    raw_input: str | None = None,
    *,
    canonical_type_decisions: Mapping[str, CanonicalExperienceTypeDecision] | None = None,
    apply_canonical_types: bool = True,
    stage: str = "unknown",
    generation_result_id: int | None = None,
    write_log: bool = True,
) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    if canonical_type_decisions is not None:
        write_mode = "apply" if apply_canonical_types else "validate"
        for project in updated.resume_sections.projects:
            source_id = str(project.get("source_experience_id") or "")
            decision = canonical_type_decisions.get(source_id)
            if decision is None:
                if write_log:
                    _write_unmapped_canonical_log(
                        source_id,
                        stage=stage,
                        generation_result_id=generation_result_id,
                        write_mode=write_mode,
                    )
                continue
            llm_meta = str(project.get("meta") or "项目经历")
            if apply_canonical_types:
                project["meta"] = decision.canonical_experience_type
                project["resolved_experience_type"] = decision.canonical_experience_type
                project["type_resolution_version"] = RESOLVER_VERSION
                project["type_locked"] = True
            if write_log:
                _write_log(
                    _canonical_resolution(decision),
                    llm_meta,
                    str(project.get("meta") or "项目经历"),
                    stage,
                    generation_result_id,
                    authority_mode="canonical",
                    write_mode=write_mode,
                    canonical_decision=decision,
                )
        return updated

    resolutions = build_type_resolutions(raw_input)
    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        resolution = resolutions.get(source_id)
        if not resolution:
            continue
        llm_meta = str(project.get("meta") or "项目经历")
        project["meta"] = resolution.resolved_type
        project["resolved_experience_type"] = resolution.resolved_type
        project["type_resolution_version"] = RESOLVER_VERSION
        project["type_locked"] = True
        if write_log:
            _write_log(resolution, llm_meta, resolution.resolved_type, stage, generation_result_id)
    return updated
