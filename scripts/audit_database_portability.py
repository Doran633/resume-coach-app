from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.backup_service import latest_backup, verify_restore
from scripts.observability_common import BEIJING, load_jsonl, write_json


SQLITE_MARKERS = ("PRAGMA ", "sqlite_master", "sqlite3.connect", "exec_driver_sql")


def _source_findings(source_root: Path) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for path in source_root.rglob("*.py"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        markers = sorted({marker.strip() for marker in SQLITE_MARKERS if marker in text})
        if markers:
            findings.append({"file": str(path.relative_to(ROOT)), "markers": markers})
    return findings


def audit_database(
    database_path: Path,
    *,
    source_root: Path,
    logs_dir: Path,
    backups_dir: Path,
) -> dict[str, Any]:
    table_rows: dict[str, int] = {}
    indexes = 0
    foreign_keys = 0
    integrity = "missing"
    database_error_type = ""
    if database_path.exists():
        try:
            connection = sqlite3.connect(f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True)
            try:
                integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
                tables = [
                    str(row[0]) for row in connection.execute(
                        "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
                    )
                ]
                for table in tables:
                    escaped = table.replace('"', '""')
                    table_rows[table] = int(connection.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0])
                    foreign_keys += len(connection.execute(f'PRAGMA foreign_key_list("{escaped}")').fetchall())
                indexes = int(connection.execute(
                    "select count(*) from sqlite_master where type='index' and name not like 'sqlite_%'"
                ).fetchone()[0])
            finally:
                connection.close()
        except sqlite3.Error as exc:
            integrity = "unavailable"
            database_error_type = type(exc).__name__
    lock_errors = sum(
        "lock" in str(row.get("error_type") or "").lower() or "lock" in str(row.get("error_code") or "").lower()
        for row in [*load_jsonl(logs_dir, "runtime"), *load_jsonl(logs_dir, "security_events")]
    )
    backup = latest_backup(backups_dir)
    restore_seconds = None
    backup_verified = False
    if backup:
        started = time.perf_counter()
        try:
            backup_verified = bool(verify_restore(backup)["ok"])
        except (OSError, RuntimeError, sqlite3.Error):
            backup_verified = False
        restore_seconds = round(time.perf_counter() - started, 3)
    source_findings = _source_findings(source_root)
    database_size = database_path.stat().st_size if database_path.exists() else 0
    wal_path = Path(str(database_path) + "-wal")
    wal_size = wal_path.stat().st_size if wal_path.exists() else 0
    blockers = [
        "SQLite在线备份与完整性脚本需要替换为PostgreSQL方案",
        "ensure_v01_schema中的PRAGMA/ALTER逻辑需要迁移工具接管",
    ]
    if source_findings:
        blockers.append("存在SQLite专属调用，需要在迁移前逐项替换或隔离")
    should_prepare = lock_errors >= 5 or database_size >= 2 * 1024**3 or restore_seconds is not None and restore_seconds > 300
    recommendation = "先修复数据库可读性" if integrity not in {"ok", "missing"} else "准备迁移" if should_prepare else "继续使用 SQLite"
    reason = (
        "SQLite文件无法以只读方式完成完整性审计"
        if integrity not in {"ok", "missing"}
        else "检测到持续写锁、数据库体积或恢复时间已接近迁移阈值"
        if should_prepare else "当前单实例、数据库体积、写锁和恢复时间尚未触发迁移阈值"
    )
    return {
        "created_at": datetime.now(BEIJING).isoformat(),
        "status": "critical" if integrity not in {"ok", "missing"} else "warning" if should_prepare or integrity == "missing" else "healthy",
        "database_engine": "sqlite",
        "database_integrity": integrity,
        "database_error_type": database_error_type,
        "database_size_bytes": database_size,
        "wal_size_bytes": wal_size,
        "table_count": len(table_rows),
        "table_row_counts": table_rows,
        "index_count": indexes,
        "foreign_key_count": foreign_keys,
        "write_lock_error_count": lock_errors,
        "latest_backup_verified": backup_verified,
        "restore_verification_seconds": restore_seconds,
        "sqlite_specific_source_count": len(source_findings),
        "sqlite_specific_sources": source_findings,
        "postgresql_blockers": blockers,
        "multi_instance_ready": False,
        "recommendation": recommendation,
        "reason": reason,
        "production_database_modified": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 数据库可迁移性审计", "",
        f"- 生成时间：{report['created_at']}",
        f"- 建议：{report['recommendation']}",
        f"- 原因：{report['reason']}",
        f"- 完整性：{report['database_integrity']}",
        f"- 数据库大小：{report['database_size_bytes']} bytes",
        f"- WAL大小：{report['wal_size_bytes']} bytes",
        f"- 表/索引/外键：{report['table_count']} / {report['index_count']} / {report['foreign_key_count']}",
        f"- 写锁错误：{report['write_lock_error_count']}",
        f"- 多实例数据库就绪：{'是' if report['multi_instance_ready'] else '否'}",
        f"- 最近备份恢复验证：{'通过' if report['latest_backup_verified'] else '暂无或失败'}",
        f"- 恢复验证耗时：{report['restore_verification_seconds'] if report['restore_verification_seconds'] is not None else '暂无'} 秒", "",
        "## PostgreSQL迁移阻塞项", "",
    ]
    lines.extend(f"- {item}" for item in report["postgresql_blockers"])
    lines.extend(["", "本审计只读取结构、数量和脱敏运行指标，未连接PostgreSQL，也未修改生产数据库。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit SQLite portability without migrating production data.")
    parser.add_argument("--database", type=Path, default=ROOT / "backend" / "data" / "resume_coach.db")
    parser.add_argument("--logs", type=Path, default=ROOT / "backend" / "logs")
    parser.add_argument("--backups", type=Path, default=ROOT / "backend" / "backups")
    parser.add_argument("--out", type=Path, default=ROOT / "backend" / "reports")
    args = parser.parse_args()
    report = audit_database(args.database, source_root=ROOT / "backend" / "app", logs_dir=args.logs, backups_dir=args.backups)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "database-portability-latest.json", report)
    path = args.out / "database-portability-latest.md"
    path.write_text(render_markdown(report), encoding="utf-8")
    print(path)
    if report["database_integrity"] not in {"ok", "missing"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
