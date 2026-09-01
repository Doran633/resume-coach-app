import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.backup_service import DEFAULT_BACKUP_DIR, latest_backup, verify_restore
from backend.app.services.structured_log_service import write_structured_log


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a backup into a temporary directory and verify it.")
    parser.add_argument("backup", type=Path, nargs="?")
    parser.add_argument("--backups", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()
    backup = args.backup or latest_backup(args.backups)
    if not backup:
        raise SystemExit("No backup is available for verification.")
    result = verify_restore(backup)
    write_structured_log(
        "runtime", "database_backup_verified",
        status="success" if result["ok"] else "failed",
        table_count=result["table_count"],
    )
    print(f"backup: {Path(backup).name}")
    print(f"integrity: {result['integrity']}")
    print(f"tables: {result['table_count']}")
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
