# Canonical Display Name Qualification

## 目的

`v0.9.8.8` 为每次 Semantic Compilation 的每个 `experience_id` 建立一次名称展示资格。它解决的是 Canonical Project Projection 把内部 identity 标题、层级名称或 alias 直接投影为可见项目名称的问题。

该机制不是新的 Identity、Claim 或 Fact 系统，也不改变现有 ID、Fact eligibility、owner、type 或原始事实。

## 名称来源与资格

候选只能来自既有 `ExperienceIdentity` 的：

- `canonical_project_name`
- `title`
- `project_aliases`

每个候选都必须经过同一资格判定。名称可展示的来源证明仅有两种：

1. 显式标题结构中、与经历类型标签分离的真实名称。
2. 当前 owner 的已确认、eligible Claim 对名称的语义支持。

`项目经历`、`科研经历`、`竞赛经历` 等结构标签不能成为名称。用户指令、否定约束、不确定或计划表达也不能成为名称。判定读取 Claim 的 `semantic_role`、`polarity`、`certainty` 和 eligibility，不把单个词（例如“没有”）当作否定证据。

对于某些显式标题，标题文字不属于经历正文的 Claim 范围。此时仅识别“没有开发”“未负责”“不参与”等完整否定断言或指令句法，避免它们借显式标题通道变成名称；`没有边界的检索工具`这类名词短语不会因此被拒绝。

名称资格与 Fact eligibility 是两条独立契约：显式标题中的真实名称不需要被编造成 Fact；有 eligible Fact 的经历也不一定已经给出了可展示名称。

## 投影行为

Canonical Project Projection 仅通过 `CanonicalConsumerViews.planner_view.display_name_qualification_for_owner()` 获取名称。

- 名称合格：投影已验证名称和当前 owner 的 eligible Fact。
- 名称待补充：保留 owner 与 eligible Fact，名称使用 `[待补充经历名称]`，并增加不包含用户原文的泛化补充问题。

这不会放宽 Slot Binder，也不会复用被 Ownerless Containment 删除的 LLM 文本。

## 证据与隐私

`backend/logs/canonical_display_name_qualification.jsonl` 只写入请求/尝试/结果 ID、资格数量、来源类别、原因聚合和指纹。它不包含标题、项目名、用户正文、Claim/Fact 文本、Cookie、IP 或密钥。

历史运行证据和当前代码重放必须分开表述：历史日志描述当时请求已记录的状态；本地或服务器的重放只能验证当前代码对同一输入的判定，不能替代历史快照。

## 非目标与后续发现

本版不修改 LLM 直接输出的项目标题，也不处理标题格式化、Fact attachment、分段、包装强度或 DOCX。

`NEW_FINDING-POST_COMMIT_NAME_WRITERS`：静态审计发现 `resume_title_format_service`、`resume_experience_validity_service`、`resume_project_reconciliation_service`、`resume_experience_entity_dedup_service` 和部分 Presentation/legacy 路径仍可能写入项目名称。它们不阻塞本版 Projection 名称资格，但必须在 Immutable Delivery Revision 中统一消费冻结后的交付 revision；本版不顺手收回其权限。
