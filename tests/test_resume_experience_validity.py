import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import (  # noqa: E402
    docx_service,
    resume_experience_validity_service,
    resume_section_fallback_service,
)
from app.services.docx_delivery_readiness_service import prepare_docx_delivery  # noqa: E402
from app.services.experience_identity_service import build_experience_identities  # noqa: E402
from app.services.project_hierarchy_service import classify_shell_project, is_shell_project  # noqa: E402
from app.services.resume_experience_entity_dedup_service import deduplicate_resume_experience_entities  # noqa: E402
from app.services.resume_experience_validity_service import ensure_resume_experience_validity  # noqa: E402
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW_INPUT = """项目一｜北辰 Agent / AI Study Assistant
独立开发 AI 学习助手，面向大学生课程复习场景提供智能问答与学习辅助。
实现文档解析、文本切块、Embedding、向量检索、RAG 问答与 Citation 来源展示。
按客户端和课程维度实现数据隔离，增加 request_id 日志、健康检查和 Smoke Test。
通过 Nginx 与 systemd 完成部署，并处理 CORS 和端口冲突问题。

经历二｜其他经历
北辰 Agent / AI Study Assistant｜独立开发者｜2026 至今"""


def make_payload(projects: list[dict]) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=88,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]"},
            summary=["具备 AI 应用开发与工程交付能力。"],
            skills=["AI / 大模型应用：RAG、Embedding、Citation"],
            projects=projects,
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]"},
            interview_preparation=[],
        ),
    )


def rich_project(name: str = "北辰 Agent / AI Study Assistant", source_id: str = "EXP-001") -> dict:
    return {
        "name": name, "meta": "个人项目", "time": "2026 至今",
        "intro": "面向大学生课程复习场景开发 AI 学习助手。",
        "role": "独立负责产品设计、功能开发与部署验证。",
        "details": [
            "实现文档解析、文本切块、Embedding、向量检索、RAG 问答与 Citation 来源展示。",
            "按客户端和课程维度实现数据隔离，避免学习资料串用。",
            "增加 request_id 日志、健康检查和 Smoke Test，支持问题定位与发布验证。",
            "通过 Nginx 与 systemd 完成部署，并处理 CORS 和端口冲突问题。",
        ],
        "source_experience_id": source_id,
        "source_fact_ids": [f"{source_id}-F{index:03d}" for index in range(1, 5)],
    }


def heading_shell(source_id: str = "EXP-002") -> dict:
    heading = "北辰 Agent / AI Study Assistant｜独立开发者｜2026 至今"
    return {
        "name": "其他经历", "meta": "个人项目", "time": "[待填写]",
        "intro": heading, "role": heading, "details": [heading],
        "source_experience_id": source_id,
    }


def test_screenshot_other_experience_shell_is_absorbed_without_losing_facts():
    result = ensure_resume_experience_validity(
        make_payload([rich_project(), heading_shell()]), RAW_INPUT, write_log=False,
    )
    assert len(result.resume_sections.projects) == 1
    project = result.resume_sections.projects[0]
    assert project["name"] == "北辰 Agent / AI Study Assistant"
    text = "\n".join(project["details"])
    for fact in ["RAG", "Citation", "数据隔离", "日志", "健康检查", "Smoke Test", "Nginx", "systemd", "CORS"]:
        assert fact in text
    for invented in ["Docker", "高并发", "用户数", "一等奖"]:
        assert invented not in text
    assert "其他经历" not in result.model_dump_json()


def test_repeated_heading_fields_are_classified_as_shell():
    shell = heading_shell()
    shell["name"] = "北辰 Agent 标题残片"
    assert is_shell_project(shell)
    assert classify_shell_project(shell) == "heading_residue_shell"


def test_heading_only_segment_does_not_receive_experience_id():
    identities = build_experience_identities(RAW_INPUT)
    assert len(identities) == 1
    assert identities[0].title == "北辰 Agent / AI Study Assistant"


def test_fallback_does_not_create_heading_only_project():
    empty = make_payload([])
    result = fill_resume_sections(empty, raw_input=RAW_INPUT, write_log=False)
    assert len(result.resume_sections.projects) == 1
    assert result.resume_sections.projects[0]["name"] != "其他经历"
    assert "独立开发者｜2026 至今" not in "\n".join(result.resume_sections.projects[0]["details"])


def test_fallback_logs_rejected_heading_candidate():
    data = make_payload([]).model_dump()
    data["recommended_version"] = (
        "项目一｜其他经历\n北辰 Agent / AI Study Assistant｜独立开发者｜2026 至今"
    )
    old_path = resume_section_fallback_service.LOG_PATH
    old_dir = resume_section_fallback_service.LOG_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            resume_section_fallback_service.LOG_DIR = Path(tmpdir)
            resume_section_fallback_service.LOG_PATH = Path(tmpdir) / "fallback.jsonl"
            result = fill_resume_sections(data, stage="test")
            entry = json.loads(resume_section_fallback_service.LOG_PATH.read_text(encoding="utf-8"))
            assert result.resume_sections.projects == []
            assert entry["fallback_candidate_rejected_count"] >= 1
        finally:
            resume_section_fallback_service.LOG_PATH = old_path
            resume_section_fallback_service.LOG_DIR = old_dir


def test_entity_dedup_absorbs_heading_shell_even_with_distinct_source_ids():
    result = deduplicate_resume_experience_entities(
        make_payload([rich_project(), heading_shell()]), RAW_INPUT, write_log=False,
    )
    assert len(result.resume_sections.projects) == 1
    assert result.resume_sections.projects[0]["name"] == "北辰 Agent / AI Study Assistant"


def test_two_independent_rag_projects_remain_separate():
    first = rich_project("课程 RAG 学习助手", "EXP-001")
    second = rich_project("企业知识库 RAG 平台", "EXP-002")
    second["intro"] = "面向企业知识检索场景开发独立的 RAG 平台。"
    second["details"] = ["实现企业文档检索与组织权限隔离，并建立独立评测集。"]
    result = ensure_resume_experience_validity(make_payload([first, second]), write_log=False)
    assert len(result.resume_sections.projects) == 2


def test_real_non_project_experiences_are_preserved():
    rows = []
    for name, meta, detail in [
        ("实验室检索研究", "科研经历", "参与资料整理、实验记录和检索结果分析。"),
        ("创新创业比赛", "竞赛经历", "负责方案设计与答辩展示，获得一等奖。"),
        ("开源文档贡献", "开源经历", "参与问题修复、文档完善和提交评审。"),
        ("学院晚会", "校园 / 社团经历", "参与节目安排、沟通协调和现场执行。"),
    ]:
        rows.append({
            "name": name, "meta": meta, "time": "[待填写]", "intro": detail,
            "role": detail, "details": [detail],
        })
    result = ensure_resume_experience_validity(make_payload(rows), write_log=False)
    assert len(result.resume_sections.projects) == 4


def test_unmatched_shell_is_removed_and_requests_more_information():
    shell = heading_shell()
    shell["intro"] = shell["role"] = shell["details"][0] = "未确认产品｜参与者｜2026"
    result = ensure_resume_experience_validity(make_payload([shell]), write_log=False)
    assert result.resume_sections.projects == []
    assert any("职责、技术动作或结果证据" in item for item in result.missing_questions)


def test_delivery_gate_rejects_invalid_project_and_internal_fields_do_not_leak():
    result = prepare_docx_delivery(make_payload([rich_project(), heading_shell()]))
    dumped = result.model_dump_json()
    assert len(result.resume_sections.projects) == 1
    assert "其他经历" not in dumped
    assert "heading_residue_shell" not in dumped


def test_validity_log_is_structured_and_does_not_contain_resume_body():
    old_path = resume_experience_validity_service.LOG_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            resume_experience_validity_service.LOG_PATH = Path(tmpdir) / "validity.jsonl"
            ensure_resume_experience_validity(
                make_payload([rich_project(), heading_shell()]), RAW_INPUT,
                stage="test", generation_result_id=909,
            )
            entry = json.loads(resume_experience_validity_service.LOG_PATH.read_text(encoding="utf-8"))
            assert entry["generic_experience_name_count"] == 1
            assert entry["heading_residue_project_count"] == 1
            assert entry["absorbed_shell_count"] == 1
            assert entry["generation_result_id"] == 909
            assert "文档解析" not in json.dumps(entry, ensure_ascii=False)
        finally:
            resume_experience_validity_service.LOG_PATH = old_path


def test_historical_docx_removes_other_experience():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=1, anonymous_user_id=None, session_id="validity", target_role="AI Agent 开发",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW_INPUT,
    ))
    db.add(models.GenerationResult(
        id=909, experience_input_id=1, completeness_score=88,
        result_json=make_payload([rich_project(), heading_shell()]).model_dump_json(),
    ))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=909,
            ))
            paragraphs = [
                paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs
            ]
            text = "\n".join(paragraphs)
            project_headings = [
                line for line in paragraphs
                if line.startswith("北辰 Agent / AI Study Assistant")
            ]
            assert len(project_headings) == 1
            assert "其他经历" not in text
            assert "source_experience_id" not in text and "fact_id" not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()
