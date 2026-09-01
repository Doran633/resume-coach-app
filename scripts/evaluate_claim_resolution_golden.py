import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.services.experience_fact_ledger_service import build_experience_fact_ledger, fact_match_score  # noqa: E402
from app.services.experience_identity_service import build_experience_identities  # noqa: E402
from app.services.input_claim_resolution_service import (  # noqa: E402
    PROBABLE,
    UNCERTAIN,
    resolve_experience_claims,
)
from app.services.resume_delivery_quality_gate_service import evaluate_delivery_quality_issues  # noqa: E402
from scripts.evaluate_golden_resume import (  # noqa: E402
    _generate_openai,
    evaluate_payload,
    load_case,
    process_fixed_payload,
    render_fixed_docx,
)


DEFAULT_OUT = ROOT / "backend" / "reports"


def evaluate_claim_resolution(case: dict, payload, docx_text: str = "") -> dict:
    raw_input = str(case.get("raw_input") or "")
    identities = build_experience_identities(raw_input)
    resolutions = [
        resolve_experience_claims(item.experience_id, item.raw_text, item.source_span[0])
        for item in identities
    ]
    ledger = build_experience_fact_ledger(raw_input)
    issues = evaluate_delivery_quality_issues(payload, raw_input)
    codes = [issue.issue_code for issue in issues]
    base = evaluate_payload(case, payload, docx_text)
    eligible = len(ledger.facts)
    covered_ids = {
        fact_id
        for project in payload.resume_sections.projects
        for fact_id in project.get("source_fact_ids", []) or []
    }
    projects_by_owner: dict[str, list[dict]] = {}
    for project in payload.resume_sections.projects:
        owner = str(project.get("immutable_source_experience_id") or project.get("source_experience_id") or "")
        if owner:
            projects_by_owner.setdefault(owner, []).append(project)
    covered_eligible = {
        fact.fact_id
        for fact in ledger.facts
        if fact.fact_id in covered_ids or any(
            fact_match_score(
                "\n".join([
                    str(project.get("intro") or ""), str(project.get("role") or ""),
                    *[str(item) for item in project.get("details", []) or []],
                ]),
                fact,
            ) >= 0.48
            for project in projects_by_owner.get(fact.experience_id, [])
        )
    }
    return {
        "case_id": case.get("case_id"),
        "eligible_fact_count": eligible,
        "eligible_fact_retention": round(len(covered_eligible) / max(1, eligible) * 100, 1),
        "instruction_leakage": sum(code in {"INSTRUCTION_LEAK", "USER_CONSTRAINT_RENDERED"} for code in codes),
        "negative_constraint_violations": sum(code in {"NEGATIVE_CONSTRAINT_LEAK", "DENIED_CLAIM_ASSERTED"} for code in codes),
        "uncertain_claim_assertion_count": codes.count("UNCERTAIN_CLAIM_ASSERTED"),
        "planned_as_completed_count": codes.count("PLANNED_WORK_PRESENTED_AS_COMPLETED"),
        "claim_owner_violations": codes.count("CLAIM_OWNER_CHANGED"),
        "unresolved_conflicts": sum(item.unresolved_conflict_count for item in resolutions),
        "withheld_claim_count": sum(len(item.withheld_claims) for item in resolutions),
        "uncertain_claim_count": sum(
            claim.certainty in {UNCERTAIN, PROBABLE}
            for item in resolutions for claim in item.claims
        ),
        "high_value_fact_coverage": base["fact_coverage_rate"],
        "experience_type_accuracy": base["experience_type_accuracy"],
        "docx_readiness": base["docx_delivery_ready"],
        "critical_issue_codes": sorted({issue.issue_code for issue in issues if issue.severity == "critical"}),
    }


def _load_baseline(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_report(metrics: dict, mode: str, output_dir: Path, baseline: dict | None = None) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    json_path = output_dir / f"claim-resolution-evaluation-{date}.json"
    md_path = output_dir / f"claim-resolution-evaluation-{date}.md"
    comparison = {
        key: metrics.get(key) - baseline.get(key)
        for key in ("eligible_fact_retention", "high_value_fact_coverage", "experience_type_accuracy")
        if isinstance(metrics.get(key), (int, float)) and isinstance(baseline.get(key), (int, float))
    }
    report = {"created_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(), "mode": mode, **metrics, "baseline_delta": comparison}
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Claim Resolution Golden Evaluation", "",
        f"- 案例：{metrics['case_id']}", f"- 模式：{mode}",
        f"- Eligible Fact 保留率：{metrics['eligible_fact_retention']}%",
        f"- 高价值事实覆盖率：{metrics['high_value_fact_coverage']}%",
        f"- 经历类型准确率：{metrics['experience_type_accuracy']}%",
        f"- 指令泄露：{metrics['instruction_leakage']}",
        f"- 否定约束违规：{metrics['negative_constraint_violations']}",
        f"- 不确定事实断言：{metrics['uncertain_claim_assertion_count']}",
        f"- 计划事项完成化：{metrics['planned_as_completed_count']}",
        f"- Claim Owner 违规：{metrics['claim_owner_violations']}",
        f"- 未解决冲突：{metrics['unresolved_conflicts']}",
        f"- DOCX 投递就绪：{'是' if metrics['docx_readiness'] else '否'}", "",
        "## Critical", "",
        *(f"- {code}" for code in metrics["critical_issue_codes"]),
        *( ["- 无"] if not metrics["critical_issue_codes"] else [] ),
        "", "> 报告不包含用户原始输入、完整 Claim 文本或简历正文。", "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Claim Resolution without exact-text snapshots.")
    parser.add_argument("--case", default="v057_ai_agent_full_resume")
    parser.add_argument("--mode", choices=["mock", "openai"], default="mock")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--compare-baseline", type=Path)
    args = parser.parse_args()
    case = load_case(args.case)
    if args.mode == "openai":
        payload, docx_text = _generate_openai(case)
    else:
        payload = process_fixed_payload(case)
        docx_text = render_fixed_docx(case, payload)
    metrics = evaluate_claim_resolution(case, payload, docx_text)
    json_path, md_path = write_report(metrics, args.mode, args.out, _load_baseline(args.compare_baseline))
    print(json_path)
    print(md_path)
    return 2 if metrics["critical_issue_codes"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
