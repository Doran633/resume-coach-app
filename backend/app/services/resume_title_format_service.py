import re

from .. import schemas
from .experience_identity_service import build_experience_identities
from .experience_fact_ledger_service import build_experience_fact_ledger
from .input_claim_resolution_service import ELIGIBLE, resolve_experience_claims


PLACEHOLDER = "[待填写]"
COMPANY_ENTITY = r"[A-Za-z0-9一-鿿·（）()]{2,40}(?:有限责任公司|有限公司|公司|企业|事务所|研究院)"
COMPANY_PATTERN = re.compile(rf"({COMPANY_ENTITY})", re.I)
CONTEXTUAL_COMPANY_PATTERNS = [
    re.compile(
        rf"(?:曾在|就职于|任职于|在|于)\s*(?P<company>{COMPANY_ENTITY})"
        r"(?=\s*(?:担任|任职|从事|参与|工作|做|实习|[^，。；;\n]{1,28}(?:岗位)?实习))",
        re.I,
    ),
]
POSITION_PATTERNS = [
    re.compile(r"(?:有限责任公司|有限公司|公司|企业|事务所|研究院)[ \t]*(?:担任[ \t]*)?([^，。；;\n]{2,32}?)(?:岗位)?实习", re.I),
    re.compile(r"担任\s*([^，。；;\n]{2,30}?)(?:实习生|实习)", re.I),
    re.compile(r"((?:AI\s*Agent|前端|后端|测试开发|测试|产品|运营|算法|数据|Java|Python)[^，。；;\n]{0,14}?)(?:岗位)?实习", re.I),
]
SPECIFIC_PROJECT_TYPES = {"个人项目", "课程项目", "团队项目", "开源项目", "科研项目"}


def _normalize_position(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" ，,、；;：:")
    text = re.sub(r"岗位$", "", text).strip()
    text = re.sub(r"实习生$", "", text).strip()
    text = re.sub(r"实习$", "", text).strip()
    text = re.sub(r"AI\s*Agent", "AI Agent", text, flags=re.I)
    text = text.replace("AI Agent开发", "AI Agent 开发")
    if text == "AI Agent":
        text = "AI Agent 开发"
    if text in {"前端", "后端"}:
        text += "开发"
    if not text or text in {"岗位", "开发岗位", "实习"}:
        return PLACEHOLDER
    return text + "实习"


def extract_internship_position(local_raw_text: str, llm_position: str = "") -> str:
    text = local_raw_text or ""
    for pattern in POSITION_PATTERNS:
        match = pattern.search(text)
        if match:
            position = _normalize_position(match.group(1))
            if position != PLACEHOLDER:
                return position
    candidate = _normalize_position(llm_position)
    if candidate != PLACEHOLDER:
        core = re.sub(r"开发|实习|岗位|\s+", "", candidate, flags=re.I)
        if core and core.lower() in re.sub(r"\s+", "", text).lower():
            return candidate
    return PLACEHOLDER


def extract_company(local_raw_text: str) -> str:
    text = str(local_raw_text or "").strip()
    for pattern in CONTEXTUAL_COMPANY_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group("company").strip()
    match = COMPANY_PATTERN.search(text)
    if not match:
        return ""
    company = match.group(1).strip()
    # A bare locative prefix without employment context is ambiguous. Do not
    # render it as part of the company entity or guess the missing company.
    if re.match(r"^(?:曾在|就职于|任职于|于)", company) or (
        company.startswith("在") and not company.startswith("在线")
    ):
        return ""
    return company


def _company_from_internship_title(title: str, position: str) -> str:
    value = re.sub(r"\s+", " ", str(title or "")).strip(" ，,、；;：:|｜")
    if not value or position == PLACEHOLDER:
        return ""
    position_core = re.sub(r"实习$", "", position).strip()
    suffixes = [position, position_core + "实习生", position_core + "岗位实习"]
    for suffix in suffixes:
        if suffix and value.lower().endswith(suffix.lower()):
            company = value[: len(value) - len(suffix)].strip(" ，,、；;：:|｜")
            if company and not re.search(r"(?:项目|经历)$", company):
                return company
    return ""


def resolve_project_display_type(local_raw_text: str, current_meta: str) -> str:
    if current_meta in SPECIFIC_PROJECT_TYPES:
        return current_meta
    text = local_raw_text or ""
    if re.search(r"课程项目|课程大作业|大作业|课设", text):
        return "课程项目"
    if re.search(r"开源项目|开源贡献|Pull Request|\bPR\b", text, re.I):
        return "开源项目"
    if re.search(r"科研项目|研究课题|论文", text):
        return "科研项目"
    if re.search(r"团队项目|小组项目|小组作业|团队核心成员", text):
        return "团队项目"
    if re.search(r"独立设计|独立开发|独立完成|个人项目|从零设计", text):
        return "个人项目"
    return "项目经历"


def resolve_resume_titles(payload: schemas.GenerationPayload, raw_input: str) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    identities = {item.experience_id: item for item in build_experience_identities(raw_input)}
    ledger = build_experience_fact_ledger(raw_input)
    for project in updated.resume_sections.projects:
        source_id = str(project.get("source_experience_id") or "")
        identity = identities.get(source_id)
        eligible_body = "\n".join(fact.fact_text for fact in ledger.for_experience(source_id))
        title_claims = (
            resolve_experience_claims(source_id, identity.title).claims
            if identity and identity.title else []
        )
        trusted_title = (
            identity.title
            if identity and identity.declared_experience_type
            and title_claims and all(claim.eligibility == ELIGIBLE for claim in title_claims)
            else ""
        )
        local = "\n".join(filter(None, [trusted_title, eligible_body]))
        meta = str(project.get("resolved_experience_type") or project.get("meta") or "项目经历")
        if meta == "实习经历":
            project["position"] = extract_internship_position(local, str(project.get("position") or ""))
            company = (
                extract_company(local)
                or extract_company(str(project.get("name") or ""))
                or _company_from_internship_title(identity.title if identity else "", project["position"])
            )
            project["name"] = company or PLACEHOLDER
            project["meta"] = "实习经历"
        elif meta == "项目经历":
            project["meta"] = resolve_project_display_type(local, str(project.get("meta") or ""))
    return updated
