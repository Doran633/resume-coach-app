import json
import time
from pathlib import Path
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .. import models, schemas
from .identity_service import ensure_session, get_or_create_anonymous_user
from .json_repair_service import JSONRepairError, parse_llm_json
from .llm_service import LLMServiceError, call_openai, get_llm_mode, get_openai_model
from .prompt_service import build_generation_prompt
from .result_cleanup_service import cleanup_generation_payload
from .resume_section_fallback_service import fill_resume_sections
from .fact_guard_service import guard_hard_facts
from .enhancement_guard_service import ensure_packaging_gain
from .long_input_service import LongInputContext, analyze_long_input
from .stable_generation_fallback_service import build_stable_generation_fallback
from .experience_boundary_guard_service import guard_experience_boundaries
from .uncertain_expression_cleanup_service import cleanup_uncertain_expressions
from .project_specificity_guard_service import guard_project_specificity
from .weak_profile_strategy_service import strengthen_weak_profile_payload
from .resume_body_sanitizer_service import sanitize_resume_body
from .resume_project_reconciliation_service import reconcile_resume_projects
from .resume_text_integrity_service import ensure_resume_text_integrity
from .fact_coverage_guard_service import guard_fact_coverage
from .resume_summary_quality_service import ensure_resume_summary_quality
from .resume_output_firewall_service import guard_resume_output
from .resume_language_professionalization_service import professionalize_resume_language
from .resume_section_schema_service import normalize_resume_section_schema
from .resume_section_integrity_service import ensure_resume_section_integrity
from .experience_type_resolution_service import resolve_project_types
from .resume_section_routing_service import route_resume_projects
from .resume_fact_dedup_service import deduplicate_resume_facts
from .resume_title_format_service import resolve_resume_titles
from .generation_stage_quality_service import log_generation_stage
from .resume_dedup_quality_service import ensure_dedup_quality
from .resume_typography_quality_service import ensure_typography_quality
from .resume_output_quality_gate_service import evaluate_resume_output_quality
from .resume_adaptive_narrative_service import organize_adaptive_narrative
from .resume_information_gain_service import ensure_information_gain
from .resume_template_language_guard_service import guard_template_language
from .resume_narrative_coherence_service import evaluate_narrative_quality
from .resume_semantic_unit_service import ensure_semantic_units
from .resume_fact_cluster_dedup_service import deduplicate_fact_clusters
from .resume_skill_evidence_guard_service import guard_resume_skill_evidence
from .resume_section_layering_service import layer_resume_sections
from .resume_fact_increment_service import ensure_resume_fact_increment
from .resume_skill_taxonomy_service import calibrate_resume_skill_taxonomy
from .recruiter_facing_technical_language_service import ensure_recruiter_facing_technical_language
from .resume_recruiter_readability_service import ensure_recruiter_readability
from .paired_symbol_integrity_service import ensure_paired_symbol_integrity
from .resume_whitespace_quality_service import ensure_resume_whitespace_quality
from .resume_role_resolution_service import resolve_resume_roles
from .resume_experience_entity_dedup_service import deduplicate_resume_experience_entities


LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


class GenerationServiceError(RuntimeError):
    pass


def _write_llm_log(log: dict):
    log_path = LOG_DIR / "llm_calls.jsonl"
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(log, ensure_ascii=False) + "\n")


def _write_generation_stability_log(log: dict):
    try:
        log_path = LOG_DIR / "generation_stability.jsonl"
        payload = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), **log}
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        return


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_to_text(item) for item in value if _to_text(item))
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            text = _to_text(item)
            if text:
                parts.append(f"{key}：{text}")
        return "\n".join(parts)
    return str(value)


def _to_string_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [text for item in value if (text := _to_text(item))]
    text = _to_text(value)
    return [text] if text else []


def normalize_llm_payload(data: dict) -> dict:
    normalized = dict(data)
    for key in ["normal_version", "bold_version", "boundary_version", "recommended_version"]:
        normalized[key] = _to_text(normalized.get(key))

    for key in ["confirmed_facts", "missing_questions", "interview_plan", "knowledge_checklist"]:
        normalized[key] = _to_string_list(normalized.get(key))

    claims = []
    for claim in normalized.get("claims") or []:
        if not isinstance(claim, dict):
            claim = {"claim": _to_text(claim)}
        risk_level = claim.get("risk_level", "yellow")
        if risk_level not in ["green", "yellow", "red", "black"]:
            risk_level = "yellow"
        claims.append(
            {
                "claim": _to_text(claim.get("claim")),
                "risk_level": risk_level,
                "evidence": _to_text(claim.get("evidence")),
                "risk_reason": _to_text(claim.get("risk_reason")),
                "interview_questions": _to_string_list(claim.get("interview_questions")),
                "knowledge_to_prepare": _to_string_list(claim.get("knowledge_to_prepare")),
                "downgrade_wording": _to_text(claim.get("downgrade_wording")),
            }
        )
    normalized["claims"] = claims

    sections = normalized.get("resume_sections")
    if not isinstance(sections, dict):
        sections = {}
    sections["personal_info"] = {str(k): _to_text(v) for k, v in (sections.get("personal_info") or {}).items()} if isinstance(sections.get("personal_info"), dict) else {}
    sections["summary"] = _to_string_list(sections.get("summary"))
    sections["skills"] = _to_string_list(sections.get("skills"))
    projects = []
    raw_projects = sections.get("projects") if isinstance(sections.get("projects"), list) else []
    for project in raw_projects:
        if not isinstance(project, dict):
            project = {"name": "项目经历", "intro": project}
        projects.append(
            {
                "name": _to_text(project.get("name")) or "项目经历",
                "meta": _to_text(project.get("meta")),
                "time": _to_text(project.get("time")) or "[待填写]",
                "intro": _to_text(project.get("intro")),
                "role": _to_text(project.get("role")),
                "details": _to_string_list(project.get("details")),
            }
        )
    sections["projects"] = projects
    sections["education"] = {str(k): _to_text(v) for k, v in (sections.get("education") or {}).items()} if isinstance(sections.get("education"), dict) else {}
    sections["interview_preparation"] = _to_string_list(sections.get("interview_preparation"))
    normalized["resume_sections"] = sections
    return normalized


@dataclass
class RoleProfile:
    label: str
    focus: list[str]
    terms: list[str]


ROLE_PROFILES = {
    "前端开发": RoleProfile("前端开发", ["页面交互", "组件抽象", "状态管理", "接口联调"], ["React/Vue", "TypeScript", "组件化", "工程化"]),
    "后端开发": RoleProfile("后端开发", ["接口设计", "数据模型", "权限", "日志与部署"], ["FastAPI/Spring Boot", "SQL", "鉴权", "并发"]),
    "AI Agent": RoleProfile("AI Agent", ["RAG", "Agent workflow", "工具调用", "上下文工程"], ["RAG", "LangChain-style", "LangGraph", "rerank"]),
    "大模型训练": RoleProfile("大模型训练", ["数据构造", "SFT/RLHF", "训练评估", "推理优化"], ["SFT", "RLHF/RLAIF", "DPO", "LoRA/QLoRA", "数据清洗", "评测集"]),
    "数据分析": RoleProfile("数据分析", ["数据清洗", "指标计算", "可视化", "业务结论"], ["Pandas", "SQL", "BI", "指标体系"]),
    "产品助理": RoleProfile("产品助理", ["需求梳理", "原型", "用户流程", "验收"], ["PRD", "原型设计", "用户路径", "优先级"]),
    "运营": RoleProfile("运营", ["内容生产", "活动执行", "数据复盘", "用户触达"], ["内容运营", "转化", "增长", "复盘"]),
    "测试开发": RoleProfile("测试开发", ["测试用例", "自动化", "接口测试", "缺陷定位"], ["pytest", "接口测试", "CI", "质量保障"]),
}


def _role_profile(target_role: str) -> RoleProfile:
    for key, profile in ROLE_PROFILES.items():
        if key.lower() in target_role.lower() or key in target_role:
            return profile
    return RoleProfile("泛互联网岗位", ["项目完整度", "业务流程", "协作交付", "问题排查"], ["项目 owner", "业务闭环", "数据意识", "工程化"])


def build_mock_generation(request: schemas.GenerateRequest) -> schemas.GenerationPayload:
    profile = _role_profile(request.target_role)
    raw = request.raw_input.strip()
    has_metric = any(token in raw for token in ["人", "用户", "star", "stars", "%", "上线", "日志"])
    has_ai = any(token.lower() in raw.lower() for token in ["rag", "agent", "llm", "langchain", "向量", "大模型", "sft", "rlhf", "dpo", "lora", "qlora", "微调", "训练", "标注", "评测"])
    has_owner = any(token in raw for token in ["独立", "负责", "主导", "owner"])

    completeness = 58
    if len(raw) > 80:
        completeness += 12
    if has_metric:
        completeness += 10
    if has_ai:
        completeness += 8
    if has_owner:
        completeness += 6
    completeness = min(completeness, 92)

    confirmed_facts = [
        f"目标岗位：{request.target_role}",
        f"经历类型：{request.experience_type}",
        f"包装强度：{request.packaging_level}",
        "用户提供了可包装的项目/经历素材",
    ]
    if has_metric:
        confirmed_facts.append("存在用户规模、部署、star 或其他结果锚点")
    if has_ai:
        confirmed_facts.append("存在 AI/RAG/Agent 相关技术素材")

    missing_questions = [
        "这段经历是否有可展示链接、截图、仓库、日志或文档？",
        "你亲自负责的模块和协作边界分别是什么？",
        "如果写成更强表达，你能否准备一个真实问题排查案例？",
    ]
    if has_metric:
        missing_questions.insert(0, "用户规模、在线人数或 star 的统计口径是什么？")
    if has_ai:
        missing_questions.insert(0, "AI/RAG/Agent/模型训练链路中哪些模块是已实现，哪些是规划中？")

    focus_text = "、".join(profile.focus)
    terms_text = "、".join(profile.terms)

    normal = (
        f"围绕{request.target_role}岗位要求，对该{request.experience_type}进行专业化表达："
        f"突出{focus_text}等能力，将原始经历中的任务拆解为项目背景、个人职责、技术动作和交付结果，"
        "让经历从“做过一些事情”提升为“完成过可解释的岗位相关实践”。"
    )
    bold = (
        f"作为{profile.label}方向核心参与者/项目 owner，围绕{focus_text}构建完整项目闭环，"
        f"主动引入{terms_text}等行业表达强化岗位匹配度；在简历中可突出“负责核心模块、推动从 0 到 1 落地、"
        "具备真实场景验证和问题排查能力”，但需要准备证据材料、技术链路和面试回答。"
    )
    boundary = (
        "边界参考版：将该经历描述为独立主导企业级生产系统、承担完整架构决策并取得明确商业增长。"
        "如果没有真实公司背景、生产权限、完整架构文档、可核验指标或深度技术解释，该版本容易在面试追问中暴露。"
    )

    claims = [
        schemas.ClaimResult(
            claim="负责核心模块 / 项目 owner",
            risk_level="yellow" if has_owner else "red",
            evidence="用户描述中存在独立、负责或项目完整交付信号。" if has_owner else "当前只看到项目参与描述，贡献边界仍需追问。",
            risk_reason="可以拉高为核心模块贡献，但需要能讲清模块边界、关键代码和问题排查。" if has_owner else "缺少明确个人负责范围，直接写 owner 容易被追问贡献边界。",
            interview_questions=["你负责的核心模块是什么？", "哪些部分是你亲自做的？", "遇到过什么问题，怎么定位？"],
            knowledge_to_prepare=["模块流程", "数据流", "关键接口/文件", "一次真实问题排查案例"],
            downgrade_wording="参与核心流程开发与问题排查",
        ),
        schemas.ClaimResult(
            claim="岗位行业术语与技术深度",
            risk_level="yellow",
            evidence=f"目标岗位可匹配 {terms_text} 等行业表达。",
            risk_reason="行业术语能增强岗位匹配，但面试中需要解释实现方式、取舍和未完成边界。",
            interview_questions=[f"{terms_text} 分别解决什么问题？", "哪些是已实现，哪些是下一步规划？"],
            knowledge_to_prepare=profile.terms + ["技术选型理由", "局限性与下一步迭代"],
            downgrade_wording=f"具备{profile.label}方向基础项目实践",
        ),
    ]
    if has_metric:
        claims.append(
            schemas.ClaimResult(
                claim="真实用户/指标/开源影响力",
                risk_level="yellow",
                evidence="用户输入中包含用户规模、日志、上线或 star 等结果锚点。",
                risk_reason="可以作为结果亮点使用，但必须区分累计用户、同时在线、峰值并发、star 归属和个人贡献比例。",
                interview_questions=["指标怎么统计？", "有没有截图、日志或仓库链接？", "这个结果与个人贡献如何对应？"],
                knowledge_to_prepare=["统计口径", "证据材料", "贡献拆分", "扩展方案"],
                downgrade_wording="具备真实使用记录或开源项目关注度",
            )
        )
    else:
        claims.append(
            schemas.ClaimResult(
                claim="量化成果",
                risk_level="black",
                evidence="当前没有明确指标锚点。",
                risk_reason="硬数字属于可核验事实，不能凭空添加，否则会直接破坏可信度。",
                interview_questions=["这个数字从哪里来？", "如何复现或核验？"],
                knowledge_to_prepare=["指标口径", "证据截图", "日志或数据来源"],
                downgrade_wording="使用定性结果描述，不写具体数字",
            )
        )

    interview_plan = [
        "准备 1 张项目流程图：输入、处理、输出、用户价值。",
        "准备 2-3 个关键模块说明：为什么重要、你做了什么、难点在哪里。",
        "准备 1 个问题排查故事：现象、定位过程、解决方案、复盘。",
        "准备强表达的降级口径，遇到追问时承认边界但不削弱价值。",
    ]
    knowledge_checklist = [
        *profile.terms,
        "项目架构与模块边界",
        "证据材料与指标口径",
        "面试回答 STAR 结构",
    ]

    resume_sections = schemas.ResumeSections(
        personal_info={
            "姓名": "[待填写]",
            "邮箱": "[待填写]",
            "手机号": "[待填写]",
            "求职意向": request.target_role,
        },
        summary=[
            f"面向{request.target_role}岗位，具备{request.experience_type}实践和项目包装表达能力。",
            f"能够围绕{focus_text}完成项目职责拆解、结果表达和面试承接准备。",
        ],
        skills=[
            f"{profile.label}能力：{terms_text}",
            "工程与协作：Git、文档、测试、部署、问题排查",
        ],
        projects=[
            {
                "name": "核心项目经历",
                "meta": f"{profile.label} / {terms_text}",
                "time": "[待填写]",
                "intro": raw[:260] + ("..." if len(raw) > 260 else ""),
                "role": bold,
                "details": [
                    f"{profile.focus[0]}：围绕目标岗位提炼项目核心链路，明确输入、处理和输出。",
                    f"{profile.focus[1]}：补充个人职责、技术动作和交付结果，让经历更接近岗位语言。",
                    "面试承接：为强表达准备事实锚点、技术解释和降级口径。",
                ],
            }
        ],
        education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
        interview_preparation=interview_plan,
    )

    return schemas.GenerationPayload(
        completeness_score=completeness,
        confirmed_facts=confirmed_facts,
        missing_questions=missing_questions[:6],
        normal_version=normal,
        bold_version=bold,
        boundary_version=boundary,
        recommended_version=bold if request.packaging_level in ["大胆", "极限"] else normal,
        claims=claims,
        interview_plan=interview_plan,
        knowledge_checklist=knowledge_checklist,
        resume_sections=resume_sections,
    )


def build_llm_generation(request: schemas.GenerateRequest, long_input_context: LongInputContext) -> tuple[schemas.GenerationPayload, dict]:
    prompt = build_generation_prompt(request, long_input_context)
    last_error = ""

    for attempt in range(2):
        try:
            llm_result = call_openai(prompt)
            parsed = parse_llm_json(llm_result.text)
            payload = schemas.GenerationPayload.model_validate(normalize_llm_payload(parsed))
            return payload, {
                "model": llm_result.model,
                "mode": "openai",
                "latency_ms": llm_result.latency_ms,
                "success": 1,
                "error_message": None,
                "attempt": attempt + 1,
                "prompt_type": "long" if long_input_context.long_input_mode else "normal",
            }
        except (JSONRepairError, ValueError) as exc:
            last_error = str(exc)
            prompt = (
                prompt
                + "\n\n上一次输出无法被解析为符合 schema 的 JSON。请只重新输出一个完整、合法、字段齐全的 JSON 对象。"
            )
        except LLMServiceError as exc:
            raise GenerationServiceError(str(exc)) from exc

    raise GenerationServiceError(f"LLM JSON validation failed after retry: {last_error}")


def create_generation(db: Session, request: schemas.GenerateRequest) -> schemas.GenerateResponse:
    started_at = time.perf_counter()
    long_input_context = analyze_long_input(request.raw_input, write_segmentation_log=True, stage="generation")
    user = get_or_create_anonymous_user(db, request.anonymous_user_id)
    ensure_session(db, user, request.session_id)

    experience = models.ExperienceInput(
        anonymous_user_id=user.id,
        session_id=request.session_id,
        target_role=request.target_role,
        mode=request.mode,
        packaging_level=request.packaging_level,
        experience_type=request.experience_type,
        raw_input=request.raw_input,
    )
    db.add(experience)
    db.commit()
    db.refresh(experience)

    mode = get_llm_mode()
    llm_log = {
        "model": "mock",
        "mode": mode,
        "latency_ms": 0,
        "success": 1,
        "error_message": None,
        "prompt_type": "normal",
    }
    stability_log = {
        "mode": mode,
        "model": "mock",
        "long_input_mode": long_input_context.long_input_mode,
        "raw_input_length": long_input_context.raw_input_length,
        "line_count": long_input_context.line_count,
        "segment_count": long_input_context.segment_count,
        "prompt_type": "long" if long_input_context.long_input_mode else "normal",
        "llm_success": mode == "mock",
        "json_repair_failed": False,
        "fallback_used": False,
        "latency_ms": None,
        "error_message": None,
    }

    if mode == "mock":
        payload = build_mock_generation(request)
        llm_log["model"] = "mock"
    elif mode == "openai":
        try:
            payload, llm_log = build_llm_generation(request, long_input_context)
            stability_log["model"] = llm_log.get("model")
            stability_log["llm_success"] = True
        except GenerationServiceError as exc:
            payload = build_stable_generation_fallback(request, long_input_context)
            stability_log["model"] = get_openai_model()
            stability_log["llm_success"] = False
            stability_log["json_repair_failed"] = "JSON" in str(exc) or "schema" in str(exc).lower()
            stability_log["fallback_used"] = True
            stability_log["error_message"] = str(exc)
            llm_log = {
                "model": get_openai_model(),
                "mode": "openai",
                "latency_ms": None,
                "success": 0,
                "error_message": str(exc),
                "prompt_type": "long" if long_input_context.long_input_mode else "normal",
            }
    else:
        raise GenerationServiceError(f"Unsupported LLM_MODE: {mode}. Use mock or openai.")

    log_generation_stage(payload, "after_llm")
    payload = normalize_resume_section_schema(payload)
    payload = cleanup_generation_payload(payload, source=mode)
    log_generation_stage(payload, "after_normalize")
    payload = guard_hard_facts(payload, request.raw_input)
    payload = fill_resume_sections(payload, stage="generation", raw_input=request.raw_input)
    log_generation_stage(payload, "after_fallback")
    payload = ensure_packaging_gain(payload, request.raw_input, request.target_role)
    payload = guard_experience_boundaries(payload, request.raw_input, stage="generation")
    payload = resolve_resume_roles(payload, request.raw_input, stage="generation")
    payload = cleanup_uncertain_expressions(payload, request.raw_input)
    payload = guard_project_specificity(payload, request.raw_input)
    payload = strengthen_weak_profile_payload(payload, request.raw_input, request.target_role)
    payload = sanitize_resume_body(payload, request.raw_input)
    payload = reconcile_resume_projects(payload, request.raw_input, stage="generation")
    log_generation_stage(payload, "after_reconciliation")
    payload = deduplicate_resume_facts(payload, stage="generation_pre_coverage")
    payload = resolve_project_types(payload, request.raw_input, stage="generation")
    route_resume_projects(payload.resume_sections.projects)
    log_generation_stage(payload, "after_type_resolution")
    payload = guard_fact_coverage(payload, request.raw_input, stage="generation")
    log_generation_stage(payload, "after_fact_coverage")
    payload = guard_experience_boundaries(payload, request.raw_input, stage="generation")
    narrative_changes: dict[str, int] = {}
    payload = layer_resume_sections(payload, stage="generation")
    payload = ensure_resume_fact_increment(payload, narrative_changes)
    payload = ensure_semantic_units(payload, request.raw_input, narrative_changes)
    payload = organize_adaptive_narrative(payload, narrative_changes)
    payload = ensure_information_gain(payload, narrative_changes)
    payload = deduplicate_resume_facts(payload, stage="generation")
    payload = ensure_dedup_quality(payload, stage="generation")
    payload = deduplicate_fact_clusters(
        payload, stage="generation", change_stats=narrative_changes,
    )
    payload = guard_template_language(payload, narrative_changes)
    evaluate_narrative_quality(payload, stage="generation", change_stats=narrative_changes)
    log_generation_stage(payload, "after_dedup")
    payload = ensure_resume_summary_quality(payload, request.raw_input, stage="generation")
    payload = guard_resume_output(payload, request.raw_input, stage="generation")
    payload = resolve_resume_roles(payload, request.raw_input, stage="before_save")
    payload = guard_resume_output(payload, request.raw_input, stage="before_save")
    payload = professionalize_resume_language(payload, stage="generation")
    payload = guard_resume_skill_evidence(payload, request.raw_input, stage="generation")
    payload = calibrate_resume_skill_taxonomy(payload, request.target_role, stage="generation")
    payload = ensure_recruiter_facing_technical_language(payload, stage="generation")
    payload = ensure_recruiter_readability(payload, stage="generation")
    payload = ensure_paired_symbol_integrity(payload, stage="generation")
    payload = ensure_resume_section_integrity(payload)
    payload = ensure_resume_text_integrity(payload, request.raw_input, stage="generation")
    payload = ensure_resume_whitespace_quality(payload, stage="generation")
    payload = ensure_typography_quality(payload, stage="generation")
    payload = guard_hard_facts(payload, request.raw_input)
    payload = guard_resume_output(payload, request.raw_input, stage="generation")
    payload = resolve_project_types(payload, request.raw_input, stage="before_save")
    payload = resolve_resume_titles(payload, request.raw_input)
    payload = deduplicate_resume_experience_entities(
        payload, request.raw_input, stage="before_save",
    )
    evaluate_resume_output_quality(payload, request.raw_input, stage="generation")
    log_generation_stage(payload, "before_save")

    result = models.GenerationResult(
        experience_input_id=experience.id,
        completeness_score=payload.completeness_score,
        result_json=payload.model_dump_json(),
    )
    db.add(result)
    db.commit()
    db.refresh(result)

    for claim in payload.claims:
        db.add(
            models.Claim(
                generation_result_id=result.id,
                claim=claim.claim,
                risk_level=claim.risk_level,
                evidence=claim.evidence,
                risk_reason=claim.risk_reason,
                interview_questions_json=json.dumps(claim.interview_questions, ensure_ascii=False),
                knowledge_json=json.dumps(claim.knowledge_to_prepare, ensure_ascii=False),
                downgrade_wording=claim.downgrade_wording,
            )
        )

    db.add(models.ResumeVersion(generation_result_id=result.id, version_type="normal", content_json=json.dumps({"content": payload.normal_version}, ensure_ascii=False)))
    db.add(models.ResumeVersion(generation_result_id=result.id, version_type="bold", content_json=json.dumps({"content": payload.bold_version}, ensure_ascii=False)))
    db.add(models.ResumeVersion(generation_result_id=result.id, version_type="boundary", content_json=json.dumps({"content": payload.boundary_version}, ensure_ascii=False)))
    db.add(models.ResumeVersion(generation_result_id=result.id, version_type="recommended", content_json=payload.resume_sections.model_dump_json()))
    llm_log["generation_result_id"] = result.id
    llm_log["long_input_mode"] = long_input_context.long_input_mode
    llm_log["raw_input_length"] = long_input_context.raw_input_length
    llm_log["line_count"] = long_input_context.line_count
    llm_log["segment_count"] = long_input_context.segment_count
    stability_log["generation_result_id"] = result.id
    db.add(models.LLMCallLog(**{key: llm_log.get(key) for key in ["generation_result_id", "model", "mode", "latency_ms", "success", "error_message"]}))
    db.commit()
    _write_llm_log(llm_log)
    stability_log["latency_ms"] = int((time.perf_counter() - started_at) * 1000)
    _write_generation_stability_log(stability_log)

    return schemas.GenerateResponse(
        experience_input_id=experience.id,
        generation_result_id=result.id,
        result=payload,
    )


def get_generation_payload(db: Session, generation_result_id: int) -> schemas.GenerationPayload | None:
    row = db.query(models.GenerationResult).filter_by(id=generation_result_id).first()
    if not row:
        return None
    return schemas.GenerationPayload.model_validate_json(row.result_json)
