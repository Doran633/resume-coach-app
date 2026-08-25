from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.supported_inference_service import build_supported_inference_context  # noqa: E402


def test_rag_supports_resume_and_interview_inferences():
    context = build_supported_inference_context("做了 RAG 测试集和检索效果评估，包含文档问答和向量检索。")

    assert "Top-K" in context.resume_terms
    assert "Retrieval" in context.resume_terms
    assert "Chunk" in context.resume_terms
    assert "Embedding" in context.resume_terms
    assert "Rerank" in context.interview_terms
    assert "Rerank" not in context.resume_terms


def test_api_inferences():
    context = build_supported_inference_context("参与后端 API 接口联调，处理请求参数和异常返回。")

    assert "RESTful API" in context.resume_terms
    assert "参数校验" in context.resume_terms
    assert "接口日志" in context.resume_terms


def test_frontend_inferences():
    context = build_supported_inference_context("使用 React 和 TypeScript 写前端页面、表单和组件。")

    assert "组件化" in context.resume_terms
    assert "状态管理" in context.resume_terms
    assert "表单校验" in context.resume_terms
    assert "性能优化" in context.interview_terms
    assert "性能优化" not in context.resume_terms


def test_deployment_inferences_do_not_create_metrics():
    context = build_supported_inference_context("通过 Nginx 和 systemd 部署到公网域名。")
    text = " ".join(context.wordings + context.knowledge_items)

    assert "反向代理" in context.resume_terms
    assert "进程守护" in context.resume_terms
    assert "1000" not in text
    assert "高并发" not in text


if __name__ == "__main__":
    test_rag_supports_resume_and_interview_inferences()
    test_api_inferences()
    test_frontend_inferences()
    test_deployment_inferences_do_not_create_metrics()
    print("supported inference tests passed")
