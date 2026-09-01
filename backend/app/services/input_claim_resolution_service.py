import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .input_semantic_role_service import (
    NEGATIVE_CONSTRAINT,
    RESUME_FACT,
    STRUCTURE_MARKER,
    TARGET_ROLE_CONTEXT,
    UNCERTAIN_FACT,
    USER_INSTRUCTION,
    classify_semantic_unit,
    split_semantic_units,
)


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "input_claim_resolution.jsonl"

POSITIVE = "positive"
NEGATIVE = "negative"
CONFIRMED = "confirmed"
PROBABLE = "probable"
UNCERTAIN = "uncertain"
DENIED = "denied"
CURRENT = "current"
HISTORICAL = "historical"
PLANNED = "planned"
UNKNOWN = "unknown"
ELIGIBLE = "eligible"
WITHHELD = "withheld"
EXCLUDED = "excluded"


@dataclass(frozen=True)
class InputClaim:
    claim_id: str
    source_experience_id: str
    source_span: tuple[int, int]
    subject: str
    predicate: str
    object: str
    text: str
    semantic_role: str
    polarity: str
    certainty: str
    temporal_status: str
    eligibility: str
    evidence_type: str = "explicit"
    exclusion_reason: str = ""
    related_claim_ids: tuple[str, ...] = ()

    @property
    def experience_id(self) -> str:
        return self.source_experience_id

    @property
    def resume_eligible(self) -> bool:
        return self.eligibility == ELIGIBLE


@dataclass
class ClaimResolution:
    claims: list[InputClaim] = field(default_factory=list)
    conflict_count: int = 0
    resolved_conflict_count: int = 0
    unresolved_conflict_count: int = 0

    @property
    def eligible_claims(self) -> list[InputClaim]:
        return [claim for claim in self.claims if claim.eligibility == ELIGIBLE]

    @property
    def withheld_claims(self) -> list[InputClaim]:
        return [claim for claim in self.claims if claim.eligibility == WITHHELD]

    @property
    def excluded_claims(self) -> list[InputClaim]:
        return [claim for claim in self.claims if claim.eligibility == EXCLUDED]


CLAUSE_BOUNDARY = re.compile(
    r"[，,](?=\s*(?:但|但是|不过|而|只|仅|实际|后来|后续|随后|最终|目前|现在|也有可能|也可能|可能|计划|准备|拟(?:开展|进行|增加|开发|上线|部署|实现|重构|迁移)|引入|是课程项目|有|我记不清|我不确定|记不清|不确定))"
)
UNCERTAINTY_PATTERN = re.compile(
    r"(?:可能|也许|或许|好像|大概|似乎|记不清|不确定|无法确认|应该是|有可能)", re.I
)
PROBABLE_PATTERN = re.compile(r"(?:推测|大概率|较可能)", re.I)
NEGATION_PATTERN = re.compile(
    r"^(?:但|但是|不过|而)?\s*(?:没有|并未|未曾|不曾|并没有|未|不是|不负责|没有负责|无法确认)", re.I
)
INSTRUCTION_PATTERN = re.compile(
    r"(?:请|不要|不得|别|希望|想要|需要).{0,48}(?:包装|突出|强调|匹配|简历|岗位|写成|编|补|串|混|删除|省略)|"
    r"(?:指标|事实|内容|项目).{0,24}(?:不要串|不能串|别串|不要混|不能混)",
    re.I,
)
PLANNED_PATTERN = re.compile(
    r"(?:后续将|下一步(?:将|计划)?|正在推进|希望增加|考虑增加)|"
    r"(?:^|[，,。；;])\s*(?:计划|准备|打算|拟)\s*(?:新增|增加|开展|进行|开发|上线|部署|实现|重构|迁移|优化|接入|支持)",
    re.I,
)
HISTORICAL_PATTERN = re.compile(r"(?:早期|最初|原先|此前|第一阶段|原型阶段|曾经|曾使用)", re.I)
CURRENT_PATTERN = re.compile(r"(?:后续|后来|随后|最终|目前|现在|第二阶段|已迁移|切换到|升级为)", re.I)
META_UNCERTAINTY_PATTERN = re.compile(r"^(?:我)?(?:记不清|不确定|无法确认)(?:了|具体情况)?$", re.I)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" \t\r\n，,。；;")


def _claim_clauses(text: str, base_offset: int) -> list[tuple[str, int, int]]:
    clauses: list[tuple[str, int, int]] = []
    for unit, start, end in split_semantic_units(text, base_offset):
        cursor = 0
        for match in CLAUSE_BOUNDARY.finditer(unit):
            value = _compact(unit[cursor:match.start()])
            if value:
                local = unit.find(value, cursor, match.start() + 1)
                clauses.append((value, start + max(0, local), start + max(0, local) + len(value)))
            cursor = match.end()
        value = _compact(unit[cursor:])
        if value:
            local = unit.find(value, cursor)
            clauses.append((value, start + max(0, local), start + max(0, local) + len(value)))
    return clauses


def _semantic_role(text: str) -> str:
    if re.fullmatch(r"(?:是|属于)?\s*(?:个人项目|课程项目|团队项目|开源项目|项目经历|实习经历|科研经历|竞赛经历)", _compact(text)):
        return STRUCTURE_MARKER
    primary, roles, _, _, _ = classify_semantic_unit(text)
    if INSTRUCTION_PATTERN.search(text):
        return USER_INSTRUCTION
    if STRUCTURE_MARKER in roles:
        return STRUCTURE_MARKER
    if TARGET_ROLE_CONTEXT in roles:
        return TARGET_ROLE_CONTEXT
    if UNCERTAIN_FACT in roles or UNCERTAINTY_PATTERN.search(text):
        return UNCERTAIN_FACT
    if NEGATIVE_CONSTRAINT in roles or NEGATION_PATTERN.search(text):
        return NEGATIVE_CONSTRAINT
    return primary if primary == RESUME_FACT else RESUME_FACT


def _attributes(text: str, role: str) -> tuple[str, str, str, str, str]:
    polarity = NEGATIVE if NEGATION_PATTERN.search(text) else POSITIVE
    if polarity == NEGATIVE:
        certainty = DENIED
    elif UNCERTAINTY_PATTERN.search(text):
        certainty = UNCERTAIN
    elif PROBABLE_PATTERN.search(text):
        certainty = PROBABLE
    else:
        certainty = CONFIRMED

    if PLANNED_PATTERN.search(text):
        temporal = PLANNED
    elif HISTORICAL_PATTERN.search(text):
        temporal = HISTORICAL
    elif CURRENT_PATTERN.search(text):
        temporal = CURRENT
    else:
        temporal = UNKNOWN

    if role in {USER_INSTRUCTION, TARGET_ROLE_CONTEXT, STRUCTURE_MARKER}:
        return polarity, certainty, temporal, EXCLUDED, role.lower()
    if polarity == NEGATIVE:
        return polarity, certainty, temporal, EXCLUDED, "negative_constraint"
    if certainty in {UNCERTAIN, PROBABLE}:
        return polarity, certainty, temporal, WITHHELD, "uncertain_claim"
    if temporal == PLANNED:
        return polarity, certainty, temporal, WITHHELD, "planned_work"
    return polarity, certainty, temporal, ELIGIBLE, ""


def _parts(text: str) -> tuple[str, str, str]:
    value = re.sub(r"^(?:但|但是|不过|而|只|仅|实际|后来|后续|随后|最终|目前|现在|同时)\s*", "", text)
    match = re.match(
        r"(?P<subject>我|本人|项目|系统|平台|团队|框架|技术栈)?\s*"
        r"(?P<predicate>没有负责|未负责|不是|没有|未|负责|参与|独立完成|完成|实现|使用|采用|迁移到|切换到|获得|提升|降低|建立|开发|设计|部署|上线|优化|是)?\s*"
        r"(?P<object>.*)",
        value,
        re.I,
    )
    if not match:
        return "", "", value
    return (
        str(match.group("subject") or "").strip(),
        str(match.group("predicate") or "").strip(),
        str(match.group("object") or value).strip(),
    )


def resolve_experience_claims(
    experience_id: str,
    text: str,
    source_offset: int = 0,
) -> ClaimResolution:
    draft: list[dict] = []
    for index, (clause, start, end) in enumerate(_claim_clauses(text, source_offset), start=1):
        role = _semantic_role(clause)
        polarity, certainty, temporal, eligibility, reason = _attributes(clause, role)
        if META_UNCERTAINTY_PATTERN.fullmatch(clause):
            eligibility, reason = EXCLUDED, "uncertainty_marker"
        claim_text = clause
        if eligibility == ELIGIBLE:
            claim_text = re.sub(r"^(?:但|但是|不过|而|只|仅|实际)\s*", "", claim_text).strip()
        subject, predicate, object_value = _parts(claim_text)
        draft.append({
            "claim_id": f"{experience_id}-C{index:03d}",
            "source_experience_id": experience_id,
            "source_span": (start, end),
            "subject": subject,
            "predicate": predicate,
            "object": object_value,
            "text": claim_text,
            "semantic_role": role,
            "polarity": polarity,
            "certainty": certainty,
            "temporal_status": temporal,
            "eligibility": eligibility,
            "exclusion_reason": reason,
        })

    ownership_instruction = bool(
        re.search(r"(?:相似|相近|不是(?:同一个|一个)项目|分别).{0,30}(?:不要|不能|别).{0,16}(?:串|混|合并)", text, re.I)
    )
    if ownership_instruction:
        for row in draft:
            if row["eligibility"] == ELIGIBLE and re.search(r"相似|相近|不是(?:同一个|一个)项目|分别", row["text"]):
                row["semantic_role"] = USER_INSTRUCTION
                row["eligibility"] = EXCLUDED
                row["exclusion_reason"] = "ownership_constraint_context"

    temporal_ids = [row["claim_id"] for row in draft if row["temporal_status"] in {HISTORICAL, CURRENT}]
    claims = [
        InputClaim(
            **row,
            related_claim_ids=tuple(item for item in temporal_ids if item != row["claim_id"]),
        )
        for row in draft
    ]
    unresolved = sum(
        claim.eligibility == WITHHELD and claim.certainty in {UNCERTAIN, PROBABLE}
        for claim in claims
    )
    return ClaimResolution(
        claims=claims,
        conflict_count=unresolved,
        unresolved_conflict_count=unresolved,
    )


def build_claim_missing_questions(resolutions: list[ClaimResolution]) -> list[str]:
    questions: list[str] = []
    for claim in (claim for resolution in resolutions for claim in resolution.withheld_claims):
        if claim.certainty in {UNCERTAIN, PROBABLE}:
            question = f"请确认 {claim.source_experience_id} 中“{claim.object or claim.text}”的准确信息。"
        elif claim.temporal_status == PLANNED:
            question = f"请确认 {claim.source_experience_id} 中“{claim.object or claim.text}”是否已经完成。"
        else:
            continue
        if question not in questions:
            questions.append(question)
    return questions[:8]


def write_claim_resolution_log(
    resolutions: list[ClaimResolution],
    *,
    stage: str,
    generation_result_id: int | None = None,
) -> None:
    try:
        claims = [claim for resolution in resolutions for claim in resolution.claims]
        reasons: dict[str, int] = {}
        for claim in claims:
            if claim.exclusion_reason:
                reasons[claim.exclusion_reason] = reasons.get(claim.exclusion_reason, 0) + 1
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "generation_result_id": generation_result_id,
            "stage": stage,
            "total_claim_count": len(claims),
            "eligible_claim_count": sum(claim.eligibility == ELIGIBLE for claim in claims),
            "withheld_claim_count": sum(claim.eligibility == WITHHELD for claim in claims),
            "excluded_claim_count": sum(claim.eligibility == EXCLUDED for claim in claims),
            "negative_claim_count": sum(claim.polarity == NEGATIVE for claim in claims),
            "uncertain_claim_count": sum(claim.certainty in {UNCERTAIN, PROBABLE} for claim in claims),
            "temporal_claim_count": sum(claim.temporal_status in {HISTORICAL, CURRENT, PLANNED} for claim in claims),
            "conflict_count": sum(item.conflict_count for item in resolutions),
            "resolved_conflict_count": sum(item.resolved_conflict_count for item in resolutions),
            "unresolved_conflict_count": sum(item.unresolved_conflict_count for item in resolutions),
            "affected_experience_ids": sorted({claim.source_experience_id for claim in claims}),
            "exclusion_reason_counts": reasons,
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
