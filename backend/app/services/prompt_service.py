import json
from pathlib import Path

from .. import schemas
from .experience_segmentation_service import build_experience_context
from .experience_segmentation_service import split_experience_segments
from .experience_identity_service import build_experience_identity_context
from .experience_identity_service import build_segmentation_questions
from .long_input_service import LongInputContext
from .experience_fact_ledger_service import build_fact_ledger_context
from .experience_fact_ledger_service import build_experience_fact_ledger
from .experience_identity_service import build_experience_identities
from .canonical_consumer_view_service import CanonicalConsumerViews


def build_semantic_role_context(raw_input: str, *, include_exact_fact_input: bool = False) -> str:
    identities = build_experience_identities(raw_input)
    segments = split_experience_segments(raw_input)
    ledger = build_experience_fact_ledger(raw_input)
    lines = [
        "以下是按固定 Experience Slot 整理的 Claim Resolution 结果。只能将 eligible facts 写入正式简历。",
    ]
    for index, identity in enumerate(identities):
        lines.append(f"{identity.experience_id}｜{identity.declared_experience_type or identity.experience_type}｜{identity.title}")
        if index < len(segments):
            lines.append(f"输入边界标题：{segments[index].label}｜{segments[index].title}")
        for fact in ledger.for_experience(identity.experience_id):
            lines.append(
                f"- eligible fact {fact.fact_id}｜claim {fact.claim_id}｜{fact.temporal_status}："
                f"{fact.resume_ready_text}"
            )
        excluded = [claim for claim in ledger.excluded_claims if claim.source_experience_id == identity.experience_id]
        withheld = [claim for claim in ledger.withheld_claims if claim.source_experience_id == identity.experience_id]
        for claim in excluded:
            lines.append(
                f"- internal constraint {claim.claim_id}｜{claim.polarity}｜{claim.exclusion_reason}："
                f"{claim.text}（禁止写入正文，也禁止反向改写）"
            )
        for claim in withheld:
            lines.append(
                f"- uncertain/planned claim {claim.claim_id}｜{claim.certainty}｜{claim.temporal_status}："
                f"{claim.text}（只能追问，不得确定性输出）"
            )
    if (
        include_exact_fact_input and raw_input.strip()
        and not ledger.excluded_claims and not ledger.withheld_claims
    ):
        # Preserve the exact source for ordinary fact-only short inputs. Mixed
        # instructions, constraints and uncertain statements are never copied
        # through this compatibility path.
        lines.append(f"用户原始输入（已确认仅含可生成事实）：{raw_input.strip()}")
    return "\n".join(lines)


BASE_DIR = Path(__file__).resolve().parents[3]
PROMPTS_DIR = BASE_DIR / "prompts"


def load_prompt(name: str) -> str:
    prompt_path = PROMPTS_DIR / name
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _generation_template(name: str, *, canonical: bool = False) -> str:
    parts = load_prompt(name).split("<!-- legacy-project -->")
    if len(parts) % 2 == 0:
        raise ValueError("Unpaired legacy project template block.")
    return "".join(part for index, part in enumerate(parts) if not canonical or index % 2 == 0)


def _canonical_evidence_context(request: schemas.GenerateRequest, views: CanonicalConsumerViews) -> str:
    """Serialize existing decisions once; this is not a second semantic build."""
    background = views.non_experience_context(request.raw_input)
    owners = []
    constraints = []
    for owner in views.experience_ids:
        scope = views.scope_for_owner(owner)
        header = views.planner_view.experience_header_decision_for_owner(owner)
        if scope is None or header is None:
            raise ValueError("Canonical model evidence requires frozen owner headers.")
        claims = {claim.claim_id: claim for claim in views.claims_for_owner(owner)}
        facts = []
        for fact in views.facts_for_owner(owner):
            claim = claims.get(fact.claim_id)
            if claim is None or not scope.permits_claim(claim.claim_id):
                raise ValueError("Canonical fact is missing its eligible owner-local Claim.")
            facts.append({
                "fact_id": fact.fact_id,
                "source_experience_id": owner,
                "source_claim_ids": [claim.claim_id],
                "source_span": fact.source_span,
                "eligibility": fact.eligibility,
                "importance": fact.importance,
                "temporal_status": fact.temporal_status,
                "resume_ready_text": fact.resume_ready_text,
                "source_claim_text": claim.text,
                "claim_source_span": claim.source_span,
                "related_claim_ids": claim.related_claim_ids,
            })
        fields = {
            ("name" if field.field_key == "organization" else field.field_key): field.display_text
            for field in header.fields
        }
        owners.append({
            "source_experience_id": owner,
            "experience_type": scope.canonical_experience_type,
            "project_header": {**fields, "meta": scope.canonical_experience_type},
            "header_qualification": {field.field_key: field.status for field in header.fields},
            "missing_questions": [field.missing_question for field in header.fields if not field.qualified],
            "eligible_facts": facts,
        })
        for claim in claims.values():
            if scope.permits_claim(claim.claim_id):
                continue
            constraints.append({
                "source_experience_id": owner,
                "claim_id": claim.claim_id,
                "source_span": claim.source_span,
                "text": claim.text,
                "eligibility": claim.eligibility,
                "semantic_role": claim.semantic_role,
                "polarity": claim.polarity,
                "certainty": claim.certainty,
                "temporal_status": claim.temporal_status,
                "exclusion_reason": claim.exclusion_reason,
            })
    evidence = {
        "owners": owners,
        "internal_constraints_not_resume_facts": constraints,
        "non_experience_context_not_project_facts": [
            {"source_span": span, "text": text} for span, text in background
        ],
        "segmentation_questions": views.clarification_questions,
    }
    return "<canonical_model_evidence>\n" + json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) + "\n</canonical_model_evidence>"


def build_generation_prompt(
    request: schemas.GenerateRequest,
    long_input_context: LongInputContext | None = None,
    *,
    consumer_views: CanonicalConsumerViews | None = None,
) -> str:
    if consumer_views is not None:
        # Project prose instructions exit this path; other writing rules and
        # all evidence still come from the existing templates and frozen views.
        evidence = _canonical_evidence_context(request, consumer_views)
        reference = "见同请求 canonical_model_evidence；不另建摘要。"
        is_long = bool(long_input_context and long_input_context.long_input_mode)
        template = _generation_template("generate_resume_coach_result_long.md" if is_long else "generate_resume_coach_result.md", canonical=True)
        return template.format(
            project_task="Canonical projects 仅返回事实引用，不生成正文或表头。以下写作、包装、删改和格式规则仅适用于模型生成的非 projects 字段；项目引用以 canonical_model_output_contract 为唯一协议，不按篇幅省略 Fact。",
            project_fields="projects: 数组，每项仅含 source_experience_id 和 fact_placements；不含正文、表头或 Claim 行",
            model_output_contract=_canonical_output_contract(),
            target_role=request.target_role, mode=request.mode,
            packaging_level=request.packaging_level,
            experience_type="、".join(dict.fromkeys(
                scope.canonical_experience_type for scope in consumer_views.owner_scopes.values()
            )),
            raw_input=evidence, compact_experience_context=evidence,
            experience_context=reference, experience_identity_context=reference,
            experience_fact_ledger_context=reference,
            segmentation_question_context="\n".join(
                f"- {item}" for item in consumer_views.clarification_questions
            ) or "无低置信度分段追问。",
        )
    # Independent legacy callers keep the pre-Canonical API.
    segmentation_questions = build_segmentation_questions(request.raw_input)
    segmentation_question_context = "\n".join(f"- {item}" for item in segmentation_questions) or "无低置信度分段追问。"
    if long_input_context and long_input_context.long_input_mode:
        template = _generation_template("generate_resume_coach_result_long.md")
        return template.format(
            project_task="",
            project_fields="projects: 数组，每项包含 name、meta、time、intro、role、details，并尽量包含 source_experience_id；实习可包含 position",
            model_output_contract="",
            target_role=request.target_role,
            mode=request.mode,
            packaging_level=request.packaging_level,
            experience_type=request.experience_type,
            compact_experience_context=build_semantic_role_context(request.raw_input),
            experience_identity_context=build_experience_identity_context(request.raw_input),
            experience_fact_ledger_context=build_fact_ledger_context(request.raw_input),
            segmentation_question_context=segmentation_question_context,
        )

    template = _generation_template("generate_resume_coach_result.md")
    return template.format(
        project_task="",
        project_fields="projects: 对象数组，每项包含 name、meta、time、intro、role、details，并尽量包含 source_experience_id；实习可包含 position",
        model_output_contract="",
        target_role=request.target_role,
        mode=request.mode,
        packaging_level=request.packaging_level,
        experience_type=request.experience_type,
        raw_input=build_semantic_role_context(request.raw_input, include_exact_fact_input=True),
        experience_context=build_experience_context(request.raw_input),
        experience_identity_context=build_experience_identity_context(request.raw_input),
        experience_fact_ledger_context=build_fact_ledger_context(request.raw_input),
        segmentation_question_context=segmentation_question_context,
    )


def _canonical_output_contract() -> str:
    """One destination per frozen Fact; text and order are owned by the receiver."""
    contract = {
        "applies_to": "resume_sections.projects",
        "protocol": "canonical_fact_placements_v1",
        "required_fields": {
            "source_experience_id": "当前 canonical_model_evidence 中的 owner ID",
            "fact_placements": "object；键为本 owner 的完整 Fact ID，值只能为 intro、role 或 detail，分别表示简介、职责或详情位置",
        },
        "field_references": {
            "intro": "fact_placements 中值为 intro 的 Fact",
            "role": "fact_placements 中值为 role 的 Fact",
            "details": "fact_placements 中值为 detail 的 Fact，每 Fact 一行",
        },
        "reference_format": {
            "complete_assignment": "全部 owner 提供的每个 eligible Fact 必须且只能分配一次，不按篇幅或重要性省略；每个 owner 最多一个项目",
            "empty_body": "两个字段必须存在；没有分配到 intro 或 role 的 Fact 时，由后端保留空正文，不要求填满位置",
            "multiple_facts": "不指定分组或排列顺序；后端按冻结 source_span 顺序组装，同位置沿用证据顺序；intro/role 的完整原句按既有规则连接",
            "lineage": "模型只选择 fact_id；后端取得完整 resume_ready_text、Claim lineage 和聚合来源，不要求模型抄写",
            "headers": "后端使用冻结 project_header；模型不返回 name/meta/time/position",
        },
        "backend_verification": {
            "declaration_is_not_proof": True,
            "accepted_support": "只校验引用存在性、owner、eligibility、lineage、精确分配集合与位置枚举；后端确定性组装原句后执行既有正文支持校验，位置不构成新的职责证明",
            "forbidden_fields": "项目对象只允许 required_fields 两个字段；不得返回旧引用数组、intro/role/details、Claim行、聚合ID、表头、冻结/可信标记或其他字段",
            "failure": "重复 JSON 键、缺失、伪造、跨 owner、不可用引用、非法位置及额外字段明确失败；不覆盖重复键，不忽略正文后替换原句伪造验证成功",
        },
    }
    return "<canonical_model_output_contract>\n" + json.dumps(contract, ensure_ascii=False) + "\n</canonical_model_output_contract>"
