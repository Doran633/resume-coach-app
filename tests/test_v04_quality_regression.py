import json
from pathlib import Path
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.docx_delivery_readiness_service import prepare_docx_delivery  # noqa: E402
from app.services.experience_boundary_guard_service import guard_experience_boundaries  # noqa: E402
from app.services.experience_type_resolution_service import resolve_project_types  # noqa: E402
from app.services.fact_coverage_guard_service import guard_fact_coverage  # noqa: E402
from app.services.fact_guard_service import guard_hard_facts  # noqa: E402
from app.services.long_input_service import analyze_long_input  # noqa: E402
from app.services.project_specificity_guard_service import guard_project_specificity  # noqa: E402
from app.services.resume_body_sanitizer_service import sanitize_resume_body  # noqa: E402
from app.services.resume_fact_dedup_service import deduplicate_resume_facts  # noqa: E402
from app.services.resume_output_firewall_service import guard_resume_output  # noqa: E402
from app.services.resume_project_reconciliation_service import reconcile_resume_projects  # noqa: E402
from app.services.resume_section_integrity_service import ensure_resume_section_integrity  # noqa: E402
from app.services.resume_summary_quality_service import ensure_resume_summary_quality  # noqa: E402
from app.services.resume_text_integrity_service import ensure_resume_text_integrity  # noqa: E402
from app.services.resume_title_format_service import resolve_resume_titles  # noqa: E402
from app.services.resume_dedup_quality_service import ensure_dedup_quality  # noqa: E402
from app.services.resume_typography_quality_service import ensure_typography_quality  # noqa: E402
from app.services.resume_output_quality_gate_service import evaluate_resume_output_quality  # noqa: E402
from app.services.stable_generation_fallback_service import build_stable_generation_fallback  # noqa: E402
from app.services.uncertain_expression_cleanup_service import cleanup_uncertain_expressions  # noqa: E402
from app.services.weak_profile_strategy_service import strengthen_weak_profile_payload  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


CASES = json.loads((ROOT / "tests" / "fixtures" / "real_world_resume_cases.json").read_text(encoding="utf-8"))
BODY_FORBIDDEN = [
    "综合经历项目", "技术动作", "我做过", "希望包装", "原文截断", "需补充原文",
    "source_experience_id", "source_fact_ids", "fact_id", "可面试承接", "适合将",
]


def _request(case: dict) -> schemas.GenerateRequest:
    return schemas.GenerateRequest(
        anonymous_user_id=f"u-{case['id']}", session_id=f"s-{case['id']}",
        target_role=case["target_role"], mode="full_resume", packaging_level="大胆",
        experience_type="综合经历", raw_input=case["raw_input"],
    )


def _formal_text(payload: schemas.GenerationPayload) -> str:
    sections = payload.resume_sections
    return "\n".join([
        *sections.summary, *sections.skills,
        *[str(value) for project in sections.projects for key, value in project.items()
          if key not in {"source_experience_id", "source_fact_ids", "detail_fact_ids", "type_lineage"}],
    ])


def _quality_pipeline(case: dict) -> schemas.GenerationPayload:
    raw = case["raw_input"]
    request = _request(case)
    payload = build_stable_generation_fallback(request, analyze_long_input(raw))
    payload = guard_hard_facts(payload, raw)
    payload = guard_experience_boundaries(payload, raw, stage="test", write_log=False)
    payload = cleanup_uncertain_expressions(payload, raw)
    payload = guard_project_specificity(payload, raw)
    payload = strengthen_weak_profile_payload(payload, raw, case["target_role"])
    payload = sanitize_resume_body(payload, raw)
    payload = reconcile_resume_projects(payload, raw, stage="test", write_log=False)
    payload = deduplicate_resume_facts(payload, stage="test", write_log=False)
    payload = ensure_dedup_quality(payload, stage="test", write_log=False)
    payload = resolve_project_types(payload, raw, stage="test", write_log=False)
    payload = guard_fact_coverage(payload, raw, stage="test", write_log=False)
    payload = guard_experience_boundaries(payload, raw, stage="test", write_log=False)
    payload = deduplicate_resume_facts(payload, stage="test", write_log=False)
    payload = ensure_resume_summary_quality(payload, raw, stage="test", write_log=False)
    payload = ensure_resume_section_integrity(payload)
    payload = ensure_resume_text_integrity(payload, raw, stage="test", write_log=False)
    payload = guard_hard_facts(payload, raw)
    payload = guard_resume_output(payload, raw, stage="test", write_log=False)
    payload = ensure_typography_quality(payload, stage="test", write_log=False)
    payload = resolve_resume_titles(payload, raw)
    evaluate_resume_output_quality(payload, raw, stage="test", write_log=False)
    return payload


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_real_world_case_preserves_boundaries_and_delivery_quality(case):
    payload = _quality_pipeline(case)
    projects = payload.resume_sections.projects
    formal_text = _formal_text(payload)

    assert len(projects) >= case["min_experiences"]
    assert all(project.get("source_experience_id") for project in projects)
    assert len({project["source_experience_id"] for project in projects}) == len(projects)
    assert not any(term in formal_text for term in BODY_FORBIDDEN)
    assert not any(term in formal_text for term in ["、、", "，，", "。。", "、,", ",、"])
    assert not any(term in formal_text for term in case.get("forbidden_resume_terms", []))
    for term in case["required_terms"]:
        assert term.lower() in formal_text.lower(), f"missing high-value term: {term}"

    if case.get("expects_internship"):
        internships = [project for project in projects if project.get("meta") == "实习经历"]
        assert len(internships) == 1
        assert internships[0].get("position") == case["expected_position"]
    else:
        assert not any(project.get("meta") == "实习经历" for project in projects)

    for project in projects:
        normalized = ["".join(str(item).split()).rstrip("。") for item in project.get("details", [])]
        assert len(normalized) == len(set(normalized))


def test_all_real_world_cases_generate_nonempty_delivery_docx_without_internal_content():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            for index, case in enumerate(CASES, start=1):
                payload = prepare_docx_delivery(_quality_pipeline(case), generation_result_id=index)
                db.add(models.ExperienceInput(
                    id=index, anonymous_user_id=1, session_id=f"s-{index}", target_role=case["target_role"],
                    mode="full_resume", packaging_level="大胆", experience_type="综合经历", raw_input=case["raw_input"],
                ))
                db.add(models.GenerationResult(
                    id=index, experience_input_id=index, completeness_score=payload.completeness_score,
                    result_json=payload.model_dump_json(),
                ))
                db.commit()
                response = docx_service.create_docx(db, schemas.DocxCreate(
                    anonymous_user_id=f"u-{index}", session_id=f"s-{index}", generation_result_id=index,
                ))
                text = "\n".join(p.text for p in Document(Path(tmpdir) / response.file_name).paragraphs)
                assert "个人简历" in text and "个人优势" in text
                if payload.resume_sections.skills:
                    assert "技能与能力" in text
                else:
                    assert "技能与能力" not in text
                assert not any(term in text for term in ["面试准备清单", "source_experience_id", "fact_id", "综合经历项目"])
                if case.get("expects_internship"):
                    assert text.index("技能与能力") < text.index("实习经历") < text.index("项目经历")
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()
