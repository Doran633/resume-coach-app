from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.resume_typography_quality_service import clean_typography, ensure_typography_quality  # noqa: E402


def test_typography_examples_and_technical_terms():
    assert clean_typography("标题感知切块、、Query Intent") == "标题感知切块、Query Intent"
    assert clean_typography("RAG，，Agent") == "RAG，Agent"
    assert clean_typography("React、TypeScript、") == "React、TypeScript"
    assert clean_typography("功能开发。。。") == "功能开发。"
    assert clean_typography("Query  Intent 与 AI  Agent") == "Query Intent 与 AI Agent"
    protected = "C++、C#、Node.js、Vue.js、BAAI/bge-m3、Top-K、no-answer policy、-5%"
    assert clean_typography(protected) == protected


def test_leading_markdown_and_list_markers_are_removed_without_losing_content():
    cases = {
        " - 根据真实用户测试持续迭代输入流程": "根据真实用户测试持续迭代输入流程",
        "• * 建立 Experience ID 事实边界": "建立 Experience ID 事实边界",
        "- [ ] 完成 DOCX 验证": "完成 DOCX 验证",
        "- 完成功能开发": "完成功能开发",
        "* 完成功能开发": "完成功能开发",
        "+ 完成功能开发": "完成功能开发",
        "# 项目经历": "项目经历",
        "### Resume Coach": "Resume Coach",
        "> 引用内容": "引用内容",
        "1. 第一项": "第一项",
        "1) 第一项": "第一项",
    }
    for source, expected in cases.items():
        assert clean_typography(source) == expected
        assert clean_typography(clean_typography(source)) == expected


def test_typography_service_preserves_internal_provenance():
    project = {
        "name": "RAG、、助手", "meta": "个人项目", "time": "2026",
        "intro": "实现 RAG，，Agent 应用。", "role": "负责 Query  Intent 设计。",
        "details": [" - React、TypeScript、", "使用 C++、C#、Node.js 和 BAAI/bge-m3。"],
        "source_experience_id": "EXP-001", "source_fact_ids": ["EXP-001-F001"],
        "detail_fact_ids": [["EXP-001-F001"], ["EXP-001-F002"]],
    }
    value = schemas.GenerationPayload(
        completeness_score=80, confirmed_facts=[], missing_questions=[], normal_version="n",
        bold_version="b", boundary_version="x", recommended_version="r", claims=[],
        interview_plan=[], knowledge_checklist=[], resume_sections=schemas.ResumeSections(projects=[project]),
    )
    result = ensure_typography_quality(value, stage="test", write_log=False)
    cleaned = result.resume_sections.projects[0]
    assert cleaned["name"] == "RAG、助手"
    assert cleaned["role"] == "负责 Query Intent 设计。"
    assert cleaned["details"][0] == "React、TypeScript"
    assert cleaned["source_experience_id"] == "EXP-001"
    assert cleaned["source_fact_ids"] == ["EXP-001-F001"]
    assert cleaned["detail_fact_ids"] == [["EXP-001-F001"], ["EXP-001-F002"]]
