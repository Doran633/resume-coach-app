# Canonical Fact Projection Completeness

## 目的

v0.9.9.3 收口 Canonical 生成链路中“已有项目缺少 eligible Fact”这一正文写入权限。事实补齐只发生在 Canonical Project Projection Planner，Canonical Coverage 继续验证，不再第二次补写正文。

## 受限投影契约

一个新增 detail 必须同时满足：

- 项目具有 `immutable_source_experience_id` 且 `source_binding_locked=true`；
- 当前 owner 只有一个冻结项目；
- Fact 与 Claim 都在该 owner 的 Canonical Consumer View eligible scope 内；
- 现有可见字段拥有精确、可验证的 Fact / Claim 行；
- 没有把项目聚合来源误当作 intro、role 或 detail 的精确来源；
- 仍满足既有高价值优先级、每项目详情上限与全局详情上限。

不满足任一条件时，Planner 只跳过并记录脱敏原因；它不会根据文本相似度、项目位置、技术栈或项目聚合集合猜测字段绑定。

## 正文与来源共同变换

以下展示服务在过滤、排序或裁剪 detail 时，均共同处理 `details`、`detail_fact_ids`、`detail_claim_ids`：

- `resume_section_layering_service`
- `resume_fact_increment_service`
- `resume_information_gain_service`
- `resume_adaptive_narrative_service`
- `resume_project_reconciliation_service` 的 detail budget

项目级 `source_fact_ids` 和 `source_claim_ids` 仍是聚合集合，不会倒推为字段级证明。正文删除时，只有已删除 detail 独占且不再被 role 或其他存续 detail 承载的来源才会从聚合集合移除。

## 可观测性

`backend/logs/canonical_project_projection.jsonl` 继续记录投影候选与既有项目 detail 计划的脱敏摘要：选择的 Fact ID、跳过计数以及持久化前仍保留的数量。查询投影缺失继续使用：

```bash
.venv/bin/python scripts/list_canonical_projection_gaps.py --attempt-id <attempt_id>
```

日志不保存原始输入、标题、正文、Fact 文本或 Claim 文本。

## 非目标

本版本不修改 Prompt、LLM、Fallback、Slot Binder 阈值、owner、type、eligibility、Ledger、DOCX、前端、数据库或公开 API。不提升包装强度，也不处理字段改写本身的职业化质量。
