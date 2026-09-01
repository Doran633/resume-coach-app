from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.observability_common import BEIJING, write_json
from scripts.operations_common import exclusive_operation_lock


@dataclass(frozen=True)
class Task:
    name: str
    arguments: list[str]
    critical: bool = True


def build_tasks(
    mode: str, *, public_base: str, backups: Path, reports: Path,
    env_path: Path, frontend_env: Path, full_smoke: bool,
) -> list[Task]:
    py = sys.executable
    common = ["--out", str(reports)]
    shallow = Task("shallow_smoke", [py, "scripts/run_public_smoke_test.py", "--base", public_base, "--mode", "shallow", *common])
    slo = Task("operational_slo", [py, "scripts/check_operational_slo.py", "--hours", "24", "--backups", str(backups), "--public-base", public_base, *common])
    incidents = Task("quality_incidents", [py, "scripts/list_recent_quality_incidents.py", "--hours", "72", "--json", "--out", str(reports / "recent-quality-incidents.json")], False)
    freshness = Task("operations_freshness", [py, "scripts/check_operations_freshness.py", "--reports", str(reports), "--backups", str(backups)], False)
    status = Task("operations_status", [
        py, "scripts/export_operations_status.py", "--reports", str(reports), "--backups", str(backups),
        "--env", str(env_path), "--frontend-env", str(frontend_env), "--public-base", public_base,
    ], False)
    if mode == "hourly":
        return [shallow, slo, incidents, freshness, status]
    if mode == "daily":
        return [
            Task("database_backup", [py, "scripts/backup_production_data.py", "--out", str(backups)]),
            Task("backup_verification", [py, "scripts/verify_production_backup.py", "--backups", str(backups)]),
            Task("retention_cleanup", [py, "scripts/cleanup_retained_data.py"]),
            Task("runtime_report", [py, "scripts/export_runtime_protection.py", "--days", "1", "--backups", str(backups), "--public-base", public_base, *common], False),
            Task("generation_funnel", [py, "scripts/export_generation_funnel.py", "--days", "1", *common], False),
            Task("quality_drift", [py, "scripts/check_output_quality_drift.py", "--hours", "72", *common]),
            Task("rate_limit_rollout", [py, "scripts/evaluate_rate_limit_rollout.py", "--hours", "72", *common], False),
            Task("database_portability", [py, "scripts/audit_database_portability.py", "--backups", str(backups), *common], False),
            freshness, status,
        ]
    tasks = [
        shallow,
        Task("operational_slo", slo.arguments),
        Task("rollback_readiness", [py, "scripts/verify_rollback_readiness.py", "--reports", str(reports), "--backups", str(backups), *common]),
    ]
    if full_smoke:
        tasks.append(Task("full_smoke", [py, "scripts/run_public_smoke_test.py", "--base", public_base, "--mode", "full", *common]))
    tasks.extend([
        Task("launch_preflight", [
            py, "scripts/launch_preflight.py", "--env", str(env_path), "--frontend-env", str(frontend_env),
            "--public-base", public_base, "--backups", str(backups),
        ]),
        freshness, status,
    ])
    return tasks


def execute_tasks(tasks: list[Task], *, dry_run: bool = False, project_root: Path = ROOT) -> tuple[list[dict[str, Any]], int]:
    results: list[dict[str, Any]] = []
    highest = 0
    for task in tasks:
        if dry_run:
            results.append({"task": task.name, "status": "planned", "return_code": None, "critical": task.critical})
            continue
        started = time.perf_counter()
        try:
            completed = subprocess.run(task.arguments, cwd=project_root, text=True, capture_output=True)
            code = completed.returncode
        except OSError:
            code = 2
        elapsed = round((time.perf_counter() - started) * 1000)
        status = "passed" if code == 0 else "warning" if code == 1 or not task.critical else "failed"
        results.append({"task": task.name, "status": status, "return_code": code, "critical": task.critical, "elapsed_ms": elapsed})
        if code and task.critical:
            highest = max(highest, 2 if code >= 2 else 1)
    return results, highest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run public-beta operational checks as one resilient workflow.")
    parser.add_argument("--mode", choices=["hourly", "daily", "post-deploy"], required=True)
    parser.add_argument("--public-base", required=True)
    parser.add_argument("--backups", type=Path, default=ROOT / "backend" / "backups")
    parser.add_argument("--reports", type=Path, default=ROOT / "backend" / "reports")
    parser.add_argument("--env", type=Path, default=Path("/etc/resume-coach/resume-coach.env") if os.name != "nt" else ROOT / ".env")
    parser.add_argument("--frontend-env", type=Path, default=ROOT / "frontend" / ".env.production")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--full-smoke", action="store_true", default=os.getenv("ENABLE_FULL_SMOKE", "").lower() in {"1", "true", "yes", "on"})
    args = parser.parse_args()
    args.reports.mkdir(parents=True, exist_ok=True)
    tasks = build_tasks(
        args.mode, public_base=args.public_base, backups=args.backups, reports=args.reports,
        env_path=args.env, frontend_env=args.frontend_env, full_smoke=args.full_smoke,
    )
    lock = args.reports / ".public-beta-operations.lock"
    try:
        with exclusive_operation_lock(lock):
            results, code = execute_tasks(tasks, dry_run=args.dry_run)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
    payload = {
        "created_at": datetime.now(BEIJING).isoformat(), "mode": args.mode,
        "dry_run": args.dry_run, "full_smoke_enabled": args.full_smoke,
        "status": "planned" if args.dry_run else "failed" if code == 2 else "warning" if code == 1 else "healthy",
        "tasks": results,
    }
    write_json(args.reports / "public-beta-operations-latest.json", payload)
    print(args.reports / "public-beta-operations-latest.json")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
