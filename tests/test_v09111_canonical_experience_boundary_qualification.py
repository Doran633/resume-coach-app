from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.semantic_experience_segmentation_service import segment_semantic_experiences  # noqa: E402


def test_result_178_shape_merges_a_result_clause_without_an_independent_anchor():
    raw = (
        "独立开发大学生消费行为数据分析项目，使用 Python 完成数据清洗、分析和可视化。"
        "参与后续成果展示并完成上线，GitHub 中保留项目说明和结果。"
    )

    result = segment_semantic_experiences(raw)

    assert len(result.segments) == 1
    assert result.segments[0].start_offset == 0
    assert result.segments[0].end_offset >= len(raw) - 1
    assert "GitHub" in result.segments[0].raw_text
    assert result.weak_boundary_merged_count == 1
    assert result.weak_boundary_reason_counts == {"missing_independent_experience_anchor": 1}
    assert result.clarification_questions == []


def test_actions_results_metrics_and_delivery_alone_do_not_create_owner_scopes():
    raw = (
        "开发图书借阅管理系统，完成借阅流程和数据整理。"
        "负责测试并将准确率提升至 90%，随后上传 GitHub 并完成上线。"
    )

    result = segment_semantic_experiences(raw)
    build = build_canonical_semantic_build(raw)

    assert len(result.segments) == 1
    assert len(build.identities) == 1
    assert {fact.experience_id for fact in build.ledger.facts} <= {"EXP-001"}
    assert {claim.experience_id for claim in build.claim_resolutions[0].eligible_claims} <= {"EXP-001"}


def test_named_projects_and_organizations_remain_independent_experiences():
    raw = (
        "独立开发图书借阅管理系统，完成借阅记录维护。\n\n"
        "设计校园活动管理平台，负责报名与通知流程。\n\n"
        "在星河科技有限公司担任后端实习生，参与接口开发和测试。"
    )

    result = segment_semantic_experiences(raw)

    assert len(result.segments) == 3
    assert "图书借阅管理系统" in result.segments[0].raw_text
    assert "校园活动管理平台" in result.segments[1].raw_text
    assert result.segments[2].experience_type == "实习经历"


def test_project_competition_research_and_campus_boundaries_still_split():
    raw = (
        "开发课程学习助手，完成资料整理和问答功能。\n\n"
        "参加华东数学建模竞赛，负责数据建模并获二等奖。\n\n"
        "参与智能问答课题组研究，完成实验设计。\n\n"
        "参与学校校庆志愿活动，负责现场引导和物资整理。"
    )

    result = segment_semantic_experiences(raw)

    assert len(result.segments) == 4
    assert result.segments[1].experience_type == "竞赛获奖"
    assert result.segments[2].experience_type == "科研经历"
    assert result.segments[3].experience_type == "校园活动经历"


def test_explicit_headings_keep_priority_without_implicit_anchor_checks():
    raw = """项目一：课程学习助手
完成资料整理和问答功能。

项目二：大学生消费行为数据分析
完成数据清洗和可视化。
"""

    result = segment_semantic_experiences(raw)

    assert len(result.segments) == 2
    assert [segment.boundary_source for segment in result.segments] == ["explicit_heading", "explicit_heading"]


def test_single_experience_title_behavior_is_unchanged_in_this_phase():
    raw = "了解对数据分析的基本流程和 Python 数据处理工具，并完成大学生消费行为数据分析。"

    result = segment_semantic_experiences(raw)

    assert len(result.segments) == 1
