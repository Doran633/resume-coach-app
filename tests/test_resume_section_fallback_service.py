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
from app.services.resume_section_fallback_service import fill_resume_sections  # noqa: E402


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
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
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
    db.close()


if __name__ == "__main__":
    test_fallback_fills_empty_sections_from_recommended_version()
    test_fallback_does_not_override_existing_sections()
    test_fallback_uses_only_existing_technical_terms()
    test_docx_service_fallback_generates_nonblank_docx_for_empty_resume_sections()
    print("resume section fallback tests passed")
