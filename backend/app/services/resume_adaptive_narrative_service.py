import re
from collections import Counter

from .. import schemas


DIMENSION_MARKERS = {
    "outcome": ["提升", "降低", "上线", "交付", "获奖", "用户", "相关度", "准确率", "%", "一等奖"],
    "iteration": ["用户反馈", "迭代", "重构", "版本", "持续优化", "复盘"],
    "engineering": ["日志", "健康检查", "smoke test", "部署", "nginx", "systemd", "vps", "隔离", "权限", "监控", "测试"],
    "decision": ["定位", "排查", "解决", "修复", "权衡", "选择", "调优", "优化", "实验", "阈值", "top-k", "cors", "冲突"],
    "collaboration": ["协作", "沟通", "推进", "组织", "协调", "答辩", "汇报", "验收"],
    "ownership": ["主导", "独立", "负责", "承担", "owner"],
    "implementation": ["实现", "构建", "开发", "接入", "设计", "搭建", "联调", "解析", "检索", "接口", "组件"],
}

TYPE_ORDERS = {
    "实习": ["ownership", "implementation", "decision", "collaboration", "engineering", "iteration", "outcome", "context"],
    "科研": ["context", "decision", "implementation", "engineering", "outcome", "collaboration", "iteration", "ownership"],
    "竞赛": ["context", "ownership", "decision", "implementation", "collaboration", "outcome", "iteration", "engineering"],
    "开源": ["context", "decision", "implementation", "collaboration", "outcome", "engineering", "iteration", "ownership"],
    "校园": ["context", "ownership", "collaboration", "implementation", "outcome", "iteration", "decision", "engineering"],
    "社团": ["context", "ownership", "collaboration", "implementation", "outcome", "iteration", "decision", "engineering"],
    "项目": ["ownership", "implementation", "decision", "engineering", "iteration", "outcome", "collaboration", "context"],
}


def narrative_dimension(text: str) -> str:
    value = str(text or "").lower()
    scores = Counter({name: sum(marker in value for marker in markers) for name, markers in DIMENSION_MARKERS.items()})
    best, score = scores.most_common(1)[0]
    if score:
        return best
    if re.search(r"\d+(?:\.\d+)?", value):
        return "outcome"
    return "context"


def narrative_order(meta: str) -> list[str]:
    for marker, order in TYPE_ORDERS.items():
        if marker in str(meta or ""):
            return order
    return TYPE_ORDERS["项目"]


def organize_adaptive_narrative(payload: schemas.GenerationPayload, stats: dict | None = None) -> schemas.GenerationPayload:
    updated = payload.model_copy(deep=True)
    for project in updated.resume_sections.projects:
        details = [str(item).strip() for item in project.get("details", []) if str(item).strip()]
        fact_rows = project.get("detail_fact_ids") if isinstance(project.get("detail_fact_ids"), list) else []
        records = [
            (detail, fact_rows[index] if index < len(fact_rows) and isinstance(fact_rows[index], list) else [], index)
            for index, detail in enumerate(details)
        ]
        order = narrative_order(str(project.get("meta") or ""))
        rank = {dimension: index for index, dimension in enumerate(order)}
        records.sort(key=lambda item: (rank.get(narrative_dimension(item[0]), len(rank)), item[2]))
        if stats is not None:
            stats["reordered_detail_count"] = stats.get("reordered_detail_count", 0) + sum(
                original_index != new_index for new_index, (_, _, original_index) in enumerate(records)
            )
        project["details"] = [item[0] for item in records]
        project["detail_fact_ids"] = [item[1] for item in records]
    return updated


def narrative_distribution(payload: schemas.GenerationPayload) -> dict[str, int]:
    counts = Counter()
    for project in payload.resume_sections.projects:
        counts.update(narrative_dimension(str(detail)) for detail in project.get("details", []) or [])
    return dict(counts)
