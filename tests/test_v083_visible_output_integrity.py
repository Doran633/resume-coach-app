import json
import sys

import pytest

from backend.app import schemas
from backend.app.services.resume_delivery_quality_gate_service import (
    ensure_resume_delivery_quality,
    measure_high_value_fact_coverage,
)
from backend.app.services.resume_visible_output_service import find_internal_field_leaks
import scripts.run_public_smoke_test as smoke_module
from scripts.run_public_smoke_test import SmokeFailure, run_full, validate_generation


RAW = (
    "独立开发课程资料问答项目，使用 Python、FastAPI 和 SQLite，实现文档解析、"
    "检索问答与引用展示，并通过测试集检查回答质量。"
)


def _payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=90,
        confirmed_facts=["独立开发课程资料问答项目"],
        missing_questions=[],
        normal_version="完成课程资料问答项目",
        bold_version="完成课程资料问答项目",
        boundary_version="完成课程资料问答项目",
        recommended_version="完成课程资料问答项目",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            summary=["具备独立项目交付能力"],
            skills=["编程语言：Python", "后端开发：FastAPI、SQLite"],
            projects=[{
                "name": "课程资料问答项目",
                "meta": "项目经历",
                "time": "[待填写]",
                "intro": "面向课程资料检索与问答场景",
                "role": "独立完成项目设计与开发",
                "details": ["实现文档解析、检索问答与引用展示，并通过测试集检查回答质量"],
                "source_experience_id": "EXP-001",
                "source_fact_ids": ["EXP-001-F001"],
                "detail_fact_ids": [["EXP-001-F001"]],
            }],
        ),
    )


def test_delivery_gate_cleans_internal_fields_from_all_visible_versions():
    dirty = _payload()
    dirty.normal_version = "根据 raw_text 整理项目事实"
    dirty.bold_version = "使用 source_experience_id 约束经历边界"
    dirty.boundary_version = "每条事实绑定 source_fact_ids"
    dirty.recommended_version = "通过 fact_id 保持事实归属"
    dirty.resume_sections.projects[0]["details"].append(
        "使用 source_experience_id 约束项目详情"
    )

    result = ensure_resume_delivery_quality(dirty, RAW, write_log=False)

    assert find_internal_field_leaks(result) == []
    assert "原始经历文本" in result.normal_version
    assert "经历来源标识" in result.bold_version
    assert "事实来源标识" in result.boundary_version
    assert "事实来源标识" in result.recommended_version


def test_delivery_gate_keeps_recruiter_facing_product_concepts_and_fact_coverage():
    raw = RAW + "项目中引入 Experience ID 与 Fact Ledger，约束多经历事实归属。"
    dirty = _payload()
    dirty.resume_sections.projects[0]["details"].append(
        "引入 Experience ID 与 Fact Ledger，约束多经历事实归属"
    )
    before = measure_high_value_fact_coverage(dirty, raw)

    result = ensure_resume_delivery_quality(dirty, raw, write_log=False)

    text = json.dumps(result.model_dump(), ensure_ascii=False)
    assert "Experience ID" in text
    assert "Fact Ledger" in text
    assert measure_high_value_fact_coverage(result, raw) >= before
    assert find_internal_field_leaks(result) == []


def test_visible_internal_field_cleanup_is_idempotent():
    dirty = _payload()
    dirty.recommended_version = "通过 source_fact_ids 与 claim_id 记录来源"

    once = ensure_resume_delivery_quality(dirty, RAW, write_log=False)
    twice = ensure_resume_delivery_quality(once, RAW, write_log=False)

    assert once.model_dump() == twice.model_dump()


def test_smoke_reports_marker_and_field_path_without_visible_text():
    generation = {
        "result": _payload().model_dump(),
    }
    generation["result"]["recommended_version"] = "通过 source_fact_ids 绑定课程资料事实"

    with pytest.raises(SmokeFailure, match="internal_field_leak") as raised:
        validate_generation(generation)

    assert raised.value.details["leaked_markers"] == ["source_fact_ids"]
    assert raised.value.details["affected_field_paths"] == ["recommended_version"]
    assert "课程资料" not in json.dumps(raised.value.details, ensure_ascii=False)


class _PollutedFullSmokeClient:
    def __init__(self):
        self.deleted = False

    def json(self, path, *, method="GET", payload=None, origin=False):
        if path == "/api/identity":
            return 200, {"ok": True}, {}
        if path == "/api/events":
            return 200, {"ok": True}, {}
        if path == "/api/generation-attempts":
            generation = {
                "generation_result_id": 83,
                "result": _payload().model_dump(),
            }
            generation["result"]["recommended_version"] = "fact_id=EXP-001-F001"
            return 202, {"status": "succeeded", "generation": generation}, {"x-request-id": "req_smokev083"}
        if path == "/api/privacy/my-data":
            self.deleted = True
            return 200, {"ok": True}, {}
        raise AssertionError(path)


def test_full_smoke_failure_keeps_safe_trace_context_and_cleanup_status():
    client = _PollutedFullSmokeClient()

    with pytest.raises(SmokeFailure, match="internal_field_leak") as raised:
        run_full(client)

    details = raised.value.details
    assert client.deleted is True
    assert details["request_id"] == "req_smokev083"
    assert details["generation_result_id"] == 83
    assert details["cleanup_attempted"] is True
    assert details["cleanup_passed"] is True
    assert details["leaked_markers"] == ["fact_id"]
    assert details["affected_field_paths"] == ["recommended_version"]
    assert "EXP-001-F001" not in json.dumps(details, ensure_ascii=False)


def test_full_smoke_report_persists_safe_failure_details(tmp_path, monkeypatch):
    def fail_full(*args, **kwargs):
        raise SmokeFailure(
            "internal_field_leak",
            details={
                "attempt_id": "smoke_report",
                "request_id": "req_smokereport",
                "generation_result_id": 84,
                "cleanup_passed": True,
                "leaked_markers": ["fact_id"],
                "affected_field_paths": ["recommended_version"],
            },
        )

    monkeypatch.setattr(smoke_module, "run_full", fail_full)
    monkeypatch.setattr(sys, "argv", [
        "run_public_smoke_test.py",
        "--base", "https://resume.example.test",
        "--mode", "full",
        "--out", str(tmp_path),
    ])

    with pytest.raises(SystemExit) as raised:
        smoke_module.main()

    assert raised.value.code == 2
    report = json.loads((tmp_path / "public-smoke-full-latest.json").read_text(encoding="utf-8"))
    assert report["generation_result_id"] == 84
    assert report["cleanup_passed"] is True
    assert report["leaked_markers"] == ["fact_id"]
    assert report["affected_field_paths"] == ["recommended_version"]
    assert "简历正文" not in json.dumps(report, ensure_ascii=False)


def test_smoke_accepts_payload_after_delivery_gate_cleanup():
    dirty = _payload()
    dirty.recommended_version = "使用 source_experience_id 约束事实边界"
    clean = ensure_resume_delivery_quality(dirty, RAW, write_log=False)

    metrics = validate_generation({"result": clean.model_dump()})

    assert metrics["internal_field_leak_count"] == 0
