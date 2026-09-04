from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.resume_delivery_quality_gate_service import ensure_resume_delivery_quality  # noqa: E402
from app.services.resume_skill_evidence_guard_service import guard_resume_skill_evidence  # noqa: E402
from app.services.resume_skill_taxonomy_service import calibrate_resume_skill_taxonomy  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """独立设计并开发 Resume Coach，使用 Python、FastAPI、React、TypeScript 和 Git，实现简历定位、Claim 风险检查和 DOCX 导出，探索如何在表达更强和面试能够真实承接之间找到边界。真实用户测试发现结构校验成功但正式简历字段仍可能为空，因此增加业务完整性检查和 Resume Section Fallback。针对多经历事实串用问题，引入 Experience ID 和 Fact Ledger 建立经历级事实边界。"""


def payload():
    return schemas.GenerationPayload(
        completeness_score=90, confirmed_facts=[], missing_questions=[], normal_version="n", bold_version="b",
        boundary_version="x", recommended_version="r", claims=[], interview_plan=[], knowledge_checklist=["学习 Docker"],
        resume_sections=schemas.ResumeSections(
            skills=["编程语言：Python、TypeScript", "工具：Git、Docker（如掌握）"],
            projects=[{"name": "Resume Coach", "meta": "个人项目", "time": "2026",
                "intro": "面向求职者设计 AI 简历定位与面试承接平台。", "role": "独立开发",
                "details": [
                    "如何在“ ” “ 表达更强 和 面试能够真实承接”之间找到边界",
                    "将用户输入拆分为 EXP-001、EXP-002，并提取 raw_text、experience_type、explicit_tech_terms、explicit_metrics、evidence_terms 和 risk_terms。",
                    "引入 Experience ID 和 Fact Ledger 建立经历级事实边界。",
                ], "source_experience_id": "EXP-001"}],
            education={"学校": "[待填写]", "专业": "[待填写]", "学历": "[待填写]", "时间": "[待填写]"},
        ),
    )


def test_historical_docx_is_delivery_ready():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="AI Agent",
        mode="full_resume", packaging_level="大胆", experience_type="项目经历", raw_input=RAW))
    persisted = guard_resume_skill_evidence(payload(), RAW, write_log=False)
    persisted = calibrate_resume_skill_taxonomy(persisted, raw_input=RAW, write_log=False)
    persisted = ensure_resume_delivery_quality(persisted, RAW, write_log=False)
    db.add(models.GenerationResult(id=953, experience_input_id=1, completeness_score=90,
        result_json=persisted.model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(
                anonymous_user_id="u", session_id="s", generation_result_id=953))
            text = "\n".join(p.text for p in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert "Docker" not in text and "如掌握" not in text
            assert "编程语言：" in text and "Python" in text and "TypeScript" in text
            assert "工程化与部署：" in text and "Git" in text
            assert "\nPython\n" not in f"\n{text}\n"
            assert "raw_text" not in text and "explicit_metrics" not in text
            assert "如何在“ ” “" not in text
            assert not ("找到边界" in text and "表达强度" not in text)
            assert "Experience ID" in text and "Fact Ledger" in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()
