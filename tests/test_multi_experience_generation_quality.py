from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services import resume_section_fallback_service  # noqa: E402
from app.services.result_cleanup_service import cleanup_generation_payload  # noqa: E402
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402


LONG_REALISTIC_RECOMMENDED = """项目一｜AI RAG 智能助手

从零设计并持续迭代一套可公网使用的 AI RAG 助手，使用 React + TypeScript、FastAPI、SQLite 完成前后端与数据持久化，实现文件上传解析、文本切块、BAAI/bge-m3 Embedding、向量检索、RAG 问答、Citation、连续对话与会话恢复。围绕 chunk、Top-K、阈值及检索排序进行了多轮量化优化，并搭建 Debug Trace、固定测试集和 Groundedness、Citation、Retrieval 等评测指标。工程侧完成匿名用户数据隔离、邀请码保护、日志、健康检查、Smoke Test，并解决旧进程、端口冲突、Embedding 配置、CORS 等实际联调问题，最终通过 VPS + Nginx + systemd 部署并上线独立域名。

### 项目二｜Resume Positioning Coach

独立设计并开发 AI 简历定位与包装网站，核心目标是将用户真实经历转化为“表达更强、但面试能够承接”的简历内容。设计“经历输入 → 信息完整度分析 → 岗位定位 → 三档包装 → Claim 承接检查 → 面试准备 → 简历生成 → DOCX 导出”的完整工作流，并通过风险分级识别缺乏事实支撑的夸大表达。根据真实用户测试持续优化产品：重构早期复杂按钮式 UI，形成更清晰的流程化交互；发现 LLM 虽满足 JSON Schema 但正式简历字段可能为空后，引入 Resume Section Fallback，在保存和导出前进行业务完整性检查。目前进一步发现多经历场景存在 Experience Dilution，正推进经历级拆分与分阶段生成以保持单段履历的信息密度。
"""


def build_multi_project_payload(project_count: int = 3):
    project_blocks = [
        (
            "项目一：AI 复习辅助系统\n"
            "项目简介：面向学生复习场景的 RAG 工具，支持资料解析、知识检索和复习重点生成。\n"
            "我的职责：独立完成前后端链路、资料上传、检索流程和用户反馈迭代。\n"
            "技术细节：使用 Python 和 FastAPI 构建接口。接入 RAG 检索流程。设计 SQLite 数据存储。记录访问日志和部署记录。\n"
            "项目成果：有真实用户访问记录。"
        ),
        (
            "项目二：开源简历包装 Skill\n"
            "项目简介：面向技术求职者的简历定位与包装工具，支持追问、边界判断和面试承接。\n"
            "我的职责：设计 Skill 目录结构、规则文档、测试脚本和 DOCX 生成链路。\n"
            "技术细节：沉淀 Claim 风险规则。构建面试知识映射。实现版本化测试报告。维护 GitHub 仓库。\n"
            "项目成果：形成可复用的简历生成工作流。"
        ),
        (
            "项目三：校园数据分析项目\n"
            "项目简介：围绕学生学习行为数据进行整理、分析和可视化展示。\n"
            "我的职责：负责数据清洗、指标整理和分析结论输出。\n"
            "技术细节：使用 Pandas 完成数据处理。使用 Matplotlib 输出图表。对异常数据进行筛查。整理分析报告。\n"
            "项目成果：支持团队进行课程展示和答辩。"
        ),
    ][:project_count]

    recommended = "\n\n".join(project_blocks)
    return {
        "completeness_score": 78,
        "confirmed_facts": [
            "用户做过 AI 复习辅助系统",
            "用户做过简历包装 Skill",
            "用户做过校园数据分析项目",
        ][:project_count],
        "missing_questions": ["各项目的具体时间和量化指标还可以继续补充"],
        "normal_version": recommended,
        "bold_version": recommended,
        "boundary_version": "边界参考：不要把未提供的企业实习、模型训练或性能提升写成既成事实。",
        "recommended_version": recommended,
        "claims": [
            {
                "claim": "负责 RAG 检索链路设计",
                "risk_level": "yellow",
                "evidence": "用户提供了 RAG 项目经历",
                "risk_reason": "需要能讲清检索、召回和生成链路",
                "interview_questions": ["RAG 的分块和检索策略是什么？"],
                "knowledge_to_prepare": ["RAG", "向量检索"],
                "downgrade_wording": "参与 RAG 检索链路实现与调试",
            }
        ],
        "interview_plan": [
            "面试问题：请介绍 AI 复习辅助系统。回答要点：说明项目目标、RAG 链路和个人职责。",
            "面试问题：请介绍简历包装 Skill。回答要点：说明规则设计、测试报告和 DOCX 生成。",
        ],
        "knowledge_checklist": ["Python", "FastAPI", "SQLite", "RAG", "Pandas", "Matplotlib"],
        "resume_sections": {
            "personal_info": {"姓名": "[待填写]", "求职意向": "AI / 大模型 / Agent 开发实习生"},
            "summary": [],
            "skills": [],
            "projects": [],
            "education": {"学校": "[待填写]", "专业": "[待填写]", "学历": "本科", "时间": "[待填写]"},
            "interview_preparation": [],
        },
    }


def test_fallback_keeps_two_project_experiences():
    payload = fill_resume_sections(build_multi_project_payload(2), write_log=False)

    assert len(payload.resume_sections.projects) >= 2
    assert payload.resume_sections.projects[0]["name"] == "AI 复习辅助系统"
    assert payload.resume_sections.projects[1]["name"] == "开源简历包装 Skill"
    assert all(len(project["details"]) >= 4 for project in payload.resume_sections.projects[:2])


def test_fallback_does_not_merge_three_experiences_into_one():
    payload = fill_resume_sections(build_multi_project_payload(3), write_log=False)
    names = [project["name"] for project in payload.resume_sections.projects]

    assert len(payload.resume_sections.projects) >= 3
    assert "AI 复习辅助系统" in names
    assert "开源简历包装 Skill" in names
    assert "校园数据分析项目" in names


def test_fallback_parses_realistic_long_vertical_bar_project_input():
    data = build_multi_project_payload(2)
    data["recommended_version"] = LONG_REALISTIC_RECOMMENDED
    data["bold_version"] = LONG_REALISTIC_RECOMMENDED
    data["normal_version"] = LONG_REALISTIC_RECOMMENDED

    payload = fill_resume_sections(data, write_log=False)
    names = [project["name"] for project in payload.resume_sections.projects]

    assert len(payload.resume_sections.projects) >= 2
    assert "AI RAG 智能助手" in names
    assert "Resume Positioning Coach" in names
    assert all(len(project["details"]) >= 4 for project in payload.resume_sections.projects[:2])


def test_cleanup_keeps_multi_project_density():
    data = build_multi_project_payload(3)
    data["resume_sections"]["projects"] = [
        {
            "name": f"项目 {index}",
            "meta": "个人项目",
            "time": "[待填写]",
            "intro": "项目简介",
            "role": "我的职责",
            "details": [f"技术细节 {detail}" for detail in range(10)],
        }
        for index in range(5)
    ]

    cleaned = cleanup_generation_payload(data, source="test")

    assert len(cleaned.resume_sections.projects) == 5
    assert len(cleaned.resume_sections.projects[0]["details"]) == 8


def test_skills_are_extracted_only_from_existing_terms():
    payload = fill_resume_sections(build_multi_project_payload(2), write_log=False)

    assert "Python" in payload.resume_sections.skills
    assert "FastAPI" in payload.resume_sections.skills
    assert "RAG" in payload.resume_sections.skills
    assert "LangGraph" not in payload.resume_sections.skills
    assert "Redis" not in payload.resume_sections.skills


def test_multi_project_docx_contains_multiple_project_names():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    payload = fill_resume_sections(build_multi_project_payload(2), write_log=False)
    db.add(models.ExperienceInput(
        id=1,
        anonymous_user_id=1,
        session_id="s-test",
        target_role="AI / 大模型 / Agent",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="项目经历",
        raw_input=payload.recommended_version,
    ))
    row = models.GenerationResult(
        id=301,
        experience_input_id=1,
        completeness_score=payload.completeness_score,
        result_json=payload.model_dump_json(),
    )
    db.add(row)
    db.commit()

    original_output_dir = docx_service.OUTPUT_DIR
    original_log_path = resume_section_fallback_service.LOG_PATH
    original_log_dir = resume_section_fallback_service.LOG_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            resume_section_fallback_service.LOG_DIR = Path(tmpdir)
            resume_section_fallback_service.LOG_PATH = Path(tmpdir) / "resume_section_fallback.jsonl"
            response = docx_service.create_docx(
                db,
                schemas.DocxCreate(anonymous_user_id="u-test", session_id="s-test", generation_result_id=301),
            )

            assert response is not None
            path = Path(tmpdir) / response.file_name
            assert path.exists()
            text = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
            assert "AI 复习辅助系统" in text
            assert "开源简历包装 Skill" in text
            assert "项目经历" in text
        finally:
            docx_service.OUTPUT_DIR = original_output_dir
            resume_section_fallback_service.LOG_PATH = original_log_path
            resume_section_fallback_service.LOG_DIR = original_log_dir
    db.close()


if __name__ == "__main__":
    test_fallback_keeps_two_project_experiences()
    test_fallback_does_not_merge_three_experiences_into_one()
    test_fallback_parses_realistic_long_vertical_bar_project_input()
    test_cleanup_keeps_multi_project_density()
    test_skills_are_extracted_only_from_existing_terms()
    test_multi_project_docx_contains_multiple_project_names()
    print("multi experience generation quality tests passed")
