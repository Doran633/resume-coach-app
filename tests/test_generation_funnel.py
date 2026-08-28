import json
import sqlite3
from pathlib import Path

from scripts.export_generation_funnel import build_report, export_report


def _create_db(path: Path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table anonymous_users (id integer primary key, anonymous_id text);
        create table events (
            id integer primary key,
            anonymous_user_id integer,
            session_id text,
            event_name text,
            payload_json text,
            created_at text
        );
        create table generation_results (id integer primary key, created_at text);
        create table generated_files (id integer primary key, created_at text);
        create table feedback (id integer primary key, created_at text);
        insert into anonymous_users values (1, 'anon-test');
        """
    )
    events = [
        (1, "submit_experience", {"attempt_id": "attempt-1", "input_length": 120}),
        (2, "generate_success", {"attempt_id": "attempt-1", "generation_result_id": 10, "elapsed_ms": 40000}),
        (3, "view_generation_result", {"attempt_id": "attempt-1", "generation_result_id": 10}),
        (4, "generate_docx", {"attempt_id": "attempt-1", "generation_result_id": 10}),
        (5, "download_docx", {"attempt_id": "attempt-1", "generation_result_id": 10}),
        (6, "submit_experience", {"attempt_id": "attempt-2", "input_length": 80}),
        (7, "generate_failed", {"attempt_id": "attempt-2", "error_type": "timeout", "elapsed_ms": 70000}),
        (8, "submit_experience", {"raw_input": "历史敏感原文，不得进入报告"}),
    ]
    conn.executemany(
        "insert into events values (?, 1, 'session-test', ?, ?, '2026-08-29 01:00:00')",
        [(event_id, name, json.dumps(payload, ensure_ascii=False)) for event_id, name, payload in events],
    )
    conn.execute("insert into generation_results values (10, '2026-08-29 01:00:01')")
    conn.execute("insert into generated_files values (20, '2026-08-29 01:00:02')")
    conn.commit()
    conn.close()


def test_generation_funnel_correlates_attempts_without_exporting_raw_input(tmp_path):
    db_path = tmp_path / "resume.db"
    logs = tmp_path / "logs"
    logs.mkdir()
    _create_db(db_path)

    report = build_report(db_path, logs)

    assert "生成尝试次数 | 2" in report
    assert "生成成功次数 | 1" in report
    assert "生成失败次数 | 1" in report
    assert "timeout | 1" in report
    assert "超过 35 秒：2" in report
    assert "超过 60 秒：1" in report
    assert "缺少 attempt_id 的历史生成相关事件：1" in report
    assert "历史敏感原文" not in report


def test_generation_funnel_exports_when_optional_logs_are_missing(tmp_path):
    db_path = tmp_path / "resume.db"
    logs = tmp_path / "missing-logs"
    out = tmp_path / "reports"
    _create_db(db_path)

    path = export_report(db_path, logs, out)

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "暂无对应日志" in content


def test_submit_experience_event_does_not_spread_backend_payload():
    source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "InputPage.tsx").read_text(encoding="utf-8")
    event_block = source.split('trackEvent(identity, "submit_experience"', 1)[1].split("});", 1)[0]
    assert "...backendValues" not in event_block
    assert "raw_input:" not in event_block
    assert "input_length:" in event_block
    assert "attempt_id:" in event_block


def test_attempt_ids_and_safe_operation_errors_are_wired_into_frontend():
    root = Path(__file__).resolve().parents[1] / "frontend" / "src"
    input_source = (root / "pages" / "InputPage.tsx").read_text(encoding="utf-8")
    result_source = (root / "pages" / "ResultPage.tsx").read_text(encoding="utf-8")
    export_source = (root / "pages" / "ExportPage.tsx").read_text(encoding="utf-8")

    assert "pendingAttemptIdRef.current || createAttemptId()" in input_source
    assert "pendingAttemptIdRef.current = attemptId" in input_source
    assert 'trackEvent(identity, "retry_generation"' in input_source
    assert 'trackEvent(identity, "generate_success"' in result_source
    assert 'trackEvent(identity, "generate_failed"' in result_source
    assert 'window.addEventListener("beforeunload"' in input_source
    assert 'window.addEventListener("beforeunload"' in result_source
    assert "error_type: errorInfo.type" in export_source
    assert "message: String(error)" not in export_source
    assert "form={feedbackForm}" in export_source
    assert "feedbackForm.resetFields" not in export_source
