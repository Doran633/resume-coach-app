from pathlib import Path
import os
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import schemas  # noqa: E402
from app.database import Base  # noqa: E402
from app.services import generation_service  # noqa: E402
from app.services.json_repair_service import parse_llm_json  # noqa: E402
from app.services.long_input_service import analyze_long_input  # noqa: E402
from app.services.llm_service import LLMResult  # noqa: E402
from app.services.prompt_service import build_generation_prompt  # noqa: E402
from app.services.stable_generation_fallback_service import build_stable_generation_fallback  # noqa: E402


LONG_INPUT = """项目经历｜AI RAG 智能助手
使用 React、TypeScript、FastAPI、SQLite、RAG、Embedding 实现资料上传、向量检索和问答。通过 VPS、Nginx、systemd 部署到公网域名，有日志和访问记录。企业级和高并发相关表达需要谨慎。

实习经历｜前端开发实习
参与内部后台页面开发、接口联调、表单校验、缺陷修复和需求验收。

竞赛经历｜大学生创新创业训练项目
负责项目方案设计、原型展示、答辩材料整理和校级立项展示。
"""

MIXED_INPUT = LONG_INPUT + """

科研经历｜课程知识图谱研究
参与资料整理、论文阅读、实验记录和阶段汇报，主要围绕知识点关系抽取和学习路径组织进行探索。
"""


def request(raw_input: str = LONG_INPUT) -> schemas.GenerateRequest:
    return schemas.GenerateRequest(
        anonymous_user_id="u-test",
        session_id="s-test",
        target_role="AI / 大模型 / Agent",
        mode="full_resume",
        packaging_level="大胆",
        experience_type="综合经历",
        raw_input=raw_input,
    )


def test_long_input_mode_by_length():
    context = analyze_long_input("项目经历｜长文本\n" + "这是长输入。" * 380)

    assert context.long_input_mode is True
    assert context.raw_input_length > 1800


def test_long_input_mode_by_three_segments():
    context = analyze_long_input(LONG_INPUT)

    assert context.long_input_mode is True
    assert context.segment_count == 3


def test_compact_context_contains_titles_terms_evidence_and_risks():
    context = analyze_long_input(LONG_INPUT)

    assert "AI RAG 智能助手" in context.compact_context
    assert "前端开发实习" in context.compact_context
    assert "大学生创新创业训练项目" in context.compact_context
    assert "React" in context.compact_context
    assert "部署" in context.compact_context
    assert "高并发" in context.compact_context


def test_long_prompt_is_selected_for_long_input():
    context = analyze_long_input(LONG_INPUT)
    prompt = build_generation_prompt(request(), context)

    assert "长输入摘要" in prompt
    assert "claims 最多 8 条" in prompt
    assert "用户原始输入" not in prompt


def test_normal_prompt_is_selected_for_short_input():
    raw = "我做了一个 Vue 后台管理系统，写页面、调接口、修 bug。"
    context = analyze_long_input(raw)
    prompt = build_generation_prompt(request(raw), context)

    assert context.long_input_mode is False
    assert "用户原始输入" in prompt
    assert raw in prompt


def test_stable_fallback_generates_projects_without_hard_fact_hallucination():
    context = analyze_long_input(LONG_INPUT)
    payload = build_stable_generation_fallback(request(), context)
    text = payload.model_dump_json()

    assert len(payload.resume_sections.projects) >= 2
    assert "实习经历" in text
    assert "竞赛经历" in text
    assert "计算机相关专业" not in text
    assert "高并发访问" not in text
    assert payload.resume_sections.education["学校"] == "[待填写]"
    assert payload.resume_sections.education["专业"] == "[待填写]"


def test_stable_fallback_keeps_non_project_experience_meta():
    context = analyze_long_input(MIXED_INPUT)
    payload = build_stable_generation_fallback(request(MIXED_INPUT), context)
    metas = {project["meta"] for project in payload.resume_sections.projects}

    assert "实习经历" in metas
    assert "科研经历" in metas
    assert "竞赛经历" in metas


def test_json_repair_can_close_truncated_json():
    parsed = parse_llm_json('```json\n{"items": ["a", "b"], "nested": {"ok": true')

    assert parsed["items"] == ["a", "b"]
    assert parsed["nested"]["ok"] is True


def test_generation_service_uses_fallback_when_llm_json_fails():
    original_mode = os.environ.get("LLM_MODE")
    original_call = generation_service.call_openai
    original_log_dir = generation_service.LOG_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            os.environ["LLM_MODE"] = "openai"
            generation_service.LOG_DIR = Path(tmpdir)

            def fake_call_openai(prompt: str) -> LLMResult:
                return LLMResult(text="not a json response", model="fake-model", latency_ms=12)

            generation_service.call_openai = fake_call_openai
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(bind=engine)
            db = sessionmaker(bind=engine)()
            response = generation_service.create_generation(db, request())
            text = response.result.model_dump_json()

            assert response.generation_result_id is not None
            assert len(response.result.resume_sections.projects) >= 2
            assert "计算机相关专业" not in text
            stability_log = generation_service.LOG_DIR / "generation_stability.jsonl"
            assert stability_log.exists()
            assert '"fallback_used": true' in stability_log.read_text(encoding="utf-8")
            db.close()
        finally:
            generation_service.call_openai = original_call
            generation_service.LOG_DIR = original_log_dir
            if original_mode is None:
                os.environ.pop("LLM_MODE", None)
            else:
                os.environ["LLM_MODE"] = original_mode


if __name__ == "__main__":
    test_long_input_mode_by_length()
    test_long_input_mode_by_three_segments()
    test_compact_context_contains_titles_terms_evidence_and_risks()
    test_long_prompt_is_selected_for_long_input()
    test_normal_prompt_is_selected_for_short_input()
    test_stable_fallback_generates_projects_without_hard_fact_hallucination()
    test_stable_fallback_keeps_non_project_experience_meta()
    test_json_repair_can_close_truncated_json()
    test_generation_service_uses_fallback_when_llm_json_fails()
    print("long input stability tests passed")
