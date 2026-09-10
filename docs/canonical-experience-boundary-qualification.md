# Canonical Experience Boundary Qualification

## 目的

无显式经历标题的自然语言输入会先经过语义分段，再生成稳定的
`experience_id`、Claim、Fact 和 owner scope。分段错误会使同一经历的尾部
结果、技术或上线说明变成额外项目，即使其中的事实本身没有跨 owner 污染。

v0.9.11.1 将隐式分段改为“双条件”资格：既有边界分数必须达到候选条件，
并且后续片段必须含有独立经历锚点。

## 允许建立隐式经历的锚点

- 明确的新项目、产品或活动实体；
- 新公司、实验室、课题组、协会、社团、学生会等组织与独立角色关系；
- 明确的新时间范围；
- 显式经历类型标签。

完整标点、自然段、动作、技术、指标、获奖、GitHub、上线与普通主题变化
仍可提高边界分数，但不能单独创建 Experience。

## 并回语义

缺少独立锚点的候选片段会追加到前一段的原文范围中：不删除正文，不创建
新的 `experience_id`，也不丢失后续 Claim 或 Fact。后续 Semantic Compilation
只会为合并后的 Experience 建立一个 owner scope。

分段日志只记录 `weak_boundary_merged_count` 和按原因聚合的
`weak_boundary_reason_counts`，不记录该片段的正文或标题。

## 不在本阶段处理的事项

本版本不改变标题推断或 Display Name Qualification。单经历内把总结性描述
误作名称的独立问题继续归入 v0.9.11.2 处理。
