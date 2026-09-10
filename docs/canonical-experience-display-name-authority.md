# Canonical Experience Display Name Authority

## 目的

v0.9.11.2 将 Experience 的展示名称收束为 Semantic Compilation 的单一只读决策。Identity 的推断标题仍可帮助内部理解，但不能自行成为项目标题。

## 名称决策

每个 `experience_id` 仅产生一个 `CanonicalDisplayNameQualification`。候选按以下权威顺序选择：

1. 显式经历标题中的实体名称。
2. `项目名称是`、`项目名为`、`项目：` 等明确命名结构。
3. 当前 owner 的 eligible Claim 中，带有明确项目、产品或活动实体的本地表达。
4. 当前 owner 原文中“开发/设计/搭建”加明确实体的表达。

结构标签、总结或能力描述、工具列表、职责、指标、结果、GitHub、用户指令和不确定/否定表达不构成名称来源。包含“没有”等普通词的合法产品名不会仅凭字面拒绝。

## 消费边界

`CanonicalSemanticState` 仅公开已经资格化的名称。Canonical Project Projection 和 Canonical Title Resolver 都通过 Consumer View 读取此决策；后者会覆盖未经资格的已有项目名。名称未知时不删除 owner、Fact 或 Claim，而是输出现有待补充名称并添加泛化缺失问题。

名称处理不改动 Experience 数量、owner、type、Fact/Claim eligibility、Ledger 或任何字段 attachment。日志只保存 owner、来源类别、原因聚合和 fingerprint，不保存原始名称或正文。

## 审计结论

当前 Canonical 路径中，Project Projection 和 Title Resolver 是名称展示消费者，均已接入资格结果。Experience Validity、Entity Dedup 和 Project Reconciliation 的旧名称恢复/合并分支只对 legacy 调用可达；它们不是本阶段重构对象，但不得重新接回 Canonical 路径。
