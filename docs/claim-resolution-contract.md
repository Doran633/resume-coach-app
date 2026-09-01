# Claim Resolution Contract

## 目的

Claim Resolution 位于输入语义角色和 Experience Fact Ledger 之间。它不负责润色文本，而是回答一项主张是否可以被正式断言。Experience ID 决定事实归属，Claim Resolution 决定断言资格。

## 三层数据

1. **Semantic Unit**：识别一段输入是事实、指令、否定约束、不确定信息、岗位上下文还是结构标记。
2. **Claim**：把混合语义拆成原子主张，记录 polarity、certainty、temporal status、eligibility、source span 和 Experience owner。
3. **Fact**：只由 eligible Claim 生成，拥有稳定 `fact_id`，并保留对应 `claim_id`。

这些内部字段不进入前端 API、正式简历或 DOCX。

## Eligibility

- `eligible`：用户明确提供的正向、非计划事实，可以进入 Fact Ledger。
- `withheld`：probable、uncertain 或 planned 主张，只能用于确认问题。
- `excluded`：用户指令、结构标记、目标岗位上下文和否定约束，只用于控制生成。

Coverage 只以 eligible Claim 生成的事实为分母。系统不得为提高覆盖率恢复 withheld 或 excluded 内容。

## 否定作用域

否定只约束对应原子主张。“没有负责架构设计，只参与接口测试”拆成 denied 的架构主张和 eligible 的测试事实。不得删除整句，也不得把 denied 主张改写成较强的正向职责。

## 不确定性

“可能、好像、记不清、应该是”等信息保持 uncertain/probable。系统不能从多个候选中自行选择，也不能为了补技能栏把它们升级为 confirmed。对输出有价值的 withheld Claim 进入 `missing_questions`。

## 时间状态

- `historical`：明确发生过的早期状态，可以用于说明演进。
- `current`：后续或当前状态。
- `planned`：准备、拟进行或正在推进但未确认完成的事项，不得写成 completed。
- `unknown`：用户未明确提供时间关系，但事实本身已确认。

“早期使用 Flask，后续迁移到 FastAPI”是两个有关联的 confirmed Claim，不是冲突或重复。

## 冲突处理

同一 Slot 中 confirmed 优先于 probable/uncertain，current 优先表达当前状态但不删除有工程价值的 historical 演进。无法裁决时保持 withheld 并追问；不得读取其他 Experience 的事实解决冲突。

## 下游约束

- Prompt 只把 eligible facts 作为正文来源。
- Fallback、Reconciliation、Coverage 和技能聚合只消费 eligible Fact。
- 专业化表达不能改变 polarity、certainty、temporal status、Experience owner、claim_id 或 fact_id。
- Delivery Quality Gate 检查不确定断言、否定反转、计划完成化、owner 变化和用户约束泄露。

## 扩展测试

新增复杂输入时，应同时断言 eligible、withheld、excluded 三类结果，而不是只比较最终句式。真实模型评测检查事实覆盖、边界和断言资格，不做全文逐字快照。
