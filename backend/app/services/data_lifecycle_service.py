from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models
from ..config import get_settings


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "outputs"


@dataclass
class DataDeletionStats:
    users: int = 0
    sessions: int = 0
    events: int = 0
    experience_inputs: int = 0
    generation_results: int = 0
    claims: int = 0
    llm_call_logs: int = 0
    resume_versions: int = 0
    generated_files: int = 0
    feedback: int = 0
    files_removed: int = 0
    files_cleanup_pending: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


def _safe_output_path(raw_path: str, output_dir: Path) -> Path | None:
    try:
        path = Path(raw_path).resolve()
        root = output_dir.resolve()
        return path if path == root or root in path.parents else None
    except (OSError, RuntimeError):
        return None


def _stage_files(paths: list[str], output_dir: Path) -> tuple[list[tuple[Path, Path]], int]:
    staged: list[tuple[Path, Path]] = []
    pending = 0
    quarantine = output_dir / ".deleting"
    for raw_path in dict.fromkeys(paths):
        source = _safe_output_path(raw_path, output_dir)
        if source is None:
            pending += 1
            continue
        if not source.exists():
            continue
        try:
            quarantine.mkdir(parents=True, exist_ok=True)
            target = quarantine / f"{uuid.uuid4().hex}-{source.name}"
            source.replace(target)
            staged.append((source, target))
        except OSError:
            pending += 1
    return staged, pending


def _restore_staged_files(staged: list[tuple[Path, Path]]) -> None:
    for source, target in reversed(staged):
        try:
            if target.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                target.replace(source)
        except OSError:
            continue


def _remove_staged_files(staged: list[tuple[Path, Path]]) -> tuple[int, int]:
    removed = 0
    pending = 0
    for _, target in staged:
        try:
            target.unlink(missing_ok=True)
            removed += 1
        except OSError:
            pending += 1
    return removed, pending


def _delete_generation_graph(db: Session, generation_ids: list[int], stats: DataDeletionStats) -> None:
    if not generation_ids:
        return
    stats.generated_files += db.query(models.GeneratedFile).filter(
        models.GeneratedFile.generation_result_id.in_(generation_ids)
    ).delete(synchronize_session=False)
    stats.resume_versions += db.query(models.ResumeVersion).filter(
        models.ResumeVersion.generation_result_id.in_(generation_ids)
    ).delete(synchronize_session=False)
    stats.claims += db.query(models.Claim).filter(
        models.Claim.generation_result_id.in_(generation_ids)
    ).delete(synchronize_session=False)
    stats.llm_call_logs += db.query(models.LLMCallLog).filter(
        models.LLMCallLog.generation_result_id.in_(generation_ids)
    ).delete(synchronize_session=False)
    stats.generation_results += db.query(models.GenerationResult).filter(
        models.GenerationResult.id.in_(generation_ids)
    ).delete(synchronize_session=False)


def delete_anonymous_user_data(
    db: Session,
    anonymous_id: str,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> DataDeletionStats:
    stats = DataDeletionStats()
    user = db.query(models.AnonymousUser).filter_by(anonymous_id=anonymous_id).first()
    if not user:
        return stats

    experience_ids = [
        row[0] for row in db.query(models.ExperienceInput.id).filter_by(anonymous_user_id=user.id).all()
    ]
    generation_ids = [
        row[0] for row in db.query(models.GenerationResult.id).filter(
            models.GenerationResult.experience_input_id.in_(experience_ids)
        ).all()
    ] if experience_ids else []
    file_paths = [
        row[0] for row in db.query(models.GeneratedFile.file_path).filter(
            models.GeneratedFile.generation_result_id.in_(generation_ids)
        ).all()
    ] if generation_ids else []
    staged, unsafe_count = _stage_files(file_paths, output_dir)
    if unsafe_count:
        _restore_staged_files(staged)
        raise RuntimeError("one or more generated files could not be prepared for deletion")

    try:
        stats.feedback += db.query(models.Feedback).filter(
            or_(
                models.Feedback.anonymous_user_id == user.id,
                (
                    models.Feedback.generation_result_id.in_(generation_ids)
                    & models.Feedback.anonymous_user_id.is_(None)
                ) if generation_ids else False,
            )
        ).delete(synchronize_session=False)
        if generation_ids:
            db.query(models.Feedback).filter(
                models.Feedback.generation_result_id.in_(generation_ids),
                models.Feedback.anonymous_user_id.isnot(None),
                models.Feedback.anonymous_user_id != user.id,
            ).update({models.Feedback.generation_result_id: None}, synchronize_session=False)
        _delete_generation_graph(db, generation_ids, stats)
        if experience_ids:
            stats.experience_inputs += db.query(models.ExperienceInput).filter(
                models.ExperienceInput.id.in_(experience_ids)
            ).delete(synchronize_session=False)
        stats.events += db.query(models.Event).filter_by(anonymous_user_id=user.id).delete(synchronize_session=False)
        stats.sessions += db.query(models.SessionRecord).filter_by(anonymous_user_id=user.id).delete(synchronize_session=False)
        stats.users += db.query(models.AnonymousUser).filter_by(id=user.id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        _restore_staged_files(staged)
        raise

    removed, pending = _remove_staged_files(staged)
    stats.files_removed += removed
    stats.files_cleanup_pending += pending
    return stats


def cleanup_expired_data(
    db: Session,
    *,
    now: datetime | None = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    dry_run: bool = False,
) -> DataDeletionStats:
    settings = get_settings()
    current = now or datetime.utcnow()
    content_cutoff = current - timedelta(days=max(1, settings.user_content_retention_days))
    file_cutoff = current - timedelta(days=max(1, settings.generated_file_retention_days))
    analytics_cutoff = current - timedelta(days=max(1, settings.analytics_retention_days))
    stats = DataDeletionStats()

    old_experience_ids = [
        row[0] for row in db.query(models.ExperienceInput.id).filter(
            models.ExperienceInput.created_at < content_cutoff
        ).all()
    ]
    old_generation_ids = [
        row[0] for row in db.query(models.GenerationResult.id).filter(
            models.GenerationResult.experience_input_id.in_(old_experience_ids)
        ).all()
    ] if old_experience_ids else []
    old_file_rows = db.query(models.GeneratedFile).filter(
        or_(
            models.GeneratedFile.created_at < file_cutoff,
            models.GeneratedFile.generation_result_id.in_(old_generation_ids) if old_generation_ids else False,
        )
    ).all()
    file_ids = [row.id for row in old_file_rows]
    file_paths = [row.file_path for row in old_file_rows]

    expired_event_count = db.query(models.Event).filter(models.Event.created_at < analytics_cutoff).count()
    expired_feedback_count = db.query(models.Feedback).filter(models.Feedback.created_at < analytics_cutoff).count()
    expired_session_count = db.query(models.SessionRecord).filter(models.SessionRecord.started_at < analytics_cutoff).count()
    if dry_run:
        stats.generated_files = len(file_ids)
        stats.generation_results = len(old_generation_ids)
        stats.experience_inputs = len(old_experience_ids)
        stats.events = expired_event_count
        stats.feedback = expired_feedback_count
        stats.sessions = expired_session_count
        return stats

    stats.generated_files = len(file_ids)
    stats.events = expired_event_count
    stats.feedback = expired_feedback_count
    stats.sessions = expired_session_count
    staged, unsafe_count = _stage_files(file_paths, output_dir)
    if unsafe_count:
        _restore_staged_files(staged)
        raise RuntimeError("one or more expired files could not be prepared for deletion")
    try:
        if old_generation_ids:
            db.query(models.Feedback).filter(
                models.Feedback.generation_result_id.in_(old_generation_ids)
            ).update({models.Feedback.generation_result_id: None}, synchronize_session=False)
        if file_ids:
            db.query(models.GeneratedFile).filter(models.GeneratedFile.id.in_(file_ids)).delete(synchronize_session=False)
        stats.generated_files = len(file_ids)
        _delete_generation_graph(db, old_generation_ids, stats)
        if old_experience_ids:
            stats.experience_inputs = db.query(models.ExperienceInput).filter(
                models.ExperienceInput.id.in_(old_experience_ids)
            ).delete(synchronize_session=False)
        db.query(models.Event).filter(models.Event.created_at < analytics_cutoff).delete(synchronize_session=False)
        db.query(models.Feedback).filter(models.Feedback.created_at < analytics_cutoff).delete(synchronize_session=False)
        db.query(models.SessionRecord).filter(models.SessionRecord.started_at < analytics_cutoff).delete(synchronize_session=False)
        orphan_users = db.query(models.AnonymousUser).filter(
            models.AnonymousUser.last_seen_at < analytics_cutoff,
            ~models.AnonymousUser.id.in_(db.query(models.ExperienceInput.anonymous_user_id).filter(models.ExperienceInput.anonymous_user_id.isnot(None))),
            ~models.AnonymousUser.id.in_(db.query(models.Event.anonymous_user_id).filter(models.Event.anonymous_user_id.isnot(None))),
            ~models.AnonymousUser.id.in_(db.query(models.Feedback.anonymous_user_id).filter(models.Feedback.anonymous_user_id.isnot(None))),
            ~models.AnonymousUser.id.in_(db.query(models.SessionRecord.anonymous_user_id)),
        )
        stats.users = orphan_users.delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        _restore_staged_files(staged)
        raise

    removed, pending = _remove_staged_files(staged)
    stats.files_removed += removed
    stats.files_cleanup_pending += pending
    return stats
