from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.resume_summary_quality_service import (  # noqa: E402
    build_grounded_summary_candidates,
    ensure_resume_summary_quality,
)
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """独立开发回归分析计算器，完成环境搭建、回归函数选择、数据合理性检测、图像生成和分析结果验证。

作为团队核心成员设计智能停车场系统，参与产品分析与技术方案设计，根据路线、天气和车流情况提供停车指引，并在路演中取得一等奖。

参与学校校庆活动策划与执行，负责节目安排、材料审核、现场沟通和活动复盘。"""
SINGLE_RAW = "独立开发回归分析计算器，实现回归函数选择、数据合理性检测和图像生成。"
COACH_SENTENCE = "具备学习迁移能力，适合将课程项目、小项目或竞赛经历整理为可面试承接的实践表达。"


def payload(raw: str = RAW) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=80, confirmed_facts=[], missing_questions=[], normal_version="",
        bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[], resume_sections=schemas.ResumeSections(
            summary=[
                "AI 应用开发爱好者，具备项目实践基础。",
                "项目驱动型候选人，能够围绕已有任务梳理目标。",
                "在回归分析计算器中独立完成从环境搭建到功能实现的全流程。",
                COACH_SENTENCE,
                "面试时可以准备项目原理和降级表达。",
            ],
            projects=[{
                "name": "实践项目", "meta": "项目经历", "time": "[待填写]",
                "intro": raw.split("\n\n")[0], "role": "负责相关实现",
                "details": [raw.split("\n\n")[0]], "source_experience_id": "EXP-001",
            }]))


def all_summary_text(result: schemas.GenerationPayload) -> str:
    return "\n".join(result.resume_sections.summary)


def test_coach_language_and_self_downgrading_labels_are_removed():
    result = ensure_resume_summary_quality(payload(), RAW, write_log=False)
    text = all_summary_text(result)
    for phrase in ["适合将", "课程项目、小项目", "可面试承接", "爱好者", "候选人", "降级表达"]:
        assert phrase not in text
    assert 3 <= len(result.resume_sections.summary) <= 4


def test_summary_is_fact_grounded_and_uses_candidate_capabilities():
    result = ensure_resume_summary_quality(payload(), RAW, write_log=False)
    text = all_summary_text(result)
    assert "独立推进" in text or "独立完成" in text
    assert "协作" in text or "交付" in text
    assert "经验丰富" not in text and "行业专家" not in text
    assert any(item.dimension == "learning_transfer" for item in build_grounded_summary_candidates(RAW))


def test_single_experience_does_not_get_learning_transfer_claim():
    result = ensure_resume_summary_quality(payload(SINGLE_RAW), SINGLE_RAW, write_log=False)
    assert "学习迁移" not in all_summary_text(result)


def test_summary_candidates_carry_internal_fact_bindings():
    candidates = build_grounded_summary_candidates(RAW)
    assert candidates
    assert all(item.source_experience_ids and item.source_fact_ids for item in candidates)


def test_no_collaboration_or_metrics_means_no_corresponding_claim():
    result = ensure_resume_summary_quality(payload(SINGLE_RAW), SINGLE_RAW, write_log=False)
    text = all_summary_text(result)
    assert "协作" not in text
    assert "明确指标" not in text and "优化前后" not in text


def test_historical_docx_removes_coach_language():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="泛互联网岗位",
        mode="full_resume", packaging_level="大胆", experience_type="综合经历", raw_input=RAW))
    db.add(models.GenerationResult(id=805, experience_input_id=1, completeness_score=80,
        result_json=payload().model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=805))
            text = "\n".join(p.text for p in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert COACH_SENTENCE not in text
            assert "AI 应用开发爱好者" not in text
            assert "项目驱动型候选人" not in text
            assert "可面试承接的实践表达" not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


if __name__ == "__main__":
    test_coach_language_and_self_downgrading_labels_are_removed()
    test_summary_is_fact_grounded_and_uses_candidate_capabilities()
    test_single_experience_does_not_get_learning_transfer_claim()
    test_summary_candidates_carry_internal_fact_bindings()
    test_no_collaboration_or_metrics_means_no_corresponding_claim()
    test_historical_docx_removes_coach_language()
    print("resume summary quality tests passed")
