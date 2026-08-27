# 生成质量管线

## 目标

Resume Coach 的生成链路不是“Prompt -> DOCX”，而是带 provenance 的结构化生成系统。管线必须同时保证：经历不串通、明确事实不丢失、硬事实不编造、文案专业、DOCX 可直接进入投递前核对。

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
| Experience Identity | `experience_identity_service` | 否 | 生成 `EXP-001` 等内部身份和局部事实范围 |
| Fact Ledger | `experience_fact_ledger_service` | 否 | 提取原子事实并生成 `fact_id`、类型和重要度 |
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
| Section 完整性 | `resume_section_integrity_service` | 是 | 保证正式 Section 具备业务可用内容 |
| 文本完整性 | `resume_text_integrity_service` | 是 | 修复截断句和内部摘要污染 |
| 标点净化 | `resume_typography_quality_service` | 是 | 修复连续/混合标点和异常空格，不改变技术词与事实 |
| 最终事实复检 | Fact Guard + Output Firewall | 是 | 对后续改写产生的内容做最终安全检查 |
| 最终类型与标题 | Type Resolver + `resume_title_format_service` | 修改类型/标题 | 固化类型；生成公司、岗位、项目类型和时间标题 |
| 输出质量评分 | `resume_output_quality_gate_service` | 否 | 记录七项质量分数和告警，不修改正文或阻断交付 |

## 为什么存在复检

- Fact Coverage 会恢复原文事实，因此之后必须再次执行 Boundary Guard 和 Dedup。
- 语言专业化、文本完整性会改写正文，因此保存前必须再次执行 Fact Guard 和 Output Firewall。
- 类型解析在初次对账后运行，并在保存前复检；第二次只校验后续服务没有破坏类型锁。
- 这些是有明确写入者位于中间的 checkpoint，不是无意义重复。
- v0.5.0 的 Output Quality Gate 是只读观察器，不能为了提高分数删除、恢复或编造内容。

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

1. `resume_skill_evidence_guard_service`：只决定技能是否有资格进入正式简历，不负责知识推荐。
2. `resume_skill_presentation_service`：仅组织已经通过证据校验的技能，负责分类、去重和目标岗位排序，不得新增技术事实。

技能处理顺序固定为：Skill Evidence Guard -> Resume Skill Presentation -> Recruiter Language -> Whitespace Quality。后置文本清洗不得删除技能分类标题。

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
