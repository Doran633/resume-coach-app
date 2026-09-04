import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services import resume_experience_entity_dedup_service as entity_dedup_service  # noqa: E402
from app.services.resume_experience_entity_dedup_service import (  # noqa: E402
    analyze_duplicate_experience_entities,
    deduplicate_resume_experience_entities,
    normalize_project_title,
)
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW_INPUT = """项目一｜回归分析计算器
独立完成回归分析计算器，支持数据导入与预处理、线性回归和多项式回归，并生成可视化图表，对比分析结果后推荐更适合的回归模型。

项目二｜智能停车系统
作为团队核心成员设计智能停车系统，根据地图路线、天气和车流信息提供停车指引，在创新创业路演中获得一等奖。"""


def make_payload(projects):
    return schemas.GenerationPayload(
        completeness_score=85,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]"}, education={}, summary=["具备项目实践能力。"],
            skills=[], projects=projects, interview_preparation=[],
        ),
    )


def regression_project(name="回归分析计算器", source_id="EXP-001", details=None):
    return {
        "name": name, "meta": "个人项目", "time": "[待填写]",
        "intro": "面向数据分析场景开发回归分析工具，支持模型选择与智能制图。",
        "role": "独立完成项目设计、开发与测试。",
        "details": details or [
            "实现数据导入与预处理，支持线性回归和多项式回归。",
            "开发智能制图模块，生成回归分析可视化图表。",
        ],
        "source_experience_id": source_id,
        "source_fact_ids": [f"{source_id}-F001", f"{source_id}-F002"] if source_id else [],
    }


def parking_project(source_id="EXP-002"):
    return {
        "name": "智能停车系统", "meta": "项目经历", "time": "[待填写]",
        "intro": "结合地图、天气与车流信息提供智能停车指引。",
        "role": "作为团队核心成员参与产品设计与技术方案落地。",
        "details": ["实现地图寻车位、历史车位记录与实时路线规划。", "项目在创新创业路演中获得一等奖。"],
        "source_experience_id": source_id,
        "source_fact_ids": [f"{source_id}-F001", f"{source_id}-F002"],
    }


def test_same_source_id_projects_merge_and_recover_unique_facts():
    duplicate = regression_project(
        "我做过一个回归分析计算器",
        details=[
            "实现数据导入与预处理，支持线性回归和多项式回归。",
            "对比多种回归分析结果并推荐更适合的数据模型。",
        ],
    )
    result = deduplicate_resume_experience_entities(
        make_payload([regression_project(), parking_project(), duplicate]), RAW_INPUT, write_log=False,
    )
    assert len(result.resume_sections.projects) == 2
    regression = next(item for item in result.resume_sections.projects if item["source_experience_id"] == "EXP-001")
    assert normalize_project_title(regression["name"]) == "回归分析计算器"
    text = " ".join(regression["details"])
    for term in ["数据导入", "多项式回归", "智能制图", "推荐"]:
        assert term in text
    assert analyze_duplicate_experience_entities(result)["duplicate_experience_entity_count"] == 0


def test_normalized_title_detects_duplicate_without_source_id():
    first = regression_project(source_id="")
    second = regression_project("我独立完成了回归分析计算器", source_id="", details=["完成模型效果对比与最优回归模型推荐。"])
    result = deduplicate_resume_experience_entities(make_payload([first, second]), "", write_log=False)
    assert len(result.resume_sections.projects) == 1
    assert result.resume_sections.projects[0]["name"] == "回归分析计算器"


def test_generic_title_suffix_is_ignored_only_with_matching_local_facts():
    first = regression_project("回归分析计算器项目", source_id="")
    second = regression_project("回归分析计算器工具", source_id="", details=["完成多种回归模型效果对比与结果推荐。"])
    result = deduplicate_resume_experience_entities(make_payload([first, second]), "", write_log=False)
    assert len(result.resume_sections.projects) == 1
    assert normalize_project_title(result.resume_sections.projects[0]["name"]) == "回归分析计算器"


def test_distinct_source_ids_are_never_merged_for_shared_technology():
    rag_app = regression_project("RAG 学习助手", "EXP-001", ["实现文档解析、Embedding 与向量检索问答。"])
    rag_eval = regression_project("RAG 评测平台", "EXP-002", ["建立 RAG 测试集与 Groundedness 评测指标。"])
    result = deduplicate_resume_experience_entities(make_payload([rag_app, rag_eval]), "", write_log=False)
    assert len(result.resume_sections.projects) == 2


def test_project_and_internship_are_not_merged_for_shared_rag_stack():
    rag_project = regression_project("RAG 学习助手", "EXP-001", ["实现文档解析、Embedding 与向量检索问答。"])
    internship = regression_project("某科技公司 RAG 优化", "EXP-002", ["在实习中建立 RAG 测试集并优化检索效果。"])
    internship["meta"] = "实习经历"
    result = deduplicate_resume_experience_entities(make_payload([rag_project, internship]), "", write_log=False)
    assert len(result.resume_sections.projects) == 2


def test_fact_fingerprint_merges_when_source_id_is_missing():
    first = regression_project("回归效果分析器", source_id="")
    second = regression_project("回归模型比较器", source_id="", details=["完成多种回归模型效果对比与推荐。"])
    first["source_fact_ids"] = ["FACT-REGRESSION-001"]
    second["source_fact_ids"] = ["FACT-REGRESSION-001"]
    result = deduplicate_resume_experience_entities(make_payload([first, second]), "", write_log=False)
    assert len(result.resume_sections.projects) == 1


def test_similar_title_with_different_facts_is_kept_when_confidence_is_low():
    first = regression_project("数据分析工具", "", ["实现回归分析和模型效果对比。"])
    second = regression_project("数据分析平台", "", ["实现销售数据看板和季度营收趋势分析。"])
    result = deduplicate_resume_experience_entities(make_payload([first, second]), "", write_log=False)
    assert len(result.resume_sections.projects) == 2
    metrics = analyze_duplicate_experience_entities(result)
    assert metrics["duplicate_experience_entity_count"] == 0
    assert metrics["possible_duplicate_count"] >= 1


def test_comprehensive_fallback_row_is_deferred_to_reconciliation():
    comprehensive = regression_project("综合经历项目", "EXP-001", ["从多个经历中恢复的临时事实。"])
    comprehensive["meta"] = "综合经历"
    result = deduplicate_resume_experience_entities(
        make_payload([regression_project(), comprehensive]), RAW_INPUT, write_log=False,
    )
    assert len(result.resume_sections.projects) == 2


def test_possible_duplicate_is_logged_without_auto_merge():
    old_log_path = entity_dedup_service.LOG_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            log_path = Path(tmpdir) / "entity-dedup.jsonl"
            entity_dedup_service.LOG_PATH = log_path
            first = regression_project("数据分析工具", "", ["实现回归分析和模型效果对比。"])
            second = regression_project("数据分析平台", "", ["实现销售数据看板和季度营收趋势分析。"])
            result = deduplicate_resume_experience_entities(make_payload([first, second]), "", stage="test")
            assert len(result.resume_sections.projects) == 2
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
            assert entry["possible_duplicate_count"] >= 1
            assert entry["merged_project_count"] == 0
            assert entry["decisions"][0]["result"] == "kept_separate"
        finally:
            entity_dedup_service.LOG_PATH = old_log_path


def test_docx_contains_each_experience_entity_once():
    duplicate = regression_project("我做过一个回归分析计算器", details=["完成模型效果对比与最优回归模型推荐。"])
    payload = deduplicate_resume_experience_entities(
        make_payload([regression_project(), parking_project(), duplicate]), RAW_INPUT, write_log=False,
    )
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=1, anonymous_user_id=None, session_id="entity-dedup", target_role="数据分析",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW_INPUT,
    ))
    db.add(models.GenerationResult(
        id=601, experience_input_id=1, completeness_score=85,
        result_json=json.dumps(payload.model_dump(), ensure_ascii=False),
    ))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="entity-dedup", session_id="entity-dedup", generation_result_id=601,
            ))
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert text.count("回归分析计算器｜") == 1
            assert "我做过一个回归分析计算器" not in text
            assert text.count("智能停车系统｜") == 1
            for internal in ["EXP-001", "EXP-002", "source_experience_id", "fact_id"]:
                assert internal not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()
