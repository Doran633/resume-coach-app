from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.experience_fact_ledger_service import build_experience_fact_ledger  # noqa: E402
from app.services.fact_coverage_guard_service import guard_fact_coverage  # noqa: E402
from app.services.resume_project_reconciliation_service import reconcile_resume_projects  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW_INPUT = """从零设计并持续迭代一套可公网使用的 AI RAG 助手，使用 React + TypeScript、FastAPI、SQLite 完成前后端与数据持久化，实现文件上传解析、文本切块、BAAI/bge-m3 Embedding、向量检索、RAG 问答、Citation、连续对话与会话恢复。围绕 chunk、Top-K、阈值及检索排序进行了多轮量化优化，并搭建 Debug Trace、固定测试集和 Groundedness、Citation、Retrieval 等评测指标。工程侧完成匿名用户数据隔离、邀请码保护、日志、健康检查、Smoke Test，并解决旧进程、端口冲突、Embedding 配置、CORS 等实际联调问题，最终通过 VPS + Nginx + systemd 部署并上线独立域名。

独立设计并开发 AI 简历定位与包装网站，核心目标是将用户真实经历转化为“表达更强、但面试能够承接”的简历内容。设计“经历输入 → 信息完整度分析 → 岗位定位 → 三档包装 → Claim 承接检查 → 面试准备 → 简历生成 → DOCX 导出”的完整工作流，并通过风险分级识别缺乏事实支撑的夸大表达。根据真实用户测试持续优化产品：重构早期复杂按钮式 UI，形成更清晰的流程化交互；发现 LLM 虽满足 JSON Schema 但正式简历字段可能为空后，引入 Resume Section Fallback，在保存和导出前进行业务完整性检查。目前进一步发现多经历场景存在 Experience Dilution，正推进经历级拆分与分阶段生成以保持单段履历的信息密度。

在自行者科技有限公司AIagent开发岗位实习，参与企业级agent训练部署上线，建立测试集对RAG模块进行训练，使回答相关度从0.4315提升到0.7243，平均token消耗从1400降低到600每次。"""


def payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="",
        bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[],
        knowledge_checklist=[], resume_sections=schemas.ResumeSections(
            summary=["具备 AI 应用开发能力"], skills=["React、TypeScript、FastAPI、RAG"],
            projects=[
                {"name": "AI RAG 助手", "meta": "项目经历", "time": "[待填写]",
                 "intro": "从零设计并持续迭代可公网使用的 AI RAG 助手", "role": "独立开发者",
                 "details": [
                     "使用 React + TypeScript、FastAPI、SQLite 完成前后端与数据持久化",
                     "围绕 chunk、Top-K 和检索排序进行量化优化",
                     "通过 Nginx 和 systemd 完成公网部署",
                     "项目定位：围绕真实使用场景梳理需求、功能链路和交付目标，将原始经历整理为可投递的项目表达",
                 ], "source_experience_id": "EXP-001"},
                {"name": "AI 简历定位与包装网站", "meta": "项目经历", "time": "[待填写]",
                 "intro": "独立设计并开发 AI 简历定位与包装网站", "role": "独立开发者",
                 "details": ["设计从经历输入到 DOCX 导出的完整工作流", "根据真实用户测试重构 UI"],
                 "source_experience_id": "EXP-002"},
                {"name": "Agent 助手优化", "meta": "实习经历", "time": "[待填写]",
                 "intro": "在自行者科技有限公司参与 Agent 助手开发", "role": "AI Agent 开发实习生",
                 "details": ["相关度从 0.4315 提升到 0.7243", "平均 token 消耗从 1400 降低到 600"],
                 "source_experience_id": "EXP-003"},
            ]))


def processed() -> schemas.GenerationPayload:
    value = reconcile_resume_projects(payload(), RAW_INPUT, write_log=False)
    return guard_fact_coverage(value, RAW_INPUT, write_log=False)


def test_ledger_assigns_fact_ids_to_experiences():
    ledger = build_experience_fact_ledger(RAW_INPUT)
    assert ledger.for_experience("EXP-001")
    assert ledger.for_experience("EXP-002")
    assert all(fact.fact_id.startswith(fact.experience_id) for fact in ledger.facts)


def test_high_value_rag_and_resume_facts_are_recovered_without_crossing():
    result = processed()
    rag = "\n".join(result.resume_sections.projects[0]["details"])
    resume = "\n".join(result.resume_sections.projects[1]["details"])
    internship = "\n".join(result.resume_sections.projects[2]["details"])
    for term in ["匿名用户数据隔离", "邀请码", "健康检查", "Smoke Test", "CORS", "Retrieval"]:
        assert term in rag
    assert "Resume Section Fallback" in resume
    assert "Experience Dilution" in resume
    assert "围绕真实使用场景梳理需求" not in rag
    assert "0.4315" not in rag and "0.4315" not in resume
    assert "0.4315" in internship and "0.7243" in internship


def test_fact_budget_keeps_specific_facts_and_drops_generic_fillers():
    result = processed()
    details = [item for project in result.resume_sections.projects for item in project["details"]]
    assert len(details) <= 20
    assert not any("将原始经历整理为可投递" in item for item in details)
    assert any("Fallback" in item for item in details)


def test_docx_hides_internal_fact_and_experience_ids():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s-test", target_role="AI / 大模型 / Agent",
        mode="full_resume", packaging_level="大胆", experience_type="综合经历", raw_input=RAW_INPUT))
    db.add(models.GenerationResult(id=704, experience_input_id=1, completeness_score=90,
        result_json=payload().model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s-test", generation_result_id=704))
            text = "\n".join(p.text for p in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert "EXP-001" not in text and "F001" not in text and "source_fact_ids" not in text
            assert "Resume Section Fallback" in text and "匿名用户数据隔离" in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


if __name__ == "__main__":
    test_ledger_assigns_fact_ids_to_experiences()
    test_high_value_rag_and_resume_facts_are_recovered_without_crossing()
    test_fact_budget_keeps_specific_facts_and_drops_generic_fillers()
    test_docx_hides_internal_fact_and_experience_ids()
    print("experience fact coverage tests passed")
