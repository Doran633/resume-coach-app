"""Fixed rendering replays for v0.9.13.1, not historical request snapshots."""

import json
import sys
import tempfile
from pathlib import Path

from docx import Document
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402


def _payload() -> schemas.GenerationPayload:
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
            personal_info={"姓名": "【待填写】"},
            education={"学校": "【待填写】"},
            projects=[
                {
                    "name": "企业：星河科技有限公司",
                    "position": "岗位：产品运营实习",
                    "meta": "实习经历",
                    "time": "时间：2024.03-2024.06",
                    "intro": "完成用户调研与数据复盘。",
                    "role": "负责访谈记录整理。",
                    "details": ["技术细节：", "整理用户反馈并形成分析结论。", "技术细节：保留实际正文。"],
                    "source_experience_id": "EXP-001",
                    "immutable_source_experience_id": "EXP-001",
                    "source_binding_locked": True,
                    "source_fact_ids": ["EXP-001-F001", "EXP-001-F002"],
                    "role_source_fact_ids": ["EXP-001-F001"],
                    "detail_fact_ids": [[], ["EXP-001-F002"], ["EXP-001-F001"]],
                    "source_claim_ids": ["EXP-001-C001", "EXP-001-C002"],
                    "role_source_claim_ids": ["EXP-001-C001"],
                    "detail_claim_ids": [[], ["EXP-001-C002"], ["EXP-001-C001"]],
                },
                {
                    "name": "项目：校园活动管理系统",
                    "position": "岗位：不应展示",
                    "meta": "项目经历",
                    "time": "时间：【待填写】",
                    "intro": "完成活动报名流程。",
                    "role": "",
                    "details": ["实现活动信息维护。"],
                    "source_experience_id": "EXP-002",
                    "immutable_source_experience_id": "EXP-002",
                    "source_binding_locked": True,
                    "source_fact_ids": ["EXP-002-F001"],
                    "role_source_fact_ids": [],
                    "detail_fact_ids": [["EXP-002-F001"]],
                    "source_claim_ids": ["EXP-002-C001"],
                    "role_source_claim_ids": [],
                    "detail_claim_ids": [["EXP-002-C001"]],
                },
            ],
        ),
    )


def _database(payload: schemas.GenerationPayload):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(
        id=1,
        anonymous_user_id=1,
        session_id="rendering-v09131",
        target_role="产品运营",
        mode="full_resume",
        packaging_level="稳健",
        experience_type="项目经历",
        raw_input="fixed replay",
    ))
    db.add(models.GenerationResult(
        id=9131,
        experience_input_id=1,
        completeness_score=90,
        result_json=payload.model_dump_json(),
    ))
    db.commit()
    return db


def test_docx_consumes_persisted_fields_without_an_empty_technical_detail_bullet():
    payload = _payload()
    before = payload.model_dump(mode="json")
    db = _database(payload)
    stored_before = db.get(models.GenerationResult, 9131).result_json
    old_output = docx_service.OUTPUT_DIR

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(
                db,
                schemas.DocxCreate(
                    anonymous_user_id="u",
                    session_id="rendering-v09131",
                    generation_result_id=9131,
                ),
            )
            paragraphs = [
                paragraph.text
                for paragraph in Document(Path(tmpdir) / response.file_name).paragraphs
            ]
        finally:
            docx_service.OUTPUT_DIR = old_output

    assert "企业：星河科技有限公司｜岗位：产品运营实习｜时间：2024.03-2024.06" in paragraphs
    assert "项目：校园活动管理系统｜项目经历｜时间：【待填写】" in paragraphs
    assert "岗位：不应展示" not in "\n".join(paragraphs)
    assert "技术细节：" not in paragraphs
    assert "技术细节：整理用户反馈并形成分析结论。" in paragraphs
    assert "技术细节：保留实际正文。" in paragraphs
    assert payload.model_dump(mode="json") == before
    assert db.get(models.GenerationResult, 9131).result_json == stored_before
    db.close()


def test_frontend_has_type_scoped_header_mapping_without_semantic_reconstruction():
    source = (ROOT / "frontend" / "src" / "pages" / "ResultPage.tsx").read_text(encoding="utf-8")
    preview = source.split("function ProjectPreview", 1)[1].split("function FactStrip", 1)[0]

    assert 'project.meta === "实习经历"' in preview
    assert "project.position" in preview
    assert '"企业：【待填写】"' in preview
    assert '"岗位：【待填写】"' in preview
    assert '"时间：【待填写】"' in preview
    assert "raw_input" not in preview
    assert "details.join" not in preview


def test_fixed_payload_uses_strings_for_intro_role_and_a_list_for_details():
    project = _payload().resume_sections.projects[0]

    assert isinstance(project["intro"], str)
    assert isinstance(project["role"], str)
    assert isinstance(project["details"], list)
    assert all(isinstance(item, str) for item in project["details"])
    assert json.dumps(project["detail_fact_ids"]) == json.dumps(
        [[], ["EXP-001-F002"], ["EXP-001-F001"]]
    )

