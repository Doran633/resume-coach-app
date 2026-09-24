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
from .input_semantic_role_service import STRUCTURE_MARKER


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
    text = load_prompt(name)
    for marker in ("<!-- legacy-expression -->", "<!-- legacy-project -->"):
        parts = text.split(marker)
        if len(parts) % 2 == 0:
            raise ValueError(f"Unpaired template block: {marker}")
        text = "".join(part for index, part in enumerate(parts) if not canonical or index % 2 == 0)
    version_fields = (
        '- normal_version: 非空字符串，已有事实的清晰表达\n'
        '- bold_version: 非空字符串，突出有证据的岗位相关工作\n'
        '- boundary_version: 非空字符串，明确标注的风险示例与边界说明\n'
        '- recommended_version: 非空字符串，事实边界内的投递表达'
    ) if canonical else ''
    if canonical and name == 'generate_resume_coach_result_long.md':
        version_fields = (
            'JSON 顶层字段必须完整包含：\n'
            '- completeness_score: 0-100 的整数\n'
            '- confirmed_facts: 字符串数组\n'
            '- missing_questions: 字符串数组\n' + version_fields + '\n'
            '- claims: Claim 风险数组\n'
            '- interview_plan: 面试承接计划数组\n'
            '- knowledge_checklist: 知识补齐清单数组\n'
            '- resume_sections: 正式简历结构'
        )
    text = text.replace('{canonical_version_fields}', version_fields)
    if canonical:
        text = (
            '<canonical_expression_tasks>\n'
            'normal_version、bold_version、boundary_version、recommended_version 是四个必需的顶层字符串字段，均须提供各自用途的内容。\n'
            'resume_sections.projects：按 canonical_model_output_contract 的 expression_scope 写作，表达单元声明完整来源，不借其他字段扩充事实。\n'
            'normal_version：清晰完整地表达已有经历；bold_version：突出有证据的岗位相关工作；recommended_version：提供适合投递的表达。三者可以调整句式和组织重点，不能提高职责等级或补写具体工作；不以字数、相似度或必须改写评价成功。\n'
            '各可投递字段保留辅助性质、团队归属、状态和必要限定。口语可以书面化，履历单薄不要求扩写；目的不写成已实现成效。\n'
            'boundary_version：仅作明确标注的风险示例及边界说明，不能作为正式项目的事实来源，不把假设风险写成用户既有经历。\n'
            'claims、interview_plan、knowledge_checklist、interview_preparation：说明证据缺口、待准备知识和表达风险；知识承接和面试提醒不是新增行动或职责的授权，不从这些字段反推已具备能力。\n'
            '</canonical_expression_tasks>\n\n' + text
        )
    return text


def _canonical_evidence_context(request: schemas.GenerateRequest, views: CanonicalConsumerViews) -> str:
    """Serialize existing decisions once; this is not a second semantic build."""
    background = views.non_experience_context(request.raw_input)
    owners = []
    constraints = []
    structures = []
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
        local_constraints, local_structures = _owner_expression_claims(views, owner)
        constraints.extend(local_constraints)
        structures.extend(local_structures)
    evidence = {
        "owners": owners,
        "internal_constraints_not_resume_facts": constraints,
        "structural_context_not_resume_facts": structures,
        "non_experience_context_not_project_facts": [
            {"source_span": span, "text": text} for span, text in background
        ],
        "segmentation_questions": views.clarification_questions,
    }
    return "<canonical_model_evidence>\n" + json.dumps(evidence, ensure_ascii=False, separators=(",", ":")) + "\n</canonical_model_evidence>"


def _owner_expression_claims(views, owner):
    """Expose frozen roles, never classify text or change Claim eligibility."""
    constraints, structures = [], []
    for claim in views.claims_for_owner(owner):
        if claim.eligibility == 'eligible':
            continue
        row = {
            'source_experience_id': owner, 'claim_id': claim.claim_id,
            'source_span': claim.source_span, 'text': claim.text,
            'eligibility': claim.eligibility, 'semantic_role': claim.semantic_role,
            'polarity': claim.polarity, 'certainty': claim.certainty,
            'temporal_status': claim.temporal_status, 'exclusion_reason': claim.exclusion_reason,
        }
        (structures if claim.semantic_role == STRUCTURE_MARKER else constraints).append(row)
    return constraints, structures


def _expression_scope():
    return [
        '在事实边界内充分改善职业化表达：允许口语书面化、句式重组、明确行动对象和有依据的说明性展开，不以接近原句、增加字数或固定替换词作为标准。原文清楚或没有展开依据时允许保留。',
        '当前表达单元显式引用的全部Fact的resume_ready_text是唯一可重述的事实；保留全部实质信息、数量、工具、团队归属、职责程度、状态和必要限定。原文字词可变，限定的含义不能变；限定换一种自然表达不等于限定消失。',
        '说明性展开可以讲清已有行动及其对象，不能新增具体工作、技术步骤、规模、成效、责任等级、熟练程度或经历广度。用途和意图不能升级为已实现效果；行业常见做法不能作为事实。',
        '仅允许同owner冻结来源顺序相邻的完整Fact组成一个表达单元；相邻不证明语义可融合，行动主体、对象、职责和时间状态须兼容。并列工作不能编成未经支持的因果或成果。owner背景、结构标题和同Claim上下文仅用于理解，不得搬入未引用Fact的行动或结果，不跨owner借用。',
        '独立否定或不确定内容可以不作为正文展示，但仍约束表达；含限定的肯定Fact和项目状态必须完整保留，不按限制词隐藏。指令、结构标题和排除内容不是待包装事实。',
        '单薄履历不强制扩写；包装级别、软事实和面试提醒均不能授权编造。无法核实的扩展不能靠合法ID或词语相似获得支持。',
        '职责按行动、对象范围、自主程度、责任归属、团队关系及完成状态分别核对。一般职责措辞不自动等于主导，但不得抹去协助或仅负责的范围；稀疏描述无法证明更强责任时保留原范围，复核不能确定时返回uncertain。',
    ]


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
            project_task="Canonical projects 仅按 canonical_model_output_contract 使用显式完整来源的表达单元覆盖全部 Fact；同owner来源可在不同最终字段或详情行有界复用，每次均完整表达并独立验证。允许单Fact，不强制融合。其他写作、包装、删改规则仅适用于非 projects 字段；项目不得借包装级别扩大事实，不按篇幅省略 Fact。",
            project_fields="projects: 数组，每项仅含 source_experience_id 和 expression_units；单元仅含 fact_ids、position、text，不含表头或 Claim 行",
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
    """Explicit complete source units; frozen evidence is not rewritten."""
    contract = {
        "applies_to": "resume_sections.projects",
        "protocol": "canonical_fact_compositions_v2",
        "required_fields": {
            "source_experience_id": "当前 canonical_model_evidence 中的 owner ID",
            "expression_units": "数组；每项仅含fact_ids（本owner相邻且按冻结来源顺序排列的非空完整Fact ID数组）、position（intro、role、detail之一）、text（全部引用Fact共同支持的非空候选正文）",
        },
        "field_references": {
            "intro": "position为intro的候选",
            "role": "position为role的候选",
            "details": "position为detail的候选，每表达单元一行",
        },
        "reference_format": {
            "complete_assignment": "全部 owner 提供的每个 eligible Fact 必须至少完整表达一次，不按篇幅或重要性省略；每个 owner 最多一个项目",
            "empty_body": "没有分配到 intro 或 role 的 Fact 时，由后端保留空正文，不要求填满位置",
            "multiple_facts": "每个单元内Fact ID唯一且每项完整；同owner来源可在不同最终字段或详情行复用，每次显式声明完整来源并独立验证；同一intro或role内部多个单元不得重叠。单元内Fact按冻结来源顺序相邻且语义兼容。后端按冻结source_span顺序排列单元；不补连接性结论",
            "lineage": "后端派生Claim及聚合来源；模型不得自报可信或语义复核结论",
            "headers": "后端使用冻结 project_header；模型不返回 name/meta/time/position",
        },
        "backend_verification": {
            "declaration_is_not_proof": True,
            "accepted_support": "原句及无损格式变化可确定验证；非原句需独立语义复核。引用合法和位置不证明正文受支持",
            "forbidden_fields": "项目对象只允许 required_fields 两个字段；不得返回旧引用数组、intro/role/details、Claim行、聚合ID、表头、冻结/可信标记或其他字段",
            "failure": "重复 JSON 键、缺失、伪造、跨 owner、不可用引用、非法位置及额外字段明确失败；不覆盖重复键，不忽略正文后替换原句伪造验证成功",
        },
        "expression_scope": _expression_scope(),
    }
    return "<canonical_model_output_contract>\n" + json.dumps(contract, ensure_ascii=False) + "\n</canonical_model_output_contract>"


def build_expression_review_prompt(review, consumer_views) -> str:
    """Independent assessment of the entire cited unit, not its owner's fact pool."""
    rows = {}
    for fid, row in review.pending.items():
        facts = {f.fact_id: f for f in consumer_views.facts_for_owner(row['owner'])}
        selected = [facts[source_id] for source_id in row['sources']]
        claims = {c.claim_id: c for c in consumer_views.claims_for_owner(row['owner'])}
        constraints, structures = _owner_expression_claims(consumer_views, row['owner'])
        header = consumer_views.planner_view.experience_header_decision_for_owner(row['owner'])
        rows[fid] = {
            'source_experience_id': row['owner'],
            'sources': [{'fact_id': fact.fact_id, 'source_text': fact.resume_ready_text,
                         'source_span': fact.source_span, 'source_claim_id': fact.claim_id} for fact in selected],
            'candidate_text': row['candidate'],
            'constraints': constraints,
            'owner_context': {
                'source_experience_id': row['owner'],
                'experience_type': consumer_views.scope_for_owner(row['owner']).canonical_experience_type,
                'project_header': {f.field_key: f.display_text for f in header.fields},
                'structural_context_not_resume_facts': structures,
            },
            'claim_context_not_additional_fact_support': [
                {'claim_id': cid, 'text': claims[cid].text, 'source_span': claims[cid].source_span}
                for cid in dict.fromkeys(f.claim_id for f in selected)
            ],
        }
    return (load_prompt('review_canonical_expressions.md')
            + '\n<expression_scope>\n' + json.dumps(_expression_scope(), ensure_ascii=False) + '\n</expression_scope>'
            + '\n<expression_review>\n' + json.dumps(rows, ensure_ascii=False) + '\n</expression_review>')
