import re
from dataclasses import dataclass

from .resume_information_gain_service import information_terms


CLUSTER_MARKERS = {
    "citation": ["citation source cards", "来源文件", "章节路径", "chunk 位置", "内容预览", "答案溯源"],
    "evaluation": ["groundedness", "retrieval", "固定测试集", "质量评测", "评测指标", "benchmark"],
    "retrieval_optimization": ["top-k", "score threshold", "retrieval ranking", "chunk overlap", "query intent", "keyword bonus", "参数实验"],
    "observability": ["debug trace", "日志", "健康检查", "smoke test", "监控", "token usage", "answer_policy"],
    "deployment": ["公网部署", "nginx", "systemd", "vps", "域名", "本地 mvp", "部署闭环"],
    "isolation": ["数据隔离", "用户隔离", "课程隔离", "权限"],
    "reliability": ["json schema", "pydantic", "fallback", "空字段", "业务完整性"],
    "user_feedback": ["用户反馈", "真实用户", "用户测试"],
    "product_iteration": ["experience dilution", "事实串用", "版本迭代", "重构", "experience id"],
    "quantified_result": ["提升", "降低", "相关度", "准确率", "%", "token/次"],
    "collaboration": ["协作", "沟通", "验收", "答辩", "汇报"],
    "ownership": ["独立开发", "主导", "负责", "owner"],
    "core_pipeline": ["文档解析", "文本切块", "embedding", "向量检索", "rag 问答", "接口链路"],
    "product_positioning": ["面向", "项目起点", "核心目标", "定位", "解决用户"],
}


@dataclass
class FactCluster:
    name: str
    auxiliary: set[str]
    components: set[str]


def classify_fact_cluster(text: str) -> FactCluster:
    value = str(text or "").lower()
    hits = {
        name: sum(marker in value for marker in markers)
        for name, markers in CLUSTER_MARKERS.items()
    }
    primary = max(hits, key=hits.get) if any(hits.values()) else "implementation"
    auxiliary = {name for name, score in hits.items() if score and name != primary}
    components = information_terms(text)
    components.update(re.findall(r"来源文件|章节路径|内容预览|参数实验|测试集|部署闭环|事实边界|业务完整性", value))
    return FactCluster(primary, auxiliary, components)
