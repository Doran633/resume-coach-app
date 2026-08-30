from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BACKUP_DIR = PROJECT_ROOT / "backend" / "backups"


def sqlite_database_path(database_url: str, *, base_dir: Path = PROJECT_ROOT) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("Only SQLite databases are supported by this backup tool.")
    raw_path = database_url[len(prefix):]
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def database_integrity(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "database file not found"
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()
        message = str(result[0]) if result else "no result"
        return message.lower() == "ok", message
    finally:
        connection.close()


def create_sqlite_backup(source: Path, backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    backup_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(backup_dir, 0o700)
    except OSError:
        pass
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = backup_dir / f"resume-coach-{stamp}.sqlite3"
    temporary = destination.with_suffix(".tmp")
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    target_connection = sqlite3.connect(temporary)
    try:
        source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()
    valid, message = database_integrity(temporary)
    if not valid:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"backup integrity check failed: {message}")
    temporary.replace(destination)
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass
    return destination


def verify_restore(backup_path: Path) -> dict[str, int | str | bool]:
    backup_path = backup_path.resolve()
    if not backup_path.exists():
        raise FileNotFoundError(backup_path)
    with tempfile.TemporaryDirectory(prefix="resume-coach-restore-") as temp_dir:
        restored = Path(temp_dir) / "restored.sqlite3"
        source = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
        target = sqlite3.connect(restored)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        valid, message = database_integrity(restored)
        connection = sqlite3.connect(f"file:{restored.as_posix()}?mode=ro", uri=True)
        try:
            table_count = int(connection.execute(
                "select count(*) from sqlite_master where type='table' and name not like 'sqlite_%'"
            ).fetchone()[0])
        finally:
            connection.close()
        return {"ok": valid, "integrity": message, "table_count": table_count}


def prune_backups(backup_dir: Path, retention_days: int, *, now: datetime | None = None) -> int:
    if not backup_dir.exists():
        return 0
    cutoff = (now or datetime.now()) - timedelta(days=max(1, retention_days))
    removed = 0
    for path in backup_dir.glob("resume-coach-*.sqlite3"):
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        if modified < cutoff:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def latest_backup(backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path | None:
    candidates = sorted(backup_dir.glob("resume-coach-*.sqlite3"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None
