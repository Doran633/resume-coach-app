from pathlib import Path
import json
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
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402
from app.services.long_input_service import analyze_long_input  # noqa: E402
from app.services.stable_generation_fallback_service import build_stable_generation_fallback  # noqa: E402


def build_friend_like_payload():
    recommended = (
        "个人优势：大二学生，具备AI应用开发经验，熟悉Python及常用机器学习库，对AI Agent开发有浓厚兴趣。"
        "\n项目经历：项目名称：回归分析智能计算器\n"
        "项目简介：面向数据分析场景的智能回归分析工具，实现数据合理性检测、模型自动选择与可视化评估。\n"
        "我的职责：独立设计并实现核心算法模块，包括数据清洗、异常检测、回归模型集成与评估。\n"
        "技术细节：基于Python，使用Pandas进行数据预处理，Scikit-learn实现线性回归，使用Matplotlib生成可视化报告。\n"
        "项目成果：工具可辅助用户快速完成回归分析。\n"
        "项目名称：智能停车场系统\n"
        "项目简介：融合多源数据的智能停车指引系统。\n"
        "我的职责：作为团队成员参与系统设计和算法模块实现。\n"
        "技术细节：使用Python、Flask构建后端服务，调用地图API处理路线数据。\n"
        "项目成果：系统在路演中获一等奖。"
    )
    return {
        "completeness_score": 65,
        "confirmed_facts": [
            "大二学生",
            "做过回归分析计算器",
            "作为团队成员设计智能停车场系统，路演获一等奖",
        ],
        "missing_questions": [],
        "normal_version": "个人优势：具备项目实践经历。",
        "bold_version": recommended,
        "boundary_version": "边界参考：不要写成企业级生产系统。",
        "recommended_version": recommended,
        "claims": [
            {
                "claim": "独立设计并实现核心算法模块",
                "risk_level": "yellow",
                "evidence": "用户提供了回归分析计算器经历",
                "risk_reason": "需要准备具体算法实现细节",
                "interview_questions": ["你如何检测数据合理性？"],
                "knowledge_to_prepare": ["异常检测", "回归模型评估"],
                "downgrade_wording": "参与开发回归分析计算器",
            }
        ],
        "interview_plan": ["面试问题：请介绍一下回归分析计算器。回答要点：说明项目背景、职责和技术实现。"],
        "knowledge_checklist": ["Python", "Pandas", "Scikit-learn", "Matplotlib", "Flask", "Agent"],
        "resume_sections": {
            "personal_info": {"姓名": "[待填写]", "求职意向": "AI / 大模型 / Agent 开发实习生"},
            "summary": [],
            "skills": [],
            "projects": [],
            "education": {"学校": "[待填写]", "专业": "[待填写]", "学历": "本科", "时间": "[待填写]"},
            "interview_preparation": [],
        },
    }


def test_fallback_fills_empty_sections_from_recommended_version():
    payload = fill_resume_sections(build_friend_like_payload(), write_log=False)

    assert payload.resume_sections.summary
    assert payload.resume_sections.skills
    assert len(payload.resume_sections.projects) >= 1
    assert payload.resume_sections.interview_preparation
    assert payload.resume_sections.projects[0]["name"] == "回归分析智能计算器"
    assert "Python" in payload.resume_sections.skills
    assert "Scikit-learn" in payload.resume_sections.skills


def test_fallback_does_not_override_existing_sections():
    data = build_friend_like_payload()
    data["resume_sections"]["summary"] = ["已有优势"]
    data["resume_sections"]["skills"] = ["已有技能"]
    data["resume_sections"]["projects"] = [
        {
            "name": "已有项目",
            "meta": "个人项目",
            "time": "2026",
            "intro": "已有简介",
            "role": "已有职责",
            "details": ["已有细节"],
        }
    ]
    data["resume_sections"]["interview_preparation"] = ["已有准备"]

    payload = fill_resume_sections(data, write_log=False)

    assert payload.resume_sections.summary == ["已有优势"]
    assert payload.resume_sections.skills == ["已有技能"]
    assert payload.resume_sections.projects[0]["name"] == "已有项目"
    assert payload.resume_sections.interview_preparation == ["已有准备"]


def test_fallback_uses_only_existing_technical_terms():
    payload = fill_resume_sections(build_friend_like_payload(), write_log=False)

    assert "Python" in payload.resume_sections.skills
    assert "React" not in payload.resume_sections.skills
    assert "LangGraph" not in payload.resume_sections.skills


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_fallback_log_records_structured_empty_and_generation_stage():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_log_path = resume_section_fallback_service.LOG_PATH
        original_log_dir = resume_section_fallback_service.LOG_DIR
        try:
            resume_section_fallback_service.LOG_DIR = Path(tmpdir)
            resume_section_fallback_service.LOG_PATH = Path(tmpdir) / "resume_section_fallback.jsonl"
            fill_resume_sections(build_friend_like_payload(), generation_result_id=32, stage="generation")
            [log] = read_jsonl(resume_section_fallback_service.LOG_PATH)

            assert log["resume_fallback_triggered"] is True
            assert log["changed"] is True
            assert log["fallback_reason"] == "structured_resume_empty"
            assert "structured_resume_empty" in log["fallback_reasons"]
            assert "projects" in log["fallback_sections"]
            assert log["generation_result_id"] == 32
            assert log["stage"] == "generation"
        finally:
            resume_section_fallback_service.LOG_PATH = original_log_path
            resume_section_fallback_service.LOG_DIR = original_log_dir


def test_fallback_log_records_docx_export_stage():
    with tempfile.TemporaryDirectory() as tmpdir:
        original_log_path = resume_section_fallback_service.LOG_PATH
        original_log_dir = resume_section_fallback_service.LOG_DIR
        try:
            resume_section_fallback_service.LOG_DIR = Path(tmpdir)
            resume_section_fallback_service.LOG_PATH = Path(tmpdir) / "resume_section_fallback.jsonl"
            fill_resume_sections(build_friend_like_payload(), generation_result_id=32, stage="docx_export")
            [log] = read_jsonl(resume_section_fallback_service.LOG_PATH)

            assert log["resume_fallback_triggered"] is True
            assert log["stage"] == "docx_export"
        finally:
            resume_section_fallback_service.LOG_PATH = original_log_path
            resume_section_fallback_service.LOG_DIR = original_log_dir


def test_fallback_log_records_no_trigger_for_complete_sections():
    data = build_friend_like_payload()
    data["resume_sections"]["summary"] = ["已有优势"]
    data["resume_sections"]["skills"] = ["Python"]
    data["resume_sections"]["projects"] = [
        {
            "name": "已有项目",
            "meta": "个人项目",
            "time": "2026",
            "intro": "已有简介",
            "role": "已有职责",
            "details": ["已有细节"],
        }
    ]
    data["resume_sections"]["interview_preparation"] = ["已有准备"]

    with tempfile.TemporaryDirectory() as tmpdir:
        original_log_path = resume_section_fallback_service.LOG_PATH
        original_log_dir = resume_section_fallback_service.LOG_DIR
        try:
            resume_section_fallback_service.LOG_DIR = Path(tmpdir)
            resume_section_fallback_service.LOG_PATH = Path(tmpdir) / "resume_section_fallback.jsonl"
            fill_resume_sections(data, generation_result_id=33, stage="generation")
            [log] = read_jsonl(resume_section_fallback_service.LOG_PATH)

            assert log["resume_fallback_triggered"] is False
            assert log["changed"] is False
            assert log["fallback_sections"] == []
            assert log["fallback_reasons"] == []
            assert log["fallback_reason"] == ""
        finally:
            resume_section_fallback_service.LOG_PATH = original_log_path
            resume_section_fallback_service.LOG_DIR = original_log_dir


def test_docx_service_fallback_generates_nonblank_docx_for_empty_resume_sections():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    payload = schemas.GenerationPayload.model_validate(build_friend_like_payload())
    row = models.GenerationResult(
        id=32,
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
                schemas.DocxCreate(anonymous_user_id="u-test", session_id="s-test", generation_result_id=32),
            )
            assert response is not None
            path = Path(tmpdir) / response.file_name
            assert path.exists()
            text = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
            assert "回归分析智能计算器" in text
            assert "个人优势" in text
            assert "项目经历" in text
        finally:
            docx_service.OUTPUT_DIR = original_output_dir
            resume_section_fallback_service.LOG_PATH = original_log_path
            resume_section_fallback_service.LOG_DIR = original_log_dir
    db.close()


WEAK_NO_INTERNSHIP_RAW = """我是大二学生，想投前端开发或者泛互联网技术岗。
现在没有实习经历，主要做过一个课程大作业和一些学生工作。

课程项目是一个校园二手交易小系统，主要是小组作业。我负责写了几个 Vue 页面，包括商品列表、商品详情、发布商品和登录页面，也调了一些后端接口，处理过表单校验、页面跳转和接口返回数据展示。项目最后在课堂上做了展示，没有正式上线，也没有真实用户。
"""


def test_fallback_does_not_infer_internship_from_negative_statement():
    data = build_friend_like_payload()
    data["recommended_version"] = ""
    data["bold_version"] = ""
    data["normal_version"] = ""
    data["resume_sections"]["projects"] = []

    payload = fill_resume_sections(data, raw_input=WEAK_NO_INTERNSHIP_RAW, write_log=False)
    text = payload.model_dump_json()

    assert "实习经历" not in text
    assert all(project.get("meta") != "实习经历" for project in payload.resume_sections.projects)


def test_stable_generation_fallback_does_not_infer_internship_from_negative_statement():
    request = schemas.GenerateRequest(
        anonymous_user_id="u-test",
        session_id="s-test",
        target_role="前端开发",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="综合经历",
        raw_input=WEAK_NO_INTERNSHIP_RAW,
    )
    payload = build_stable_generation_fallback(request, analyze_long_input(WEAK_NO_INTERNSHIP_RAW))
    text = payload.model_dump_json()

    assert "实习经历" not in text
    assert all(project.get("meta") != "实习经历" for project in payload.resume_sections.projects)


if __name__ == "__main__":
    test_fallback_fills_empty_sections_from_recommended_version()
    test_fallback_does_not_override_existing_sections()
    test_fallback_uses_only_existing_technical_terms()
    test_fallback_log_records_structured_empty_and_generation_stage()
    test_fallback_log_records_docx_export_stage()
    test_fallback_log_records_no_trigger_for_complete_sections()
    test_docx_service_fallback_generates_nonblank_docx_for_empty_resume_sections()
    test_fallback_does_not_infer_internship_from_negative_statement()
    test_stable_generation_fallback_does_not_infer_internship_from_negative_statement()
    print("resume section fallback tests passed")
