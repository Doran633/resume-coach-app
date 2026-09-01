from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.backup_service import latest_backup, verify_restore
from scripts.observability_common import BEIJING, write_json
from scripts.operations_common import worst_status


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _git(project_root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=project_root, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def evaluate_rollback(project_root: Path, reports_dir: Path, backups_dir: Path) -> dict[str, Any]:
    current = _git(project_root, "rev-parse", "HEAD")
    records = [_json(path) for path in reports_dir.glob("release-verification-*.json")]
    records = [item for item in records if item.get("golden_regression_passed") and item.get("commit")]
    records.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    current_record = next((item for item in records if item.get("commit") == current), {})
    previous = next((item for item in records if item.get("commit") != current), {})
    previous_commit = str(previous.get("commit") or "")
    schema_diff = _git(
        project_root, "diff", "--name-only", previous_commit, current, "--",
        "backend/app/models.py", "backend/app/database.py",
    ) if previous_commit and current else ""
    backup = latest_backup(backups_dir)
    backup_ok = False
    if backup:
        try:
            backup_ok = bool(verify_restore(backup)["ok"])
        except Exception:
            backup_ok = False
    dist = project_root / "frontend" / "dist"
    frontend_ok = (dist / "index.html").exists() and any((dist / "assets").glob("*.js"))
    requirements_ok = (project_root / "backend" / "requirements.txt").exists()
    checks = [
        {"check": "current_release_verification", "status": "healthy" if current_record else "critical", "message": "当前commit有质量门记录" if current_record else "当前commit缺少质量门记录"},
        {"check": "previous_stable_commit", "status": "healthy" if previous else "warning", "message": str(previous.get("short_commit") or "未找到上一稳定commit")},
        {"check": "restorable_backup", "status": "healthy" if backup_ok else "critical", "message": backup.name if backup_ok and backup else "没有可验证备份"},
        {"check": "frontend_build", "status": "healthy" if frontend_ok else "critical", "message": "frontend/dist完整" if frontend_ok else "frontend/dist缺失"},
        {"check": "requirements", "status": "healthy" if requirements_ok else "critical", "message": "后端依赖清单存在" if requirements_ok else "后端依赖清单缺失"},
        {
            "check": "database_schema_compatibility", "status": "warning" if schema_diff else "healthy",
            "message": "数据库模型或初始化代码发生变化，需要人工确认向后兼容" if schema_diff else "未检测到数据库模型或初始化代码变化",
        },
    ]
    status = worst_status([item["status"] for item in checks])
    return {
        "created_at": datetime.now(BEIJING).isoformat(),
        "status": status,
        "current_commit": current[:8] if current else "unknown",
        "previous_stable_commit": str(previous.get("short_commit") or ""),
        "checks": checks,
        "rollback_commands": [
            "git fetch origin main",
            "git switch --detach <previous-stable-commit>",
            ".venv/bin/python -m pip install -r backend/requirements.txt",
            "cd frontend && pnpm build && cd ..",
            "systemctl restart resume-coach-backend",
        ] if previous else [],
        "automatic_rollback_performed": False,
        "production_database_modified": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 回滚准备检查", "", f"- 生成时间：{report['created_at']}", f"- 状态：{report['status']}",
        f"- 当前commit：{report['current_commit']}", f"- 上一稳定commit：{report['previous_stable_commit'] or '暂无'}", "",
    ]
    lines.extend(f"- [{item['status']}] {item['check']}：{item['message']}" for item in report["checks"])
    lines.extend(["", "本脚本没有执行Git切换、数据库覆盖或服务重启。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify rollback prerequisites without performing rollback.")
    parser.add_argument("--reports", type=Path, default=ROOT / "backend" / "reports")
    parser.add_argument("--backups", type=Path, default=ROOT / "backend" / "backups")
    parser.add_argument("--out", type=Path, default=ROOT / "backend" / "reports")
    args = parser.parse_args()
    report = evaluate_rollback(ROOT, args.reports, args.backups)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "rollback-readiness-latest.json", report)
    path = args.out / "rollback-readiness-latest.md"
    path.write_text(render_markdown(report), encoding="utf-8")
    print(path)
    raise SystemExit(2 if report["status"] == "critical" else 1 if report["status"] == "warning" else 0)


if __name__ == "__main__":
    main()
