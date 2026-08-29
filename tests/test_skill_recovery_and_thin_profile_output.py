from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.resume_output_quality_gate_service import evaluate_resume_output_quality  # noqa: E402
from app.services.resume_skill_evidence_guard_service import guard_resume_skill_evidence  # noqa: E402
from app.services.resume_skill_taxonomy_service import calibrate_resume_skill_taxonomy  # noqa: E402
from app.services.weak_profile_strategy_service import strengthen_weak_profile_payload  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW_INPUT = """我做过一个回归分析计算器，目标是解决数据的回归分析模型选择与智能制图。我独立完成此项目，使用了CodeBuddy与连接虚拟机，项目实现了数据分析、多种回归分析效果对比、数据制图、分析最优。
我做过一个智能停车系统设计，目标是解决停车位寻找不便、浪费时间，车位信息不透明。我主要负责产品服务与技术分析，风险预估与应对，使用了LoRa无线通信+地磁传感器、地图API二次开发、SSL+Token双重加密。项目实现了地图寻找车位、历史车位记录、实时路线规划，在创新创业路演中获得一等奖。希望包装得更有岗位匹配度，但不要写成完全无法解释的内容。"""


def _payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=65,
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
            skills=[],
            projects=[
                {
                    "name": "回归分析计算器",
                    "meta": "个人项目",
                    "time": "[待填写]",
                    "intro": "面向回归模型选择与数据制图场景。",
                    "role": "独立完成项目。",
                    "details": ["实现回归分析。"],
                    "source_experience_id": "EXP-001",
                },
                {
                    "name": "智能停车系统",
                    "meta": "竞赛项目",
                    "time": "[待填写]",
                    "intro": "面向停车位查找与路线规划场景。",
                    "role": "负责产品服务与技术分析、风险预估与应对。",
                    "details": ["完成智能停车系统设计。"],
                    "source_experience_id": "EXP-002",
                },
            ],
        ),
    )


def test_empty_skills_are_recovered_from_explicit_evidence_and_categorized():
    payload = guard_resume_skill_evidence(_payload(), RAW_INPUT, write_log=False)
    payload = calibrate_resume_skill_taxonomy(payload, raw_input=RAW_INPUT, write_log=False)
    text = "\n".join(payload.resume_sections.skills)

    for expected in ["CodeBuddy", "虚拟机", "LoRa", "地磁传感器", "地图 API", "SSL", "Token", "回归分析", "数据可视化", "路线规划"]:
        assert expected in text
    for category in ["数据分析与建模", "数据可视化", "物联网与通信", "地图与路线服务", "安全机制", "开发工具与环境"]:
        assert category in text
    for invented in ["Python", "Java", "React", "Docker", "MySQL"]:
        assert invented not in text


def test_weak_profile_projects_recover_local_facts_without_cross_contamination():
    payload = strengthen_weak_profile_payload(_payload(), RAW_INPUT, "泛互联网岗位")
    first, second = payload.resume_sections.projects
    first_text = " ".join(first["details"])
    second_text = " ".join(second["details"])

    assert len(first["details"]) >= 3
    assert len(second["details"]) >= 3
    assert "一等奖" not in first_text
    assert "LoRa" not in first_text
    assert "一等奖" in second_text
    assert "回归分析" not in second_text
    assert "希望包装" not in first_text + second_text
    assert "完全无法解释" not in first_text + second_text


def test_quality_gate_reports_skill_and_thin_output_regressions():
    scores = evaluate_resume_output_quality(_payload(), RAW_INPUT, write_log=False)

    assert scores.empty_skill_section_count == 1
    assert scores.explicit_skill_not_present_count > 0
    assert scores.thin_project_output_count >= 1
    assert "EMPTY_SKILL_WITH_EVIDENCE" in scores.warning_codes
    assert "THIN_PROJECT_OUTPUT" in scores.warning_codes


def test_docx_recovers_nonempty_skills_and_keeps_both_projects():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=611, anonymous_user_id=1, session_id="s", target_role="泛互联网岗位",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW_INPUT,
    ))
    db.add(models.GenerationResult(
        id=611, experience_input_id=611, completeness_score=65, result_json=_payload().model_dump_json(),
    ))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=611,
            ))
            text = "\n".join(
                paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs
            )
            assert "技能与能力" in text
            assert "回归分析" in text and "LoRa" in text
            assert "回归分析计算器" in text and "智能停车系统" in text
            assert "希望包装" not in text and "完全无法解释" not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()
