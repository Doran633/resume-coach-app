import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services import project_hierarchy_service  # noqa: E402
from app.services.experience_identity_service import build_experience_identities  # noqa: E402
from app.services.project_hierarchy_service import (  # noqa: E402
    HIERARCHY_INTERNAL_FIELDS,
    is_heading_detail,
    is_shell_project,
    merge_resume_project_hierarchies,
    strip_project_hierarchy_metadata,
)
from app.services.resume_experience_entity_dedup_service import deduplicate_resume_experience_entities  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW_INPUT = """项目一｜北辰 Agent / AI Study Assistant
北辰 Agent / AI Study Assistant｜独立开发者｜2026至今

项目二｜Course-scoped Study MVP（RAG 学习助手）
Course-scoped Study MVP（RAG 学习助手）｜个人项目｜2026至今
该阶段由北辰 Agent / AI Study Assistant 演进而来，面向大学生课程复习场景构建 RAG 问答系统。
实现课程管理、文件上传、文档解析、文本切块、Embedding、向量检索、RAG 问答与 Citation 来源展示。
围绕 chunk size、Top-K、阈值和检索排序开展对比实验，提升课程资料检索效果。
按客户端和课程维度实现数据隔离，避免不同学习空间之间的数据串用。
增加日志、健康检查、request_id 和 Smoke Test，支持问题定位与发布验证。
通过 Nginx 与 systemd 完成服务部署，并处理 CORS 和端口冲突问题。"""


def payload(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=90,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]"},
            summary=["具备 AI 应用从功能实现到部署验证的完整工程实践能力。"],
            skills=["AI / 大模型应用：RAG、Embedding、Citation"],
            projects=projects,
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]"},
            interview_preparation=[],
        ),
    )


def shell_project(source_id: str = "EXP-001") -> dict:
    return {
        "name": "北辰 Agent / AI Study Assistant",
        "meta": "个人项目",
        "time": "2026至今",
        "intro": "面向学习场景的 AI Agent 应用，旨在提供智能学习辅助",
        "role": "独立开发者，负责整体设计与实现",
        "details": ["北辰 Agent / AI Study Assistant｜独立开发者｜2026至今"],
        "source_experience_id": source_id,
    }


def phase_project(source_id: str = "EXP-002") -> dict:
    return {
        "name": "Course-scoped Study MVP（RAG 学习助手）",
        "meta": "个人项目",
        "time": "2026至今",
        "intro": "面向大学生课程复习场景构建 RAG 问答系统",
        "role": "独立完成从北辰 Agent 到 Course-scoped Study MVP 的产品演进与工程实现",
        "details": [
            "实现课程管理、文件上传、文档解析、文本切块、Embedding、向量检索、RAG 问答与 Citation 来源展示。",
            "围绕 chunk size、Top-K、阈值和检索排序开展对比实验，提升课程资料检索效果。",
            "按客户端和课程维度实现数据隔离，避免不同学习空间之间的数据串用。",
            "增加日志、健康检查、request_id 和 Smoke Test，支持问题定位与发布验证。",
            "通过 Nginx 与 systemd 完成服务部署，并处理 CORS 和端口冲突问题。",
        ],
        "source_experience_id": source_id,
        "source_fact_ids": [f"{source_id}-F{index:03d}" for index in range(1, 6)],
    }


def test_heading_only_parent_is_recognized_as_shell():
    assert is_heading_detail(shell_project()["details"][0])
    assert is_shell_project(shell_project())
    assert not is_shell_project(phase_project())


def test_parent_product_and_mvp_merge_with_canonical_title_and_all_facts():
    result = merge_resume_project_hierarchies(
        payload([shell_project(), phase_project()]), RAW_INPUT, write_log=False,
    )
    projects = result.resume_sections.projects
    assert len(projects) == 1
    project = projects[0]
    assert project["name"] == "北辰 Agent / AI Study Assistant（Course-scoped Study MVP）"
    assert project["relation_type"] == "phase_of"
    assert project["merged_source_experience_ids"] == ["EXP-001", "EXP-002"]
    assert len(project["details"]) == 5
    text = "\n".join(project["details"])
    for fact in ["文档解析", "Citation", "Top-K", "数据隔离", "健康检查", "Smoke Test", "Nginx", "systemd", "CORS"]:
        assert fact in text
    assert "独立开发者｜2026至今" not in text


def test_same_source_parent_and_phase_merge():
    result = merge_resume_project_hierarchies(
        payload([shell_project("EXP-001"), phase_project("EXP-001")]), RAW_INPUT, write_log=False,
    )
    assert len(result.resume_sections.projects) == 1


def test_entity_dedup_runs_parent_child_merge_before_string_dedup():
    result = deduplicate_resume_experience_entities(
        payload([shell_project(), phase_project()]), RAW_INPUT, write_log=False,
    )
    assert len(result.resume_sections.projects) == 1
    assert result.resume_sections.projects[0]["name"].startswith("北辰 Agent / AI Study Assistant（")


def test_two_independent_rag_projects_are_not_merged_for_shared_stack():
    first = phase_project("EXP-001")
    first["name"] = "课程 RAG 学习助手"
    first["role"] = "独立完成课程资料问答链路开发"
    second = phase_project("EXP-002")
    second["name"] = "企业知识库 RAG 平台"
    second["role"] = "负责企业文档检索与权限隔离"
    second["details"] = [
        "实现企业文档解析、Embedding 与向量检索链路。",
        "按组织权限隔离知识库，并建立 RAG 测试集。",
    ]
    result = merge_resume_project_hierarchies(payload([first, second]), "", write_log=False)
    assert len(result.resume_sections.projects) == 2


def test_two_rich_subsystems_remain_separate_without_parent_child_evidence():
    retrieval = phase_project("EXP-001")
    retrieval["name"] = "检索评测子系统"
    generation = phase_project("EXP-002")
    generation["name"] = "回答生成子系统"
    generation["details"] = [
        "实现上下文构建和回答生成链路。",
        "增加 Citation 来源展示与回答结果校验。",
    ]
    result = merge_resume_project_hierarchies(payload([retrieval, generation]), "", write_log=False)
    assert len(result.resume_sections.projects) == 2


def test_identity_records_product_hierarchy_without_creating_heading_only_identity():
    single_experience = RAW_INPUT.replace("项目二｜", "阶段说明｜")
    identities = build_experience_identities(single_experience)
    assert len(identities) == 1
    identity = identities[0]
    assert identity.canonical_project_name == "北辰 Agent / AI Study Assistant"
    assert identity.phase_name == "Course-scoped Study MVP"
    assert identity.relation_type == "phase_of"


def test_hierarchy_metadata_can_be_removed_before_api_or_docx_output():
    merged = merge_resume_project_hierarchies(
        payload([shell_project(), phase_project()]), RAW_INPUT, write_log=False,
    )
    stripped = strip_project_hierarchy_metadata(merged)
    project = stripped.resume_sections.projects[0]
    assert not HIERARCHY_INTERNAL_FIELDS.intersection(project)
    assert "北辰 Agent" in project["name"]


def test_hierarchy_log_contains_only_structured_relation_summary():
    old_log_path = project_hierarchy_service.LOG_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            log_path = Path(tmpdir) / "project-hierarchy.jsonl"
            project_hierarchy_service.LOG_PATH = log_path
            merge_resume_project_hierarchies(
                payload([shell_project(), phase_project()]),
                RAW_INPUT,
                stage="test",
                generation_result_id=680,
            )
            entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
            for key in [
                "detected_shell_project_count", "parent_child_relation_count", "merged_project_count",
                "removed_heading_detail_count", "canonical_project_names",
                "merged_source_experience_ids", "low_confidence_relation_count", "stage",
            ]:
                assert key in entry
            assert entry["merged_project_count"] == 1
            assert entry["merged_source_experience_ids"] == [["EXP-001", "EXP-002"]]
            assert "课程管理、文件上传" not in log_path.read_text(encoding="utf-8")
        finally:
            project_hierarchy_service.LOG_PATH = old_log_path


def test_historical_docx_contains_one_blessed_project_and_no_internal_fields():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=1, anonymous_user_id=None, session_id="hierarchy", target_role="AI Agent 开发",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW_INPUT,
    ))
    db.add(models.GenerationResult(
        id=680, experience_input_id=1, completeness_score=90,
        result_json=json.dumps(payload([shell_project(), phase_project()]).model_dump(), ensure_ascii=False),
    ))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="hierarchy", session_id="hierarchy", generation_result_id=680,
            ))
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert text.count("北辰 Agent / AI Study Assistant（Course-scoped Study MVP）｜") == 1
            assert "Course-scoped Study MVP（RAG 学习助手）｜个人项目" not in text
            assert "北辰 Agent / AI Study Assistant｜独立开发者｜2026至今" not in text
            for fact in ["文档解析", "Citation", "Top-K", "数据隔离", "健康检查", "Nginx", "systemd"]:
                assert fact in text
            for internal in HIERARCHY_INTERNAL_FIELDS | {"source_experience_id", "source_fact_ids", "fact_id"}:
                assert internal not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()
