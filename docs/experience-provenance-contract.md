# Experience Provenance Contract

## 目的

Experience provenance 用来回答两个问题：一条简历内容来自哪段用户经历，以及系统是否有权把它写入当前项目。文本更流畅或事实覆盖率更高，都不能替代来源正确性。

## 显式边界

“项目一、项目二、项目 A、实习经历、科研经历、竞赛经历、校园经历”等用户标签是强边界。标题与事实写在同一行时只把标签视为结构；显式标题之前存在有效经历时，该前导经历也必须保留。普通详情中的编号列表只有在呈现紧凑标题结构时才可作为边界。

显式标签给出的 `declared_experience_type` 高于局部关键词。例如“项目二：论文阅读助手”仍是项目；只有课题、实验室、研究职责、实验研究或论文发表等关系证据才能支持科研经历。

## 输入语义角色

每个 Experience 内的语义单元分为：

- `RESUME_FACT`：可以进入 Fact Ledger 和正式简历。
- `USER_INSTRUCTION`：仅约束生成，不作为候选人事实。
- `NEGATIVE_CONSTRAINT`：禁止反向生成对应能力或结果。
- `UNCERTAIN_FACT`：可用于追问，不能确定性写入技能或正文。
- `TARGET_ROLE_CONTEXT`：用于定位，不证明候选人已经具备某技能。
- `STRUCTURE_MARKER`：只帮助解析输入结构。

一个单元包含转折关系时应按语义拆分。例如“目标岗位需要 Redis，但项目使用 SQLite”中，Redis 是岗位上下文，SQLite 是项目事实。

从 v0.8.2 起，语义角色之后还必须经过 Claim Resolution。Experience ID 回答“属于哪段经历”，Claim 的 polarity、certainty、temporal status 与 eligibility 回答“这项主张能否被确定地写入”。Fact Ledger 只接受 eligible Claim，并保留对应 `claim_id`；详细契约见 `docs/claim-resolution-contract.md`。

## 不可变所有权

分段后创建固定 Experience Slot。每个 Slot 包含不可变 `experience_id`、声明类型、局部 `source_span` 和本段 Fact ID。Fact ID 的 Experience 前缀是原始所有者，后续服务不能只根据当前 project 的可变字段改变它。

LLM 只能填写已有 Slot。返回 ID 需要通过标题别名和局部事实验证；未知 ID、候选接近或只共享技术栈时拒绝绑定。用于 API 和 DOCX 的内部绑定元数据在保存或渲染前清理。

## Fallback 与恢复

Stable Fallback 和 Resume Section Fallback 均按 Slot 工作：

1. 只读取当前 Experience 的 Identity、Fact Ledger 和 constraints。
2. 只恢复属于当前 Experience 的 Fact ID。
3. 没有可靠局部事实时留空或写入 `missing_questions`。
4. 不为覆盖一个 ID 创建通用项目，也不访问全局事实池补正文。

Fact Coverage 恢复前后都要校验 Fact owner。覆盖率用于观察有价值事实是否被承载，不能抵消事实归属错误。

## Reconciliation 与 Dedup

Reconciliation 使用标题、别名、局部事实和候选分差进行高置信绑定。已有固定 Slot 绑定不可被重分配；历史 Payload 可以通过一致的 Fact owner 恢复可信绑定。

Dedup 不把相同推断 ID 当作实体相同。父项目与阶段项目仍可依据层级证据合并；两个名称、目标或独立事实不同的项目即使都使用 RAG，也必须保留。发生 `PROVENANCE_CONFLICT` 或 `INFERRED_ID_COLLISION` 时停止合并并记录事件。

## 质量门

最终投递质量门检查显式边界丢失、用户指令泄露、否定约束泄露、不确定事实断言、Fact owner 冲突和推断 ID 碰撞。高置信问题可局部恢复或删除污染；低置信问题只记录，不通过跨经历事实或模板句补足。

新增会修改项目正文的服务必须遵循：保持固定 Slot、携带 Fact provenance、只读取局部事实、在写入后重新执行 Boundary 与 Delivery Quality Gate，并提供新增无关经历和调换经历顺序的 metamorphic regression。
