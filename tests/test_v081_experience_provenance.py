import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.experience_fact_ledger_service import build_experience_fact_ledger  # noqa: E402
from app.services.experience_identity_service import build_experience_identities  # noqa: E402
from app.services.experience_slot_service import bind_projects_to_experience_slots  # noqa: E402
from app.services.experience_type_resolution_service import build_type_resolutions  # noqa: E402
from app.services.input_semantic_role_service import (  # noqa: E402
    NEGATIVE_CONSTRAINT,
    RESUME_FACT,
    TARGET_ROLE_CONTEXT,
    UNCERTAIN_FACT,
    USER_INSTRUCTION,
    analyze_experience_semantics,
)
from app.services.resume_delivery_quality_gate_service import (  # noqa: E402
    ensure_resume_delivery_quality,
    evaluate_delivery_quality_issues,
)
from app.services.resume_experience_entity_dedup_service import (  # noqa: E402
    deduplicate_resume_experience_entities,
)
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402


RAW = """项目一：论文阅读助手
独立开发论文阅读助手，使用 Python 完成论文解析、检索和问答。
两个项目技术很像，但不是一个项目，指标不要串。
没有负责架构设计，也没有独立上线。
框架好像是 Flask，也有可能是 FastAPI，我记不太清。

项目二：智能客服系统
开发智能客服系统，使用 RAG 建立 120 条测试集，将回答相关度提升至 81%。
请不要为了让简历更丰富给其他经历编技术内容。

校园经历：迎新志愿活动
负责新生签到、路线引导和现场秩序维护。
我想投后端开发岗位。"""


def payload(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=85,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=["具备项目开发与问题分析能力。"], skills=[], projects=projects,
        ),
    )


def test_explicit_project_boundaries_override_paper_keyword():
    identities = build_experience_identities(RAW)
    assert len(identities) == 3
    assert identities[0].title == "论文阅读助手"
    assert identities[0].declared_experience_type == "项目经历"
    assert identities[0].boundary_source == "explicit_heading"
    assert build_type_resolutions(RAW)["EXP-001"].resolved_type == "项目经历"


def test_semantic_roles_separate_facts_instructions_constraints_and_uncertainty():
    identity = build_experience_identities(RAW)[0]
    analysis = analyze_experience_semantics(identity.experience_id, identity.raw_text, identity.source_span[0])
    roles = {role for unit in analysis.units for role in unit.roles}
    assert RESUME_FACT in roles
    assert USER_INSTRUCTION in roles
    assert NEGATIVE_CONSTRAINT in roles
    assert UNCERTAIN_FACT in roles
    third = build_experience_identities(RAW)[2]
    third_roles = {
        role
        for unit in analyze_experience_semantics(third.experience_id, third.raw_text, third.source_span[0]).units
        for role in unit.roles
    }
    assert TARGET_ROLE_CONTEXT in third_roles


def test_fact_ledger_contains_only_resume_eligible_facts():
    ledger = build_experience_fact_ledger(RAW)
    body = "\n".join(fact.fact_text for fact in ledger.facts)
    assert "论文解析" in body and "120 条测试集" in body and "新生签到" in body
    for forbidden in ["指标不要串", "不要为了", "没有负责架构设计", "记不太清", "我想投"]:
        assert forbidden not in body
    assert ledger.constraints and ledger.uncertain_facts and ledger.excluded_units
    assert all(fact.immutable_experience_id == fact.experience_id for fact in ledger.facts)


def test_wrong_llm_ids_are_corrected_by_title_and_local_fact_evidence():
    dirty = payload([
        {
            "name": "智能客服系统", "meta": "项目经历", "time": "[待填写]",
            "intro": "开发智能客服系统。", "role": "负责客服问答功能。",
            "details": ["使用 RAG 建立 120 条测试集，将回答相关度提升至 81%。"],
            "source_experience_id": "EXP-003",
        },
        {
            "name": "迎新志愿活动", "meta": "校园 / 社团经历", "time": "[待填写]",
            "intro": "参与迎新志愿活动。", "role": "负责现场执行。",
            "details": ["负责新生签到、路线引导和现场秩序维护。"],
            "source_experience_id": "EXP-002",
        },
    ])
    bound = bind_projects_to_experience_slots(dirty, RAW, write_log=False)
    by_name = {project["name"]: project for project in bound.resume_sections.projects}
    assert by_name["智能客服系统"]["source_experience_id"] == "EXP-002"
    assert by_name["迎新志愿活动"]["source_experience_id"] == "EXP-003"
    assert all(project["source_binding_locked"] for project in by_name.values())


def test_fallback_uses_only_local_resume_facts():
    empty = payload([])
    filled = fill_resume_sections(empty, raw_input=RAW, write_log=False)
    by_id = {project["source_experience_id"]: project for project in filled.resume_sections.projects}
    paper = json.dumps(by_id["EXP-001"], ensure_ascii=False)
    customer = json.dumps(by_id["EXP-002"], ensure_ascii=False)
    volunteer = json.dumps(by_id["EXP-003"], ensure_ascii=False)
    assert "论文解析" in paper and "120 条测试集" not in paper and "新生签到" not in paper
    assert "120 条测试集" in customer and "新生签到" not in customer
    assert "新生签到" in volunteer and "RAG" not in volunteer and "81%" not in volunteer
    for forbidden in ["指标不要串", "不要为了", "没有独立上线", "记不太清", "我想投"]:
        assert forbidden not in paper + customer + volunteer


def test_inferred_same_source_id_does_not_merge_distinct_projects():
    dirty = payload([
        {
            "name": "智能客服系统", "meta": "项目经历", "time": "[待填写]",
            "intro": "开发智能客服系统。", "role": "负责客服问答功能。",
            "details": ["使用 RAG 建立测试集。"], "source_experience_id": "EXP-002",
            "source_binding_origin": "inferred", "source_binding_locked": False,
        },
        {
            "name": "迎新志愿活动", "meta": "校园 / 社团经历", "time": "[待填写]",
            "intro": "参与迎新志愿活动。", "role": "负责现场执行。",
            "details": ["负责新生签到和路线引导。"], "source_experience_id": "EXP-002",
            "source_binding_origin": "inferred", "source_binding_locked": False,
        },
    ])
    result = deduplicate_resume_experience_entities(dirty, RAW, write_log=False)
    assert len(result.resume_sections.projects) == 2


def test_delivery_gate_removes_instruction_negative_and_uncertain_assertions():
    dirty = payload([
        {
            "name": "论文阅读助手", "meta": "项目经历", "time": "[待填写]",
            "intro": "独立开发论文阅读助手。", "role": "负责架构设计。",
            "details": [
                "使用 Flask 完成后端开发。",
                "两个项目技术很像，但不是一个项目，指标不要串。",
                "使用 Python 完成论文解析、检索和问答。",
            ],
            "source_experience_id": "EXP-001",
            "immutable_source_experience_id": "EXP-001",
            "source_binding_locked": True,
        },
    ])
    result = ensure_resume_delivery_quality(dirty, RAW, write_log=False)
    visible = json.dumps(result.resume_sections.model_dump(), ensure_ascii=False)
    assert "指标不要串" not in visible
    assert "负责架构设计" not in visible
    assert "使用 Flask" not in visible and "FastAPI" not in visible
    assert "使用 Python 完成论文解析" in visible


def test_metamorphic_append_keeps_existing_fact_ownership():
    first_two = RAW.split("\n\n校园经历", 1)[0]
    base = build_experience_fact_ledger(first_two)
    expanded = build_experience_fact_ledger(RAW)
    base_map = {
        fact.fact_text: fact.experience_id
        for fact in base.facts
    }
    expanded_map = {
        fact.fact_text: fact.experience_id
        for fact in expanded.facts
        if fact.fact_text in base_map
    }
    assert expanded_map == base_map


def test_metamorphic_reorder_keeps_facts_with_titles_not_array_position():
    blocks = RAW.split("\n\n")
    reordered = "\n\n".join([blocks[1], blocks[0], blocks[2]])
    identities = build_experience_identities(reordered)
    facts = build_experience_fact_ledger(reordered)
    owner_by_title = {
        identity.title: "\n".join(fact.fact_text for fact in facts.for_experience(identity.experience_id))
        for identity in identities
    }
    assert "120 条测试集" in owner_by_title["智能客服系统"]
    assert "论文解析" in owner_by_title["论文阅读助手"]
    assert "新生签到" in owner_by_title["迎新志愿活动"]


def test_clean_result_has_no_new_v081_critical_issue_codes():
    filled = fill_resume_sections(payload([]), raw_input=RAW, write_log=False)
    result = ensure_resume_delivery_quality(filled, RAW, write_log=False)
    codes = {
        issue.issue_code for issue in evaluate_delivery_quality_issues(result, RAW)
        if issue.severity == "critical"
    }
    assert not codes.intersection({
        "EXPLICIT_BOUNDARY_LOST", "INSTRUCTION_LEAK", "NEGATIVE_CONSTRAINT_LEAK",
        "UNCERTAIN_FACT_ASSERTED", "PROVENANCE_CONFLICT", "INFERRED_ID_COLLISION",
    })
