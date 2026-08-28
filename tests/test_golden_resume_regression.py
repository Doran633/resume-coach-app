import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from scripts.evaluate_golden_resume import (  # noqa: E402
    evaluate_payload,
    load_case,
    process_fixed_payload,
    project_texts,
    render_fixed_docx,
    visible_text,
)
from app.services.resume_fact_dedup_service import similarity  # noqa: E402
from app.services.resume_experience_entity_dedup_service import (  # noqa: E402
    analyze_duplicate_experience_entities,
    normalize_project_title,
)


CASE_ID = "v057_ai_agent_full_resume"


def golden():
    case = load_case(CASE_ID)
    payload = process_fixed_payload(case)
    return case, payload


def test_golden_fixture_and_snapshot_are_anonymized():
    fixture = (ROOT / "tests" / "fixtures" / "golden_resume_cases.json").read_text(encoding="utf-8")
    snapshot = (ROOT / "tests" / "snapshots" / "v057_golden_resume.txt").read_text(encoding="utf-8")
    combined = fixture + snapshot
    assert not re.search(r"1[3-9]\d{9}", combined)
    assert not re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", combined)
    assert "某科技公司" in combined


def test_golden_structure_boundaries_and_summary_quality():
    case, payload = golden()
    sections = payload.resume_sections
    text = visible_text(payload)
    projects = project_texts(payload)

    assert case["summary_min_count"] <= len(sections.summary) <= case["summary_max_count"]
    assert len(sections.projects) >= case["expected_experience_count"]
    assert all(project.get("source_experience_id") for project in sections.projects)
    source_ids = [str(project.get("source_experience_id")) for project in sections.projects]
    normalized_titles = [normalize_project_title(project.get("name")) for project in sections.projects]
    assert len(source_ids) == len(set(source_ids))
    assert len(normalized_titles) == len(set(normalized_titles))
    assert analyze_duplicate_experience_entities(payload)["duplicate_experience_entity_count"] == 0
    assert [project.get("meta") for project in sections.projects].count("实习经历") == 1
    assert all(term not in text for term in case["forbidden_phrases"])
    assert all(term not in text for term in case["forbidden_internal_fields"])

    for source_id, rules in case["experience_boundaries"].items():
        source_text = projects[source_id]
        assert all(term.lower() in source_text.lower() for term in rules.get("required", []))
        assert all(term.lower() not in source_text.lower() for term in rules.get("forbidden", []))


def test_golden_facts_details_and_skill_taxonomy_do_not_regress():
    case, payload = golden()
    metrics = evaluate_payload(case, payload)
    assert metrics["fact_coverage_rate"] >= 90
    assert metrics["duplicate_detail_count"] == 0
    assert metrics["duplicate_experience_entity_count"] == 0
    assert metrics["internal_field_leak_count"] == 0
    assert metrics["experience_boundary_accuracy"] == 100
    assert metrics["experience_type_accuracy"] == 100
    assert metrics["skill_category_accuracy"] == 100

    skills = "\n".join(payload.resume_sections.skills)
    for term in ["Python", "TypeScript", "React", "FastAPI", "SQLite", "Nginx", "systemd", "Smoke Test"]:
        assert skills.count(term) == 1
    assert "编程语言：Python、TypeScript" in skills

    for project in payload.resume_sections.projects:
        intro = str(project.get("intro") or "")
        role = str(project.get("role") or "")
        details = [str(item) for item in project.get("details", [])]
        limits = case["project_detail_limits"]
        assert limits["min"] <= len(details) <= limits["max"]
        assert all(similarity(intro, detail) < 0.90 for detail in details)
        assert all(similarity(role, detail) < 0.90 for detail in details)
        for left in range(len(details)):
            for right in range(left + 1, len(details)):
                assert similarity(details[left], details[right]) < 0.90


def test_golden_docx_is_delivery_ready():
    case, payload = golden()
    docx_text = render_fixed_docx(case, payload)
    assert docx_text.strip()
    assert "实习经历" in docx_text and "项目经历" in docx_text
    assert docx_text.index("实习经历") < docx_text.index("项目经历")
    for forbidden in ["面试准备清单", "source_experience_id", "experience_id", "fact_id", "EXP-001", "EXP-002", "EXP-003"]:
        assert forbidden not in docx_text


def test_golden_case_schema_contains_required_quality_contract():
    case = load_case(CASE_ID)
    required = {
        "case_id", "description", "raw_input", "target_role", "packaging_level",
        "experience_type", "expected_experience_count", "expected_experience_types",
        "required_facts", "required_technical_terms", "expected_skill_categories",
        "forbidden_phrases", "forbidden_internal_fields", "summary_min_count",
        "summary_max_count", "project_detail_limits", "expected_section_order",
    }
    assert required <= set(case)
    json.dumps(case, ensure_ascii=False)


def test_duplicate_entity_golden_case_keeps_two_real_projects():
    case = load_case("v060_duplicate_regression_project")
    payload = process_fixed_payload(case)
    projects = payload.resume_sections.projects
    assert len(projects) == 2
    assert len({project.get("source_experience_id") for project in projects}) == 2
    assert len({normalize_project_title(project.get("name")) for project in projects}) == 2
    regression = next(project for project in projects if project.get("source_experience_id") == "EXP-001")
    parking = next(project for project in projects if project.get("source_experience_id") == "EXP-002")
    regression_text = " ".join([regression["name"], *regression["details"]])
    parking_text = " ".join([parking["name"], *parking["details"]])
    assert regression["name"] == "回归分析计算器"
    assert all(project["name"] != "我做过一个回归分析计算器" for project in projects)
    assert "数据导入" in regression_text and "模型推荐" in regression_text
    assert "地图路线" in parking_text and "一等奖" in parking_text
    assert "一等奖" not in regression_text
    assert "回归分析" not in parking_text
    docx_text = render_fixed_docx(case, payload)
    assert docx_text.count("回归分析计算器｜") == 1
    assert "我做过一个回归分析计算器｜" not in docx_text
