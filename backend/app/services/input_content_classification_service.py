import re
from dataclasses import dataclass, field


TARGET_PATTERNS = [
    r"(?:我)?想投(?:递)?[^，。；;]*", r"希望投递[^，。；;]*", r"目标岗位(?:是|为)?[^，。；;]*",
]
PACKAGING_PATTERNS = [
    r"希望包装(?:得)?[^，。；;]*", r"希望(?:写|改|优化)(?:得)?[^，。；;]*", r"希望更适合[^，。；;]*",
    r"想突出[^，。；;]*", r"帮我(?:优化|包装)[^，。；;]*", r"不要写(?:得|成)?[^，。；;]*",
    r"不要夸张[^，。；;]*", r"面试别[^，。；;]*露馅[^，。；;]*", r"提高岗位匹配度[^，。；;]*",
]
UNCERTAINTY_PATTERNS = [
    r"不太熟[^，。；;]*", r"不确定[^，。；;]*", r"没有(?:实习|上线|用户|获奖)[^，。；;]*",
]
TEMPLATE_PATTERNS = [r"哪些地方想重点放大", r"我想投\s*\[目标岗位\]", r"\[项目名称\]", r"\[技术栈\]"]


@dataclass
class ClassifiedContent:
    experience_facts: list[str] = field(default_factory=list)
    target_intents: list[str] = field(default_factory=list)
    packaging_instructions: list[str] = field(default_factory=list)
    uncertainty_statements: list[str] = field(default_factory=list)
    template_residues: list[str] = field(default_factory=list)
    noise: list[str] = field(default_factory=list)


def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def strip_non_fact_fragments(text: str) -> tuple[str, list[str]]:
    cleaned = str(text or "").strip()
    removed: list[str] = []
    for patterns in (TEMPLATE_PATTERNS, PACKAGING_PATTERNS, TARGET_PATTERNS, UNCERTAINTY_PATTERNS):
        for pattern in patterns:
            matches = list(re.finditer(pattern, cleaned, re.IGNORECASE))
            removed.extend(match.group(0).strip() for match in matches if match.group(0).strip())
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?:我)?匹配度", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"[，,、；;：:。 ]+$", "", cleaned)
    cleaned = re.sub(r"(?:但|并且|同时)$", "", cleaned)
    cleaned = re.sub(r"^[，,、；;：:。 ]+", "", cleaned)
    return cleaned.strip(), removed


def classify_input_content(raw_input: str) -> ClassifiedContent:
    result = ClassifiedContent()
    clauses = [part.strip() for part in re.split(r"(?<=[。！？；;])\s*|\n+", raw_input or "") if part.strip()]
    for clause in clauses:
        if _matches(clause, TEMPLATE_PATTERNS):
            result.template_residues.append(clause)
        if _matches(clause, TARGET_PATTERNS):
            result.target_intents.append(clause)
        if _matches(clause, PACKAGING_PATTERNS):
            result.packaging_instructions.append(clause)
        if _matches(clause, UNCERTAINTY_PATTERNS):
            result.uncertainty_statements.append(clause)
        fact, _ = strip_non_fact_fragments(clause)
        if len(re.sub(r"\W", "", fact)) >= 6:
            result.experience_facts.append(fact)
        elif not any((result.target_intents, result.packaging_instructions, result.uncertainty_statements, result.template_residues)):
            result.noise.append(clause)
    return result
