from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.observability_common import BEIJING, average, cutoff_for_hours, is_smoke_attempt, load_jsonl, parse_time, write_json
from scripts.operations_common import STATUS_RANK, read_json, worst_status


def _git_commit(project_root: Path) -> str:
    configured = os.getenv("BUILD_COMMIT", "").strip()
    if configured:
        return configured
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project_root,
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _number(rows: list[dict[str, Any]], *keys: str) -> int:
    return sum(int(row.get(key) or 0) for row in rows for key in keys)


def _rows_for_results(logs_dir: Path, name: str, cutoff, result_ids: set[int]) -> list[dict[str, Any]]:
    rows = load_jsonl(logs_dir, name, cutoff)
    if not result_ids:
        return []
    return [row for row in rows if int(row.get("generation_result_id") or -1) in result_ids]


def analyze_quality(
    logs_dir: Path, *, hours: int = 24, project_root: Path = ROOT,
    cutoff_override: datetime | None = None,
) -> dict[str, Any]:
    cutoff = cutoff_override or cutoff_for_hours(hours)
    stability = [
        row for row in load_jsonl(logs_dir, "generation_stability", cutoff)
        if row.get("generation_result_id") and row.get("attempt_id") and not is_smoke_attempt(row.get("attempt_id"))
    ]
    result_ids = {int(row["generation_result_id"]) for row in stability}
    sample_count = len(stability)
    coverage_values = [float(row["high_value_fact_coverage"]) for row in stability if row.get("high_value_fact_coverage") is not None]
    coverage = average(coverage_values)
    bound = sum(int(row.get("projects_with_source_id") or 0) for row in stability)
    missing = sum(int(row.get("projects_missing_source_id") or 0) for row in stability)
    binding = bound / (bound + missing) if bound + missing else None
    stable_fallback = sum(bool(row.get("fallback_used")) for row in stability)
    section_fallback = sum(bool(row.get("resume_section_fallback_triggered")) for row in stability)
    unresolved_critical = sum(int(row.get("unresolved_critical_issue_count") or 0) for row in stability)

    boundary = _rows_for_results(logs_dir, "experience_boundary", cutoff, result_ids)
    validity = _rows_for_results(logs_dir, "resume_experience_validity", cutoff, result_ids)
    dedup = _rows_for_results(logs_dir, "resume_fact_dedup", cutoff, result_ids)
    delivery = _rows_for_results(logs_dir, "resume_delivery_quality_gate", cutoff, result_ids)
    typography = _rows_for_results(logs_dir, "resume_typography_quality", cutoff, result_ids)
    integrity = _rows_for_results(logs_dir, "resume_text_integrity", cutoff, result_ids)
    docx = _rows_for_results(logs_dir, "docx_delivery_readiness", cutoff, result_ids)

    contamination = _number(boundary, "contamination_fixed_count")
    invalid_entities = _number(validity, "invalid_experience_count", "generic_experience_name_count", "heading_residue_project_count")
    duplicate_facts = _number(dedup, "exact_duplicate_count", "semantic_duplicate_count", "containment_duplicate_count")
    internal_leaks = _number(delivery, "internal_leak_count")
    invalid_characters = _number(delivery, "invalid_character_count") + _number(typography, "abnormal_punctuation_count")
    truncated = _number(integrity, "truncated_text_detected_count", "removed_incomplete_sentences")
    docx_repairs = sum(
        any(int(row.get(key) or 0) > 0 for key in (
            "coaching_text_removed_count", "internal_marker_detected_count", "invalid_incomplete_text_count",
        ))
        for row in docx
    )
    metrics: dict[str, float | int | None] = {
        "high_value_fact_coverage": round(coverage, 4) if coverage is not None else None,
        "experience_id_binding_rate": round(binding, 4) if binding is not None else None,
        "cross_experience_repair_rate": round(contamination / sample_count, 4) if sample_count else None,
        "duplicate_fact_rate": round(duplicate_facts / sample_count, 4) if sample_count else None,
        "invalid_experience_rate": round(invalid_entities / sample_count, 4) if sample_count else None,
        "stable_fallback_rate": round(stable_fallback / sample_count, 4) if sample_count else None,
        "resume_section_fallback_rate": round(section_fallback / sample_count, 4) if sample_count else None,
        "docx_repair_rate": round(docx_repairs / len(docx), 4) if docx else None,
        "unresolved_critical_count": unresolved_critical,
        "internal_field_leak_count": internal_leaks,
        "invalid_character_count": invalid_characters,
        "truncated_text_count": truncated,
    }
    return {
        "created_at": datetime.now(BEIJING).isoformat(),
        "hours": hours,
        "version": os.getenv("APP_VERSION", (project_root / "VERSION").read_text(encoding="utf-8").strip()),
        "build_commit": _git_commit(project_root)[:8],
        "sample_count": sample_count,
        "smoke_traffic_excluded": True,
        "metrics": metrics,
    }


def current_build_cutoff(logs_dir: Path, *, project_root: Path = ROOT) -> datetime | None:
    commit = _git_commit(project_root)
    candidates = []
    for row in load_jsonl(logs_dir, "runtime"):
        if row.get("event_name") != "service_started":
            continue
        logged = str(row.get("build_commit") or "")
        if commit != "unknown" and logged and not (commit.startswith(logged) or logged.startswith(commit[:8])):
            continue
        created = parse_time(row.get("created_at"))
        if created is not None:
            candidates.append(created)
    return max(candidates) if candidates else None


def collect_quality_windows(logs_dir: Path, *, project_root: Path = ROOT) -> dict[str, dict[str, Any]]:
    build_cutoff = current_build_cutoff(logs_dir, project_root=project_root)
    windows = {
        "24h": analyze_quality(logs_dir, hours=24, project_root=project_root),
        "72h": analyze_quality(logs_dir, hours=72, project_root=project_root),
    }
    if build_cutoff is not None:
        windows["current_build"] = analyze_quality(
            logs_dir, hours=max(1, round((datetime.now(BEIJING) - build_cutoff).total_seconds() / 3600)),
            project_root=project_root, cutoff_override=build_cutoff,
        )
        windows["current_build"]["started_at"] = build_cutoff.isoformat()
    else:
        windows["current_build"] = {"available": False, "sample_count": 0, "metrics": {}}
    return windows


def evaluate_drift(snapshot: dict[str, Any], baseline: dict[str, Any] | None = None) -> dict[str, Any]:
    metrics = snapshot["metrics"]
    sample_count = int(snapshot.get("sample_count") or 0)
    findings: list[dict[str, Any]] = []

    def add(code: str, status: str, value: Any, message: str) -> None:
        findings.append({"issue_code": code, "status": status, "value": value, "message": message})

    if sample_count < 10:
        add("INSUFFICIENT_QUALITY_SAMPLE", "observe", sample_count, "非烟测样本少于10次，趋势指标仅观察")
    coverage = metrics.get("high_value_fact_coverage")
    binding = metrics.get("experience_id_binding_rate")
    if coverage is not None and coverage < 0.8:
        add("LOW_HIGH_VALUE_FACT_COVERAGE", "warning", coverage, "高价值事实覆盖率低于80%")
    if binding is not None and binding < 0.9:
        add("LOW_EXPERIENCE_ID_BINDING", "warning", binding, "Experience ID绑定率低于90%")
    if (metrics.get("resume_section_fallback_rate") or 0) > 0.2:
        add("HIGH_RESUME_SECTION_FALLBACK", "warning", metrics["resume_section_fallback_rate"], "Resume Section Fallback超过20%")
    if int(metrics.get("unresolved_critical_count") or 0) > 0:
        add("UNRESOLVED_OUTPUT_CRITICAL", "critical", metrics["unresolved_critical_count"], "存在未解决的正式输出关键问题")
    for key, code in [
        ("internal_field_leak_count", "INTERNAL_FIELD_LEAK"),
        ("invalid_character_count", "INVALID_CHARACTER"),
        ("truncated_text_count", "INCOMPLETE_TEXT"),
    ]:
        if int(metrics.get(key) or 0) > 0:
            add(code, "warning", metrics[key], "检测到已修复或待复核的专业性问题")

    baseline_metrics = (baseline or {}).get("metrics") if isinstance(baseline, dict) else None
    comparisons: dict[str, dict[str, float]] = {}
    if isinstance(baseline_metrics, dict):
        for key in (
            "cross_experience_repair_rate", "duplicate_fact_rate", "invalid_experience_rate",
            "stable_fallback_rate", "resume_section_fallback_rate", "docx_repair_rate",
        ):
            current = metrics.get(key)
            previous = baseline_metrics.get(key)
            if current is None or previous is None:
                continue
            delta = round(float(current) - float(previous), 4)
            comparisons[key] = {"current": float(current), "baseline": float(previous), "delta": delta}
            if sample_count >= 10 and delta >= 0.1:
                add(f"{key.upper()}_REGRESSION", "warning", delta, f"{key}较稳定基线上升至少10个百分点")
        for key in ("high_value_fact_coverage", "experience_id_binding_rate"):
            current = metrics.get(key)
            previous = baseline_metrics.get(key)
            if current is None or previous is None:
                continue
            delta = round(float(current) - float(previous), 4)
            comparisons[key] = {"current": float(current), "baseline": float(previous), "delta": delta}
            if sample_count >= 10 and delta <= -0.1:
                add(f"{key.upper()}_REGRESSION", "warning", delta, f"{key}较稳定基线下降至少10个百分点")
    elif sample_count >= 10:
        add("QUALITY_BASELINE_MISSING", "warning", None, "尚未建立稳定质量基线")

    status = worst_status([item["status"] for item in findings], "observe" if sample_count < 10 else "healthy")
    return {**snapshot, "status": status, "findings": findings, "baseline_comparison": comparisons}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 输出质量漂移报告", "",
        f"- 生成时间：{report['created_at']}",
        f"- 版本：{report['version']} ({report['build_commit']})",
        f"- 窗口：最近 {report['hours']} 小时",
        f"- 非烟测样本：{report['sample_count']}",
        f"- 状态：{report['status']}", "",
        "| 指标 | 当前值 |", "|---|---:|",
    ]
    lines.extend(f"| {key} | {value if value is not None else '暂无'} |" for key, value in report["metrics"].items())
    lines.extend(["", "## 观察窗口", "", "| 窗口 | 样本 | 事实覆盖率 | Experience ID绑定率 |", "|---|---:|---:|---:|"])
    for name, window in report.get("windows", {}).items():
        metrics = window.get("metrics", {})
        lines.append(
            f"| {name} | {window.get('sample_count', 0)} | {metrics.get('high_value_fact_coverage', '暂无')} | "
            f"{metrics.get('experience_id_binding_rate', '暂无')} |"
        )
    lines.extend(["", "## 发现", ""])
    if report["findings"]:
        lines.extend(f"- [{item['status']}] {item['issue_code']}：{item['message']}" for item in report["findings"])
    else:
        lines.append("- 未发现超出阈值的质量漂移。")
    lines.extend(["", "本报告只使用脱敏聚合指标，不包含用户输入、完整简历或模型输出。", ""])
    return "\n".join(lines)


def baseline_write_allowed(report: dict[str, Any]) -> bool:
    return int(report.get("sample_count") or 0) >= 10 and report.get("status") != "critical"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check aggregate resume output quality drift.")
    parser.add_argument("--logs", type=Path, default=ROOT / "backend" / "logs")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--baseline", type=Path, default=ROOT / "backend" / "reports" / "output-quality-baseline.json")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "backend" / "reports")
    args = parser.parse_args()
    snapshot = analyze_quality(args.logs, hours=args.hours)
    baseline = read_json(args.baseline)
    report = evaluate_drift(snapshot, baseline)
    report["windows"] = collect_quality_windows(args.logs)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "output-quality-drift-latest.json", report)
    (args.out / "output-quality-drift-latest.md").write_text(render_markdown(report), encoding="utf-8")
    if args.write_baseline:
        if not baseline_write_allowed(report):
            print("Baseline refused: at least 10 non-smoke samples and no critical issue are required.", file=sys.stderr)
            raise SystemExit(2)
        write_json(args.baseline, {
            "created_at": report["created_at"], "version": report["version"],
            "build_commit": report["build_commit"], "sample_count": report["sample_count"],
            "metrics": report["metrics"],
        })
    print(args.out / "output-quality-drift-latest.md")
    raise SystemExit(STATUS_RANK.get(report["status"], 0))


if __name__ == "__main__":
    main()
