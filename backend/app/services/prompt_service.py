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
        # Legacy templates retain their writing rules. All old data slots refer
        # to the same unabridged evidence instead of building competing summaries.
        evidence = _canonical_evidence_context(request, consumer_views)
        reference = "见同请求 canonical_model_evidence；不另建摘要。"
        is_long = bool(long_input_context and long_input_context.long_input_mode)
        template = load_prompt("generate_resume_coach_result_long.md" if is_long else "generate_resume_coach_result.md")
        return template.format(
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
        template = load_prompt("generate_resume_coach_result_long.md")
        return template.format(
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

    template = load_prompt("generate_resume_coach_result.md")
    return template.format(
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
    """Internal return format only; no new writing policy or semantic state."""
    contract = {
        "applies_to": "resume_sections.projects",
        "required_fields": {
            "source_experience_id": "当前 canonical_model_evidence 中的 owner ID",
            "name": "已提供的 project_header.name",
            "meta": "已提供的 project_header.meta",
            "time": "已提供的 project_header.time",
            "intro": "string，空正文使用空字符串",
            "role": "string，空正文使用空字符串",
            "details": "list[string]，每项为一条正文",
        },
        "field_references": {
            "intro": ["intro_source_fact_ids", "intro_source_claim_ids"],
            "role": ["role_source_fact_ids", "role_source_claim_ids"],
            "details": ["detail_fact_ids", "detail_claim_ids"],
        },
        "reference_format": {
            "intro_role": "list[string]；非空正文必须同时声明 Fact ID 和 Claim ID",
            "details": "list[list[string]]；与 details 原始索引和长度一一对应，包括空行",
            "empty_body": "允许省略该字段来源或使用空数组；不得附带孤立来源",
            "multiple_facts": "一行表达多个事实时，Fact ID 按表达顺序声明，Claim ID 为对应 lineage 集合",
            "lineage": "只引用本 owner eligible_facts 中的 fact_id 及其 source_claim_ids",
            "aggregates": "source_fact_ids/source_claim_ids 仅为项目聚合集合，不能代替任何字段来源",
            "position": "实习使用已提供的 project_header.position",
        },
        "backend_verification": {
            "declaration_is_not_proof": True,
            "accepted_support": "现有验证器仅确定验证引用 Fact 的 resume_ready_text、排版/句末标点等价形式和按声明顺序用分号或句号连接的组合",
            "unsupported": "合法 ID 不能证明任意改写；来源缺失、非法或正文无法验证会使该次返回不满足契约",
            "trust_flags": "不得声明 immutable_source_experience_id、source_binding_locked 或其他后端冻结/可信状态",
            "failure": "不确定内容不能通过省略来源、清空已有正文或整段替换来声明成功",
        },
    }
    return "<canonical_model_output_contract>\n" + json.dumps(contract, ensure_ascii=False) + "\n</canonical_model_output_contract>"
