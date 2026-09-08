# Canonical Title Resolution Authority

## 目的

Semantic Commit 之后的标题解析只消费同一请求已经编译的 Canonical
Consumer View。它不再读取 `raw_input`，也不再构建新的 Identity、Claim 或
Fact Ledger。

## 允许的操作

- 读取当前冻结 owner 的名称展示资格。
- 在名称为空、待填写或通用占位时，使用同 owner 已通过资格验证的名称。
- 保留既有项目公开字段与所有 Fact / Claim attachment。

## 禁止的操作

- 基于原始输入、关键词或全局经历重新判定项目、科研、开源或个人经历类型。
- 推断公司、岗位、技术、指标、职责、时间或项目名称。
- 修改项目数量、owner、冻结 type、Claim eligibility、Fact / Claim owner。
- 清空、合并、重排或重建项目级、role 级和 detail 行级 provenance。

## 兼容性

`resolve_resume_titles(payload, raw_input)` 仍保留给 legacy 调用。Canonical
生产生成改用 `resolve_canonical_resume_titles(payload, planner_view)`；DOCX
链路不在本阶段变更。
