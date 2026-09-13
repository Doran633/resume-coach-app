"""Current-code replays of supplied inputs, not historical request snapshots."""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.experience_type_resolution_service import resolve_identity_type
from app.services.semantic_experience_segmentation_service import _infer_type


SAMPLES = {
    "frontend": """基本信息：本科在读，软件工程专业，预计2027年毕业，希望申请前端开发实习。
前端开发实习：2026年6月至2026年8月，在星河软件公司参与内部工单系统开发。使用React和TypeScript完成工单列表、筛选表单和详情页面，根据接口文档进行联调。按照测试人员提供的记录修复12个页面问题，补充空数据、加载中和请求失败的展示状态。代码经同事评审后合入。
课程项目：校园图书预约平台。2026年3月至2026年5月，四人小组完成课程作业，我负责使用Vue开发图书检索、预约记录和登录页面。完成8条前端交互测试，并参与课堂演示。
技能：能够使用React、Vue、TypeScript和Git，了解浏览器开发者工具。""",
    "backend": """基本信息：本科在读，计算机科学与技术专业，希望申请Java后端开发实习。
后端开发实习：2026年5月至2026年7月，在云桥科技公司参与订单管理后台开发。使用Spring Boot和MySQL实现订单查询、状态筛选及导出接口，配合前端完成联调。根据既有规范补充参数校验和异常日志，编写18条接口测试用例。数据库结构由正式员工设计，我按照已有设计实现接口。
个人项目：活动报名平台。2025年11月至2026年1月，使用Spring Boot和MySQL实现活动发布、报名和取消报名功能，通过唯一约束避免重复报名。邀请6位同学试用，根据反馈调整报名提示。将代码上传GitHub保存。
技能：能够使用Java、Spring Boot、MySQL和Git。""",
    "ai": """基本信息：本科在读，人工智能专业，希望申请AI应用或后端开发实习。
AI应用开发实习：2026年6月至2026年8月，在知远科技公司参与内部知识库问答工具开发。使用Python和FastAPI维护文件上传及问答接口，按照团队方案调整文档切块参数。整理40条测试问题，记录检索结果、回答内容和引用出处，协助比较调整前后的效果。没有参与模型训练。
个人项目：课程资料检索助手。2026年2月至2026年4月，使用Python读取课程PDF，调用现成Embedding接口并通过FAISS建立本地索引。使用15份课程资料验证关键词检索与语义检索结果，为回答增加来源文件名和页码展示。
技能：能够使用Python、FastAPI和Git，了解向量检索的基本流程。""",
    "testing": """基本信息：本科在读，软件工程专业，希望申请测试开发实习。
测试开发实习：2026年4月至2026年7月，在明川软件公司参与会员管理系统测试。根据需求文档整理注册、登录和会员信息修改场景，使用Postman执行接口检查。使用Python和pytest编写24条自动化接口用例，将失败请求和响应整理给开发同事，并在修复后回归验证。
课程项目：商品管理后台。2025年10月至2025年12月，三人小组使用Vue和Spring Boot完成课程作业，我负责商品列表、编辑表单和接口联调。在演示前发现并修复7处表单校验问题。
技能：能够使用Python、pytest、Postman和SQL，了解Git基本操作。""",
}
MARKERS = {
    "frontend": ("12", "8", "2026年6月至2026年8月", "2026年3月至2026年5月"),
    "backend": ("18", "6位", "2026年5月至2026年7月", "2025年11月至2026年1月"),
    "ai": ("40", "15份", "2026年6月至2026年8月", "2026年2月至2026年4月"),
    "testing": ("24", "7处", "2026年4月至2026年7月", "2025年10月至2025年12月"),
}


def variants(raw):
    yield raw
    yield raw.replace("\n", "")
    yield raw.replace("：", "：\n")
    yield raw.replace("：", "\n")
    yield raw.replace("。", "。\n\n").replace("：", "：\n\n")
    yield raw.replace("：", "：\n").replace("\n", "\r\n")


def fact_signature(build):
    return [(f.experience_id, re.sub(r"\s+", "", f.fact_text)) for f in build.ledger.facts]


@pytest.mark.parametrize("key", SAMPLES)
def test_full_inputs_have_owner_scoped_internship_and_project(key):
    baseline = build_canonical_semantic_build(SAMPLES[key])
    for raw in variants(SAMPLES[key]):
        build = build_canonical_semantic_build(raw)
        assert [d.canonical_experience_type for d in build.experience_type_decisions] == ["实习经历", "项目经历"]
        assert len(build.identities) == 2
        for index, identity in enumerate(build.identities):
            assert raw[slice(*identity.source_span)] == identity.raw_text
            assert MARKERS[key][index + 2] in identity.raw_text
            assert MARKERS[key][3 - index] not in identity.raw_text
            assert "基本信息" not in identity.raw_text and "技能：" not in identity.raw_text
            facts = [f for f in build.ledger.facts if f.experience_id == identity.experience_id]
            assert any(MARKERS[key][index] in f.fact_text for f in facts)
            for fact in facts:
                assert identity.source_span[0] <= fact.source_span[0] < fact.source_span[1] <= identity.source_span[1]
                original = raw[slice(*fact.source_span)]
                assert re.sub(r"\s+", "", original).strip("。；，:：") == re.sub(r"\s+", "", fact.fact_text)
        assert fact_signature(build) == fact_signature(baseline)
        assert all(not f.fact_text.rstrip("：:").endswith("开发实习") for f in build.ledger.facts)


@pytest.mark.parametrize("title", ["开源经历", "科研经历", "实习经历", "课程项目", "担任实习生", "没有实习", ""])
def test_generated_title_cannot_change_canonical_type_or_scores(title):
    build = build_canonical_semantic_build("后端开发实习：在某软件公司参与订单管理后台开发。使用Spring Boot完成接口。")
    identity, claims = build.identities[0], build.claim_resolutions[0]
    before = deepcopy((identity, claims))
    expected = resolve_identity_type(replace(identity, title=""), claims)
    actual = resolve_identity_type(replace(identity, title=title, experience_type="科研经历"), claims)
    assert actual.resolved_type == expected.resolved_type == "实习经历"
    assert actual.evidence_scores == expected.evidence_scores
    assert (identity, claims) == before


@pytest.mark.parametrize("raw", [
    "使用Spring Boot完成接口。", "使用Spring Boot完成接口并合并代码。",
    "将代码上传GitHub保存。", "创建PR。", "完成一次commit。", "整理仓库。",
])
def test_tokens_without_contribution_relation_do_not_prove_open_source(raw):
    build = build_canonical_semantic_build(raw)
    assert build.experience_type_decisions[0].canonical_experience_type != "开源经历"


def test_spring_is_not_a_provisional_pr_signal():
    assert _infer_type("使用Spring Boot完成接口。") != "开源经历"


@pytest.mark.parametrize("raw", ["向开源社区提交PR并被合并，修复issue。", "PR被合并，修复接口问题。"])
def test_real_contribution_still_qualifies(raw):
    assert build_canonical_semantic_build(raw).experience_type_decisions[0].canonical_experience_type == "开源经历"


@pytest.mark.parametrize("heading", ["前端开发实习", "技术支持实习", "商业化策略实习", "信息安全实习"])
def test_role_headings_do_not_require_a_fixed_occupation_list(heading):
    build = build_canonical_semantic_build(f"{heading}：在某公司参与内部业务，完成资料核对。")
    assert build.experience_type_decisions[0].canonical_experience_type == "实习经历"


@pytest.mark.parametrize("body", ["计划参与内部业务。", "没有参与内部业务。", "可能参与内部业务。", "请帮我写成参与内部业务。"])
def test_heading_without_confirmed_duty_cannot_prove_internship(body):
    build = build_canonical_semantic_build("前端开发实习：" + body)
    assert all(d.canonical_experience_type != "实习经历" for d in build.experience_type_decisions)


@pytest.mark.parametrize("raw", [
    "计划在某公司担任实习生，负责测试接口。",
    "前端开发实习：计划在某公司担任实习生。",
])
def test_prospective_employment_is_not_a_present_type_relation(raw):
    build = build_canonical_semantic_build(raw)
    assert all(d.canonical_experience_type != "实习经历" for d in build.experience_type_decisions)


def test_future_intention_does_not_cancel_independent_confirmed_duties():
    raw = "前端开发实习：参与业务。希望以后申请其他实习。"
    assert build_canonical_semantic_build(raw).experience_type_decisions[0].canonical_experience_type == "实习经历"


@pytest.mark.parametrize("heading", ["计划前端开发实习", "没有前端开发实习", "可能的前端开发实习", "希望申请前端开发实习"])
def test_intent_negative_uncertain_and_planned_headings_do_not_qualify(heading):
    build = build_canonical_semantic_build(f"{heading}：完成接口开发。")
    assert all(d.canonical_experience_type != "实习经历" for d in build.experience_type_decisions)


def test_owner_cannot_borrow_another_owners_duties():
    build = build_canonical_semantic_build("前端开发实习：了解内部工作。\n课程项目：完成接口开发。")
    assert len(build.identities) == 2
    assert build.experience_type_decisions[0].canonical_experience_type != "实习经历"
    mixed = replace(build.claim_resolutions[0], claims=build.claim_resolutions[1].claims)
    assert resolve_identity_type(build.identities[0], mixed).resolved_type != "实习经历"


def test_explicit_type_keeps_priority_and_repeated_build_is_stable():
    raw = "实习经历：课程工具\n完成课程项目接口。"
    before = build_canonical_semantic_build(raw)
    assert before.experience_type_decisions[0].canonical_experience_type == "实习经历"
    assert asdict(before) == asdict(build_canonical_semantic_build(raw))


def test_strong_internship_relation_is_not_overruled_by_project_word_accumulation():
    raw = "后端开发实习：在某公司参与业务。独立开发系统，从零设计，持续迭代，实现完整工作流，公网部署，用户测试。"
    assert build_canonical_semantic_build(raw).experience_type_decisions[0].canonical_experience_type == "实习经历"


@pytest.mark.parametrize("change", [
    {"eligibility": "withheld"}, {"polarity": "negative"}, {"certainty": "uncertain"},
    {"temporal_status": "planned"}, {"semantic_role": "USER_INSTRUCTION"},
    {"source_experience_id": "EXP-999"}, {"source_span": (1, 7)},
])
def test_structure_evidence_requires_confirmed_owner_local_provenance(change):
    build = build_canonical_semantic_build("前端开发实习：参与接口开发。")
    identity, resolution = build.identities[0], build.claim_resolutions[0]
    claims = list(resolution.claims)
    claims[0] = replace(claims[0], **change)
    altered = replace(resolution, claims=tuple(claims))
    assert resolve_identity_type(identity, altered).resolved_type != "实习经历"


def test_real_build_evaluates_each_owner_once_without_mutating_components(monkeypatch):
    from app.services import canonical_semantic_state_service as service
    original = service.resolve_identity_type
    calls = []
    def observe(identity, claims):
        before = deepcopy((identity, claims))
        result = original(identity, claims)
        assert (identity, claims) == before
        calls.append(identity.experience_id)
        return result
    monkeypatch.setattr(service, "resolve_identity_type", observe)
    service.build_canonical_semantic_build(SAMPLES["backend"])
    assert calls == ["EXP-001", "EXP-002"]


@pytest.mark.parametrize("key", SAMPLES)
def test_actual_mock_generation_persists_frozen_types_and_headers(key, tmp_path, monkeypatch):
    import json
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import models, schemas
    from app.database import Base
    from app.services import generation_service as service
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setattr(service, "LOG_DIR", tmp_path)
    def forbidden(*a, **kw):
        raise AssertionError("This deterministic test must not call a paid model")
    monkeypatch.setattr(service, "call_openai", forbidden)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with sessionmaker(bind=engine)() as db:
            request = schemas.GenerateRequest(
                anonymous_user_id="v09151-user", session_id="v09151-session",
                target_role="后端开发", mode="full_resume", packaging_level="稳妥",
                experience_type="综合经历", raw_input=SAMPLES[key], attempt_id="v09151_" + key,
            )
            response = service.create_generation(db, request, request_id="req_v09151_" + key)
            row = db.get(models.GenerationResult, response.generation_result_id)
            projects = json.loads(row.result_json)["resume_sections"]["projects"]
            assert len(projects) == 2
            by_owner = {p["source_experience_id"]: p for p in projects}
            assert set(by_owner) == {"EXP-001", "EXP-002"}
            assert by_owner["EXP-001"]["meta"] == "实习经历"
            assert by_owner["EXP-002"]["meta"] == "项目经历"
            assert by_owner["EXP-001"]["name"].startswith("企业：")
            assert by_owner["EXP-001"]["position"].startswith("岗位：")
            assert by_owner["EXP-002"]["name"].startswith("项目：")
    finally:
        engine.dispose()
