"""Regression coverage for Canonical Experience Type Authority.

These samples are current-code replays, not historical request snapshots.
"""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services import experience_type_resolution_service as type_service  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.experience_type_resolution_service import resolve_project_types  # noqa: E402


def _decision(raw: str, index: int = 0):
    return build_canonical_semantic_build(raw).experience_type_decisions[index]


def _payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=0,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(projects=[{
            "name": "[待补充经历名称]",
            "meta": "开源经历",
            "time": "[待填写]",
            "intro": "完成本地功能。",
            "role": "",
            "details": [],
            "source_experience_id": "EXP-001",
            "immutable_source_experience_id": "EXP-001",
            "source_binding_locked": True,
        }]),
    )


def test_campus_activity_management_system_and_github_are_a_project_not_open_source():
    build = build_canonical_semantic_build(
        "课程项目：校园活动管理系统。使用 Vue 完成报名和通知功能，并将代码上传 GitHub。"
    )

    assert build.identities[0].experience_type == "开源经历"  # provisional keyword hint
    assert build.experience_type_decisions[0].canonical_experience_type == "项目经历"
    assert build.experience_type_decisions[0].type_source == "relation_score"


def test_role_named_internship_with_local_duties_is_an_internship():
    build = build_canonical_semantic_build("产品运营实习，负责用户调研、内容运营和数据复盘。")

    assert build.identities[0].experience_type == "项目经历"
    assert build.experience_type_decisions[0].canonical_experience_type == "实习经历"
    assert build.experience_type_decisions[0].type_source == "relation_score"


def test_intent_negative_and_github_only_cannot_create_internship_or_open_source():
    assert _decision("想投产品运营实习，目前没有实习经历；开发数据分析工具。").canonical_experience_type == "项目经历"
    assert _decision("将课程项目代码上传 GitHub，并完成部署说明。").canonical_experience_type == "项目经历"


def test_external_open_source_contribution_and_real_campus_activity_require_relations():
    assert _decision("向开源社区提交 PR 并被合并，修复 issue。 ").canonical_experience_type == "开源经历"
    assert _decision("参与学校校庆志愿活动，负责现场引导和物资整理。").canonical_experience_type == "校园 / 社团经历"
    assert _decision("开发校园活动管理系统，完成报名和通知功能。").canonical_experience_type == "项目经历"


def test_research_competition_and_explicit_labels_keep_their_local_authority():
    assert _decision("参与智能问答课题组研究，完成实验设计和记录。").canonical_experience_type == "科研经历"
    assert _decision("参加华东数学建模竞赛，负责数据建模并获二等奖。").canonical_experience_type == "竞赛获奖"
    assert _decision("实习经历：课程学习助手\n完成资料整理和问答功能。").canonical_experience_type == "实习经历"


def test_multiple_owners_cannot_borrow_type_evidence():
    build = build_canonical_semantic_build(
        "项目经历：图书借阅管理系统\n开发借阅登记功能。\n\n"
        "开源经历：社区贡献\n向开源社区提交 PR 并被合并，修复 issue。"
    )

    assert [item.canonical_experience_type for item in build.experience_type_decisions] == ["项目经历", "开源经历"]


def test_canonical_type_decision_does_not_change_identity_facts_or_claims():
    raw = "产品运营实习，负责用户调研、内容运营和数据复盘。"
    build = build_canonical_semantic_build(raw)
    decision = build.experience_type_decisions[0]

    assert decision.experience_id == build.identities[0].experience_id
    assert {claim.source_experience_id for claim in build.ledger.claims} == {"EXP-001"}
    assert {fact.experience_id for fact in build.ledger.facts} == {"EXP-001"}
    assert decision == build_canonical_semantic_build(raw).experience_type_decisions[0]


def test_canonical_type_routing_applies_the_frozen_decision_without_raw_rebuild(monkeypatch, tmp_path):
    build = build_canonical_semantic_build("产品运营实习，负责用户调研和数据复盘。")
    monkeypatch.setattr(
        type_service,
        "build_type_resolutions",
        lambda _raw: (_ for _ in ()).throw(AssertionError("legacy raw rebuild must be unreachable")),
    )

    result = resolve_project_types(
        _payload(),
        None,
        canonical_type_decisions=build.canonical_type_by_experience_id,
        write_log=False,
    )

    assert result.resume_sections.projects[0]["meta"] == "实习经历"
    assert result.resume_sections.projects[0]["source_experience_id"] == "EXP-001"

    monkeypatch.setattr(type_service, "LOG_PATH", tmp_path / "experience_type_resolution.jsonl")
    resolve_project_types(
        _payload(),
        None,
        canonical_type_decisions=build.canonical_type_by_experience_id,
        write_log=True,
    )
    entry = (tmp_path / "experience_type_resolution.jsonl").read_text(encoding="utf-8")
    assert "产品运营实习" not in entry
    assert "用户调研" not in entry
    assert '"authority_mode": "canonical"' in entry
