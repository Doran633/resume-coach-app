import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "input_semantic_role.jsonl"

RESUME_FACT = "RESUME_FACT"
USER_INSTRUCTION = "USER_INSTRUCTION"
NEGATIVE_CONSTRAINT = "NEGATIVE_CONSTRAINT"
UNCERTAIN_FACT = "UNCERTAIN_FACT"
TARGET_ROLE_CONTEXT = "TARGET_ROLE_CONTEXT"
STRUCTURE_MARKER = "STRUCTURE_MARKER"


@dataclass(frozen=True)
class InputSemanticUnit:
    semantic_unit_id: str
    experience_id: str
    text: str
    role: str
    source_span: tuple[int, int]
    polarity: str = "positive"
    certainty: str = "certain"
    resume_eligible: bool = True
    roles: tuple[str, ...] = ()


@dataclass
class InputSemanticAnalysis:
    units: list[InputSemanticUnit] = field(default_factory=list)

    @property
    def resume_facts(self) -> list[InputSemanticUnit]:
        return [unit for unit in self.units if unit.resume_eligible and unit.role == RESUME_FACT]

    @property
    def constraints(self) -> list[InputSemanticUnit]:
        return [unit for unit in self.units if NEGATIVE_CONSTRAINT in unit.roles]

    @property
    def uncertain_facts(self) -> list[InputSemanticUnit]:
        return [unit for unit in self.units if UNCERTAIN_FACT in unit.roles]


INSTRUCTION_PATTERNS = (
    r"(?:请|不要|不得|别)(?:为了|把|将|写|编|补|合并|串|混|删除|省略)",
    r"(?:希望|想要|需要).{0,36}(?:包装|突出|强调|匹配|简历|岗位|写成|表达)",
    r"(?:指标|事实|内容|项目).{0,18}(?:不要串|不能串|别串|不要混|不能混)",
    r"(?:以用户原文|以实际情况|以事实为准|不要编造|不能编造)",
)
NEGATIVE_PATTERNS = (
    r"(?:没有|并未|不曾|并没有|不负责|未负责|不是我负责|无法确认|未(?:曾|参与|实现|完成|上线|获奖|使用|部署)).{0,40}",
    r"(?:不要|不得|不能|别(?:把|将|写|编|补|删)).{0,40}(?:编造|补充|写成|归入|混入|串用|夸大)",
)
UNCERTAIN_PATTERNS = (
    r"(?:好像|也许|大概|似乎|记不清|不确定|无法确认|有可能)",
    r"(?:框架|技术|接口|模型|工具).{0,12}可能(?:是|为|用了?|使用)",
    r"(?:Flask|FastAPI|Django|React|Vue|Python|Java).{0,18}(?:或|还是).{0,18}(?:记不清|不确定|可能)",
)
TARGET_ROLE_PATTERNS = (
    r"(?:我想投|想投|目标岗位(?:是|为)?|求职方向(?:是|为)?|希望投递|岗位方向)",
)
STRUCTURE_PATTERNS = (
    r"^(?:项目|经历)[一二三四五六七八九十\dA-Za-z]*\s*[:：|｜\-—]?\s*$",
    r"^(?:技术动作|补充说明|用户说明|约束|备注|目标岗位|项目介绍|我的职责|技术细节)\s*[:：]?\s*$",
    r"^(?:#{1,6}|[-*+>•▪]|\d+[.)、])\s*$",
)


def _compact(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" \t\r\n，,。；;")


def _strip_fact_shell(text: str) -> str:
    value = _compact(text)
    value = re.sub(r"^(?:但|但是|不过|而(?:本人|项目|实际)?)\s*", "", value)
    value = re.sub(r"^(?:我(?:曾经)?做过(?:一个|一套)?|我做了(?:一个|一套)?|我参与过|我参与了)\s*", "", value)
    value = re.sub(r"^(?:技术动作|项目事实|事实说明)\s*[:：]\s*", "", value)
    return value.strip()


def _roles_for(text: str) -> tuple[str, ...]:
    value = _compact(text)
    roles: list[str] = []
    if any(re.search(pattern, value, re.IGNORECASE) for pattern in STRUCTURE_PATTERNS):
        roles.append(STRUCTURE_MARKER)
    if any(re.search(pattern, value, re.IGNORECASE) for pattern in TARGET_ROLE_PATTERNS):
        roles.append(TARGET_ROLE_CONTEXT)
    if any(re.search(pattern, value, re.IGNORECASE) for pattern in UNCERTAIN_PATTERNS):
        roles.append(UNCERTAIN_FACT)
    if any(re.search(pattern, value, re.IGNORECASE) for pattern in NEGATIVE_PATTERNS):
        roles.append(NEGATIVE_CONSTRAINT)
    if any(re.search(pattern, value, re.IGNORECASE) for pattern in INSTRUCTION_PATTERNS):
        roles.append(USER_INSTRUCTION)
    if not roles:
        roles.append(RESUME_FACT)
    return tuple(dict.fromkeys(roles))


def classify_semantic_unit(text: str) -> tuple[str, tuple[str, ...], str, str, bool]:
    roles = _roles_for(text)
    if STRUCTURE_MARKER in roles:
        primary = STRUCTURE_MARKER
    elif USER_INSTRUCTION in roles:
        primary = USER_INSTRUCTION
    elif UNCERTAIN_FACT in roles:
        primary = UNCERTAIN_FACT
    elif NEGATIVE_CONSTRAINT in roles:
        primary = NEGATIVE_CONSTRAINT
    elif TARGET_ROLE_CONTEXT in roles:
        primary = TARGET_ROLE_CONTEXT
    else:
        primary = RESUME_FACT
    polarity = "negative" if NEGATIVE_CONSTRAINT in roles else "positive"
    certainty = "uncertain" if UNCERTAIN_FACT in roles else "certain"
    return primary, roles, polarity, certainty, primary == RESUME_FACT


def split_semantic_units(text: str, base_offset: int = 0) -> list[tuple[str, int, int]]:
    source = str(text or "")
    units: list[tuple[str, int, int]] = []
    cursor = 0
    for match in re.finditer(
        r"(?<=[。！？；;])\s*|\n+|(?<=[，,])(?=(?:但|但是|不过|而(?:本人|项目|实际)))",
        source,
    ):
        raw = source[cursor:match.start()]
        value = _compact(raw)
        if value:
            local = source.find(value, cursor, match.start() + 1)
            local = cursor if local < 0 else local
            units.append((value, base_offset + local, base_offset + local + len(value)))
        cursor = match.end()
    raw = source[cursor:]
    value = _compact(raw)
    if value:
        local = source.find(value, cursor)
        local = cursor if local < 0 else local
        units.append((value, base_offset + local, base_offset + local + len(value)))
    return units


def analyze_experience_semantics(
    experience_id: str,
    text: str,
    source_offset: int = 0,
) -> InputSemanticAnalysis:
    units: list[InputSemanticUnit] = []
    for index, (raw_text, start, end) in enumerate(split_semantic_units(text, source_offset), start=1):
        role, roles, polarity, certainty, eligible = classify_semantic_unit(raw_text)
        cleaned = _strip_fact_shell(raw_text) if eligible else raw_text
        if not cleaned:
            continue
        units.append(InputSemanticUnit(
            semantic_unit_id=f"{experience_id}-U{index:03d}",
            experience_id=experience_id,
            text=cleaned,
            role=role,
            roles=roles,
            source_span=(start, end),
            polarity=polarity,
            certainty=certainty,
            resume_eligible=eligible,
        ))
    return InputSemanticAnalysis(units=units)


def write_semantic_role_log(
    analyses: list[InputSemanticAnalysis],
    *,
    stage: str,
    generation_result_id: int | None = None,
) -> None:
    try:
        counts: dict[str, int] = {}
        units = [unit for analysis in analyses for unit in analysis.units]
        for unit in units:
            for role in unit.roles:
                counts[role] = counts.get(role, 0) + 1
        entry = {
            "created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "stage": stage,
            "generation_result_id": generation_result_id,
            "semantic_role_count_by_type": counts,
            "excluded_instruction_count": counts.get(USER_INSTRUCTION, 0),
            "negative_constraint_count": counts.get(NEGATIVE_CONSTRAINT, 0),
            "uncertain_fact_count": counts.get(UNCERTAIN_FACT, 0),
            "experience_ids": sorted({unit.experience_id for unit in units}),
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        return
