# 生成质量管线

## 黄金样例回归

v0.5.8 在现有质量管线之外增加两层验证：

1. **确定性后处理回归**：读取匿名固定 `GenerationPayload`，依次执行事实守卫、经历边界、分层、事实增量、去重、个人优势、技能证据、技能分类、招聘语言、文本完整性、输出防火墙、类型解析和标题格式化，最后走生产 DOCX 导出。
2. **真实 LLM 质量评测**：调用真实生成链路，计算经历保留率、事实覆盖率、重复数、内部字段泄露、类型与技能准确率，不加入普通 `pytest` 强制门禁。

黄金案例位于 `tests/fixtures/golden_resume_cases.json`，人工基线位于 `tests/snapshots/v057_golden_resume.txt`。基线不要求逐字一致，因为专业改写和句式调整是允许的；回归只锁定不能退化的事实、结构、边界、信息增量和投递要求。

新增黄金案例时必须：

- 删除姓名、手机号、邮箱、学校等个人信息。
- 只把用户明确提供的内容列入 `required_facts`。
- 定义每个 `experience_id` 的必需事实和禁止串入事实。
- 定义技能分类、禁止短语、内部字段和 DOCX section 顺序。
- 同时提供固定 Payload，保证 CI 不依赖模型和网络。

## 目标

Resume Coach 的生成链路不是“Prompt -> DOCX”，而是带 provenance 的结构化生成系统。管线必须同时保证：经历不串通、明确事实不丢失、硬事实不编造、文案专业、DOCX 可直接进入投递前核对。

v0.8.3 在 v0.8.2 的输入、主张与来源链路后增加统一可见输出契约：

```text
显式边界 / 语义分段
  -> Input Semantic Role
  -> Atomic Claim Resolution (polarity / certainty / temporal / eligibility)
  -> Experience Identity + immutable source span
  -> Experience Fact Ledger (eligible Claim only)
  -> Fixed Experience Slots
  -> LLM / per-slot Stable Fallback
  -> Slot Binding
  -> Local Section Fallback
  -> Reconciliation (high confidence only)
  -> Fact Coverage + Boundary owner validation
  -> Entity Dedup provenance conflict protection
  -> Delivery Quality Gate
  -> Visible Output Contract (all version fields + resume sections)
  -> strip internal provenance metadata
  -> save / DOCX render
```

`Semantic Role` 判断一段话是什么性质，`Claim Resolution` 判断其中每个原子主张能否被断言，`Fact Ledger` 只保存可用于简历的事实。否定、指令和结构信息为 excluded；不确定和计划事项为 withheld；只有 confirmed 且非 planned 的正向 Claim 为 eligible。

```text
原始输入
  -> 输入分类 / 语义分段
  -> Experience Identity (EXP-xxx)
  -> Experience Fact Ledger (EXP-xxx-Fxxx)
  -> LLM 或 Stable Fallback
  -> Schema Normalize / Result Cleanup
  -> 初始事实与结构修复
  -> 项目对账、类型解析和事实覆盖
  -> 边界复检、事实去重和正文质量检查
  -> 投递标题处理
  -> 保存 GenerationPayload
  -> DOCX 导出前二次质量检查
```

## 生成阶段

| 阶段 | 主要服务 | 是否修改正文 | 职责 |
|---|---|---:|---|
| 输入分类 | `input_content_classification_service` | 否 | 区分经历事实、求职意图、包装指令和噪声 |
| 语义分段 | `semantic_experience_segmentation_service` | 否 | 在无标题或混合段落中识别经历边界 |
| Claim 裁决 | `input_claim_resolution_service` | 否 | 拆分混合句，解析否定、确定性、时间状态和正文可用性 |
| Experience Identity | `experience_identity_service` | 否 | 生成 `EXP-001` 等内部身份和局部事实范围 |
| Fact Ledger | `experience_fact_ledger_service` | 否 | 只接收 eligible Claim，生成 `fact_id` 并保留 `claim_id` 与 owner |
| 模型生成 | `llm_service` / `stable_generation_fallback_service` | 是 | 生成结构化 Payload；异常时提供可控安全网 |
| Schema 清理 | `resume_section_schema_service` / `result_cleanup_service` | 是 | 标准化 key、修复缺失字段和内部字段泄露 |
| 硬事实检查 | `fact_guard_service` | 是 | 删除或降级未被原文支持的硬事实 |
| Section Fallback | `resume_section_fallback_service` | 是 | 只在结构缺失时恢复 summary、skills、projects |
| 包装增益 | `enhancement_guard_service` | 是 | 将口语事实整理为岗位化表达，不增加硬事实 |
| 经历边界 | `experience_boundary_guard_service` | 是 | 按 `source_experience_id` 清理跨经历污染 |
| 不确定表达 | `uncertain_expression_cleanup_service` | 是 | 将“如有、建议掌握”等移出正式正文 |
| 项目专属性 | `project_specificity_guard_service` | 是 | 清理跨项目模板句，保留项目专属事实 |
| 弱履历策略 | `weak_profile_strategy_service` | 是 | 正向组织课程项目、竞赛和校园经历 |
| 正文净化 | `resume_body_sanitizer_service` | 是 | 清理“没有实习、只是作业”等负面正文 |
| 项目对账 | `resume_project_reconciliation_service` | 是 | 移除综合经历并把遗漏内容归还正确项目 |
| 经历实体去重 | `resume_experience_entity_dedup_service` | 是 | 合并同一经历的重复 project，回收独立事实并规范标题 |
| 去重检查点 A | `resume_fact_dedup_service` | 是 | 在覆盖恢复前清理高置信重复，减少模板内容 |
| 类型解析 | `experience_type_resolution_service` | 修改 meta | 使用局部关系证据锁定项目、实习等类型 |
| Section Routing | `resume_section_routing_service` | 否 | 根据最终类型决定 DOCX 分组，不重新判断类型 |
| 事实覆盖 | `fact_coverage_guard_service` | 是 | 恢复未覆盖的高价值明确事实 |
| 边界复检 | `experience_boundary_guard_service` | 是 | 检查覆盖恢复内容仍属于对应 experience |
| 去重检查点 B | `resume_fact_dedup_service` | 是 | 清理恢复后新出现的重复，不删除独立事实 |
| 去重质量复检 | `resume_dedup_quality_service` | 是 | 检查跨字段与事实簇重复，保护去重前后 provenance 覆盖 |
| 个人优势 | `resume_summary_quality_service` | 是 | 生成事实支撑的候选人能力，隔离教练话术 |
| 输出防火墙 | `resume_output_firewall_service` | 是 | 清理写作指令、模板残片和调试文本 |
| 语言专业化 | `resume_language_professionalization_service` | 是 | 将口语和内部标签转换为行动表达 |
| 技术术语消歧 | `technical_term_disambiguation_service` | 否 | 基于局部事实语境解析 Token、模型、训练、部署、用户和测试等歧义词 |
| 技能证据与分类 | Skill Evidence + `resume_skill_taxonomy_service` | 修改 skills | 先验证事实证据，再消费消歧结果分类，不按孤立关键词推导能力 |
| 输出相关性 | `resume_output_relevance_service` | 修改 skills / missing_questions | 移动错误类别、删除低置信歧义技能，并保留项目正文事实 |
| Section 完整性 | `resume_section_integrity_service` | 是 | 保证正式 Section 具备业务可用内容 |
| 文本完整性 | `resume_text_integrity_service` | 是 | 修复截断句和内部摘要污染 |
| 标点净化 | `resume_typography_quality_service` | 是 | 修复连续/混合标点和异常空格，不改变技术词与事实 |
| 最终事实复检 | Fact Guard + Output Firewall | 是 | 对后续改写产生的内容做最终安全检查 |
| 最终类型与标题 | Type Resolver + `resume_title_format_service` | 修改类型/标题 | 固化类型；生成公司、岗位、项目类型和时间标题 |
| 输出质量评分 | `resume_output_quality_gate_service` | 否 | 记录七项质量分数和告警，不修改正文或阻断交付 |
| 最终投递质量门 | `resume_delivery_quality_gate_service` | 是 | 汇总严重输出问题、执行保守修复并验证高价值事实覆盖率 |
| 可见输出契约 | `resume_visible_output_service` | 是 | 统一枚举四档版本与简历 Section 的可见字符串，检测并转换内部字段 |

## v0.6.10 最终投递顺序

生成保存前：

```text
Existing Quality Pipeline
-> Experience Entity Dedup
-> Experience Validity
-> Resume Delivery Quality Gate
-> Read-only Quality Evaluation
-> Strip Internal Hierarchy Metadata
-> Save
```

DOCX 导出前：

```text
Project Reconciliation
-> Experience Boundary
-> Experience Entity Dedup
-> Experience Validity
-> Resume Delivery Quality Gate
-> DOCX Delivery Readiness
-> Strip Internal Hierarchy Metadata
-> Render
```

`Resume Delivery Quality Gate` 是现有服务的终局编排器，不是新的内容生成器。它只从同一 `experience_id` / `fact_id` 恢复事实，并复用已有确定性清洗能力。质量门之后禁止运行 Fallback、Fact Coverage 或其他会新增 projects、skills、summary、role、intro、details 的服务。

v0.8.3 起，`normal_version`、`bold_version`、`boundary_version`、`recommended_version` 与 `resume_sections` 使用同一可见字段定义。结构化 provenance metadata 可以在质量管线内部存在，但 `source_experience_id`、`source_fact_ids`、`fact_id`、`raw_text` 等变量名不得进入任何用户可见字符串。Full smoke 调用同一检测函数，并在失败报告中只记录命中标记、字段路径和关联 ID。

自动修复仅用于高置信严重问题：空壳、明确跨经历事实、未支持硬事实、完全重复、确定性残句、异常字符和内部话术。低置信语义重复、完整的技术术语列表和难以判断的信息增量只记录为 warning / observe。自动删除普通详情不得超过项目详情的 25%，明确污染和标题空壳除外。

事实保护通过修复前后高价值覆盖率实现。相似表达若绑定不同 `fact_id`，或包含不同指标、动作、结果和工程证据，必须保留；覆盖下降时只能从本段 Fact Ledger 恢复，之后重新执行 Experience Boundary 与 Experience Validity。

## v0.6.0 经历实体唯一性检查点

```text
Fallback -> Reconciliation -> Experience Entity Dedup
-> Fact Coverage -> Boundary / Fact Dedup -> Text Guards
-> Experience Entity Dedup Final Check -> Save / DOCX Render
```

- 第一次实体去重合并 LLM、Fallback 和 Reconciliation 产生的重复项目，再由 Fact Coverage 恢复独立高价值事实。
- 最终实体去重只合并后续阶段意外重新产生的高置信重复，不扩写新内容。
- 相同非空 `source_experience_id` 必须唯一；缺失 ID 时需要规范标题和局部事实同时提供强信号。
- “综合经历项目”是 Reconciliation 使用的临时事实容器，不能在 Fallback 阶段提前并入具体项目，否则会造成跨经历污染。
- 低置信 `possible_duplicate` 只记录日志，不能为了追求零重复而误删两个真实项目。
- DOCX Renderer 不展示 `source_experience_id`、`source_fact_ids` 或判重信息。

## 为什么存在复检

- Fact Coverage 会恢复原文事实，因此之后必须再次执行 Boundary Guard 和 Dedup。
- 语言专业化、文本完整性会改写正文，因此保存前必须再次执行 Fact Guard 和 Output Firewall。
- 类型解析在初次对账后运行，并在保存前复检；第二次只校验后续服务没有破坏类型锁。
- 这些是有明确写入者位于中间的 checkpoint，不是无意义重复。
- v0.5.0 的 Output Quality Gate 是只读观察器，不能为了提高分数删除、恢复或编造内容。

## v0.5.9 最终审计结论

- 生成链路与 DOCX 历史导出链路保持同一关键顺序：结构与事实恢复在前，边界和去重复检在后，技能证据先于分类，事实与污染最终复检位于保存或渲染之前。
- 两次 Experience Boundary 分别保护初始模型结果和 Fact Coverage 恢复结果，不能合并。
- 两次 Role Resolution 分别处理早期职责归属和投递前职责恢复；后者之后必须再次执行 Output Firewall。
- Type Resolver 在项目对账后首次锁定类型，在保存或渲染前验证后续服务没有破坏类型锁。
- 最终 Fact Guard 与 Output Firewall 用于检查语言、完整性和排版改写后的正文，不替代前面的局部检查。
- 未发现 fallback 在最终 Guard 后重新补回污染内容，也未发现去重位于 Fact Coverage 之后而阻止事实恢复的问题。
- 本次审计不调整代码顺序，避免为了形式上的“少执行一次”削弱已经通过黄金回归的质量边界。

## v0.5 事实簇与质量分数

事实簇去重按 `source_fact_ids`、包含关系、同一事实动作和高置信语义顺序判断。表达选择使用信息量评分，奖励具体技术、动作、指标、证据和问题排查，降低空泛前缀权重。只有没有新增技术、证据、指标或工程侧面的内容才会合并。

Quality Gate 记录：`fact_coverage_score`、`experience_boundary_score`、`duplicate_score`、`language_professionalism_score`、`typography_score`、`internal_marker_score`、`delivery_readiness_score` 和总分。分数只用于观察模型、Prompt 与管线变化，不进入 API 和数据库。

## ID 生命周期

### experience_id

1. 输入分段生成 `EXP-001`。
2. Prompt 要求项目返回 `source_experience_id`。
3. Reconciliation 在缺失时根据局部标题和事实回匹配。
4. Boundary、Coverage、Type Resolver 只在对应局部经历内工作。
5. ID 保存在内部 Payload，前端正文与 DOCX Renderer 不展示。

### fact_id

1. Fact Ledger 为原子事实生成 `EXP-001-F001`。
2. Coverage Guard 记录 detail 对应的 `source_fact_ids`。
3. Dedup 合并同一事实表达时合并 ID，不丢 provenance。
4. 日志只记录 ID 与统计，不记录完整原文。
5. DOCX 渲染前过滤内部字段。

## Fallback 触发边界

- Stable Fallback：LLM 请求、JSON 修复或 Schema 校验失败时触发。
- Resume Section Fallback：Payload 合法但正式简历 Section 为空或缺项时触发。
- Fallback 必须逐 experience 生成，不得默认合并为“综合经历项目”。
- Fallback 必须记录触发率；高触发率表示上游退化，不能因用户表面可用而忽略。

## DOCX 二次检查

历史结果可能由旧版本生成，因此导出时重新执行结构补全、事实边界、项目对账、事实覆盖、去重、类型解析、标题处理和投递就绪检查。DOCX 不输出面试准备、Claim、降级表达、`experience_id` 或 `fact_id`。

## 新增 Guard 规范

1. 先说明它保护的明确不变量，再决定是否新增服务。
2. 优先扩展已有服务，避免一类问题出现多个写入者。
3. 明确输入、输出、可修改字段和日志字段。
4. 不得清除 `source_experience_id`、`source_fact_ids` 和类型锁。
5. 如果会恢复或新增正文，后面必须有边界与事实复检。
6. 如果只检测，不应修改 Payload。
7. 必须提供真实失败案例回归测试。
8. 日志不得包含完整用户输入或简历正文。

## v0.8.1 Provenance 规则

- `declared_experience_type` 的优先级高于局部内容关键词和 LLM `meta`。
- `immutable_experience_id` 与 Fact ID 前缀共同表达原始所有者；二者冲突时停止恢复并记录 critical。
- Prompt 只提供各 Slot 的可生成事实及内部约束，不提供跨 Experience 的恢复池。
- Fallback 只补当前 Slot；没有局部事实时留空或追问，不创建通用项目。
- Reconciliation 只有在标题、局部事实和候选分差同时满足阈值时绑定；共享框架不构成主要证据。
- Dedup 只有在实体关系和事实重叠均得到支持时合并；相同推断 ID 但项目名和事实不同视为 provenance 冲突。
- Fact Coverage 是召回指标，不能证明归属正确；所有恢复内容必须再次通过 Fact owner 与 Experience Boundary 校验。

## v0.5.7 信息分层与招聘者表达

在 Fact Coverage 和 Experience Boundary 完成后执行：

`Section Layering -> Fact Increment -> Dedup -> Summary Quality`

- `resume_section_layering_service`：只决定事实应位于项目简介、我的职责还是技术细节，不创造新事实。
- `resume_fact_increment_service`：检查每条 detail 是否相对标题字段和前序详情增加新的技术、动作、问题、指标或证据。
- `resume_skill_taxonomy_service`：只分类 Skill Evidence Guard 已确认的技能，不从知识补齐清单引入待学习内容。
- `recruiter_facing_technical_language_service`：将代码字段和内部 Pipeline 表达转换为工程价值，不改变 provenance。
- 高价值事实保护优先于篇幅压缩；充实项目允许保留 6-8 条互不重复的详情。

## 核心原则（通用）

- Fallback 是安全网，不是垃圾桶。
- 事实恢复优先于文案压缩。
- 事实归属优先于文本流畅。
- 去重只能删除重复，不得删除独立高价值事实。
- 类型解析只能依据局部经历关系证据。
- 用户可见正文不得出现内部字段和调试文本。

## v0.5.1 自适应叙事层

`Fact Coverage -> Adaptive Narrative -> Information Gain -> Fact Dedup -> Dedup Quality -> Template Language Guard -> Typography -> Output Quality Gate`

- Adaptive Narrative 只重排已有事实，不补齐不存在的叙事阶段。
- Information Gain 检查 intro、role、details 是否重复，并保留带来独立技术、动作、结果或证据的内容。
- Narrative Coherence 根据经历类型检查自然顺序，但不要求每个项目采用相同结构。
- Template Language Guard 清理口语和模板残留，不改变事实归属。
- narrative dimension 只用于后端计算，不写入 API、数据库或 DOCX。

## v0.5.2 语义单元与事实簇层

`Fact Ledger -> Semantic Unit Recovery -> Fact Coverage -> Adaptive Narrative -> Fact Cluster -> Information Gain -> Cluster Dedup -> Narrative Quality`

- Semantic Unit Recovery 只能从当前 experience_id 的原文事实与相邻 source_span 恢复内容。
- Fact Cluster 使用动作、对象、指标、证据和工程价值识别重复簇，技术词相同不直接判重。
- 概括句被具体事实完整覆盖时删除；Citation 链路与 Citation 展示等不同价值默认保留。
- 指标与优化对象保持在同一语义单元，无法从原文恢复的残句不进入 DOCX。
- semantic_unit_id、related_fact_ids、cluster 标签只存在于运行时，不进入 API、数据库或 DOCX。
## v0.5.3 投递前语言治理

在事实覆盖、语义单元恢复和事实簇去重完成后，依次执行：

1. `technical_term_disambiguation_service`：先结合对应事实句确认歧义术语含义，不修改简历正文。
2. `resume_skill_evidence_guard_service`：只决定技能是否有资格进入正式简历，不负责知识推荐。
3. `resume_skill_taxonomy_service` / `resume_skill_presentation_service`：仅组织已经通过证据校验的技能，并消费消歧结果，不得新增技术事实。
4. `resume_output_relevance_service`：检查类别与事实语境是否一致；低置信项进入信息缺口，不以“如有”形式写入简历。

技能处理顺序固定为：Technical Term Disambiguation -> Skill Evidence Guard -> Skill Taxonomy -> Output Relevance -> Recruiter Language -> Whitespace Quality。后置文本清洗不得删除技能分类标题。

### v0.6.11 全局技能证据聚合

技能链路调整为：`Experience Fact Ledger -> Skill Evidence Aggregation -> Skill Evidence Guard -> Skill Taxonomy -> Output Relevance -> Delivery Quality Gate`。

- Skill Evidence Aggregation 读取所有经历的明确技术事实，记录 `term`、证据类型、置信度、来源 Experience ID、来源 Fact ID 和确定性推断依据。
- 项目 intro、role、details 继续只能读取各自 Experience ID；只有 skills 是跨经历能力视图，不能把聚合结果反向灌入项目正文。
- Python 可由 FastAPI、SQLAlchemy、Pydantic、pytest、Django、Flask 等专属生态确定性支撑；React/Vite/Ant Design/Zustand 不足以证明 TypeScript，Spring 不足以证明 Java。
- 目标岗位、包装指令、knowledge checklist、interview plan 和 missing questions 不参与证据聚合。
- Skill Evidence Guard 决定技能是否准入，Taxonomy 只分类和排序，Output Relevance 处理 Token 等上下文歧义，Delivery Quality Gate 只复检、不承担技能推断。
- DOCX 导出会重新构建聚合证据，历史结果即使 skills 为空，也能恢复真实能力且不展示内部证据字段。

职责处理遵循：Experience Boundary Guard -> Resume Role Resolution -> Template Language Guard -> Resume Output Firewall。Role Resolution 只能使用当前 `experience_id` 的职责/动作事实；无法恢复时允许留空，任何后置服务不得重新写入系统占位说明。
2. `recruiter_language_service`：把内部字段枚举转换为招聘者可理解的工程价值，不改变事实归属。
3. `resume_recruiter_readability_service`：清理开发日志、文件清单和与项目简介重复的低价值详情。
4. `paired_symbol_integrity_service`：维护用户可见文本的配对符号结构，不承担普通标点美化。
5. 原有 Text Integrity、Typography 和 Output Firewall 继续负责断句恢复、普通标点与最终污染拦截。

DOCX 导出前重复执行上述投递检查，使历史结果重新导出时也能得到修复。任何后置服务不得从 knowledge checklist 补回已删除的不确定技能。
## v0.5.4 语义空格阶段

正式文本后处理顺序调整为：Recruiter Language → Paired Symbol Integrity → Text Integrity → Whitespace Quality → Typography Quality → Output Firewall。

- Whitespace Quality 独占中文词内空格、标点空格和特殊空白字符治理职责。
- Paired Symbol Integrity 只维护配对符号，不再全局压缩空白。
- Recruiter Language 只转换内部字段表达，不再固化切割边界空格。
- 输入分段继续保留原始 `segment.content` 和 Fact Ledger source span；内部摘要中的压缩不会覆盖原文事实。
- 受保护技术短语通过临时占位符恢复，内部占位符不得进入日志或用户输出。

## v0.6.12 标题实体与列表结构净化

- `resume_title_format_service` 只从对应 Experience ID 的局部原文解析公司和岗位；公司字段保存实体名称，不保存“在某公司”等句法片段。
- Typography Quality 在不修改 raw input 和 Fact Ledger source span 的前提下，清理用户可见字段的 Markdown/List 行首标记。
- DOCX Renderer 在应用 Word List Bullet 前重复执行同一确定性净化，作为历史结果的最终防御；该步骤不改变字体、颜色、字号或高价值事实。
