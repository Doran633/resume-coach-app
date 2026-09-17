# v0.9.18.5.1 Canonical Semantic Unit Boundary Correction

## 基线与证据

- 开始基线：main / c6aa50d / VERSION 0.9.18.5。
- 工作区已有 `.pytest-*` 跟踪产物删除，未恢复、清理或计入本轮修改。
- 线上脱敏记录显示请求 `req_ea63b7f022584dd8987c332f6b0cc4d6` 的模型调用、Fact placement、owner、来源和10/10 Fact覆盖均通过；最终 Gate 因一个 `INCOMPLETE_SENTENCE` critical 拒绝保存。
- 本地使用同一460字符 Java 实习与个人项目输入固定重放，不把控制模型返回描述为历史原始返回。

## 最早失真

`EXP-001-F005`、对应 Claim 和原文范围均为“相关代码由正式员工审核后合并”，其后“我没有独立负责整体系统架构”正确冻结为 negative/excluded 限制。旧 `TRAILING_DEPENDENCY` 将所有句尾“并”视为连接词，因而把完整动词“合并”的末字误判为确定残句。Gate 将该原因升级为 critical，最终出口按契约拒绝交付。

这不是模型遗漏、Fact 归属错误或否定资格错误。现有测试只覆盖“完成检索参数实验，并”等确定残句，没有覆盖“合并、归并”等完整词尾反例。

## 修改边界

1. 多字依赖词及带明确逗号/分号结构的“，并”继续产生 `trailing_dependency`。
2. 无结构边界的句尾“并”产生 `ambiguous_trailing_conjunction` warning，不能单独证明正文残缺。
3. 语义单元整理对该单一歧义原因保留正文及附件，不恢复、不删除、不改写。
4. Gate 继续将空行、确定尾部依赖、未完成范围和尾部分隔符作为 critical；只增加新歧义原因的 warning 映射。
5. Gate 使用现有 intro、role、detail Fact/Claim 行记录精确字段来源和脱敏原因类别，不增加来源字段或语义权限。

未修改 Claim Resolution、Fact Ledger、Prompt、模型协议、Fact placement、后处理、Router、DOCX、前端、数据库或公开 API。

## 验证

- 完整词尾对照：“审核后合并”“多个分支合并”“数据归并”“企业兼并分析”不再产生确定残句。
- 确定残句对照：“主要包括：”“基于”“完成接口联调，”“从20提升到”仍为 critical；“完成检索参数实验，并”因明确标点边界仍是 `trailing_dependency`。
- 表面歧义“完成审核并”只记录 warning，整理过程保持正文及附件。
- 完整 Java 输入保持2个 owner、10个 eligible Fact、`EXP-001-F005` 与 negative constraint 的原文范围；控制返回执行真实接收、Gate、内存保存及 DOCX 导出。
- 本地测试使用隔离数据库和日志，不调用付费模型、不连接生产数据库、不部署。

## 残留与回滚

- warning 不宣称已经理解单字“并”的句法作用；它只表示现有表面规则无法确定证明残缺。
- `metric_without_relation`、`term_list_without_action` 和 `SKILL_WITHOUT_EVIDENCE` 的既有 warning/observe 不属于本补丁。
- 回滚仅涉及语义单元单字边界、Gate 诊断来源及本版测试文档；回滚后“合并”误报和线上生成失败会恢复。
