import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.experience_fact_ledger_service import build_experience_fact_ledger  # noqa: E402
from app.services.experience_type_resolution_service import build_type_resolutions  # noqa: E402
from app.services.input_claim_resolution_service import (  # noqa: E402
    CONFIRMED,
    CURRENT,
    DENIED,
    ELIGIBLE,
    EXCLUDED,
    HISTORICAL,
    PLANNED,
    UNCERTAIN,
    WITHHELD,
    resolve_experience_claims,
)
from app.services.resume_delivery_quality_gate_service import (  # noqa: E402
    ensure_resume_delivery_quality,
    evaluate_delivery_quality_issues,
)
from app.services.resume_project_reconciliation_service import reconcile_resume_projects  # noqa: E402
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence  # noqa: E402
from scripts.evaluate_golden_resume import evaluate_payload, load_case, process_fixed_payload  # noqa: E402


def payload(projects: list[dict], *, skills: list[str] | None = None) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=["具备基于事实推进项目实现与验证的实践能力。"],
            skills=skills or [], projects=projects,
        ),
    )


def test_mixed_negative_and_positive_claims_keep_only_confirmed_fact():
    result = resolve_experience_claims("EXP-001", "没有负责架构设计，只参与了接口测试和部署验证。")
    assert [(claim.polarity, claim.eligibility) for claim in result.claims] == [
        ("negative", EXCLUDED), ("positive", ELIGIBLE),
    ]
    assert result.claims[0].certainty == DENIED
    assert "接口测试" in result.eligible_claims[0].text


def test_uncertain_framework_alternatives_are_withheld():
    result = resolve_experience_claims(
        "EXP-001", "框架好像是 Flask，也有可能是 FastAPI，我记不太清。",
    )
    candidates = [claim for claim in result.claims if "Flask" in claim.text or "FastAPI" in claim.text]
    assert len(candidates) == 2
    assert all(claim.certainty == UNCERTAIN and claim.eligibility == WITHHELD for claim in candidates)
    assert not result.eligible_claims


def test_historical_to_current_migration_is_not_a_conflict():
    result = resolve_experience_claims("EXP-001", "早期使用 Flask，后续迁移到 FastAPI。")
    assert [claim.temporal_status for claim in result.eligible_claims] == [HISTORICAL, CURRENT]
    assert all(claim.certainty == CONFIRMED for claim in result.eligible_claims)
    assert result.unresolved_conflict_count == 0
    assert result.claims[1].claim_id in result.claims[0].related_claim_ids


def test_negative_online_claim_does_not_remove_local_test_fact():
    ledger = build_experience_fact_ledger("项目经历：演示系统\n没有上线，但完成本地部署测试。")
    body = "\n".join(fact.fact_text for fact in ledger.facts)
    assert "本地部署测试" in body
    assert "没有上线" not in body
    assert any(claim.certainty == DENIED for claim in ledger.excluded_claims)


def test_planned_docker_is_not_a_fact_or_skill():
    raw = "项目经历：接口服务\n使用 Python 完成接口开发，计划增加 Docker。"
    ledger = build_experience_fact_ledger(raw)
    assert "Docker" not in "\n".join(fact.fact_text for fact in ledger.facts)
    assert any(claim.temporal_status == PLANNED for claim in ledger.withheld_claims)
    assert "Docker" not in {item.term for item in aggregate_skill_evidence(raw)}


def test_target_role_skill_is_not_skill_evidence():
    raw = "我想投 Python 后端岗位。\n项目经历：静态页面\n使用 HTML 完成页面。"
    assert "Python" not in {item.term for item in aggregate_skill_evidence(raw)}


def test_not_internship_but_course_project_resolves_to_project():
    raw = "项目经历：课程推荐系统\n不是实习，是课程项目。使用 Python 完成功能开发。"
    resolution = build_type_resolutions(raw)["EXP-001"]
    assert resolution.resolved_type == "项目经历"
    ledger = build_experience_fact_ledger(raw)
    assert "课程项目" not in "\n".join(fact.fact_text for fact in ledger.facts)
    assert any(claim.semantic_role == "STRUCTURE_MARKER" for claim in ledger.excluded_claims)


def test_ownership_instruction_is_not_fact_ledger_content():
    raw = "项目一：系统 A\n使用 Python 完成功能。A 和 B 技术相似，但指标不要串。"
    body = "\n".join(fact.fact_text for fact in build_experience_fact_ledger(raw).facts)
    assert "技术相似" not in body and "指标不要串" not in body


def test_fact_ids_retain_claim_owner_and_claim_id():
    ledger = build_experience_fact_ledger("项目经历：接口测试工具\n参与接口测试和部署验证。")
    assert ledger.facts
    assert all(fact.claim_id.startswith("EXP-001-C") for fact in ledger.facts)
    assert all(fact.immutable_experience_id == fact.experience_id == "EXP-001" for fact in ledger.facts)
    assert all(fact.eligibility == ELIGIBLE for fact in ledger.facts)


def test_fallback_does_not_restore_withheld_or_denied_claims():
    raw = "项目经历：接口服务\n参与接口测试。没有独立上线。框架可能是 FastAPI。计划增加 Docker。"
    result = fill_resume_sections(payload([]), raw_input=raw, write_log=False)
    visible = json.dumps(result.resume_sections.model_dump(), ensure_ascii=False)
    assert "接口测试" in visible
    assert "独立上线" not in visible and "FastAPI" not in visible and "Docker" not in visible


def test_reconciliation_does_not_change_claim_owner():
    raw = "项目一：系统 A\n使用 Python 完成接口。\n\n项目二：系统 B\n使用 React 完成页面。"
    dirty = payload([{
        "name": "系统 A", "meta": "项目经历", "time": "[待填写]",
        "intro": "开发系统 A。", "role": "负责接口实现。",
        "details": ["使用 Python 完成接口。"],
        "source_experience_id": "EXP-001", "immutable_source_experience_id": "EXP-001",
        "source_fact_ids": ["EXP-001-F001"], "source_binding_locked": True,
    }])
    result = reconcile_resume_projects(dirty, raw, write_log=False)
    project = result.resume_sections.projects[0]
    assert project["source_experience_id"] == "EXP-001"
    assert all(str(fact_id).startswith("EXP-001-") for fact_id in project.get("source_fact_ids", []))


def test_delivery_gate_removes_denied_uncertain_and_planned_assertions():
    raw = "项目经历：接口服务\n参与接口测试。没有上线。框架可能是 FastAPI。计划增加 Docker。"
    dirty = payload([{
        "name": "接口服务", "meta": "项目经历", "time": "[待填写]",
        "intro": "开发接口服务。", "role": "参与接口测试。",
        "details": ["完成公网上线。", "使用 FastAPI 开发接口。", "使用 Docker 完成部署。"],
        "source_experience_id": "EXP-001", "immutable_source_experience_id": "EXP-001",
        "source_binding_locked": True,
    }], skills=["后端技术：FastAPI、Docker"])
    result = ensure_resume_delivery_quality(dirty, raw, write_log=False)
    visible = json.dumps(result.resume_sections.model_dump(), ensure_ascii=False)
    assert "公网上线" not in visible and "FastAPI" not in visible and "Docker" not in visible
    assert "接口测试" in visible


def test_delivery_gate_is_idempotent_for_claim_cleanup():
    raw = "项目经历：接口服务\n参与接口测试。计划增加 Docker。"
    dirty = payload([{
        "name": "接口服务", "meta": "项目经历", "time": "[待填写]",
        "intro": "开发接口服务。", "role": "参与接口测试。",
        "details": ["使用 Docker 完成部署。"], "source_experience_id": "EXP-001",
    }])
    once = ensure_resume_delivery_quality(dirty, raw, write_log=False)
    twice = ensure_resume_delivery_quality(once, raw, write_log=False)
    assert once.model_dump() == twice.model_dump()


def test_withheld_claims_are_not_counted_as_fact_coverage_targets():
    raw = "项目经历：接口服务\n参与接口测试。可能使用 FastAPI。计划增加 Docker。"
    ledger = build_experience_fact_ledger(raw)
    assert len(ledger.facts) == 1
    assert len(ledger.withheld_claims) == 2
    result = fill_resume_sections(payload([]), raw_input=raw, write_log=False)
    visible = json.dumps(result.resume_sections.model_dump(), ensure_ascii=False)
    assert "接口测试" in visible and "FastAPI" not in visible and "Docker" not in visible


def test_golden_baseline_does_not_regress():
    case = load_case("v057_ai_agent_full_resume")
    result = process_fixed_payload(case)
    metrics = evaluate_payload(case, result)
    assert metrics["fact_coverage_rate"] >= 90
    assert metrics["experience_boundary_accuracy"] == 100
    assert metrics["experience_type_accuracy"] == 100
    assert metrics["duplicate_experience_entity_count"] == 0
    assert metrics["internal_field_leak_count"] == 0


def test_clean_claim_result_has_no_v082_critical_issue():
    raw = "项目经历：接口服务\n参与接口测试。没有负责架构设计。计划增加 Docker。"
    result = fill_resume_sections(payload([]), raw_input=raw, write_log=False)
    result = ensure_resume_delivery_quality(result, raw, write_log=False)
    critical = {
        issue.issue_code for issue in evaluate_delivery_quality_issues(result, raw)
        if issue.severity == "critical"
    }
    assert not critical.intersection({
        "UNCERTAIN_CLAIM_ASSERTED", "DENIED_CLAIM_ASSERTED",
        "PLANNED_WORK_PRESENTED_AS_COMPLETED", "CLAIM_OWNER_CHANGED",
        "USER_CONSTRAINT_RENDERED", "TARGET_ROLE_SKILL_LEAK",
    })


def test_confirmed_claim_wins_over_earlier_uncertainty_for_same_skill():
    raw = "项目经历：接口服务\n早期记不清是否使用 FastAPI，后续确认使用 FastAPI 完成接口开发。"
    result = fill_resume_sections(payload([]), raw_input=raw, write_log=False)
    result.resume_sections.skills = ["后端框架：FastAPI"]
    issues = evaluate_delivery_quality_issues(result, raw)
    assert not any(issue.issue_code == "UNCERTAIN_CLAIM_ASSERTED" for issue in issues)
