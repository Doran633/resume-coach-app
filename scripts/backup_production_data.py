import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from backend.app.config import get_settings
from backend.app.database import engine
from backend.app.services.backup_service import (
    DEFAULT_BACKUP_DIR,
    create_sqlite_backup,
    prune_backups,
    verify_restore,
)
from backend.app.services.structured_log_service import write_structured_log


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a transactionally consistent SQLite backup.")
    parser.add_argument("--out", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()
    if engine.url.get_backend_name() != "sqlite" or not engine.url.database:
        raise SystemExit("Only the configured SQLite database can be backed up by this script.")
    source = Path(engine.url.database).resolve()
    backup = create_sqlite_backup(source, args.out)
    verification = verify_restore(backup)
    removed = prune_backups(args.out, get_settings().backup_retention_days)
    write_structured_log(
        "runtime", "database_backup_completed", status="success",
        backup_age_seconds=0, backup_size_bytes=backup.stat().st_size,
        table_count=verification["table_count"], old_backups_removed=removed,
    )
    print(backup)
    print(f"integrity: {verification['integrity']}")
    print(f"tables: {verification['table_count']}")
    print(f"old_backups_removed: {removed}")


if __name__ == "__main__":
    main()
