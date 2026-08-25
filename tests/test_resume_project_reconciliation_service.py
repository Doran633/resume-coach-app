from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.experience_identity_service import build_experience_identities  # noqa: E402
from app.services.resume_project_reconciliation_service import reconcile_resume_projects  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW_INPUT = """从零设计并持续迭代一套可公网使用的 AI RAG 助手，使用 React + TypeScript、FastAPI、SQLite 完成前后端与数据持久化，实现文件上传解析、文本切块、BAAI/bge-m3 Embedding、向量检索、RAG 问答、Citation、连续对话与会话恢复。围绕 chunk、Top-K、阈值及检索排序进行了多轮量化优化，并搭建 Debug Trace、固定测试集和 Groundedness、Citation、Retrieval 等评测指标。工程侧完成匿名用户数据隔离、邀请码保护、日志、健康检查、Smoke Test，并解决旧进程、端口冲突、Embedding 配置、CORS 等实际联调问题，最终通过 VPS + Nginx + systemd 部署并上线独立域名。

独立设计并开发 AI 简历定位与包装网站，核心目标是将用户真实经历转化为可承接的简历内容。设计经历输入、完整度分析、岗位定位、三档包装、Claim 检查、面试准备、简历生成和 DOCX 导出工作流。发现结构化简历字段为空后，引入 Resume Section Fallback，并识别 Experience Dilution 问题。

在自行者科技有限公司 AI Agent 开发岗位实习，参与企业级 Agent 助手开发，负责调试 RAG 模块、建立测试集和优化模型，最终让相关度从 0.4315 提升到 0.7258，平均 token 消耗从 1400 降低到 600。"""


def payload() -> schemas.GenerationPayload:
    return schemas.GenerationPayload(
        completeness_score=90,
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
            projects=[
                {
                    "name": "AI RAG 助手",
                    "meta": "个人项目",
                    "time": "[待填写]",
                    "intro": "从零设计并持续迭代可公网使用的 AI RAG 助手",
                    "role": "独立开发",
                    "details": [
                        "使用 React + TypeScript 构建前端界面",
                        "基于 FastAPI 和 SQLite 完成后端及数据持久化",
                        "围绕 chunk、Top-K 和检索排序进行优化",
                    ],
                },
                {
                    "name": "AI 简历定位与包装网站",
                    "meta": "个人项目",
                    "time": "[待填写]",
                    "intro": "独立设计并开发 AI 简历定位与包装网站",
                    "role": "独立设计、开发与迭代",
                    "details": [
                        "设计从经历输入到 DOCX 导出的完整工作流",
                        "引入 Claim 风险检查与面试准备",
                    ],
                },
                {
                    "name": "企业级 Agent 助手 RAG 模块优化",
                    "meta": "实习经历",
                    "time": "[待填写]",
                    "intro": "在自行者科技有限公司实习，参与 Agent 助手开发",
                    "role": "负责 RAG 模块调试和测试集建立",
                    "details": [
                        "将相关度从 0.4315 提升到 0.7258",
                        "将平均 token 消耗从 1400 降低到 600",
                    ],
                },
                {
                    "name": "综合经历项目",
                    "meta": "综合经历",
                    "time": "[待填写]",
                    "intro": "围绕用户提供的真实经历整理项目目标和技术实现",
                    "role": "根据现有经历整理个人参与内容与项目亮点",
                    "details": [
                        "使用 BAAI/bge-m3 Embedding，并实现连续对话与会话恢复",
                        "发现结构化简历字段为空后，引入 Resume Section Fallback",
                        "将相关度从 0.4315 提升到 0.7258",
                        "围绕用户提供的真实经历整理项目目标",
                    ],
                },
            ]
        ),
    )


def test_three_paragraphs_get_three_experience_ids():
    identities = build_experience_identities(RAW_INPUT)
    assert [item.experience_id for item in identities] == ["EXP-001", "EXP-002", "EXP-003"]
    assert "实习" in identities[2].raw_text


def test_comprehensive_project_is_removed_and_details_are_recovered():
    result = reconcile_resume_projects(payload(), RAW_INPUT, write_log=False)
    projects = result.resume_sections.projects
    all_text = "\n".join(str(project) for project in projects)

    assert len(projects) == 3
    assert "综合经历" not in all_text
    assert "BAAI/bge-m3" in " ".join(projects[0]["details"])
    assert "Resume Section Fallback" in " ".join(projects[1]["details"])
    assert "0.4315" in " ".join(projects[2]["details"])
    assert "0.4315" not in " ".join(projects[0]["details"])


def test_reconciliation_is_idempotent():
    once = reconcile_resume_projects(payload(), RAW_INPUT, write_log=False)
    twice = reconcile_resume_projects(once, RAW_INPUT, write_log=False)
    assert once.resume_sections.projects == twice.resume_sections.projects


def test_total_detail_budget_is_bounded_without_emptying_projects():
    result = reconcile_resume_projects(payload(), RAW_INPUT, write_log=False)
    details = [project["details"] for project in result.resume_sections.projects]
    assert sum(len(items) for items in details) <= 18
    assert all(items for items in details)


def test_historical_payload_docx_removes_comprehensive_project():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    experience = models.ExperienceInput(
        id=1,
        anonymous_user_id=1,
        session_id="s-test",
        target_role="AI / 大模型 / Agent",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="综合经历",
        raw_input=RAW_INPUT,
    )
    result_row = models.GenerationResult(
        id=502,
        experience_input_id=1,
        completeness_score=90,
        result_json=payload().model_dump_json(),
    )
    db.add(experience)
    db.add(result_row)
    db.commit()

    original_output_dir = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(
                db,
                schemas.DocxCreate(
                    anonymous_user_id="u-test",
                    session_id="s-test",
                    generation_result_id=502,
                ),
            )
            document_text = "\n".join(
                paragraph.text for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs
            )
            assert "综合经历项目" not in document_text
            assert "AI RAG 助手" in document_text
            assert "AI 简历定位与包装网站" in document_text
            assert "企业级 Agent 助手 RAG 模块优化" in document_text
            assert "BAAI/bge-m3" in document_text
        finally:
            docx_service.OUTPUT_DIR = original_output_dir
    db.close()


if __name__ == "__main__":
    test_three_paragraphs_get_three_experience_ids()
    test_comprehensive_project_is_removed_and_details_are_recovered()
    test_reconciliation_is_idempotent()
    test_total_detail_budget_is_bounded_without_emptying_projects()
    test_historical_payload_docx_removes_comprehensive_project()
    print("resume project reconciliation tests passed")
