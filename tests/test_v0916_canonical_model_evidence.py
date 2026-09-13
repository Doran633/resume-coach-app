"""Current-code model-input replays, not historical server request snapshots."""
from pathlib import Path
from copy import deepcopy
from dataclasses import replace
import json
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import schemas, models
from app.database import Base
from app.services import generation_service as generation
from app.services import prompt_service
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from test_v09151_type_evidence_integrity import SAMPLES
from test_v09141_structured_experience_boundary import SAMPLES as ECOMMERCE, FULL, formatted
from app.services.canonical_semantic_state_service import build_canonical_semantic_build
from app.services.canonical_consumer_view_service import build_canonical_consumer_views
from app.services.llm_service import LLMResult


# Previously supplied synthetic inputs, not reconstructed from exported DOCX.
MULTI_TYPE = {
    "research_course": """基本信息：
计算机科学与技术专业本科在读，预计2027年毕业，希望申请AI应用开发岗位。
科研经历：课程问答检索效果研究
2025年10月至2026年3月，在学校智能信息处理实验室参与课程问答检索课题，由指导老师确定研究方案。我负责整理60篇课程资料，检查重复文件和缺失页码，按照课题组标准记录资料来源。
使用Python处理文档，并比较两种文档切块设置下的检索结果。根据老师提供的30条测试问题，记录命中文档和引用位置，汇总错误检索案例。
参与每周组会，介绍数据整理进度和实验记录。没有训练模型，没有发表论文，实验结论由老师和小组共同讨论。
课程项目：校园活动管理系统
2026年4月至2026年6月，四人小组完成软件工程课程作业。我负责使用Vue实现活动列表、报名表单和报名记录页面，与同学完成接口联调。
编写14条页面交互测试，修复重复提交和空数据提示问题。将代码上传GitHub用于小组协作，完成课堂演示。这个系统没有投入学校实际运营。
技能：
能够使用Python、Vue和Git，了解文档检索和前端接口联调。""",
    "opensource_personal": """基本信息：
软件工程专业本科在读，预计2027年毕业，希望申请后端开发岗位。
开源经历：PageTrack文档工具贡献
2026年2月至2026年4月，参与外部维护者管理的PageTrack开源项目。我根据项目已有issue复现Markdown目录链接错误，定位到标题包含空格时的链接编码处理问题。
使用Python修改相关处理逻辑，补充9条自动化测试。向上游仓库提交2个PR，其中1个修复PR已经被维护者合并，另1个文档PR仍在审核。
我不是项目维护者，没有负责整体架构，也没有参与其他贡献者的功能开发。
个人项目：自习室预约平台
2025年11月至2026年1月，使用Spring Boot和MySQL完成个人练习项目，实现座位查询、预约和取消预约功能。
通过唯一约束处理重复预约，编写16条接口测试。邀请5位同学试用，根据反馈调整预约冲突提示。
代码上传到自己的GitHub仓库用于保存，没有向外部开源项目提交贡献，也没有商业用户。
技能：
能够使用Java、Python、Spring Boot、MySQL和Git。""",
    "competition_campus": """基本信息：
信息管理与信息系统专业本科在读，预计2027年毕业，希望申请数据分析岗位。
竞赛经历：高校数据分析挑战赛
2026年4月至2026年6月，与两位同学组成三人团队参加高校数据分析挑战赛，赛题要求分析公开的城市出行数据。
我负责使用Python和Pandas检查缺失值、重复记录及异常日期，将原始12000条记录清理为11320条有效记录，并绘制出行时段分布图。
参与撰写数据处理部分的报告，在答辩中介绍清理规则和数据局限。团队进入决赛并获得三等奖，我没有负责预测模型设计。
校园 / 社团经历：数据科学协会活动组织
2025年9月至2026年1月，担任学校数据科学协会活动部成员，协助组织3场Python入门分享活动。
根据主讲同学提供的内容整理活动通知，核对时间、地点和报名方式。使用共享表格登记报名信息，累计收到82条报名记录。
活动结束后整理签到和反馈，汇总27份反馈表中的课程难度和内容建议。82条报名记录可能包含重复报名，不能当作82名独立参与者。
技能：
能够使用Python、Pandas、Excel和PowerPoint完成基础数据整理与展示。""",
}


class CapturedModelCall(BaseException):
    """Stop before network and before any delivery transformations."""


def evidence(prompt):
    data = prompt.split("<canonical_model_evidence>\n", 1)[1]
    return json.JSONDecoder().raw_decode(data)[0]


def capture_generation(raw, monkeypatch, tmp_path, *, forbid_rebuild=False, deliver=False, retry=False):
    monkeypatch.setenv("LLM_MODE", "openai")
    monkeypatch.setattr(generation.resource_protection, "check_daily_budget", lambda: SimpleNamespace(allowed=True))
    monkeypatch.setattr(generation.resource_protection, "record_llm_usage", lambda **kw: None)
    # Existing services write local diagnostics; isolate all imported log sinks.
    for module in tuple(sys.modules.values()):
        if not getattr(module, "__name__", "").startswith("app.services."):
            continue
        for key in ("LOG_DIR", "LOG_PATH"):
            value = getattr(module, key, None)
            if isinstance(value, Path):
                target = tmp_path / value.name if key == "LOG_PATH" else tmp_path
                monkeypatch.setattr(module, key, target)
    captured = {"prompts": []}
    original = generation.build_canonical_consumer_views

    def views_built(build, *args, **kwargs):
        captured["build"] = build
        views = original(build, *args, **kwargs)
        if forbid_rebuild:
            def forbidden(*a, **kw):
                raise AssertionError("Prompt preparation rebuilt semantic evidence")
            for name in (
                "build_experience_identities", "split_experience_segments",
                "build_experience_fact_ledger", "build_segmentation_questions",
                "build_experience_context", "build_experience_identity_context",
                "build_fact_ledger_context",
            ):
                monkeypatch.setattr(prompt_service, name, forbidden)
            from app.services import semantic_experience_segmentation_service as segmentation
            from app.services import experience_identity_service as identity
            from app.services import experience_fact_ledger_service as ledger
            from app.services import input_claim_resolution_service as claims
            for module, name in (
                (segmentation, "segment_semantic_experiences"),
                (identity, "build_experience_identities"),
                (ledger, "build_experience_fact_ledger"),
                (claims, "resolve_experience_claims"),
            ):
                monkeypatch.setattr(module, name, forbidden)
        return views

    original_prompt = generation.build_generation_prompt

    def prepare(*args, **kwargs):
        # The existing shadow save attaches an input ID before model preparation.
        # Measure immutability across the requested preparation boundary itself.
        captured["before"] = deepcopy(captured["build"])
        result = original_prompt(*args, **kwargs)
        assert captured["build"] == captured["before"]
        return result

    def intercept(prompt):
        captured["prompt"] = prompt
        captured["prompts"].append(prompt)
        assert captured["build"] == captured["before"]
        if deliver:
            return LLMResult(
                text="not json" if retry and len(captured["prompts"]) == 1 else model_text,
                model="offline-fixed-return", latency_ms=0,
            )
        raise CapturedModelCall()

    monkeypatch.setattr(generation, "build_canonical_consumer_views", views_built)
    monkeypatch.setattr(generation, "build_generation_prompt", prepare)
    monkeypatch.setattr(generation, "call_openai", intercept)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    request = schemas.GenerateRequest(
        anonymous_user_id="v0916-user", session_id="v0916-session",
        target_role="后端开发", mode="full_resume", packaging_level="稳妥",
        experience_type="综合经历", raw_input=raw, attempt_id="v0916-replay",
    )
    model_text = generation.build_mock_generation(request).model_dump_json() if deliver else ""
    try:
        with Session(engine) as db:
            if deliver:
                captured["response"] = generation.create_generation(db, request, request_id="req_v0916_replay")
                row = db.get(models.GenerationResult, captured["response"].generation_result_id)
                captured["saved"] = json.loads(row.result_json)
            else:
                with pytest.raises(CapturedModelCall):
                    generation.create_generation(db, request, request_id="req_v0916_replay")
    finally:
        engine.dispose()
    return captured


@pytest.mark.parametrize("key", SAMPLES)
def test_actual_model_input_uses_frozen_type(monkeypatch, tmp_path, key):
    captured = capture_generation(SAMPLES[key], monkeypatch, tmp_path)
    owners = {row["source_experience_id"]: row for row in evidence(captured["prompt"])["owners"]}
    for decision in captured["build"].experience_type_decisions:
        assert owners[decision.experience_id]["experience_type"] == decision.canonical_experience_type


def test_actual_model_preparation_cannot_rebuild_semantics(monkeypatch, tmp_path):
    capture_generation(SAMPLES["backend"], monkeypatch, tmp_path, forbid_rebuild=True)


def test_actual_model_input_retains_non_experience_background(monkeypatch, tmp_path):
    raw = (Path(__file__).parent / "fixtures" / "v0914_ecommerce_input.txt").read_text(encoding="utf-8").strip()
    captured = capture_generation(raw, monkeypatch, tmp_path)
    assert len(captured["build"].identities) == 3
    for text in ("预计2028年毕业", "电子商务专业", "PowerPoint", "Canva", "剪映"):
        assert text in captured["prompt"]
    assert all("预计2028年毕业" not in identity.raw_text for identity in captured["build"].identities)


@pytest.mark.parametrize("raw", [*SAMPLES.values(), FULL, *ECOMMERCE.values(), *MULTI_TYPE.values()], ids=[*SAMPLES, "full_ecommerce", *ECOMMERCE, *MULTI_TYPE])
def test_sent_facts_headers_and_constraints_are_complete_and_owner_local(raw, monkeypatch, tmp_path):
    captured = capture_generation(raw, monkeypatch, tmp_path)
    build = captured["build"]
    data = evidence(captured["prompt"])
    facts = {f.fact_id: f for f in build.ledger.facts}
    claims = {c.claim_id: c for c in build.ledger.claims}
    sent_ids = []
    for row in data["owners"]:
        owner = row["source_experience_id"]
        header = build.experience_header_decision_by_experience_id[owner]
        assert row["project_header"]["meta"] == header.canonical_experience_type
        for field in header.fields:
            key = "name" if field.field_key == "organization" else field.field_key
            assert row["project_header"][key] == field.display_text
        for sent in row["eligible_facts"]:
            fact = facts[sent["fact_id"]]
            claim = claims[fact.claim_id]
            assert sent["source_experience_id"] == fact.experience_id == claim.source_experience_id == owner
            assert sent["source_claim_ids"] == [claim.claim_id]
            assert sent["resume_ready_text"] == fact.resume_ready_text
            assert sent["source_claim_text"] == claim.text
            assert sent["source_span"] == list(fact.source_span)
            assert sent["claim_source_span"] == list(claim.source_span)
            sent_ids.append(fact.fact_id)
    assert sorted(sent_ids) == sorted(facts)
    excluded = {c.claim_id for c in (*build.ledger.excluded_claims, *build.ledger.withheld_claims)}
    assert {c["claim_id"] for c in data["internal_constraints_not_resume_facts"]} == excluded
    for row in data["internal_constraints_not_resume_facts"]:
        assert row["text"] == claims[row["claim_id"]].text
        assert row["claim_id"] not in {f["source_claim_ids"][0] for o in data["owners"] for f in o["eligible_facts"]}
    for row in data["non_experience_context_not_project_facts"]:
        start, end = row["source_span"]
        assert row["text"] == raw[start:end]
        assert all(not (start < i.source_span[1] and end > i.source_span[0]) for i in build.identities)
    assert build == captured["before"]


def request_for(raw):
    return schemas.GenerateRequest(
        anonymous_user_id="v0916-user", session_id="v0916-session",
        target_role="后端开发", mode="full_resume", packaging_level="大胆",
        experience_type="综合经历", raw_input=raw,
    )


def test_normal_and_long_templates_read_identical_evidence_and_do_not_mutate_build():
    build = build_canonical_semantic_build(SAMPLES["backend"])
    before = deepcopy(build)
    views = build_canonical_consumer_views(build)
    prompts = [prompt_service.build_generation_prompt(
        request_for(SAMPLES["backend"]), replace(build.long_input_context, long_input_mode=mode), consumer_views=views,
    ) for mode in (False, True)]
    assert evidence(prompts[0]) == evidence(prompts[1])
    assert prompts[0].count("<canonical_model_evidence>") == prompts[1].count("<canonical_model_evidence>") == 1
    assert build == before
    assert prompt_service.build_generation_prompt(request_for(SAMPLES["backend"]), replace(build.long_input_context, long_input_mode=False), consumer_views=views) == prompts[0]


def test_context_from_another_request_is_rejected():
    build = build_canonical_semantic_build(SAMPLES["backend"])
    with pytest.raises(ValueError, match="same request"):
        prompt_service.build_generation_prompt(request_for(SAMPLES["ai"]), consumer_views=build_canonical_consumer_views(build))


def test_format_variants_preserve_model_fact_meaning():
    def signature(raw):
        build = build_canonical_semantic_build(raw)
        data = evidence(prompt_service.build_generation_prompt(request_for(raw), consumer_views=build_canonical_consumer_views(build)))
        return [(o["experience_type"], [re.sub(r"\s+", "", f["source_claim_text"]) for f in o["eligible_facts"]]) for o in data["owners"]]
    baseline = signature(FULL)
    for style in ("heading_lines", "sentences", "inside_sentence", "crlf"):
        assert signature(formatted(FULL, style)) == baseline


def test_ambiguous_detached_text_is_not_promoted_to_background():
    raw = "项目一：预约平台\n使用Vue开发预约页面。\n项目二：课程助手\n使用Python处理资料。\n\n我做过一个预约平台，修复提交问题。"
    build = build_canonical_semantic_build(raw)
    assert build.long_input_context.clarification_questions
    data = evidence(prompt_service.build_generation_prompt(request_for(raw), consumer_views=build_canonical_consumer_views(build)))
    assert data["segmentation_questions"] == list(build.long_input_context.clarification_questions)
    assert data["non_experience_context_not_project_facts"] == []
    assert "我做过一个预约平台" not in json.dumps(data, ensure_ascii=False)


def test_known_eligible_maintainer_claim_is_not_silently_reclassified():
    raw = "开源经历：PageTrack文档工具贡献\n参与外部维护者管理的PageTrack开源项目。我不是项目维护者，没有负责整体架构。"
    build = build_canonical_semantic_build(raw)
    fact = next(f for f in build.ledger.facts if f.fact_text == "我不是项目维护者")
    data = evidence(prompt_service.build_generation_prompt(request_for(raw), consumer_views=build_canonical_consumer_views(build)))
    sent = next(f for o in data["owners"] for f in o["eligible_facts"] if f["fact_id"] == fact.fact_id)
    assert sent["eligibility"] == "eligible"
    assert sent["source_claim_text"] == "我不是项目维护者"


def test_retry_reuses_evidence_and_real_generation_saves_without_api_leaks(monkeypatch, tmp_path):
    monkeypatch.setenv("MAX_LLM_CALLS_PER_ATTEMPT", "2")
    captured = capture_generation(SAMPLES["backend"], monkeypatch, tmp_path, deliver=True, retry=True)
    assert len(captured["prompts"]) == 2
    assert evidence(captured["prompts"][0]) == evidence(captured["prompts"][1])
    assert captured["prompts"][1].startswith(captured["prompts"][0])
    assert captured["response"].generation_result_id
    by_owner = {p["source_experience_id"]: p for p in captured["saved"]["resume_sections"]["projects"]}
    assert by_owner["EXP-001"]["meta"] == "实习经历"
    assert by_owner["EXP-002"]["meta"] == "项目经历"
    assert "canonical_model_evidence" not in json.dumps(captured["saved"])
    assert "internal_constraints_not_resume_facts" not in captured["response"].model_dump_json()


def test_long_fact_and_more_than_eight_facts_are_not_abridged(monkeypatch, tmp_path):
    raw = "项目一：资料管理平台\n" + "。".join([
        "我负责整理" + "、".join(f"第{i}类资料的来源日期与核对记录" for i in range(18)),
        *(f"使用Python核对第{i}批资料的缺失页码并记录{i + 10}项问题" for i in range(10)),
    ]) + "。"
    captured = capture_generation(raw, monkeypatch, tmp_path)
    facts = captured["build"].ledger.facts
    assert len(facts) > 8 and max(len(f.resume_ready_text) for f in facts) > 140
    sent = [f for o in evidence(captured["prompt"])["owners"] for f in o["eligible_facts"]]
    assert [(f["fact_id"], f["resume_ready_text"]) for f in sent] == [(f.fact_id, f.resume_ready_text) for f in facts]
    # Baseline compatibility API still illustrates why it must not be wired
    # into the Canonical model path: eight entries and 140-character slices.
    old_summary = prompt_service.build_fact_ledger_context(raw)
    assert facts[-1].fact_id not in old_summary
    assert max(facts, key=lambda f: len(f.resume_ready_text)).resume_ready_text not in old_summary


def test_retry_does_not_call_prompt_preparation_again(monkeypatch):
    raw = SAMPLES["ai"]
    build = build_canonical_semantic_build(raw)
    views = build_canonical_consumer_views(build)
    before = deepcopy(build)
    original = generation.build_generation_prompt
    calls = []
    prompts = []
    output = generation.build_mock_generation(request_for(raw)).model_dump_json()
    def prepare(*args, **kwargs):
        calls.append(1)
        assert len(calls) == 1
        return original(*args, **kwargs)
    def call(prompt):
        prompts.append(prompt)
        return LLMResult(text="not json" if len(prompts) == 1 else output, model="offline", latency_ms=0)
    monkeypatch.setenv("MAX_LLM_CALLS_PER_ATTEMPT", "2")
    monkeypatch.setattr(generation, "build_generation_prompt", prepare)
    monkeypatch.setattr(generation, "call_openai", call)
    monkeypatch.setattr(generation.resource_protection, "check_daily_budget", lambda: SimpleNamespace(allowed=True))
    monkeypatch.setattr(generation.resource_protection, "record_llm_usage", lambda **kw: None)
    generation.build_llm_generation(request_for(raw), build.long_input_context, consumer_views=views)
    assert len(calls) == 1 and len(prompts) == 2
    assert evidence(prompts[0]) == evidence(prompts[1])
    assert build == before


@pytest.mark.parametrize("raw", [
    "基本信息：本科在读，预计2027年毕业。技能：了解Python。",
    "本科在读，预计2027年毕业。希望申请开发岗位。",
    "本科在读，预计2027年毕业。\n项目一：资料平台\n使用Python处理资料。",
])
def test_background_only_and_preamble_ranges_are_preserved_without_owner_invention(raw):
    build = build_canonical_semantic_build(raw)
    context = build.long_input_context
    spans = context.non_experience_source_spans
    assert spans
    views = build_canonical_consumer_views(build)
    assert views.claims_for_owner("EXP-999") == ()
    data = evidence(prompt_service.build_generation_prompt(request_for(raw), consumer_views=views))
    assert len(data["owners"]) == len(build.identities)
    assert any("本科在读" in row["text"] for row in data["non_experience_context_not_project_facts"])
    assert all(raw[slice(*span)] == text for span, text in views.non_experience_context(raw))


def test_explicit_constraints_remain_separate_without_rewriting_their_meaning():
    raw = "项目一：资料管理平台\n使用Python整理资料。我没有训练模型。可能使用Flask或FastAPI。请不要编造公司。"
    build = build_canonical_semantic_build(raw)
    data = evidence(prompt_service.build_generation_prompt(request_for(raw), consumer_views=build_canonical_consumer_views(build)))
    facts = json.dumps([o["eligible_facts"] for o in data["owners"]], ensure_ascii=False)
    constraints = json.dumps(data["internal_constraints_not_resume_facts"], ensure_ascii=False)
    assert "没有训练模型" in constraints and "没有训练模型" not in facts
    assert "Flask或FastAPI" in constraints and "Flask或FastAPI" not in facts
    assert "不要编造公司" in constraints and "不要编造公司" not in facts


def test_invalid_background_range_cannot_copy_project_text():
    build = build_canonical_semantic_build(SAMPLES["backend"])
    build.long_input_context = replace(
        build.long_input_context, non_experience_source_spans=(build.identities[0].source_span,),
    )
    with pytest.raises(ValueError, match="source range"):
        prompt_service.build_generation_prompt(request_for(SAMPLES["backend"]), consumer_views=build_canonical_consumer_views(build))


def test_model_serialization_does_not_add_text_to_existing_view_logs(tmp_path, monkeypatch):
    from app.services import canonical_consumer_view_service as service
    build = build_canonical_semantic_build(SAMPLES["backend"])
    views = build_canonical_consumer_views(build)
    scopes = dict(views.owner_scopes)
    path = tmp_path / "views.jsonl"
    monkeypatch.setattr(service, "LOG_PATH", path)
    prompt_service.build_generation_prompt(request_for(SAMPLES["backend"]), consumer_views=views)
    assert not path.exists()
    service.write_canonical_consumer_views_log(views, stage="test_v0916")
    logged = path.read_text(encoding="utf-8")
    assert "云桥" not in logged and "本科在读" not in logged
    assert all(f.fact_text not in logged for f in build.ledger.facts)
    assert "canonical_model_evidence" not in logged
    assert dict(views.owner_scopes) == scopes
