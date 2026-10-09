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
            '正式大胆正文只写在 expression_units：它是 resume_sections.projects 的唯一写作入口，按 expression_scope 声明完整来源，形成适合投递的自然叙述。\n'
            'bold_version 不另写一套项目：呈现同一组 expression_units 的正文；正式交付由后端从最终结构化字段映射，不用这个字符串为项目增加事实。normal_version、recommended_version 保留兼容对照，不能给主正文补动作、成果或职责。\n'
            'boundary_version：仅作明确标注的风险示例及边界说明，不能作为正式项目的事实来源，不把假设风险写成用户既有经历；未知状态以待核实风险表达，不能把课堂演示自动写成没有上线，也不能自动写成已经上线。\n'
            'claims、interview_plan、knowledge_checklist、interview_preparation：说明证据缺口、待准备知识和表达风险；知识承接和面试提醒不是新增行动或职责的授权，不从这些字段反推已具备能力。\n'
            '</canonical_expression_tasks>\n\n'
            '<canonical_writing_brief>\n'
            '正文组织：围绕目标岗位把已有行动、对象与工作意义写成可直接投递的简历。以工作内容开头，省去“我做了、我负责”等叙述开场，但保留负责对象与实际参与关系。把有共同表达目的且来源相邻、完整声明的Fact组织成自然句子；事实并列不等于因果，不为了融合而堆成长句。\n'
            '一条表达说明一项可辨认的工作：具体做了什么、用了什么、用于什么或已经得到什么结果，按证据选择即可，不要求凑齐固定结构。辅助过程可概括，关键行动、对象、技术、数量、成果、团队归属、职责范围与状态等义保留。已有清楚的句子可保留；单薄材料也应有自然的工作说明，不用空泛能力词或重复句增加篇幅。\n'
            '表头与正文：本owner的名称、时间在qualified冻结表头中明确且对应原文时，由表头承载即可，仍声明相应Fact来源；正文保留该Fact的行动、团队与限定。不要另外写一条仅重复项目名、类型和日期的开场。若名称或时间对理解行动、阶段或限定必不可少，则保留在句中；不修改表头，不以此省略其他内容。\n'
            '个人优势：summary 从已有行动证据提炼能力与用途，可消费同请求明确背景声明。选择最匹配岗位的能力重点并给出代表性行动依据，不平均罗列项目目录、学历和完整技术清单，不重复教育区的毕业时间。内容以读者能快速理解的自然短句为准，不凑固定字数。保留实际参与范围和技能程度，不借目标岗位补能力，不将多owner工作拼成同一项目的完整流程；求职意向不能写成已经任职。\n'
            '完整对照（仅示范编辑，示例来源不属于本次请求，返回ID和事实只能取当前证据）：\n'
            '来源甲：与一位同学合作制作资料登记页面。来源乙：只负责用HTML和CSS制作信息列表。来源丙：用6条样例检查空列表提示。\n'
            '正文单元引用来源甲、乙：与一位同学协作制作资料登记页面，仅承担HTML与CSS信息列表的页面实现。正文单元引用来源丙：使用6条样例检查空列表提示，核对无数据时的页面反馈。个人优势：具备列表页面实现与空状态提示检查的实践，在合作项目中承担局部页面工作。\n'
            '相近越界：将上述内容写成“独立负责完整系统、实现接口联调与自动化测试、显著提升使用效率”会新增职责、具体行动或成果。只有来源甲的单元也不能写入来源乙的职责。\n'
            '用途对照：来源为“按日期整理记录，供同学查找”时，可写“按日期组织记录，便于同学按时间查找”；不能写“设计检索算法，将查找效率提升40%”。说明已有用途不等于证明新机制或量化收益。\n'
            '交付自查：正文能否迅速说明工作重点，个人优势能否说明能力依据；消除同义堆砌与无依据的强词，核对每个单元的全部来源和整体关键事实覆盖。这里是写作质量目标，非线上拒绝条件；不以字数、改写率或接近原句判定事实支持，也不要求把每句话都改写。\n'
            '</canonical_writing_brief>\n\n' + text
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
        '以冻结Fact为依据充分改善职业化表达：允许口语书面化、句式重组、同owner已声明事实的组织和有依据的编辑性展开；不以接近原句、逐Fact单独成句、增加字数或固定替换词衡量质量。',
        '每个eligible Fact仍须显式引用并在同owner关联单元的整体中得到有意义的表达。单元只需表达其实际承担的部分，不能因引用整条Fact就重复照抄全部内容。整体须保留关键行动、对象、数量、工具、成果、团队归属、职责范围、完成状态及必要限定；引用次数和合法ID不是完整覆盖的证明。',
        '编辑性展开可以说明现有工作用途、组织和一般能力表现；复核应聚焦重大冲突而非词语差异。不得把常见做法写成已完成的具体行动，不得新增精确数字、技术、客户、上线、奖项、证书、职位或未经支持的成果；用途和意图不能升级为已实现成效。',
        '一个单元仅使用显式声明的同owner、冻结来源顺序相邻的Fact；相邻不证明可融合。不能借未声明Fact或其他owner的内容补动作、结果或职责，也不能把并列工作写成未经支持的因果。结构标题和背景只帮助理解，不授权新增事实。',
        '独立否定或不确定内容可以不进入正文，但仍约束相反说法；肯定Fact中的辅助性质、仅负责、本地演示等必要限定必须等义保留。指令和结构标题不是待包装事实。',
        '稀疏经历允许自然说明，但不强制扩写。职责按实际参与关系、负责对象和范围判断，不以单个修饰词是否出现判定升级；辅助性质、局部负责可等义表达，不能变成独立主导、扩大责任或熟练程度。只有编辑性疑问且确认实质信息未变时可观察，无法确定是否涉及重大事实变化时仍返回uncertain。面试提醒不能替代正文的事实依据。',
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
            project_task="Canonical projects 按 canonical_model_output_contract 显式引用所有 eligible Fact，并在同owner来源内组织有依据的职业化表达；复合Fact可分条表达，关联单元整体须覆盖关键事实和限定，每条不得越界。跨字段复用须逐处声明并独立复核。允许单Fact，不强制融合或按篇幅省略Fact；其他写作规则不另授项目删改权限。",
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
    """Explicit source units with bounded editorial expression."""
    contract = {
        "applies_to": "resume_sections.projects",
        "protocol": "canonical_fact_compositions_v2",
        "required_fields": {
            "source_experience_id": "当前 canonical_model_evidence 中的 owner ID",
            "expression_units": "数组；每项仅含fact_ids（本owner相邻且按冻结来源顺序排列的非空Fact ID数组）、position（intro、role、detail之一）、text（这些来源支持的非空候选正文）",
        },
        "field_references": {
            "intro": "position为intro的候选",
            "role": "position为role的候选",
            "details": "position为detail的候选，每表达单元一行",
        },
        "reference_format": {
            "complete_assignment": "全部 owner 提供的每个 eligible Fact 必须声明；同owner关联单元整体须有意义地表达其关键行动、对象、数量、成果、归属和限定，辅助过程可概括；每个 owner 最多一个项目",
            "empty_body": "没有分配到 intro 或 role 的 Fact 时，由后端保留空正文，不要求填满位置",
            "multiple_facts": "每个单元内Fact ID唯一；同owner来源可在不同最终字段或详情行复用，每次显式声明来源并独立验证；同一intro或role内部多个单元不得重叠。单元内Fact按冻结来源顺序相邻且语义兼容。后端按冻结source_span顺序排列单元；不补未经支持的因果或成果",
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
    coverage = {}
    facts_by_owner = {
        owner: {fact.fact_id: fact for fact in consumer_views.facts_for_owner(owner)}
        for owner in consumer_views.experience_ids
    }
    for fact_id, unit_ids in review.coverage_units().items():
        owner = review.candidates[unit_ids[0]]['owner']
        fact = facts_by_owner[owner][fact_id]
        coverage[fact_id] = {
            'source_experience_id': owner, 'source_text': fact.resume_ready_text,
            'source_span': fact.source_span, 'unit_ids': unit_ids,
            'delivered_header_evidence': review.header_coverage.get(fact_id, []),
            'units': [{'unit_id': key, 'position': review.candidates[key]['position'],
                       'candidate_text': review.candidates[key]['candidate']}
                      for key in unit_ids],
        }
    return (load_prompt('review_canonical_expressions.md')
            + '\n<expression_scope>\n' + json.dumps(_expression_scope(), ensure_ascii=False) + '\n</expression_scope>'
            + '\n<expression_review>\n' + json.dumps(rows, ensure_ascii=False) + '\n</expression_review>'
            + '\n<fact_coverage>\n' + json.dumps(coverage, ensure_ascii=False) + '\n</fact_coverage>')
