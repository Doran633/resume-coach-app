from dataclasses import dataclass, field
import re


@dataclass
class SupportedInference:
    term: str
    resume_allowed: bool
    interview_required: bool
    wording: str
    knowledge_items: list[str] = field(default_factory=list)


@dataclass
class SupportedInferenceContext:
    resume_terms: list[str]
    interview_terms: list[str]
    wordings: list[str]
    knowledge_items: list[str]


def _has_any(text: str, keywords: list[str]) -> bool:
    return any(re.search(re.escape(keyword), text, re.IGNORECASE) for keyword in keywords)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def infer_supported_inferences(text: str) -> list[SupportedInference]:
    text = text or ""
    inferences: list[SupportedInference] = []

    if _has_any(text, ["RAG", "检索", "向量库", "文档问答", "知识库", "Embedding", "测试集", "评测"]):
        inferences.extend(
            [
                SupportedInference("Top-K", True, True, "围绕 Top-K 检索结果设计测试和效果分析", ["Top-K", "Recall", "Precision"]),
                SupportedInference("Retrieval", True, True, "围绕 Retrieval 质量进行检索效果评估", ["Retrieval Evaluation", "Groundedness"]),
                SupportedInference("Chunk", True, True, "关注文档切块、检索召回和回答命中效果", ["Chunk 策略", "切块粒度"]),
                SupportedInference("Embedding", True, True, "结合 Embedding 表示与相似度检索组织 RAG 链路", ["Embedding 模型", "向量相似度"]),
                SupportedInference("Citation", True, True, "关注回答依据、引用来源和可追溯性", ["Citation", "Groundedness"]),
                SupportedInference("Rerank", False, True, "Rerank 可作为后续检索优化和面试准备方向", ["Rerank", "检索排序"]),
            ]
        )

    if _has_any(text, ["接口联调", "后端 API", "API", "接口", "FastAPI", "Spring", "请求"]):
        inferences.extend(
            [
                SupportedInference("RESTful API", True, True, "围绕 RESTful API 完成接口联调和数据流转校验", ["RESTful API", "状态码"]),
                SupportedInference("参数校验", True, True, "关注请求参数校验、异常处理和接口返回一致性", ["参数校验", "异常处理"]),
                SupportedInference("接口日志", True, True, "结合接口日志定位请求链路和异常场景", ["接口日志", "请求链路"]),
            ]
        )

    if _has_any(text, ["前端", "页面", "React", "Vue", "组件", "表单", "TypeScript"]):
        inferences.extend(
            [
                SupportedInference("组件化", True, True, "围绕组件化拆分页面结构和交互状态", ["组件设计", "复用边界"]),
                SupportedInference("状态管理", True, True, "梳理页面状态、接口数据和交互反馈", ["状态管理", "数据流"]),
                SupportedInference("表单校验", True, True, "处理表单校验、异常提示和用户交互闭环", ["表单校验", "交互状态"]),
                SupportedInference("性能优化", False, True, "性能优化可作为面试扩展方向，未提供指标时不写具体结果", ["性能优化思路"]),
            ]
        )

    if _has_any(text, ["测试集", "评测", "Benchmark", "测试用例", "回归测试", "指标"]):
        inferences.extend(
            [
                SupportedInference("测试用例", True, True, "围绕测试用例和评测指标沉淀验证流程", ["测试用例设计", "指标口径"]),
                SupportedInference("Benchmark", True, True, "使用 Benchmark 思路组织固定样例和结果复盘", ["Benchmark", "回归测试"]),
                SupportedInference("误差分析", True, True, "结合误差分析定位效果波动和优化方向", ["误差分析", "结果复盘"]),
            ]
        )

    if _has_any(text, ["部署", "公网", "域名", "Nginx", "systemd", "VPS", "服务器", "上线"]):
        inferences.extend(
            [
                SupportedInference("服务部署", True, True, "围绕服务部署、访问链路和日志排查完成上线验证", ["服务部署", "健康检查"]),
                SupportedInference("反向代理", True, True, "结合 Nginx 反向代理和域名访问组织部署链路", ["Nginx", "反向代理"]),
                SupportedInference("进程守护", True, True, "使用进程守护和健康检查保障服务可访问性", ["systemd", "进程守护"]),
            ]
        )

    seen: dict[str, SupportedInference] = {}
    for inference in inferences:
        seen.setdefault(inference.term, inference)
    return list(seen.values())


def build_supported_inference_context(text: str) -> SupportedInferenceContext:
    inferences = infer_supported_inferences(text)
    return SupportedInferenceContext(
        resume_terms=_unique([item.term for item in inferences if item.resume_allowed]),
        interview_terms=_unique([item.term for item in inferences if item.interview_required]),
        wordings=_unique([item.wording for item in inferences if item.resume_allowed]),
        knowledge_items=_unique([knowledge for item in inferences for knowledge in item.knowledge_items]),
    )
