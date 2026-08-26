from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app import schemas  # noqa: E402
from app.services.result_cleanup_service import cleanup_generation_payload  # noqa: E402
from app.services.resume_section_integrity_service import ensure_resume_section_integrity  # noqa: E402
from app.services.resume_section_schema_service import ALLOWED_SECTION_KEYS, normalize_resume_section_schema  # noqa: E402


def data() -> dict:
    return {
        "completeness_score": 80, "confirmed_facts": [], "missing_questions": [], "normal_version": "",
        "bold_version": "", "boundary_version": "", "recommended_version": "", "claims": [],
        "interview_plan": [], "knowledge_checklist": [], "resume_sections": {
            "personal_info": {}, "education": {}, "summary": ["具备项目开发能力"], "个人优势": ["具备问题排查能力"],
            "skills": ["文档 Chunk 策略", "section summary chunk"], "projects": [{"name": "项目", "meta": "项目经历", "time": "[待填写]", "intro": "section 个人优势 chunk", "role": "独立开发", "details": ["优化 chunk size 和 Text Chunking", "summary chunk 内容如下"]}],
            "interview_preparation": [], "section summary": ["污染内容"],
        },
    }


def test_aliases_are_migrated_without_overwriting_summary():
    result = normalize_resume_section_schema(data())
    assert "具备项目开发能力" in result.resume_sections.summary
    assert "具备问题排查能力" in result.resume_sections.summary
    assert set(result.resume_sections.model_dump().keys()) == ALLOWED_SECTION_KEYS


def test_section_markers_are_removed_but_technical_chunk_is_preserved():
    result = ensure_resume_section_integrity(data())
    text = "\n".join(result.resume_sections.skills + result.resume_sections.projects[0]["details"])
    assert "section summary chunk" not in text
    assert "summary chunk 内容如下" not in text
    assert "文档 Chunk 策略" in text
    assert "chunk size" in text and "Text Chunking" in text
    assert result.resume_sections.projects[0]["intro"] == ""


def test_result_cleanup_no_longer_translates_standalone_summary_in_prose():
    payload = schemas.GenerationPayload.model_validate({**data(), "resume_sections": {key: value for key, value in data()["resume_sections"].items() if key in ALLOWED_SECTION_KEYS}})
    payload.normal_version = "section summary chunk"
    cleaned = cleanup_generation_payload(payload, source="test")
    assert "个人优势" not in cleaned.normal_version
    assert cleaned.normal_version == "section summary chunk"


if __name__ == "__main__":
    test_aliases_are_migrated_without_overwriting_summary()
    test_section_markers_are_removed_but_technical_chunk_is_preserved()
    test_result_cleanup_no_longer_translates_standalone_summary_in_prose()
    print("resume section integrity tests passed")
