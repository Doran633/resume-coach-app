"""Current-code controls for v0.9.18.5.1, not historical response replay."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest
from docx import Document


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.canonical_semantic_state_service import build_canonical_semantic_build  # noqa: E402
from app.services.resume_delivery_quality_gate_service import evaluate_canonical_delivery_quality_issues  # noqa: E402
from app.services.resume_semantic_unit_service import ensure_semantic_units, fragment_reasons  # noqa: E402
from test_v09162_model_output_evidence_contract import reference_return  # noqa: E402
from test_v09172_initial_evidence_preservation import detail_return  # noqa: E402
from test_v09174_fact_reference_composition import isolated  # noqa: E402,F401
from test_v09176_delivery_closure import deliver  # noqa: E402


RAW_INPUT = """基本信息：
软件工程专业本科在读，预计2027年毕业，希望申请Java后端开发实习。

后端开发实习：
2026年6月至2026年8月，在一家教育科技公司的研发部门担任后端开发实习生。
使用Spring Boot参与课程管理模块开发，负责课程查询、分类筛选和上下架状态接口。
根据接口文档完成参数校验和异常返回处理，并使用Postman编写18条接口测试。
协助排查两次测试环境问题，整理请求日志并与前端同学核对字段格式。
相关代码由正式员工审核后合并，我没有独立负责整体系统架构。

个人项目：校园失物招领平台
2026年3月至2026年5月，使用Java、Spring Boot和MySQL开发失物招领平台。
实现信息发布、分类查询和认领状态更新功能，设计失物信息和用户留言数据表。
使用25组测试数据检查重复提交、空字段和无匹配结果。
项目部署到个人云服务器，仅供同学试用，没有商业用户。

技能：
能够使用Java、Spring Boot、MySQL和Git，了解Redis的基础使用，目前对分布式系统经验较少。"""


@pytest.mark.parametrize(
    "text",
    [
        "相关代码由正式员工审核后合并",
        "支持多个分支合并",
        "完成数据归并",
        "完成企业兼并分析",
    ],
)
def test_complete_words_ending_with_bing_are_not_deterministic_fragments(text):
    reasons = fragment_reasons(text)
    assert "trailing_dependency" not in reasons
    assert not reasons or reasons == {"ambiguous_trailing_conjunction"}


@pytest.mark.parametrize("text", ["主要包括：", "基于", "完成接口联调，", "从20提升到"])
def test_deterministic_fragments_remain_critical(text):
    reasons = fragment_reasons(text)
    assert reasons & {"trailing_dependency", "trailing_separator", "incomplete_range"}


def test_single_bing_is_observable_but_not_deleted():
    project = {
        "name": "项目：测试",
        "meta": "项目经历",
        "time": "2026",
        "intro": "",
        "role": "",
        "details": ["完成审核并"],
        "source_experience_id": "EXP-001",
        "detail_fact_ids": [["EXP-001-F001"]],
        "detail_claim_ids": [["EXP-001-C001"]],
    }
    payload = schemas.GenerationPayload(
        completeness_score=90,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="n",
        bold_version="b",
        boundary_version="x",
        recommended_version="r",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(summary=["完成测试工作。"], projects=[project]),
    )
    original = deepcopy(payload)
    result = ensure_semantic_units(payload, "完成审核并")
    assert result.resume_sections.projects[0]["details"] == ["完成审核并"]
    assert result.resume_sections.projects[0]["detail_fact_ids"] == [["EXP-001-F001"]]
    assert payload == original


def test_gate_reports_ambiguous_suffix_with_exact_field_sources():
    case, build, data = detail_return(RAW_INPUT)
    payload = schemas.GenerationPayload.model_validate(data)
    issues, _, _ = evaluate_canonical_delivery_quality_issues(payload, semantic_build=build)
    target = [
        issue
        for issue in issues
        if issue.issue_code == "INCOMPLETE_SENTENCE"
        and issue.source_fact_ids == ["EXP-001-F005"]
    ]
    assert len(target) == 1
    issue = target[0]
    assert issue.severity == "warning"
    assert issue.reason_category == "ambiguous_trailing_conjunction"
    assert issue.field_path == "resume_sections.projects.0.body.6"
    assert issue.source_fact_ids == ["EXP-001-F005"]
    assert issue.source_claim_ids == ["EXP-001-C006"]


def test_full_java_sample_saves_and_exports_without_changing_evidence(monkeypatch, tmp_path, isolated):
    case, build, data = detail_return(RAW_INPUT)
    build_before = deepcopy(build)
    facts_before = [(f.fact_id, f.claim_id, f.resume_ready_text, f.source_span) for f in build.ledger.facts]
    response = json.dumps(reference_return(data), ensure_ascii=False)

    outcome = deliver(monkeypatch, tmp_path, case, [(response, "stop")])

    assert outcome["results"] == 1 and "docx" in outcome, outcome
    assert build == build_before
    assert [(f.fact_id, f.claim_id, f.resume_ready_text, f.source_span) for f in build.ledger.facts] == facts_before
    fact = next(f for f in build.ledger.facts if f.fact_id == "EXP-001-F005")
    denied = next(c for c in build.ledger.excluded_claims if c.claim_id == "EXP-001-C007")
    assert fact.resume_ready_text == "相关代码由正式员工审核后合并"
    assert RAW_INPUT[slice(*fact.source_span)] == fact.fact_text
    assert denied.text == "我没有独立负责整体系统架构"
    assert RAW_INPUT[slice(*denied.source_span)] == denied.text
    projects = outcome["saved"]["resume_sections"]["projects"]
    assigned = [fid for p in projects for row in [p.get("intro_source_fact_ids", []), p.get("role_source_fact_ids", []), *p.get("detail_fact_ids", [])] for fid in row]
    assert sorted(assigned) == sorted(f.fact_id for f in build.ledger.facts)
    assert "相关代码由正式员工审核后合并" in json.dumps(projects, ensure_ascii=False)
    assert list(tmp_path.glob("*.docx"))
    assert "相关代码由正式员工审核后合并" in "\n".join(
        paragraph.text for paragraph in Document(next(tmp_path.glob("*.docx"))).paragraphs
    )
