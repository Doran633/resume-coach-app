import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOGS = ROOT / "backend" / "logs"
DEFAULT_OUT = ROOT / "backend" / "reports"
BEIJING = timezone(timedelta(hours=8))


def parse_args():
    parser = argparse.ArgumentParser(description="Export Resume Coach generation quality report.")
    parser.add_argument("--logs", default=str(DEFAULT_LOGS), help="JSONL log directory.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Report output directory.")
    parser.add_argument("--days", type=int, default=None, help="Only include recent N days.")
    return parser.parse_args()


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(BEIJING)


def load_jsonl(path: Path, cutoff: datetime | None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(item, dict):
            continue
        created_at = _parse_time(item.get("created_at"))
        if cutoff and created_at and created_at < cutoff:
            continue
        rows.append(item)
    return rows


def _number(rows: list[dict], key: str) -> float:
    return sum(float(row.get(key) or 0) for row in rows)


def _count_true(rows: list[dict], key: str) -> int:
    return sum(bool(row.get(key)) for row in rows)


def _pct(value: float, total: float) -> str:
    return "0.0%" if not total else f"{value / total * 100:.1f}%"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _display(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}"


def _section(lines: list[str], title: str, rows: list[tuple[str, str]]) -> None:
    lines.extend([f"## {title}", "", "| 指标 | 数值 |", "|---|---:|"])
    lines.extend(f"| {label} | {value} |" for label, value in rows)
    lines.append("")


def build_report(log_dir: Path, days: int | None) -> str:
    now = datetime.now(BEIJING)
    cutoff = now - timedelta(days=days) if days is not None else None
    logs = {
        name: load_jsonl(log_dir / filename, cutoff)
        for name, filename in {
            "stability": "generation_stability.jsonl",
            "llm": "llm_calls.jsonl",
            "fallback": "resume_section_fallback.jsonl",
            "boundary": "experience_boundary.jsonl",
            "coverage": "fact_coverage.jsonl",
            "dedup": "resume_fact_dedup.jsonl",
            "dedup_quality": "resume_dedup_quality.jsonl",
            "typography": "resume_typography_quality.jsonl",
            "output_quality": "resume_output_quality.jsonl",
            "firewall": "resume_output_firewall.jsonl",
            "type": "experience_type_resolution.jsonl",
            "integrity": "resume_text_integrity.jsonl",
            "summary": "resume_summary_quality.jsonl",
            "delivery": "docx_delivery_readiness.jsonl",
        }.items()
    }

    stability = logs["stability"]
    generation_calls = len(stability) or len(logs["llm"])
    stable_fallbacks = _count_true(stability, "fallback_used")
    fallback_calls = len(logs["fallback"])
    fallback_triggers = _count_true(logs["fallback"], "resume_fallback_triggered")

    boundary = logs["boundary"]
    total_projects = _number(boundary, "project_count")
    bound_projects = _number(boundary, "projects_with_source_id")
    missing_source = _number(boundary, "projects_missing_source_id")
    contamination_fixed = _number(boundary, "contamination_fixed_count")
    binding_rate = bound_projects / total_projects if total_projects else 0.0

    coverage = logs["coverage"]
    explicit_facts = _number(coverage, "explicit_fact_count")
    high_facts = _number(coverage, "high_value_fact_count")
    covered_facts = _number(coverage, "covered_fact_count")
    restored_facts = _number(coverage, "restored_fact_count")
    coverage_values = [
        float(value)
        for row in coverage
        for value in (row.get("coverage_by_experience_id") or {}).values()
        if isinstance(value, (int, float))
    ]
    high_value_coverage = _mean(coverage_values)

    dedup = logs["dedup"]
    compared = _number(dedup, "compared_pair_count")
    exact = _number(dedup, "exact_duplicate_count")
    containment = _number(dedup, "containment_duplicate_count")
    semantic = _number(dedup, "semantic_duplicate_count")
    removed = _number(dedup, "removed_detail_count") or _number(dedup, "removed_count")
    retained = _number(dedup, "retained_unique_fact_count")
    dedup_base = removed + retained
    dedup_removal_rate = removed / dedup_base if dedup_base else 0.0

    dedup_quality = logs["dedup_quality"]
    duplicate_candidates = _number(dedup_quality, "duplicate_candidate_count")
    duplicate_clusters = _number(dedup_quality, "duplicate_cluster_count")
    quality_removed = _number(dedup_quality, "removed_duplicate_count")
    quality_merged = _number(dedup_quality, "merged_duplicate_count")
    precision_warnings = _number(dedup_quality, "dedup_precision_warning_count")
    typography = logs["typography"]
    typography_abnormal = _number(typography, "abnormal_punctuation_count")
    typography_repeated = _number(typography, "repeated_punctuation_fixed_count")
    typography_mixed = _number(typography, "mixed_punctuation_fixed_count")
    typography_spacing = _number(typography, "spacing_fixed_count")
    output_quality = logs["output_quality"]
    average_duplicate_score = _mean([float(row.get("duplicate_score") or 0) for row in output_quality])
    average_typography_score = _mean([float(row.get("typography_score") or 0) for row in output_quality])
    average_overall_score = _mean([float(row.get("overall_quality_score") or 0) for row in output_quality])
    warning_codes = Counter(code for row in output_quality for code in (row.get("warning_codes") or []))
    low_score_counts = Counter()
    for row in output_quality:
        for key, threshold in {
            "fact_coverage_score": 80, "experience_boundary_score": 90, "duplicate_score": 85,
            "typography_score": 95, "internal_marker_score": 100, "delivery_readiness_score": 90,
        }.items():
            if float(row.get(key) or 0) < threshold:
                low_score_counts[key] += 1

    firewall_removed = _number(logs["firewall"], "contamination_removed_count")
    firewall_removed += _number(logs["firewall"], "coach_instruction_removed_count")
    firewall_removed += _number(logs["firewall"], "template_residue_removed_count")
    type_corrections = _count_true(logs["type"], "correction_applied")
    truncation_fixed = _number(logs["integrity"], "truncated_text_fixed_count")
    coach_summary_removed = _number(logs["summary"], "coach_language_removed_count")
    delivery_calls = len(logs["delivery"])
    delivery_repairs = sum(
        bool(row.get("coaching_text_removed_count") or row.get("internal_marker_detected_count") or row.get("invalid_incomplete_text_count"))
        for row in logs["delivery"]
    )

    lines = [
        "# Resume Coach 生成质量报告", "",
        f"- 生成时间（北京时间）：{now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 统计范围：{'最近 ' + str(days) + ' 天' if days is not None else '全部可用日志'}",
        f"- 日志目录：`{log_dir}`", "",
    ]
    _section(lines, "生成与 Fallback", [
        ("Generation 调用次数", str(generation_calls)),
        ("Stable fallback 触发次数", str(stable_fallbacks)),
        ("Stable fallback 触发率", _pct(stable_fallbacks, generation_calls)),
        ("Resume Section Fallback 调用次数", str(fallback_calls)),
        ("Resume Section Fallback 触发次数", str(fallback_triggers)),
        ("Resume Section Fallback 触发率", _pct(fallback_triggers, fallback_calls)),
    ])
    _section(lines, "Experience ID 与事实边界", [
        ("项目检查数", str(int(total_projects))),
        ("Experience ID 平均绑定率", _pct(bound_projects, total_projects)),
        ("缺少 source_experience_id 项目数", str(int(missing_source))),
        ("跨经历污染修复数量", str(int(contamination_fixed))),
    ])
    _section(lines, "Fact Ledger 与事实覆盖", [
        ("原子明确事实数量", str(int(explicit_facts))),
        ("高价值事实数量", str(int(high_facts))),
        ("已覆盖事实数量", str(int(covered_facts))),
        ("恢复的高价值事实数量", str(int(restored_facts))),
        ("平均经历事实覆盖率", _pct(high_value_coverage, 1)),
    ])
    _section(lines, "事实去重", [
        ("比较次数", str(int(compared))),
        ("完全重复", str(int(exact))),
        ("包含重复", str(int(containment))),
        ("语义重复", str(int(semantic))),
        ("删除或合并详情数", str(int(removed))),
        ("去重后保留事实数", str(int(retained))),
        ("去重删除率", _pct(removed, dedup_base)),
        ("最终重复候选数", str(int(duplicate_candidates))),
        ("最终重复事实簇数", str(int(duplicate_clusters))),
        ("最终质量门删除数", str(int(quality_removed))),
        ("最终质量门合并数", str(int(quality_merged))),
        ("Dedup Precision 警告数", str(int(precision_warnings))),
    ])
    _section(lines, "标点与最终质量评分", [
        ("平均 Duplicate Score", _display(average_duplicate_score)),
        ("平均 Typography Score", _display(average_typography_score)),
        ("平均 Overall Quality Score", _display(average_overall_score)),
        ("异常标点发现数", str(int(typography_abnormal))),
        ("连续标点修复数", str(int(typography_repeated))),
        ("混合标点修复数", str(int(typography_mixed))),
        ("空格修复数", str(int(typography_spacing))),
    ])
    _section(lines, "输出与投递质量", [
        ("输出防火墙拦截数量", str(int(firewall_removed))),
        ("实习/项目类型纠正数量", str(type_corrections)),
        ("正文截断修复数量", str(int(truncation_fixed))),
        ("个人优势教练话术清理数量", str(int(coach_summary_removed))),
        ("DOCX 投递就绪检查次数", str(delivery_calls)),
        ("DOCX 投递前修复次数", str(delivery_repairs)),
        ("DOCX 投递修复率", _pct(delivery_repairs, delivery_calls)),
    ])

    alerts = []
    if fallback_calls and fallback_triggers / fallback_calls > 0.20:
        alerts.append("Resume Section Fallback 触发率超过 20%，建议检查上游结构化输出。")
    if total_projects and binding_rate < 0.90:
        alerts.append("source_experience_id 绑定率低于 90%，建议检查语义分段和 reconciliation。")
    if coverage_values and high_value_coverage < 0.80:
        alerts.append("事实覆盖率低于 80%，建议检查生成压缩和详情预算。")
    if boundary and contamination_fixed / max(1, total_projects) > 0.20:
        alerts.append("跨经历污染修复率偏高，建议检查 Prompt 或模型输出退化。")
    if delivery_calls and delivery_repairs / delivery_calls > 0.10:
        alerts.append("DOCX 投递修复率超过 10%，建议检查生成结果完整性。")
    if dedup_base and dedup_removal_rate > 0.35:
        alerts.append("去重删除率超过 35%，建议抽样检查 Dedup Precision。")
    lines.extend(["## 观察性阈值", ""])
    lines.extend(f"- {item}" for item in alerts or ["当前可用日志未触发观察性阈值；阈值仅用于监控，不阻止生成。"])
    lines.append("")

    lines.extend(["## Quality Gate 告警分布", ""])
    if warning_codes:
        lines.extend(f"- `{code}`：{count} 次" for code, count in warning_codes.most_common())
    else:
        lines.append("暂无 Output Quality Gate 告警。")
    if low_score_counts:
        lines.extend(["", "低于观察阈值的评分项："])
        lines.extend(f"- `{key}`：{count} 次" for key, count in low_score_counts.most_common())
    lines.append("")

    missing = [name for name, rows in logs.items() if not rows]
    lines.extend(["## 日志可用性", ""])
    if missing:
        lines.append("以下日志暂无数据：" + "、".join(missing) + "。报告已按零值处理。")
    else:
        lines.append("所需质量日志均存在可用记录。")
    lines.extend(["", "> 本报告仅聚合计数、比例和内部标识统计，不包含用户原始经历、完整推荐版本或简历正文。", ""])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    log_dir = Path(args.logs).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"generation-quality-{datetime.now(BEIJING).strftime('%Y-%m-%d')}.md"
    report_path.write_text(build_report(log_dir, args.days), encoding="utf-8")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
