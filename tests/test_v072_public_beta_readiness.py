from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from backend.app import models
from backend.app.config import get_settings
from backend.app.database import Base
from backend.app.routers import privacy
from backend.app.services.backup_service import create_sqlite_backup, database_integrity, verify_restore
from backend.app.services import data_lifecycle_service
from backend.app.services.data_lifecycle_service import cleanup_expired_data, delete_anonymous_user_data
from scripts.launch_preflight import run_checks


def _db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_generation(db, user, *, session_id: str, created_at: datetime, file_path: Path):
    experience = models.ExperienceInput(
        anonymous_user_id=user.id,
        session_id=session_id,
        target_role="开发工程师",
        mode="full_resume",
        packaging_level="稳健",
        experience_type="项目经历",
        raw_input="匿名测试经历",
        created_at=created_at,
    )
    db.add(experience)
    db.flush()
    result = models.GenerationResult(
        experience_input_id=experience.id,
        completeness_score=80,
        result_json='{"resume_sections": {}}',
        created_at=created_at,
    )
    db.add(result)
    db.flush()
    version = models.ResumeVersion(
        generation_result_id=result.id,
        version_type="recommended",
        content_json="{}",
        created_at=created_at,
    )
    db.add(version)
    db.flush()
    generated_file = models.GeneratedFile(
        generation_result_id=result.id,
        resume_version_id=version.id,
        file_type="docx",
        file_path=str(file_path),
        created_at=created_at,
    )
    db.add(generated_file)
    db.add(models.Claim(
        generation_result_id=result.id,
        claim="匿名事实",
        risk_level="low",
    ))
    db.add(models.LLMCallLog(
        generation_result_id=result.id,
        mode="mock",
        success=1,
        created_at=created_at,
    ))
    db.add(models.Feedback(
        anonymous_user_id=user.id,
        session_id=session_id,
        generation_result_id=result.id,
        model_comparison="better",
        value_choice="0",
        created_at=created_at,
    ))
    return experience, result, generated_file


def test_user_deletion_removes_only_the_signed_users_graph_and_docx(tmp_path):
    db = _db_session()
    owner = models.AnonymousUser(anonymous_id="anon-owner")
    other = models.AnonymousUser(anonymous_id="anon-other")
    db.add_all([owner, other])
    db.flush()
    for user, session_id in [(owner, "owner-session"), (other, "other-session")]:
        db.add(models.SessionRecord(
            anonymous_user_id=user.id,
            session_id=session_id,
        ))
        db.add(models.Event(
            anonymous_user_id=user.id,
            session_id=session_id,
            event_name="visit_home",
        ))
    owner_file = tmp_path / "owner.docx"
    other_file = tmp_path / "other.docx"
    owner_file.write_bytes(b"owner")
    other_file.write_bytes(b"other")
    _, owner_result, _ = _add_generation(
        db, owner, session_id="owner-session", created_at=datetime.utcnow(), file_path=owner_file,
    )
    _, other_result, _ = _add_generation(
        db, other, session_id="other-session", created_at=datetime.utcnow(), file_path=other_file,
    )
    cross_linked_feedback = models.Feedback(
        anonymous_user_id=other.id,
        session_id="other-session",
        generation_result_id=owner_result.id,
        model_comparison="same",
        value_choice="0",
    )
    db.add(cross_linked_feedback)
    db.commit()
    cross_linked_feedback_id = cross_linked_feedback.id

    stats = delete_anonymous_user_data(db, "anon-owner", output_dir=tmp_path)

    assert stats.users == 1
    assert stats.files_removed == 1
    assert not owner_file.exists()
    assert other_file.exists()
    assert db.query(models.AnonymousUser).filter_by(anonymous_id="anon-owner").first() is None
    assert db.query(models.AnonymousUser).filter_by(anonymous_id="anon-other").first() is not None
    assert db.query(models.GenerationResult).filter_by(id=other_result.id).first() is not None
    preserved_feedback = db.query(models.Feedback).filter_by(id=cross_linked_feedback_id).first()
    assert preserved_feedback is not None
    assert preserved_feedback.generation_result_id is None


def test_user_deletion_fails_before_database_commit_when_a_file_is_unsafe(tmp_path):
    db = _db_session()
    owner = models.AnonymousUser(anonymous_id="anon-owner")
    db.add(owner)
    db.flush()
    outside = tmp_path.parent / "outside.docx"
    outside.write_bytes(b"private")
    _add_generation(db, owner, session_id="owner-session", created_at=datetime.utcnow(), file_path=outside)
    db.commit()

    try:
        try:
            delete_anonymous_user_data(db, "anon-owner", output_dir=tmp_path)
            raise AssertionError("unsafe file path should reject deletion")
        except RuntimeError:
            pass
        assert db.query(models.AnonymousUser).filter_by(anonymous_id="anon-owner").first() is not None
        assert outside.exists()
    finally:
        outside.unlink(missing_ok=True)


def test_retention_dry_run_keeps_rows_and_real_cleanup_keeps_fresh_content(tmp_path, monkeypatch):
    settings = replace(
        get_settings(),
        user_content_retention_days=30,
        generated_file_retention_days=7,
        analytics_retention_days=90,
    )
    monkeypatch.setattr(data_lifecycle_service, "get_settings", lambda: settings)
    db = _db_session()
    now = datetime.utcnow()
    old_user = models.AnonymousUser(
        anonymous_id="anon-old", first_seen_at=now - timedelta(days=120), last_seen_at=now - timedelta(days=120),
    )
    fresh_user = models.AnonymousUser(anonymous_id="anon-fresh", first_seen_at=now, last_seen_at=now)
    db.add_all([old_user, fresh_user])
    db.flush()
    old_file = tmp_path / "old.docx"
    fresh_file = tmp_path / "fresh.docx"
    old_file.write_bytes(b"old")
    fresh_file.write_bytes(b"fresh")
    _add_generation(db, old_user, session_id="old", created_at=now - timedelta(days=40), file_path=old_file)
    _, fresh_result, _ = _add_generation(db, fresh_user, session_id="fresh", created_at=now, file_path=fresh_file)
    db.commit()

    preview = cleanup_expired_data(db, now=now, output_dir=tmp_path, dry_run=True)
    assert preview.experience_inputs == 1
    assert db.query(models.ExperienceInput).count() == 2
    assert old_file.exists()

    cleanup_expired_data(db, now=now, output_dir=tmp_path)
    assert not old_file.exists()
    assert fresh_file.exists()
    assert db.query(models.GenerationResult).filter_by(id=fresh_result.id).first() is not None


def test_sqlite_online_backup_and_temporary_restore_do_not_replace_source(tmp_path):
    source = tmp_path / "production.sqlite3"
    connection = sqlite3.connect(source)
    connection.execute("create table sample (id integer primary key, value text)")
    connection.execute("insert into sample(value) values ('safe')")
    connection.commit()
    connection.close()

    backup = create_sqlite_backup(source, tmp_path / "backups")
    restored = verify_restore(backup)

    assert restored["ok"] is True
    assert restored["table_count"] == 1
    assert database_integrity(source) == (True, "ok")
    connection = sqlite3.connect(source)
    try:
        assert connection.execute("select value from sample").fetchone()[0] == "safe"
    finally:
        connection.close()


def _request(origin: str | None) -> Request:
    headers = [] if origin is None else [(b"origin", origin.encode("ascii"))]
    return Request({"type": "http", "method": "DELETE", "path": "/api/privacy/my-data", "headers": headers})


def test_production_data_deletion_requires_an_allowed_origin(monkeypatch):
    settings = replace(
        get_settings(), environment="production", allowed_origins=["https://resume.example.com"],
    )
    monkeypatch.setattr(privacy, "get_settings", lambda: settings)
    privacy._validate_request_origin(_request("https://resume.example.com"))
    for origin in [None, "https://attacker.example"]:
        try:
            privacy._validate_request_origin(_request(origin))
            raise AssertionError("untrusted deletion request should be rejected")
        except HTTPException as exc:
            assert exc.status_code == 403


def test_public_policy_and_footer_configuration_are_present():
    root = Path(__file__).resolve().parents[1]
    legal = (root / "frontend" / "src" / "pages" / "LegalPage.tsx").read_text(encoding="utf-8")
    app = (root / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert all(text in legal for text in ["隐私政策", "服务条款", "AI 辅助生成说明", "删除我的数据"])
    assert all(text in app for text in ["VITE_ICP_NUMBER", "VITE_PUBLIC_SECURITY_NUMBER", "#/privacy"])


def test_preflight_fails_closed_without_secrets_redis_or_backup_and_never_echoes_secrets(tmp_path):
    for relative in ["backend/logs", "backend/outputs", "backend/reports", "backend/backups", "frontend/dist/assets"]:
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)
    (tmp_path / "frontend" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    (tmp_path / "frontend" / "dist" / "assets" / "app.js").write_text("", encoding="utf-8")
    database = tmp_path / "backend" / "data" / "resume.sqlite3"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    connection.execute("create table sample (id integer primary key)")
    connection.close()
    secret_value = "do-not-print-this-secret"
    env_path = tmp_path / "production.env"
    env_path.write_text(
        "\n".join([
            "APP_ENV=production",
            "ANONYMOUS_COOKIE_SECRET=change-me",
            f"DOWNLOAD_SIGNING_SECRET={secret_value}",
            "IP_HASH_SECRET=change-me",
            "ALLOWED_HOSTS=resume.example.com,127.0.0.1",
            "ALLOWED_ORIGINS=https://resume.example.com",
            "REDIS_URL=",
            f"DATABASE_URL=sqlite:///{database.as_posix()}",
            "RATE_LIMIT_DRY_RUN=true",
        ]),
        encoding="utf-8",
    )

    checks = run_checks(
        env_path=env_path,
        local_base="http://127.0.0.1:9",
        public_base="",
        backup_dir=tmp_path / "backend" / "backups",
        project_root=tmp_path,
    )
    status_by_name = {check.name: check.status for check in checks}
    output = "\n".join(check.message for check in checks)
    assert status_by_name["production secrets"] == "failed"
    assert status_by_name["Redis"] == "failed"
    assert status_by_name["recent verified backup"] == "failed"
    assert secret_value not in output
