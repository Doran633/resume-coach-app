import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.audit_database_portability import audit_database, render_markdown as render_database_markdown
from scripts.check_operations_freshness import evaluate_freshness
from scripts.check_output_quality_drift import analyze_quality, baseline_write_allowed, collect_quality_windows, evaluate_drift
from scripts.evaluate_rate_limit_rollout import evaluate_rollout
from scripts.export_operations_status import _update_alerts
from scripts.operations_common import BEIJING, exclusive_operation_lock
from scripts.run_public_beta_operations import Task, build_tasks, execute_tasks
from scripts.verify_rollback_readiness import evaluate_rollback


def _write_rows(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(BEIJING).isoformat()


def test_operation_lock_blocks_overlap_and_is_released(tmp_path):
    lock = tmp_path / "operations.lock"
    with exclusive_operation_lock(lock):
        assert lock.exists()
        with pytest.raises(RuntimeError, match="operation lock is active"):
            with exclusive_operation_lock(lock):
                pass
    assert not lock.exists()


def test_dry_run_plans_tasks_without_executing_commands(tmp_path, monkeypatch):
    def fail_run(*_args, **_kwargs):
        raise AssertionError("subprocess must not run during dry-run")

    monkeypatch.setattr("scripts.run_public_beta_operations.subprocess.run", fail_run)
    tasks = build_tasks(
        "daily", public_base="https://resume.example.com", backups=tmp_path / "backups",
        reports=tmp_path / "reports", env_path=tmp_path / "env", frontend_env=tmp_path / "frontend.env",
        full_smoke=False,
    )
    results, code = execute_tasks(tasks, dry_run=True, project_root=tmp_path)
    assert code == 0
    assert all(item["status"] == "planned" for item in results)
    assert any(item["task"] == "quality_drift" for item in results)


def test_task_failures_do_not_stop_later_checks(tmp_path, monkeypatch):
    class Result:
        def __init__(self, code):
            self.returncode = code

    codes = iter([2, 0])
    monkeypatch.setattr("scripts.run_public_beta_operations.subprocess.run", lambda *_args, **_kwargs: Result(next(codes)))
    results, code = execute_tasks([
        Task("failed", ["python", "failed.py"]), Task("continued", ["python", "continued.py"]),
    ], project_root=tmp_path)
    assert code == 2
    assert [item["task"] for item in results] == ["failed", "continued"]
    assert results[1]["status"] == "passed"


def test_quality_drift_excludes_smoke_and_observes_small_samples(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.check_output_quality_drift.cutoff_for_hours", lambda _hours: None)
    _write_rows(tmp_path / "generation_stability.jsonl", [
        {
            "created_at": _now(), "attempt_id": "attempt-real", "generation_result_id": 7,
            "high_value_fact_coverage": 1.0, "projects_with_source_id": 1,
            "projects_missing_source_id": 0, "unresolved_critical_issue_count": 0,
        },
        {
            "created_at": _now(), "attempt_id": "smoke_ignore", "generation_result_id": 8,
            "high_value_fact_coverage": 0.0, "projects_with_source_id": 0,
            "projects_missing_source_id": 2, "unresolved_critical_issue_count": 3,
        },
    ])
    report = evaluate_drift(analyze_quality(tmp_path, project_root=Path(__file__).resolve().parents[1]))
    assert report["sample_count"] == 1
    assert report["status"] == "observe"
    assert report["metrics"]["high_value_fact_coverage"] == 1.0


def test_quality_drift_marks_unresolved_output_as_critical(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.check_output_quality_drift.cutoff_for_hours", lambda _hours: None)
    rows = [{
        "created_at": _now(), "attempt_id": f"attempt-{index}", "generation_result_id": index + 1,
        "high_value_fact_coverage": 0.95, "projects_with_source_id": 1,
        "projects_missing_source_id": 0, "unresolved_critical_issue_count": 1 if index == 0 else 0,
    } for index in range(10)]
    _write_rows(tmp_path / "generation_stability.jsonl", rows)
    report = evaluate_drift(analyze_quality(tmp_path, project_root=Path(__file__).resolve().parents[1]))
    assert report["status"] == "critical"
    assert any(item["issue_code"] == "UNRESOLVED_OUTPUT_CRITICAL" for item in report["findings"])


def test_quality_baseline_cannot_promote_small_or_critical_samples():
    assert baseline_write_allowed({"sample_count": 9, "status": "healthy"}) is False
    assert baseline_write_allowed({"sample_count": 20, "status": "critical"}) is False
    assert baseline_write_allowed({"sample_count": 20, "status": "healthy"}) is True


def test_quality_report_has_24h_72h_and_current_build_windows(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.check_output_quality_drift.cutoff_for_hours", lambda _hours: None)
    monkeypatch.setattr("scripts.check_output_quality_drift._git_commit", lambda _root: "abc12345")
    _write_rows(tmp_path / "runtime.jsonl", [{
        "created_at": _now(), "event_name": "service_started", "build_commit": "abc12345",
    }])
    _write_rows(tmp_path / "generation_stability.jsonl", [{
        "created_at": _now(), "attempt_id": "attempt-real", "generation_result_id": 1,
        "high_value_fact_coverage": 1.0, "projects_with_source_id": 1, "projects_missing_source_id": 0,
    }])
    windows = collect_quality_windows(tmp_path, project_root=Path(__file__).resolve().parents[1])
    assert set(windows) == {"24h", "72h", "current_build"}
    assert windows["current_build"]["sample_count"] == 1


def test_missing_scheduled_run_is_not_treated_as_success(tmp_path):
    report = evaluate_freshness(tmp_path / "reports", tmp_path / "logs", tmp_path / "backups")
    assert report["status"] == "critical"
    by_name = {item["check"]: item for item in report["checks"]}
    assert by_name["database_backup"]["status"] == "critical"
    assert by_name["full_smoke"]["status"] == "observe"


def test_rate_limit_rollout_protects_shared_campus_ip(tmp_path, monkeypatch):
    monkeypatch.setattr("scripts.evaluate_rate_limit_rollout.cutoff_for_hours", lambda _hours: None)
    admissions = [{
        "created_at": _now(), "event_name": "generation_admission", "attempt_id": f"attempt-{index}",
        "anonymous_id_hash": f"user-{index % 4}", "ip_hash": "campus-ip", "status": "accepted",
    } for index in range(20)]
    _write_rows(tmp_path / "generation_queue.jsonl", admissions)
    _write_rows(tmp_path / "security_events.jsonl", [{
        "created_at": _now(), "event_name": "generation_rate_limited", "anonymous_id_hash": "user-1",
        "ip_hash": "campus-ip", "error_type": "IP_RATE_LIMITED", "dry_run": True,
    }])
    report = evaluate_rollout(tmp_path)
    assert report["shared_ip_group_count"] == 1
    assert report["recommendation"] == "暂不建议启用"
    assert "47.116" not in json.dumps(report)


def test_database_audit_is_read_only_and_contains_no_row_content(tmp_path):
    database = tmp_path / "resume.db"
    connection = sqlite3.connect(database)
    connection.execute("create table notes(id integer primary key, content text)")
    connection.execute("insert into notes(content) values (?)", ("private resume body",))
    connection.commit()
    connection.close()
    before = database.read_bytes()
    source = tmp_path / "source"
    source.mkdir()
    (source / "models.py").write_text("from sqlalchemy import Column\n", encoding="utf-8")
    report = audit_database(database, source_root=source, logs_dir=tmp_path / "logs", backups_dir=tmp_path / "backups")
    after = database.read_bytes()
    output = json.dumps(report, ensure_ascii=False) + render_database_markdown(report)
    assert before == after
    assert report["table_row_counts"] == {"notes": 1}
    assert "private resume body" not in output
    assert report["production_database_modified"] is False


def test_systemd_templates_do_not_contain_secrets():
    root = Path(__file__).resolve().parents[1]
    for path in (root / "deploy" / "systemd").glob("*"):
        content = path.read_text(encoding="utf-8")
        assert "OPENAI_API_KEY=" not in content
        assert "COOKIE_SECRET=" not in content
        assert "EnvironmentFile=/etc/resume-coach/resume-coach.env" in content or path.suffix == ".timer"


def test_alerts_merge_by_issue_code_without_resume_content(tmp_path):
    now = datetime.now(BEIJING)
    incidents = [
        {"issue_codes": ["CROSS_EXPERIENCE_FACT"], "severity": "warning", "request_id": "req_abcdefgh12345678", "generation_result_id": 7},
        {"issue_codes": ["CROSS_EXPERIENCE_FACT"], "severity": "warning", "request_id": "req_abcdefgh12345678", "generation_result_id": 7},
    ]
    payload = _update_alerts(tmp_path, {}, incidents, now)
    assert payload["alert_count"] == 1
    output = (tmp_path / "operations-alert-latest.md").read_text(encoding="utf-8")
    assert "CROSS_EXPERIENCE_FACT" in output
    assert "raw_input" not in output


def test_rollback_check_never_switches_git_or_overwrites_database(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    current = "a" * 40
    (reports / "release-verification-current.json").write_text(json.dumps({
        "created_at": "2099-01-02T00:00:00+00:00", "commit": current,
        "short_commit": current[:8], "golden_regression_passed": True,
    }), encoding="utf-8")
    monkeypatch.setattr("scripts.verify_rollback_readiness._git", lambda *_args: current)
    monkeypatch.setattr("scripts.verify_rollback_readiness.latest_backup", lambda *_args: None)
    report = evaluate_rollback(Path(__file__).resolve().parents[1], reports, tmp_path / "backups")
    assert report["automatic_rollback_performed"] is False
    assert report["production_database_modified"] is False


def test_new_operations_scripts_do_not_read_sensitive_resume_payloads():
    root = Path(__file__).resolve().parents[1]
    for name in [
        "check_output_quality_drift.py", "check_operations_freshness.py",
        "evaluate_rate_limit_rollout.py", "audit_database_portability.py",
        "verify_rollback_readiness.py", "export_operations_status.py",
        "run_public_beta_operations.py",
    ]:
        content = (root / "scripts" / name).read_text(encoding="utf-8")
        assert "result_json" not in content
        assert "OPENAI_API_KEY" not in content
        assert "raw_input" not in content
