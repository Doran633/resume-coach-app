from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTS = [
    "tests/test_golden_resume_regression.py",
    "tests/test_v04_quality_regression.py",
    "tests/test_v06_delivery_quality_gate.py",
    "tests/test_v074_public_beta_operations.py",
]


def current_commit() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def worktree_is_clean() -> bool:
    result = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True)
    return not result.stdout.strip()


def write_record(out_dir: Path, commit: str, tests: list[str], passed: bool) -> Path:
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "short_commit": commit[:8],
        "golden_regression_passed": passed,
        "tests": tests,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"release-verification-{commit[:8]}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_pytest_command(tests: list[str], base_temp: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        *tests,
        "-q",
        "-p",
        "no:cacheprovider",
        "--basetemp",
        str(base_temp),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic release regressions and record the tested commit.")
    parser.add_argument("--out", type=Path, default=ROOT / "backend" / "reports")
    parser.add_argument("--test", action="append", dest="tests")
    args = parser.parse_args()
    if not worktree_is_clean():
        print("Release verification refused: commit or stash the current changes first.", file=sys.stderr)
        raise SystemExit(2)
    tests = args.tests or DEFAULT_TESTS
    args.out.mkdir(parents=True, exist_ok=True)
    base_temp = args.out / f".pytest-release-{uuid.uuid4().hex[:12]}"
    try:
        result = subprocess.run(build_pytest_command(tests, base_temp), cwd=ROOT)
    finally:
        shutil.rmtree(base_temp, ignore_errors=True)
    commit = current_commit()
    if result.returncode == 0:
        print(write_record(args.out, commit, tests, True))
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
