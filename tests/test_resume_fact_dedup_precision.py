from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.resume_fact_dedup_service import deduplicate_resume_facts  # noqa: E402
from app.services.resume_title_format_service import extract_internship_position, resolve_resume_titles  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def make_payload(details: list[str], *, meta: str = "项目经历", name: str = "北辰 Agent", fact_ids: list[list[str]] | None = None):
    project = {
        "name": name, "meta": meta, "time": "2026", "intro": "独立开发 AI 学习助手",
        "role": "独立开发者", "details": details, "source_experience_id": "EXP-001",
        "detail_fact_ids": fact_ids or [[] for _ in details],
    }
    return schemas.GenerationPayload(
        completeness_score=85, confirmed_facts=[], missing_questions=[], normal_version="", bold_version="",
        boundary_version="", recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[],
        resume_sections=schemas.ResumeSections(
            personal_info={"姓名": "[待填写]"}, summary=["具备独立项目开发能力。"], skills=["RAG"],
            projects=[project], education={"学校": "[待填写]"}, interview_preparation=[]),
    )


def details_of(payload):
    return payload.resume_sections.projects[0]["details"]


def test_exact_and_punctuation_duplicates_are_removed():
    result = deduplicate_resume_facts(make_payload(["实现 Citation 来源展示。", "实现 Citation 来源展示", "实现 Citation 来源展示！"]), write_log=False)
    assert len(details_of(result)) == 1


def test_retrieval_experiment_duplicates_merge_to_more_complete_sentence():
    short = "围绕 chunk size、chunk overlap、Top-K、score threshold 和 retrieval ranking 进行实验"
    long = "先后围绕 chunk size、chunk overlap、Top-K、score threshold 和 retrieval ranking 进行实验，并引入 query intent 与 keyword bonus 优化"
    result = deduplicate_resume_facts(make_payload([short, long], fact_ids=[["EXP-001-F003"], ["EXP-001-F003", "EXP-001-F004"]]), write_log=False)
    assert len(details_of(result)) == 1
    assert "query intent" in details_of(result)[0]
    assert set(result.resume_sections.projects[0]["source_fact_ids"]) == {"EXP-001-F003", "EXP-001-F004"}


def test_generic_rag_chain_summary_is_removed_when_specific_details_cover_it():
    generic = "围绕文档解析、切块、Embedding、向量检索和回答生成梳理 RAG 应用链路"
    result = deduplicate_resume_facts(make_payload([
        "实现文档解析与文本切块，并生成 Embedding 写入向量索引",
        "完成向量检索、上下文构建与回答生成",
        generic,
    ]), write_log=False)
    assert generic not in details_of(result)
    assert len(details_of(result)) == 2


def test_shared_rag_terms_do_not_remove_distinct_facts():
    independent = [
        "实现 RAG 文档问答与上下文构建",
        "建立 Retrieval、Groundedness 与 Citation 评测指标",
        "实现 Citation Source Cards 展示来源文件和 Chunk 位置",
        "完成日志、健康检查与 Nginx 公网部署",
        "实现匿名用户数据隔离与课程资料隔离",
        "围绕 Top-K 和 score threshold 开展检索参数实验",
        "构建固定测试集并记录 Debug Trace",
        "解决 CORS 与端口冲突问题",
    ]
    result = deduplicate_resume_facts(make_payload(independent), write_log=False)
    assert details_of(result) == independent


def test_same_fact_ids_merge_but_do_not_invent_evaluation_scope():
    result = deduplicate_resume_facts(make_payload(
        ["构建 RAG 测试集", "构建 RAG 测试集并记录评测结果"],
        fact_ids=[["EXP-001-F005"], ["EXP-001-F005"]],
    ), write_log=False)
    text = "\n".join(details_of(result))
    assert len(details_of(result)) == 1
    assert "测试集规模" not in text and "人工评分" not in text


def test_internship_position_is_local_and_missing_stays_placeholder():
    assert extract_internship_position("在自行者科技有限公司 AI Agent 开发岗位实习，负责 RAG 测试。") == "AI Agent 开发实习"
    assert extract_internship_position("在自行者科技有限公司 AI agent 岗位实习，负责 RAG 测试。") == "AI Agent 开发实习"
    assert extract_internship_position("在自行者科技有限公司 AI Agent 实习，负责 RAG 测试。") == "AI Agent 开发实习"
    assert extract_internship_position("在自行者科技有限公司 AI Agent 测试实习，负责质量验证。") == "AI Agent 测试实习"
    assert extract_internship_position("担任后端开发实习生，负责接口开发。") == "后端开发实习"
    assert extract_internship_position("在星河科技有限公司实习，参与项目开发。", "前端开发") == "[待填写]"


def test_title_resolution_uses_company_position_and_specific_project_type():
    internship_raw = "实习经历｜自行者科技有限公司\n在自行者科技有限公司担任 AI Agent 开发实习生，负责 RAG 测试。"
    internship = make_payload(["建设 RAG 测试集"], meta="实习经历", name="自行者科技有限公司 AI Agent 开发实习")
    internship.resume_sections.projects[0]["resolved_experience_type"] = "实习经历"
    resolved = resolve_resume_titles(internship, internship_raw)
    project = resolved.resume_sections.projects[0]
    assert project["name"] == "自行者科技有限公司"
    assert project["position"] == "AI Agent 开发实习"

    personal = make_payload(["实现 RAG 问答"], meta="项目经历")
    personal.resume_sections.projects[0]["resolved_experience_type"] = "项目经历"
    personal = resolve_resume_titles(personal, "独立设计并开发北辰 Agent，实现 RAG 问答。")
    assert personal.resume_sections.projects[0]["meta"] == "个人项目"


def test_docx_uses_formal_titles_and_hides_internal_ids():
    raw = "实习经历｜自行者科技有限公司\n在自行者科技有限公司 AI agent 岗位实习，负责 RAG 测试集建设。"
    payload = make_payload(["建设 RAG 测试集"], meta="实习经历", name="自行者科技有限公司 AI Agent 开发实习", fact_ids=[["EXP-001-F001"]])
    payload.resume_sections.projects[0]["time"] = "[待填写]"
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="AI / 大模型 / Agent", mode="full_resume", packaging_level="大胆", experience_type="实习经历", raw_input=raw))
    db.add(models.GenerationResult(id=910, experience_input_id=1, completeness_score=85, result_json=payload.model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(anonymous_user_id="u", session_id="s", generation_result_id=910))
            text = "\n".join(paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert "自行者科技有限公司｜AI Agent 开发实习｜[待填写]" in text
            assert "source_experience_id" not in text and "source_fact_ids" not in text and "EXP-001" not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


if __name__ == "__main__":
    test_exact_and_punctuation_duplicates_are_removed()
    test_retrieval_experiment_duplicates_merge_to_more_complete_sentence()
    test_generic_rag_chain_summary_is_removed_when_specific_details_cover_it()
    test_shared_rag_terms_do_not_remove_distinct_facts()
    test_same_fact_ids_merge_but_do_not_invent_evaluation_scope()
    test_internship_position_is_local_and_missing_stays_placeholder()
    test_title_resolution_uses_company_position_and_specific_project_type()
    test_docx_uses_formal_titles_and_hides_internal_ids()
    print("resume fact dedup precision tests passed")
