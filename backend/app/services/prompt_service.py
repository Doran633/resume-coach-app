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
        # Legacy project writing instructions exit this path; other rules and
        # all evidence still come from the existing templates and frozen views.
        evidence = _canonical_evidence_context(request, consumer_views)
        reference = "见同请求 canonical_model_evidence；不另建摘要。"
        is_long = bool(long_input_context and long_input_context.long_input_mode)
        template = _generation_template("generate_resume_coach_result_long.md" if is_long else "generate_resume_coach_result.md", canonical=True)
        return template.format(
            project_task="Canonical projects 仅按 canonical_model_output_contract 为每个 Fact 安排位置并生成单 Fact 候选表达。其他写作、包装、删改规则仅适用于非 projects 字段；项目不得借包装级别扩大事实，不按篇幅省略 Fact。",
            project_fields="projects: 数组，每项仅含 source_experience_id 和 fact_placements；映射值为 position 与 text，不含表头或 Claim 行",
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
    """One bounded expression per frozen Fact; evidence is not rewritten."""
    contract = {
        "applies_to": "resume_sections.projects",
        "protocol": "canonical_fact_expressions_v1",
        "required_fields": {
            "source_experience_id": "当前 canonical_model_evidence 中的 owner ID",
            "fact_placements": "object；键为本 owner 的完整 Fact ID，值仅含 position（intro、role、detail之一）和 text（该Fact的完整非空候选正文）",
        },
        "field_references": {
            "intro": "position为intro的候选",
            "role": "position为role的候选",
            "details": "position为detail的候选，每Fact一行",
        },
        "reference_format": {
            "complete_assignment": "全部 owner 提供的每个 eligible Fact 必须且只能分配一次，不按篇幅或重要性省略；每个 owner 最多一个项目",
            "empty_body": "没有分配到 intro 或 role 的 Fact 时，由后端保留空正文，不要求填满位置",
            "multiple_facts": "不指定分组或排列顺序；后端按冻结source_span顺序连接已接受表达，不跨Fact融合",
            "lineage": "后端派生Claim及聚合来源；模型不得自报可信或语义复核结论",
            "headers": "后端使用冻结 project_header；模型不返回 name/meta/time/position",
        },
        "backend_verification": {
            "declaration_is_not_proof": True,
            "accepted_support": "原句及无损格式变化可确定验证；非原句需独立语义复核。引用合法和位置不证明正文受支持",
            "forbidden_fields": "项目对象只允许 required_fields 两个字段；不得返回旧引用数组、intro/role/details、Claim行、聚合ID、表头、冻结/可信标记或其他字段",
            "failure": "重复 JSON 键、缺失、伪造、跨 owner、不可用引用、非法位置及额外字段明确失败；不覆盖重复键，不忽略正文后替换原句伪造验证成功",
        },
        "expression_scope": [
            "以有依据的职业化表达为目标：对明显口语、冗余或不清晰的说法主动改善句式与行动对象表达，不把逐字回传作为默认做法。原文已经清楚或缺乏展开依据时允许保留，不强制每条改写或增加字数",
            "text只重述其键对应的一个Fact；完整保留实质信息、数量、工具、团队归属、职责程度、时间状态和必要限定",
            "不得借同owner其他Fact补入新行动、结果或因果；不得根据常见做法补技术、测试步骤、规模、性能、熟练程度或经历广度",
            "帮忙测试可表述为参与测试工作，不自动增加问题定位；只负责页面不升级为独立负责系统；工作目的不写成已实现成效",
            "薄履历可以保守表达；原文不足则保留原句或沿用非项目追问，不编造。面试提醒不替代事实依据",
        ],
    }
    return "<canonical_model_output_contract>\n" + json.dumps(contract, ensure_ascii=False) + "\n</canonical_model_output_contract>"


def build_expression_review_prompt(review, consumer_views) -> str:
    """Independent single-Fact assessment; no writer verdicts or replacement prose."""
    rows = {}
    for fid, row in review.pending.items():
        rows[fid] = {
            'source_experience_id': row['owner'], 'source_text': row['source'],
            'candidate_text': row['candidate'],
            'constraints': [
                {'text': c.text, 'eligibility': c.eligibility, 'polarity': c.polarity,
                 'certainty': c.certainty, 'temporal_status': c.temporal_status}
                for c in consumer_views.claims_for_owner(row['owner']) if c.eligibility != 'eligible'
            ],
        }
    return load_prompt('review_canonical_expressions.md') + '\n<expression_review>\n' + json.dumps(rows, ensure_ascii=False) + '\n</expression_review>'
