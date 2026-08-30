import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service, resume_delivery_quality_gate_service  # noqa: E402
from app.services.resume_delivery_quality_gate_service import (  # noqa: E402
    ensure_resume_delivery_quality,
    evaluate_delivery_quality_issues,
    measure_high_value_fact_coverage,
)
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """项目一｜课程 RAG 学习助手
独立开发课程 RAG 学习助手，使用 React、FastAPI 和 SQLite 实现前后端功能。
实现文档解析、文本切块、Embedding、向量检索、RAG 问答和 Citation 来源展示。
增加日志、健康检查和 Smoke Test，并通过 Nginx 与 systemd 完成公网部署。

项目二｜智能停车系统
作为团队核心成员设计智能停车系统，使用 LoRa、地磁传感器和地图 API 提供停车指引。
负责产品服务分析、风险预估与方案落地，实现历史车位记录和实时路线规划，在创新创业路演中获得一等奖。"""


def payload(projects: list[dict] | None = None, *, skills: list[str] | None = None) -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=88,
        confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]"},
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]"},
            summary=["具备独立项目开发与工程交付能力。"],
            skills=["前后端开发：React、FastAPI、SQLite"] if skills is None else skills,
            projects=projects if projects is not None else [rag_project(), parking_project()],
            interview_preparation=[],
        ),
    )


def rag_project(source_id: str = "EXP-001") -> dict:
    return {
        "name": "课程 RAG 学习助手", "meta": "个人项目", "time": "[待填写]",
        "intro": "面向课程复习场景开发 RAG 学习助手。",
        "role": "独立负责前后端功能开发与部署验证。",
        "details": [
            "使用 React、FastAPI 和 SQLite 搭建前后端系统。",
            "实现文档解析、文本切块、Embedding、向量检索、RAG 问答和 Citation 来源展示。",
            "增加日志、健康检查和 Smoke Test，并通过 Nginx 与 systemd 完成公网部署。",
        ],
        "source_experience_id": source_id,
        "source_fact_ids": [f"{source_id}-F001", f"{source_id}-F002", f"{source_id}-F003"],
        "detail_fact_ids": [[f"{source_id}-F001"], [f"{source_id}-F002"], [f"{source_id}-F003"]],
    }


def parking_project(source_id: str = "EXP-002") -> dict:
    return {
        "name": "智能停车系统", "meta": "项目经历", "time": "[待填写]",
        "intro": "面向停车位寻找和车位信息不透明问题设计智能停车系统。",
        "role": "作为团队核心成员负责产品服务分析、风险预估与方案落地。",
        "details": [
            "使用 LoRa、地磁传感器和地图 API 提供停车指引。",
            "实现历史车位记录和实时路线规划，在创新创业路演中获得一等奖。",
        ],
        "source_experience_id": source_id,
        "source_fact_ids": [f"{source_id}-F001", f"{source_id}-F002"],
        "detail_fact_ids": [[f"{source_id}-F001"], [f"{source_id}-F002"]],
    }


def test_empty_project_is_removed_and_fact_ledger_can_recover_empty_projects():
    empty = {"name": "其他经历", "meta": "其他经历", "time": "[待填写]", "intro": "", "role": "", "details": []}
    result = ensure_resume_delivery_quality(payload([empty]), RAW, write_log=False)
    assert len(result.resume_sections.projects) == 2
    assert all(project["name"] != "其他经历" for project in result.resume_sections.projects)
    assert all(project.get("source_experience_id") for project in result.resume_sections.projects)


def test_empty_skills_are_recovered_only_from_explicit_evidence():
    result = ensure_resume_delivery_quality(payload(skills=[]), RAW, write_log=False)
    text = "\n".join(result.resume_sections.skills)
    for term in ["React", "FastAPI", "SQLite", "RAG"]:
        assert term in text
    assert "Docker" not in text


def test_cross_experience_fact_is_moved_out_of_wrong_project():
    rag = rag_project()
    rag["details"].append("使用 LoRa 和地磁传感器提供停车指引，并在路演中获得一等奖。")
    rag["detail_fact_ids"].append([])
    result = ensure_resume_delivery_quality(payload([rag, parking_project()]), RAW, write_log=False)
    rag_text = "\n".join(result.resume_sections.projects[0]["details"])
    parking_text = "\n".join(result.resume_sections.projects[1]["details"])
    assert "LoRa" not in rag_text and "一等奖" not in rag_text
    assert "LoRa" in parking_text and "一等奖" in parking_text


def test_high_value_facts_survive_duplicate_cleanup():
    dirty = rag_project()
    dirty["details"].append(dirty["details"][2])
    dirty["detail_fact_ids"].append(["EXP-001-F003"])
    before = measure_high_value_fact_coverage(payload([dirty, parking_project()]), RAW)
    result = ensure_resume_delivery_quality(payload([dirty, parking_project()]), RAW, write_log=False)
    after = measure_high_value_fact_coverage(result, RAW)
    text = "\n".join(result.resume_sections.projects[0]["details"])
    assert after >= before
    for fact in ["日志", "健康检查", "Smoke Test", "Nginx", "systemd", "公网部署"]:
        assert fact in text


def test_distinct_fact_ids_preserve_similar_but_incremental_details():
    rag = rag_project()
    rag["details"] = [
        "围绕课程资料实现文档解析、Embedding 和向量检索。",
        "围绕课程资料实现文档解析、Embedding 和向量检索，并增加 Citation 来源展示。",
    ]
    rag["detail_fact_ids"] = [["EXP-001-F001"], ["EXP-001-F002"]]
    result = ensure_resume_delivery_quality(payload([rag, parking_project()]), RAW, write_log=False)
    assert len(result.resume_sections.projects[0]["details"]) >= 2


def test_exact_duplicate_and_cross_field_repetition_are_removed():
    rag = rag_project()
    rag["details"] = [rag["intro"], rag["details"][0], rag["details"][0], rag["details"][1]]
    rag["detail_fact_ids"] = [[], ["EXP-001-F001"], ["EXP-001-F001"], ["EXP-001-F002"]]
    result = ensure_resume_delivery_quality(payload([rag, parking_project()]), RAW, write_log=False)
    details = result.resume_sections.projects[0]["details"]
    normalized = [item.rstrip("。") for item in details]
    assert rag["intro"].rstrip("。") not in normalized
    assert normalized.count("使用 React、FastAPI 和 SQLite 搭建前后端系统") == 1


def test_fragment_is_recovered_or_removed_without_internal_prompt():
    rag = rag_project()
    rag["details"].append("针对该问题，通过")
    rag["detail_fact_ids"].append([])
    result = ensure_resume_delivery_quality(payload([rag, parking_project()]), RAW, write_log=False)
    text = result.model_dump_json()
    assert "针对该问题，通过" not in text
    assert "需补充原文" not in text


def test_invalid_characters_html_entities_and_internal_fields_are_cleaned():
    rag = rag_project()
    rag["details"].append("&#x56F4;绕 raw_text、source_fact_ids\u200b 完成质量验证。。")
    rag["detail_fact_ids"].append([])
    result = ensure_resume_delivery_quality(payload([rag, parking_project()]), RAW, write_log=False)
    visible = "\n".join([
        *result.resume_sections.summary,
        *result.resume_sections.skills,
        *[
            str(value)
            for project in result.resume_sections.projects
            for value in [
                project.get("name", ""), project.get("meta", ""), project.get("intro", ""),
                project.get("role", ""), *(project.get("details", []) or []),
            ]
        ],
    ])
    for forbidden in ["&#x56F4;", "\u200b", "raw_text", "source_fact_ids", "。。"]:
        assert forbidden not in visible
    assert "围绕" in visible and "原始经历文本" in visible


def test_coach_language_and_internal_debug_text_do_not_survive():
    dirty = payload()
    dirty.resume_sections.summary.append("如果被问到，可以准备降级表达。")
    dirty.resume_sections.projects[0]["details"].append("section summary chunk")
    result = ensure_resume_delivery_quality(dirty, RAW, write_log=False)
    visible = json.dumps(result.resume_sections.model_dump(), ensure_ascii=False)
    assert "如果被问到" not in visible
    assert "降级表达" not in visible
    assert "section summary chunk" not in visible


def test_quality_gate_is_idempotent():
    dirty = rag_project()
    dirty["details"].append(dirty["details"][0])
    dirty["detail_fact_ids"].append(["EXP-001-F001"])
    first = ensure_resume_delivery_quality(payload([dirty, parking_project()]), RAW, write_log=False)
    second = ensure_resume_delivery_quality(first, RAW, write_log=False)
    assert first.model_dump() == second.model_dump()


def test_adding_second_experience_does_not_change_first_experience_facts():
    first_only_raw = RAW.split("\n\n项目二", 1)[0]
    first = ensure_resume_delivery_quality(payload([rag_project()]), first_only_raw, write_log=False)
    combined = ensure_resume_delivery_quality(payload([rag_project(), parking_project()]), RAW, write_log=False)
    assert first.resume_sections.projects[0]["details"] == combined.resume_sections.projects[0]["details"]


def test_two_independent_rag_projects_are_not_merged():
    second = rag_project("EXP-002")
    second["name"] = "企业知识库 RAG 评测平台"
    second["intro"] = "面向企业知识检索场景建立独立的 RAG 评测平台。"
    second["details"] = ["建立固定测试集并记录 Groundedness 与 Citation 指标。"]
    raw = RAW.split("\n\n项目二", 1)[0] + "\n\n项目二｜企业知识库 RAG 评测平台\n建立固定测试集并记录 Groundedness 与 Citation 指标。"
    result = ensure_resume_delivery_quality(payload([rag_project(), second]), raw, write_log=False)
    assert len(result.resume_sections.projects) == 2


def test_weak_profile_keeps_positive_grounded_output():
    raw = "课程项目｜校园二手交易系统\n负责 Vue 页面开发、表单校验和接口联调，并完成课堂展示。"
    weak = payload([{
        "name": "校园二手交易系统", "meta": "课程项目", "time": "[待填写]",
        "intro": "围绕校园二手交易场景完成课程项目开发。", "role": "负责页面开发与接口联调。",
        "details": ["使用 Vue 完成商品列表和发布页面。", "完成表单校验与接口数据展示。"],
        "source_experience_id": "EXP-001",
    }], skills=["Vue"])
    result = ensure_resume_delivery_quality(weak, raw, write_log=False)
    visible = json.dumps(result.resume_sections.model_dump(), ensure_ascii=False)
    assert result.resume_sections.projects
    assert "Vue" in visible
    assert "没有实习" not in visible and "企业级" not in visible


def test_docx_hides_empty_skill_and_role_headings():
    raw = "校园活动经历｜学院晚会\n参与节目安排、沟通协调和现场执行，完成活动材料整理。"
    no_skill = payload([{
        "name": "学院晚会", "meta": "校园 / 社团经历", "time": "[待填写]",
        "intro": "参与学院晚会组织执行与材料整理。", "role": "", "details": ["参与节目安排、沟通协调和现场执行。"],
        "source_experience_id": "EXP-001",
    }], skills=[])
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=1, anonymous_user_id=None, session_id="gate", target_role="泛互联网岗位",
        mode="full_resume", packaging_level="大胆", experience_type="校园经历", raw_input=raw,
    ))
    db.add(models.GenerationResult(id=1001, experience_input_id=1, completeness_score=80, result_json=no_skill.model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=1001,
            ))
            paragraphs = [paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs]
            text = "\n".join(paragraphs)
            assert "技能与能力" not in text
            assert "我的职责：" not in [paragraph.strip() for paragraph in paragraphs]
            assert "学院晚会" in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


def test_gate_log_contains_only_structured_metadata():
    old_path = resume_delivery_quality_gate_service.LOG_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            resume_delivery_quality_gate_service.LOG_PATH = Path(tmpdir) / "gate.jsonl"
            ensure_resume_delivery_quality(payload(), RAW, stage="test", generation_result_id=1002)
            entry = json.loads(resume_delivery_quality_gate_service.LOG_PATH.read_text(encoding="utf-8"))
            for key in [
                "issue_count_by_code", "critical_issue_count", "repaired_issue_count",
                "high_value_coverage_before", "high_value_coverage_after", "gate_passed",
            ]:
                assert key in entry
            serialized = json.dumps(entry, ensure_ascii=False)
            assert "独立开发课程 RAG 学习助手" not in serialized
            assert "使用 LoRa、地磁传感器" not in serialized
        finally:
            resume_delivery_quality_gate_service.LOG_PATH = old_path


def test_final_evaluator_reports_no_critical_issue_for_clean_output():
    result = ensure_resume_delivery_quality(payload(), RAW, write_log=False)
    critical = [issue for issue in evaluate_delivery_quality_issues(result, RAW) if issue.severity == "critical"]
    assert critical == []
