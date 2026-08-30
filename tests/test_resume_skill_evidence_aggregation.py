from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import aggregate_skill_evidence  # noqa: E402
from app.services.resume_skill_evidence_aggregation_service import aggregate_historical_project_skill_evidence  # noqa: E402
from app.services.resume_skill_evidence_guard_service import guard_resume_skill_evidence  # noqa: E402
from app.services.resume_skill_taxonomy_service import calibrate_resume_skill_taxonomy  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


MULTI_EXPERIENCE_INPUT = """项目一｜前端工具
使用 React 和 TypeScript 完成页面开发。

项目二｜接口服务
使用 FastAPI 和 SQLAlchemy 完成后端开发。"""


def _payload(skills: list[str] | None = None) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80,
        confirmed_facts=[],
        missing_questions=[],
        normal_version="",
        bold_version="",
        boundary_version="",
        recommended_version="",
        claims=[],
        interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]"},
            summary=["具备前后端项目实践能力。"],
            skills=skills or [],
            projects=[
                {
                    "name": "前端工具",
                    "meta": "个人项目",
                    "time": "[待填写]",
                    "intro": "面向页面交互场景开发前端工具。",
                    "role": "负责页面开发与功能实现。",
                    "details": ["使用 React 和 TypeScript 完成页面开发。"],
                    "source_experience_id": "EXP-001",
                },
                {
                    "name": "接口服务",
                    "meta": "个人项目",
                    "time": "[待填写]",
                    "intro": "面向接口服务场景完成后端开发。",
                    "role": "负责接口与数据访问实现。",
                    "details": ["使用 FastAPI 和 SQLAlchemy 完成后端开发。"],
                    "source_experience_id": "EXP-002",
                },
            ],
            education={"学校": "[待填写]"},
            interview_preparation=[],
        ),
    )


def _terms(raw_input: str) -> dict[str, object]:
    return {item.term: item for item in aggregate_skill_evidence(raw_input)}


def test_explicit_typescript_and_python_ecosystem_are_aggregated_across_experiences():
    evidence = _terms(MULTI_EXPERIENCE_INPUT)
    assert evidence["TypeScript"].evidence_type == "explicit"
    assert evidence["TypeScript"].source_experience_ids == ["EXP-001"]
    assert evidence["Python"].evidence_type == "deterministic_inference"
    assert evidence["Python"].source_experience_ids == ["EXP-002"]
    assert set(evidence["Python"].inferred_from) == {"FastAPI", "SQLAlchemy"}


def test_guard_and_taxonomy_recover_programming_languages_when_skills_are_empty():
    evidence = aggregate_skill_evidence(MULTI_EXPERIENCE_INPUT)
    result = guard_resume_skill_evidence(
        _payload(), MULTI_EXPERIENCE_INPUT, aggregated_evidence=evidence, write_log=False,
    )
    result = calibrate_resume_skill_taxonomy(
        result, raw_input=MULTI_EXPERIENCE_INPUT, write_log=False,
    )
    assert "编程语言：Python、TypeScript" in result.resume_sections.skills
    assert " ".join(result.resume_sections.skills).count("Python") == 1
    assert " ".join(result.resume_sections.skills).count("TypeScript") == 1


def test_react_does_not_infer_typescript_and_spring_does_not_infer_java():
    evidence = _terms("项目经历｜应用开发\n使用 React 和 Spring 完成功能实现。")
    assert "React" in evidence and "Spring" in evidence
    assert "TypeScript" not in evidence
    assert "Java" not in evidence


def test_target_role_and_packaging_instruction_do_not_prove_python_or_docker():
    raw = "我想投 Python 后端岗位，希望包装得更匹配，并建议补充 Docker。\n项目经历｜静态页面\n使用 HTML 完成页面。"
    evidence = _terms(raw)
    assert "Python" not in evidence
    assert "Docker" not in evidence


def test_unsupported_infrastructure_skills_are_not_added():
    result = guard_resume_skill_evidence(
        _payload(["Docker、Redis、MySQL"]), MULTI_EXPERIENCE_INPUT, write_log=False,
    )
    text = " ".join(result.resume_sections.skills)
    assert "Docker" not in text and "Redis" not in text and "MySQL" not in text


def test_historical_project_body_is_used_only_when_raw_input_is_unavailable():
    historical = _payload()
    evidence = {item.term: item for item in aggregate_historical_project_skill_evidence(historical)}
    assert "TypeScript" in evidence and "Python" in evidence
    assert all(item.evidence_type == "deterministic_inference" for item in evidence.values())
    assert all("historical_project_body" in item.inferred_from or item.term == "Python" for item in evidence.values())


def test_docx_recovers_global_programming_language_summary():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=1,
        anonymous_user_id=1,
        session_id="skill-evidence",
        target_role="AI / 大模型 / Agent",
        mode="full_resume",
        packaging_level="重点放大",
        experience_type="项目经历",
        raw_input=MULTI_EXPERIENCE_INPUT,
    ))
    db.add(models.GenerationResult(
        id=9611,
        experience_input_id=1,
        completeness_score=80,
        result_json=_payload().model_dump_json(),
    ))
    db.commit()
    original_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(
                db,
                schemas.DocxCreate(
                    anonymous_user_id="anonymous",
                    session_id="skill-evidence",
                    generation_result_id=9611,
                ),
            )
            document = Document(Path(tmpdir) / response.file_name)
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            assert "编程语言：Python、TypeScript" in text
            assert "Docker" not in text and "Redis" not in text
        finally:
            docx_service.OUTPUT_DIR = original_output
            db.close()
