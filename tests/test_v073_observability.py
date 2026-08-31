import json
from datetime import datetime
from pathlib import Path

import pytest

from backend.app.services.request_id_service import is_valid_request_id, resolve_request_id
from scripts.check_operational_slo import evaluate_slo
from scripts.list_recent_quality_incidents import collect_incidents, render_text
from scripts.run_public_smoke_test import SmokeFailure, _generation_quality_summary, run_full, validate_generation
from scripts.run_release_quality_gate import write_record


def _write_rows(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _now():
    return "2099-08-31T12:00:00+08:00"


def test_request_id_accepts_only_the_supported_safe_format():
    safe = "req_abcdefgh_12345678"
    assert is_valid_request_id(safe)
    assert resolve_request_id(safe) == safe
    for unsafe in ["req_short", "req_bad\nheader123", "other_abcdefgh", "req_" + "a" * 81]:
        replacement = resolve_request_id(unsafe)
        assert replacement != unsafe
        assert is_valid_request_id(replacement)


def test_quality_incidents_link_request_attempt_result_and_legacy_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.list_recent_quality_incidents.cutoff_for_hours", lambda _hours: None)
    _write_rows(tmp_path / "generation_queue.jsonl", [{
        "created_at": _now(), "event_name": "generation_task_succeeded",
        "request_id": "req_trace12345678", "attempt_id": "attempt-1", "generation_result_id": 42,
    }])
    _write_rows(tmp_path / "resume_delivery_quality_gate.jsonl", [
        {
            "created_at": _now(), "generation_result_id": 42, "stage": "generation",
            "critical_issue_count": 1, "unresolved_issue_count": 1, "gate_passed": False,
            "issues": [{"issue_code": "CROSS_EXPERIENCE_FACT"}],
        },
        {
            "created_at": _now(), "generation_result_id": 9, "stage": "generation",
            "critical_issue_count": 0, "unresolved_issue_count": 1, "gate_passed": False,
            "issues": [{"issue_code": "LOW_HIGH_VALUE_FACT_COVERAGE"}],
        },
    ])
    incidents = collect_incidents(tmp_path, request_id="req_trace12345678")
    assert len(incidents) == 1
    assert incidents[0]["attempt_id"] == "attempt-1"
    assert incidents[0]["generation_result_id"] == 42
    assert incidents[0]["legacy"] is False
    all_incidents = collect_incidents(tmp_path)
    assert any(item["legacy"] for item in all_incidents)
    output = render_text(all_incidents)
    assert "raw_input" not in output
    assert "resume body" not in output


def test_quality_incidents_do_not_cross_link_reused_result_ids(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.list_recent_quality_incidents.cutoff_for_hours", lambda _hours: None)
    _write_rows(tmp_path / "generation_queue.jsonl", [{
        "created_at": "2099-08-31T12:00:00+08:00", "event_name": "generation_task_succeeded",
        "request_id": "req_current12345678", "attempt_id": "attempt-current", "generation_result_id": 1,
    }])
    _write_rows(tmp_path / "resume_delivery_quality_gate.jsonl", [
        {
            "created_at": "2099-08-31T12:00:02+08:00", "generation_result_id": 1,
            "critical_issue_count": 1, "unresolved_issue_count": 1, "gate_passed": False,
            "issues": [{"issue_code": "UNSUPPORTED_HARD_FACT"}],
        },
        {
            "created_at": "2099-08-31T11:00:00+08:00", "generation_result_id": 1,
            "critical_issue_count": 1, "unresolved_issue_count": 1, "gate_passed": False,
            "issues": [{"issue_code": "CROSS_EXPERIENCE_FACT"}],
        },
    ])
    linked = collect_incidents(tmp_path, request_id="req_current12345678")
    assert len(linked) == 1
    assert linked[0]["issue_codes"] == ["UNSUPPORTED_HARD_FACT"]
    all_incidents = collect_incidents(tmp_path)
    assert any(item["legacy"] and item["issue_codes"] == ["CROSS_EXPERIENCE_FACT"] for item in all_incidents)


def test_slo_thresholds_exclude_smoke_and_return_critical_for_low_success(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.check_operational_slo.cutoff_for_hours", lambda _hours: None)
    success = [{
        "created_at": _now(), "event_name": "generation_task_succeeded",
        "request_id": f"req_success{index:08d}", "attempt_id": f"attempt-{index}", "elapsed_ms": 70_000,
    } for index in range(7)]
    smoke = [{
        "created_at": _now(), "event_name": "generation_task_succeeded",
        "request_id": "req_smoke12345678", "attempt_id": "smoke_ignore", "elapsed_ms": 1,
    }]
    failed = [{
        "created_at": _now(), "event_name": "generation_task_failed",
        "request_id": f"req_failed{index:08d}", "attempt_id": f"attempt-failed-{index}", "elapsed_ms": 100_000,
    } for index in range(3)]
    _write_rows(tmp_path / "generation_queue.jsonl", success + smoke)
    _write_rows(tmp_path / "runtime.jsonl", failed)
    backups = tmp_path / "backups"
    backups.mkdir()
    backup = backups / "latest.sqlite3"
    backup.write_bytes(b"backup")
    report = evaluate_slo(tmp_path, backups_dir=backups, project_root=tmp_path)
    assert report["sample_count"] == 10
    assert report["status"] == "critical"
    by_name = {item["metric"]: item for item in report["metrics"]}
    assert by_name["generation_success_rate"]["value"] == 0.7
    assert by_name["generation_p90_ms"]["status"] == "critical"


def test_slo_ignores_untraceable_test_rows(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.check_operational_slo.cutoff_for_hours", lambda _hours: None)
    _write_rows(tmp_path / "generation_queue.jsonl", [{
        "created_at": _now(), "event_name": "generation_admission",
        "attempt_id": "attempt-test-only", "status": "full",
    }])
    _write_rows(tmp_path / "generation_stability.jsonl", [{
        "created_at": _now(), "attempt_id": "attempt-test-only", "generation_result_id": 1,
        "unresolved_critical_issue_count": 3,
    }])
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "latest.sqlite3").write_bytes(b"backup")
    report = evaluate_slo(tmp_path, backups_dir=backups, project_root=tmp_path)
    by_name = {item["metric"]: item for item in report["metrics"]}
    assert by_name["queue_full_count"]["value"] == 0
    assert by_name["unresolved_delivery_quality_issues"]["value"] == 0


def test_smoke_generation_validation_rejects_internal_fields():
    valid = {
        "result": {
            "resume_sections": {
                "summary": ["具备项目交付能力"],
                "skills": ["编程语言：Python"],
                "projects": [{"name": "问答项目", "intro": "面向课程资料检索", "role": "独立开发", "details": ["实现文档解析与检索问答"]}],
            }
        }
    }
    assert validate_generation(valid)["project_count"] == 1
    polluted = json.loads(json.dumps(valid, ensure_ascii=False))
    polluted["result"]["resume_sections"]["projects"][0]["details"].append("source_experience_id=EXP-001")
    with pytest.raises(SmokeFailure, match="internal_field_leak"):
        validate_generation(polluted)


class _FailingSmokeClient:
    def __init__(self):
        self.deleted = False

    def json(self, path, *, method="GET", payload=None, origin=False):
        if path == "/api/identity":
            return 200, {"ok": True}, {}
        if path == "/api/events":
            return 200, {"ok": True}, {}
        if path == "/api/generation-attempts":
            return 202, {"status": "failed"}, {}
        if path == "/api/privacy/my-data":
            self.deleted = True
            return 200, {"ok": True}, {}
        raise AssertionError(path)


def test_full_smoke_always_attempts_cleanup_after_generation_failure():
    client = _FailingSmokeClient()
    with pytest.raises(SmokeFailure):
        run_full(client)
    assert client.deleted is True


def test_full_smoke_quality_summary_rejects_unresolved_critical(tmp_path):
    _write_rows(tmp_path / "generation_stability.jsonl", [{
        "created_at": _now(), "attempt_id": "smoke_quality", "generation_result_id": 7,
        "unresolved_critical_issue_count": 1, "high_value_fact_coverage": 1.0,
        "projects_missing_source_id": 0,
    }])
    summary = _generation_quality_summary(
        tmp_path, "smoke_quality", 7,
        datetime.fromisoformat("2099-08-31T11:59:00+08:00"),
    )
    assert summary["unresolved_critical_issue_count"] == 1


def test_release_record_is_bound_to_the_exact_commit(tmp_path):
    commit = "a" * 40
    path = write_record(tmp_path, commit, ["tests/test_golden_resume_regression.py"], True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["commit"] == commit
    assert payload["golden_regression_passed"] is True


def test_frontend_support_code_and_release_identity_are_user_visible():
    root = Path(__file__).resolve().parents[1]
    client = (root / "frontend/src/api/client.ts").read_text(encoding="utf-8")
    support = (root / "frontend/src/components/SupportCode.tsx").read_text(encoding="utf-8")
    result_page = (root / "frontend/src/pages/ResultPage.tsx").read_text(encoding="utf-8")
    assert "X-Request-ID" in client
    assert "暂未生成问题编号" in support
    assert "copy_support_code" in result_page
    assert "报告此结果问题" in result_page


def test_observability_scripts_do_not_embed_sensitive_resume_fields():
    root = Path(__file__).resolve().parents[1]
    for relative in [
        "scripts/list_recent_quality_incidents.py",
        "scripts/check_operational_slo.py",
        "scripts/run_public_smoke_test.py",
    ]:
        content = (root / relative).read_text(encoding="utf-8")
        assert "OPENAI_API_KEY" not in content
        assert "result_json" not in content
