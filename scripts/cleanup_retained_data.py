import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from backend.app.database import SessionLocal
from backend.app.services.data_lifecycle_service import cleanup_expired_data
from backend.app.services.structured_log_service import write_structured_log


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove expired Resume Coach user content and files.")
    parser.add_argument("--dry-run", action="store_true", help="Report matching rows without deleting them.")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        stats = cleanup_expired_data(db, dry_run=args.dry_run)
    finally:
        db.close()
    data = stats.to_dict()
    write_structured_log(
        "runtime", "data_retention_checked" if args.dry_run else "data_retention_completed",
        status="dry_run" if args.dry_run else "success",
        **{f"{'matched' if args.dry_run else 'removed'}_{key}": value for key, value in data.items()},
    )
    print("mode:", "dry-run" if args.dry_run else "delete")
    for key, value in data.items():
        print(f"{key}: {value}")
    if not args.dry_run and stats.files_cleanup_pending:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
