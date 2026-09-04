from pathlib import Path
import json
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import models, schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import docx_service  # noqa: E402
from app.services.experience_identity_service import build_experience_identities  # noqa: E402
from app.services.experience_type_resolution_service import build_type_resolutions, resolve_project_types  # noqa: E402
from app.services.fact_guard_service import guard_hard_facts  # noqa: E402
from app.services.resume_project_reconciliation_service import reconcile_resume_projects  # noqa: E402
from docx import Document  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


RAW = """## 经历一：北辰 Agent / AI Study Assistant
2026 年独立设计并持续开发北辰 Agent，完成 Course-scoped 多文件 RAG、Citation、匿名数据隔离、测试和公网部署。

## 经历二：Resume Coach / AI 简历定位与面试承接平台
2026 年独立设计并开发 Resume Coach，一款面向大学生、应届生和实习求职者的 AI 简历平台。项目起点来自真实需求，独立设计完整工作流，根据用户测试持续版本迭代并完成公网部署。

## 经历三：自行者科技有限公司 AI Agent 开发实习
在自行者科技有限公司担任 AI Agent 开发实习生，参与 RAG 测试集建设、效果优化和 Token 成本优化。"""


def make_payload() -> schemas.GenerationPayload:
    projects = [
        {"name": "北辰 Agent", "meta": "实习经历", "time": "2026", "intro": "AI 学习助手", "role": "独立开发", "details": ["完成 RAG 与公网部署"], "source_experience_id": "EXP-001"},
        {"name": "Resume Coach", "meta": "实习经历", "time": "2026", "intro": "AI 简历平台", "role": "独立开发", "details": ["根据用户测试持续迭代"], "source_experience_id": "EXP-002"},
        {"name": "自行者科技", "meta": "项目经历", "time": "2026", "intro": "AI Agent 开发实习", "role": "实习生", "details": ["建设 RAG 测试集"], "source_experience_id": "EXP-003"},
    ]
    return schemas.GenerationPayload(completeness_score=85, confirmed_facts=[], missing_questions=[], normal_version="", bold_version="", boundary_version="", recommended_version="", claims=[], interview_plan=[], knowledge_checklist=[], resume_sections=schemas.ResumeSections(projects=projects))


def test_real_three_experience_relation_resolution():
    resolutions = build_type_resolutions(RAW)
    assert [resolutions[f"EXP-00{i}"].resolved_type for i in range(1, 4)] == ["项目经历", "项目经历", "实习经历"]
    assert resolutions["EXP-002"].confidence >= 0.8
    assert resolutions["EXP-003"].confidence >= 0.85
    assert resolutions["EXP-002"].excluded_context_signals
    assert not resolutions["EXP-002"].employment_relation_detected
    assert resolutions["EXP-002"].project_ownership_detected


def test_target_user_internship_words_are_not_employment_evidence():
    examples = ["独立开发面向实习生的招聘平台。", "独立开发实习岗位推荐系统。", "独立开发帮助用户准备实习面试的平台。"]
    for raw in examples:
        resolution = next(iter(build_type_resolutions(raw).values()))
        assert resolution.resolved_type == "项目经历", raw
        assert not resolution.employment_relation_detected


def test_real_employment_relations_are_internships():
    for raw in ["在星河科技有限公司担任前端实习生，负责页面开发。", "实习期间负责接口开发与联调。"]:
        assert next(iter(build_type_resolutions(raw).values())).resolved_type == "实习经历"


def test_reconciliation_only_assigns_source_and_resolver_locks_type():
    reconciled = reconcile_resume_projects(make_payload(), RAW, write_log=False)
    assert reconciled.resume_sections.projects[0]["meta"] == "实习经历"
    resolved = resolve_project_types(reconciled, RAW, write_log=False)
    assert [item["meta"] for item in resolved.resume_sections.projects] == ["项目经历", "项目经历", "实习经历"]
    guarded = guard_hard_facts(resolved, RAW)
    assert all(item.get("type_locked") for item in guarded.resume_sections.projects)
    assert guarded.resume_sections.projects[1]["meta"] == "项目经历"


def test_resolution_log_contains_relation_evidence():
    import app.services.experience_type_resolution_service as service
    old_path = service.LOG_PATH
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            service.LOG_PATH = Path(tmpdir) / "types.jsonl"
            resolve_project_types(make_payload(), RAW, stage="test", generation_result_id=808)
            entries = [json.loads(line) for line in service.LOG_PATH.read_text(encoding="utf-8").splitlines()]
            resume_entry = next(item for item in entries if item["experience_id"] == "EXP-002")
            assert resume_entry["excluded_context_count"] > 0
            assert resume_entry["resolver_version"] == "v0.9.2"
            assert "Resume Coach" not in json.dumps(resume_entry, ensure_ascii=False)
            assert resume_entry["type_locked"] is True
        finally:
            service.LOG_PATH = old_path


def test_docx_routes_projects_and_real_internship_correctly():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    db.add(models.ExperienceInput(id=1, anonymous_user_id=1, session_id="s", target_role="AI / 大模型 / Agent", mode="full_resume", packaging_level="大胆", experience_type="综合经历", raw_input=RAW))
    persisted = resolve_project_types(make_payload(), RAW, write_log=False)
    db.add(models.GenerationResult(id=808, experience_input_id=1, completeness_score=85, result_json=persisted.model_dump_json()))
    db.commit()
    old_output = docx_service.OUTPUT_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            docx_service.OUTPUT_DIR = Path(tmpdir)
            response = docx_service.create_docx(db, schemas.DocxCreate(anonymous_user_id="u", session_id="s", generation_result_id=808))
            text = "\n".join(p.text for p in Document(Path(tmpdir) / response.file_name).paragraphs)
            assert "实习经历" in text and "项目经历" in text, text.encode("unicode_escape")
            assert text.index("实习经历") < text.index("项目经历")
            assert text.index("自行者科技") < text.index("北辰 Agent")
            assert "Resume Coach" in text and "source_experience_id" not in text
        finally:
            docx_service.OUTPUT_DIR = old_output
            db.close()


if __name__ == "__main__":
    test_real_three_experience_relation_resolution()
    test_target_user_internship_words_are_not_employment_evidence()
    test_real_employment_relations_are_internships()
    test_reconciliation_only_assigns_source_and_resolver_locks_type()
    test_resolution_log_contains_relation_evidence()
    test_docx_routes_projects_and_real_internship_correctly()
    print("relation-aware experience type resolution tests passed")
