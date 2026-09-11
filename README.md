# Resume Coach App

## 当前架构：v0.9.12.3

Resume Coach 已从“原始输入直接交给模型生成简历”的模式，逐步收口为一条可追溯的编译式链路：

```text
raw_input
  -> Semantic Compilation
  -> CanonicalSemanticBuild / Display Name Qualification / Canonical Consumer Views
  -> Existing Presentation Pipeline
  -> Owner / Type / Fact Scope Freeze
  -> Delivery Gate（只读验证）
  -> Quality Repair Router（确定性局部清理）
  -> Final Ownerless Containment
  -> Delivery Gate Final Recheck（只读）
  -> Immutable Delivery Revision
  -> Persisted GenerationResult
  -> Web / DOCX One-way Renderer
```

核心职责如下：

- **Semantic Compilation**：同一次请求只构建一套 Experience Identity、Claim Resolution 和 Fact Ledger，形成请求级 CanonicalSemanticBuild。无显式标题的后续片段还必须具备独立实体、组织角色、时间范围或经历类型标签，才能创建新的 Experience owner scope；动作、技术、结果和标点只作为辅助信号。
- **Canonical Consumer Views**：Planner、Guard 和未来 Repair 只能通过按 `experience_id` 限定的只读视图读取允许的 Claim、Fact 和技能证据，不重新理解完整 `raw_input`。
- **Display Name Qualification**：每个 owner 在 Semantic Compilation 中只形成一个名称资格结果。显式标题、明确命名结构和同 owner 的明确产品实体可展示；Identity 标题、alias、总结说明、技术栈、职责和结果都只是候选，不能绕过资格进入项目名称。名称不明时保留本 owner 的事实并请求补充名称，不吞掉经历。
- **Experience Type Authority**：分段层的类型仅为 provisional hint。Semantic Compilation 基于当前 owner 的显式类型、Identity 与 eligible Claim 中的关系证据只判定一次正式类型；GitHub、技术词、动作或结果不能单独把项目变为开源、实习、校园、科研或竞赛经历。
- **Experience Time Authority**：每个 owner 在 Semantic Compilation 中只形成一个冻结时间决定。明确的年月、范围、学期或学年只能从本 owner 的 source span 与 eligible Claim 取得；版本号、指标、届次、模型/论文/数据集年份及不确定内容不能成为经历时间。时间未知时保留经历与事实，并显示 `时间：【待填写】`。
- **Experience Header Completeness Authority**：表头只组合已冻结的类型、名称与时间决定。项目、科研、竞赛、开源和校园经历显示各自名称标签与时间；实习经历额外按本 owner 的任职关系独立验证企业和岗位。缺失值显示字段级 `【待填写】`，不会猜测、借用其他经历或删除事实。
- **Owner / Type Freeze**：经历类型、事实归属和项目归属在生成链路中冻结；后续模块只能验证、删除污染或使用同 owner 事实，不能跨经历重绑。
- **Delivery Gate**：仅检查交付质量，不再恢复项目、补写事实、重建语义或修改 payload。
- **Quality Repair Router**：仅处理证据充分的局部冗余，例如同一 owner、同一 Fact binding 的完全重复字段；不会创建事实、项目、技能或职责。
- **Immutable Delivery Revision**：最终 containment 与 Gate 复查后，确定性序列化唯一交付 payload；数据库、同步响应、任务轮询和 DOCX 都消费该 revision，之后不存在语义写入者。
- **DOCX One-way Renderer**：DOCX 只消费已保存的 `GenerationResult.result_json`，进行确定性文本清理后完整渲染，不再读取原始输入或重跑语义生成链路，也不会静默裁剪项目或详情。

### v0.9 架构迁移记录

| 版本 | 阶段 | 已完成的权限收口 |
| --- | --- | --- |
| v0.9.0 | Shadow Canonical State | 构建不影响用户结果的 Canonical Semantic State 影子快照。 |
| v0.9.1 | Single Semantic Compilation | Identity、Claim、Fact Ledger 和 Canonical State 复用同一次语义编译。 |
| v0.9.2 | Experience Type Authority | 显式经历标签优先，冻结 `experience_type`，下游不再重分类。 |
| v0.9.3 / v0.9.3.1 | Canonical Fact Ownership | 冻结 Fact / Claim owner；补齐单经历合法候选的安全绑定。 |
| v0.9.4 | Scoped Fact Access | Boundary、Coverage、Reconciliation、Entity Dedup 按 owner 限定读取 Fact。 |
| v0.9.5 | Fallback / Recovery Demotion | Fallback 和 Recovery 只能使用当前 owner 的 eligible Fact，不能重建事实或跨经历借用。 |
| v0.9.6 | DOCX One-way Rendering | DOCX 从已保存 payload 单向渲染，不再重跑语义链路。 |
| v0.9.7.1 - v0.9.7.3 | Semantic Audit | 建立 Mutation Trace、校准观测误报，并阻止无 owner 项目进入正式交付。 |
| v0.9.8.1 | Authority Lockdown | Delivery Gate 收口为纯只读验证器。 |
| v0.9.8.2 | Canonical Consumer Views | 建立 Planner、Guard、Repair 的请求级只读 Canonical Views。 |
| v0.9.8.3 | Quality / Repair Split | 引入受 Canonical scope 限制的确定性 Repair Router，处理完全重复字段。 |
| v0.9.8.4 | Scoped Presentation Authority | 书面化模块按 owner 使用只读 Presentation View，不再在 Canonical 路径读取完整输入。 |
| v0.9.8.5 | Canonical Eligibility Integrity | 将 Claim eligibility 与 Fact lineage 的完整性作为编译期契约验证。 |
| v0.9.8.6 | Projection Completeness Shadow | 按 owner 观察 eligible Fact 首次未投影、未绑定或被移除的位置。 |
| v0.9.8.7 | Canonical Project Projection | 为缺少 LLM provenance 的 eligible owner 受限投影本地事实，避免真实经历消失。 |
| v0.9.8.8 | Display Name Qualification | 为 Canonical Projection 增加名称展示资格，结构标签和语义约束不能被当作项目名称。 |
| v0.9.8.8.1 | Presentation Provenance Preservation | 正文清理与 Coverage 保留并验证既有 Fact / Claim binding，避免字段来源在展示链路中丢失。 |
| v0.9.8.9 | Canonical Provenance Contract Closure | Canonical Coverage 与 Repair Router 区分字段级附件和项目聚合来源，避免跨 owner 查询和无证据去重。 |
| v0.9.8.10 | Canonical Title Resolution Authority | Canonical 标题解析不再重读 `raw_input` 或重建语义，只能使用冻结 owner 的名称资格，并完整保留 Fact / Claim attachment。 |
| v0.9.9.1 | Post-Commit Semantic Rebuild Cutoff | Canonical 路径在 Owner Freeze 后不再调用旧的原文重建、项目补写或摘要补写服务；技能术语解析复用同一次 Ledger。 |
| v0.9.9.2 | Presentation Field / Provenance Consistency | 去重与输出防火墙按原始详情索引同步正文、Fact 行和 Claim 行；项目聚合来源不再被详情重建错误覆盖。 |
| v0.9.9.3 | Canonical Fact Projection Completeness | 已绑定项目的遗漏 eligible Fact 仅在同 owner、唯一目标和精确字段证据成立时由 Projection Planner 补入；Coverage 不再作为第二个正文写入者，展示排序与预算同步维护 Fact / Claim 行。 |
| v0.9.10 | Post-Commit Authority Closure | 初始投影完成后，Boundary、Coverage、Role Recovery 与 Entity Dedup 不再补写正文、猜测字段来源、合并项目或改名；后处理只做受限清理、验证与附件同步。 |
| v0.9.10.1 | Initial Projection Duplicate Suppression | Section Fallback 在明确同 owner、同 Fact/Claim 且完全同文时，不再把同一表达重复写入 role；字段 Fact/Claim 行在候选构造时同步建立。 |
| v0.9.11 | Immutable Delivery Revision | Final Gate 检查实际持久化语义内容；GenerationResult 成为唯一不可变交付 revision，页面和 DOCX 读取同一内容，DOCX 不再静默裁剪项目或详情。 |
| v0.9.11.1 | Canonical Experience Boundary Qualification | 无显式标题的候选边界需同时具备既有边界条件和独立经历锚点；不合格的动作/结果尾部片段并回前一经历，不再创建额外 owner、Claim、Fact 或待补充项目。 |
| v0.9.11.2 | Canonical Experience Display Name Authority | 编译期为每个 owner 选择唯一、可追溯的展示名称；Identity 标题、alias 和已有项目名不能绕过资格，未知名称保留经历并进入待补充状态。 |
| v0.9.12.1 | Canonical Experience Type Authority | 分段关键词类型降级为 provisional hint；现有关系型解析器在 Claim Resolution 后按 owner 形成唯一的冻结类型决定。 |
| v0.9.12.2 | Canonical Experience Time Authority | 编译期按 owner 冻结可追溯的经历时间；投影和标题解析只消费该决定，未知时间显示明确的时间待补充提示。 |
| v0.9.12.3 | Canonical Experience Header Completeness Authority | 按冻结类型确定表头字段，组合已验证名称、时间及实习企业/岗位；缺失值显示带字段名的待填写提示。 |

后续尚未实施的架构阶段：

- **Phase 8.4 Scoped Professionalization**：在已完成冻结的事实范围内，对每个字段限定可用于书面化改写的内容，并在改写后重新校验 provenance。

后续阶段不得重新授予 Commit 后模块读取完整 `raw_input`、创建具体事实、重绑 owner 或改写 type 的权限。

### 当前质量与可观测性

- 每次请求可通过 `X-Request-ID` 关联 `request_id -> attempt_id -> generation_result_id -> file_id`。
- `semantic_mutation_trace.jsonl` 用于识别 Semantic Commit 后首次出现的 owner、type、Fact binding 或 claim eligibility 异常。
- [Presentation Provenance Preservation](docs/presentation-provenance-preservation.md) 说明正文清理、字段级 provenance 与 Coverage 的保留契约。
- [Canonical Provenance Contract Closure](docs/canonical-provenance-contract-closure.md) 说明 Coverage、Repair Router 与项目聚合来源的最终使用边界。
- [Canonical Title Resolution Authority](docs/canonical-title-resolution-authority.md) 说明标题解析在 Semantic Commit 后的只读边界与附件保留契约。
- [Post-Commit Semantic Rebuild Cutoff](docs/post-commit-semantic-rebuild-cutoff.md) 说明 Commit 后旧语义重建服务在 Canonical 生产路径中的切断边界。
- [Presentation Field / Provenance Consistency](docs/presentation-field-provenance-consistency.md) 说明正文变换如何与 Fact / Claim attachment 同步，及字段级附件和项目级聚合集合的区别。
- [Canonical Fact Projection Completeness](docs/canonical-fact-projection-completeness.md) 说明已有冻结项目的受限事实投影、Coverage 的只读边界，以及展示排序和附件同步契约。
- [Canonical Experience Display Name Authority](docs/canonical-experience-display-name-authority.md) 说明展示名称的候选来源、资格排序与下游强制消费边界。
- [Canonical Experience Time Authority](docs/canonical-experience-time-authority.md) 说明经历时间的 owner-scoped 资格、未知时间占位与下游只读消费边界。
- [Canonical Experience Header Completeness Authority](docs/canonical-experience-header-completeness-authority.md) 说明类型化表头、实习企业/岗位资格和字段级待填写提示的确定性组合契约。
- [Immutable Delivery Revision](docs/immutable-delivery-revision.md) 说明最终 Gate、确定性 revision、数据库读取和完整 DOCX 渲染的一致性契约。
- Canonical State、Ownership、Consumer Views、Delivery Gate、Repair Router 都输出脱敏聚合日志，不记录用户正文、Cookie、API Key 或原始 IP。
- shallow smoke 检查网站、法律页面、健康接口、Cookie、安全响应头和版本一致性；full smoke 显式调用模型，并在 finally 中清理测试数据。

本地常用验证命令：

```powershell
python -m pytest -q
python scripts/evaluate_golden_resume.py --mode mock
python scripts/evaluate_claim_resolution_golden.py --mode mock
```

服务器按结果查询质量证据：

```bash
.venv/bin/python scripts/list_recent_quality_incidents.py --result-id <result_id> --json
.venv/bin/python scripts/list_semantic_mutations.py --result-id <result_id> --show-transitions
tail -n 20 backend/logs/resume_quality_repair_router.jsonl
.venv/bin/python scripts/list_canonical_projection_gaps.py --result-id <result_id>
tail -n 20 backend/logs/canonical_display_name_qualification.jsonl
```

## v0.8.3 可见输出完整性与 Full Smoke 诊断

- 新增统一的用户可见输出遍历，覆盖四档版本文案以及 summary、skills 和项目全部可见字段。
- 最终投递质量门、招聘者语言转换、输出防火墙与 full smoke 使用同一组内部字段定义，避免检查范围分叉。
- `raw_text`、`fact_id`、`source_fact_ids`、`source_experience_id` 等内部变量在保存前确定性转换，不影响 Experience ID、Fact Ledger 等正常产品概念。
- full smoke 失败报告保留 attempt、request、result、file 和 cleanup 状态，并只记录命中标记及字段路径，不保存用户输入或生成正文。
- 失败清理仍在 `finally` 中执行；正式结果只有在全部可见字段不存在内部标记时才通过 smoke。

## v0.8.2 Claim Resolution

- 在 Experience Slot 与 Fact Ledger 之间增加原子 Claim 裁决，分别记录 polarity、certainty、temporal status 和 eligibility。
- 混合句不再整句删除：“没有负责架构，只参与测试”会排除架构断言，同时保留测试事实。
- probable / uncertain 技术、指标、岗位和公司只进入确认问题；planned 工作不得改写为 completed。
- historical/current 用于保留真实技术演进，Fallback、技能聚合、Coverage 和 DOCX 只消费 eligible Claim。
- 最终质量门检查否定反向断言、不确定事实断言、计划完成化、Claim owner 变化和目标岗位技能泄露。

完整约束见 [Claim Resolution Contract](docs/claim-resolution-contract.md)，评测示例：

```bash
python scripts/evaluate_claim_resolution_golden.py --mode mock
```

## v0.8.1 经历来源契约

- 显式的“项目一 / 项目二 / 实习经历”等边界优先于“论文、研究、实习”等局部关键词，标题同行事实和标题前的有效经历都不会被丢弃。
- 输入先按事实、用户指令、否定约束、不确定信息、目标岗位和结构标记分类；只有可生成事实进入 Experience Fact Ledger。
- 固定 Experience Slot 将 `experience_id`、局部 `source_span` 和 Fact 所有权绑定，后续服务不能仅凭共享技术栈重写来源。
- Resume Section Fallback 和 Stable Fallback 只读取当前 Experience 的事实；低置信 Reconciliation 拒绝绑定，Dedup 遇到 provenance 冲突时保留独立实体。
- 生成和 DOCX 投递前检查边界丢失、指令泄露、否定反向包装、不确定事实断言与来源冲突。

完整约束见 [Experience Provenance Contract](docs/experience-provenance-contract.md)。

## v0.7.4 公开测试运维闭环

- `run_public_beta_operations.py` 将小时检查、每日备份清理和部署后验证串成可继续执行的任务流，并用文件锁防止定时任务重叠。
- `operations-status-latest.md` 汇总版本、备份、烟测、SLO、质量漂移、限流、数据库和告警，日常无需逐个导出报告。
- `check_output_quality_drift.py` 比较高价值事实覆盖、Experience ID、Fallback、重复、污染、异常字符和 DOCX 修复率；少样本仅观察，不自动改变用户结果。
- `evaluate_rate_limit_rollout.py` 使用匿名身份和哈希 IP 聚合评估校园共享 IP 误伤风险，不自动关闭 `RATE_LIMIT_DRY_RUN`。
- `audit_database_portability.py` 审计 SQLite 迁移到 PostgreSQL 的阻塞项；当前仍使用 SQLite，不修改生产 schema。
- systemd 模板位于 `deploy/systemd/`，数据库迁移判断见 [数据库迁移准备](docs/database-migration-readiness.md)。

日常查看：

```bash
sed -n '1,240p' backend/reports/operations-status-latest.md
```

运维 dry-run：

```bash
.venv/bin/python scripts/run_public_beta_operations.py \
  --mode daily \
  --public-base https://resume.doran633.com \
  --backups /var/backups/resume-coach \
  --dry-run
```

## v0.7.2 公开测试上线准备

- 新增隐私政策、服务条款与 AI 辅助生成说明，全站页脚长期可访问；备案号和隐私联系邮箱由前端环境变量配置。
- 匿名用户可以删除当前签名 Cookie 对应的经历、生成结果、会话与 DOCX，服务端执行所有权校验和脱敏审计。
- 默认保留期：用户内容 30 天、DOCX 7 天、脱敏分析 90 天、SQLite 备份 14 天，均可通过环境变量调整。
- 新增在线 SQLite 备份、临时目录恢复验证、保留期清理和公开测试上线预检脚本。
- 运行防护报告增加备份新鲜度、数据库完整性、磁盘、证书、清理任务和限流观察指标。

```bash
python scripts/backup_production_data.py
python scripts/verify_production_backup.py
python scripts/cleanup_retained_data.py --dry-run
python scripts/launch_preflight.py --env /etc/resume-coach/resume-coach.env --frontend-env frontend/.env.production --public-base https://resume.example.com
```

公开测试运维见 [docs/public-beta-operations.md](docs/public-beta-operations.md)，数据删除与保留期见 [docs/data-retention-and-deletion.md](docs/data-retention-and-deletion.md)，AI 内容合规待办见 [docs/ai-content-compliance-checklist.md](docs/ai-content-compliance-checklist.md)。

## v0.7.0 公开测试安全基线

- 服务端签发匿名身份并以 HttpOnly Cookie 保存；前端身份字段继续兼容，但不再作为资源授权依据。
- Generation Result、Generated File 和 DOCX 下载均执行所有权校验；下载地址使用默认20分钟有效的HMAC签名凭证。
- 生成采用任务状态接口，Redis负责用户/IP限流、5个全站并发、15个等待任务、`attempt_id`幂等和每日模型预算；Redis故障时进入保守降级。
- 校园共享IP额度保持宽松，主要额度绑定服务端匿名身份：每个用户2次/5分钟、6次/小时、20次/天。
- 输入超过2,000字显示分段提醒，超过4,000字前后端共同拒绝，不截断、不调用模型且保留草稿。
- 生成中的 `attempt_id` 会短暂保存在浏览器；刷新页面后使用同一任务恢复，避免重复调用模型。
- 新增 `runtime.jsonl`、`generation_queue.jsonl`、`security_events.jsonl` 与 `llm_usage.jsonl`，只记录脱敏运行指标。
- Redis、systemd 和 Nginx 上线步骤见 [docs/v0.7-launch-security.md](docs/v0.7-launch-security.md)，Nginx示例见 [docs/nginx-v070-example.conf](docs/nginx-v070-example.conf)。运行与防护报告使用：

```bash
python scripts/export_runtime_protection.py --days 7
```

生产环境必须配置 Redis、HTTPS、真实域名白名单，以及独立的 Cookie、下载和IP哈希密钥。建议先使用 `RATE_LIMIT_DRY_RUN=true` 观察三天，再启用正式拦截。

## v0.6.12 实习公司实体与列表符清理

- 实习标题继续使用“公司名称｜实习岗位｜时间”，公司字段不再保留“在、曾在、于、就职于、任职于”等口语化句法成分。
- 公司提取优先读取对应 Experience ID 的局部原文，避免从其他经历借用公司；无法确认时保留 `[待填写]`。
- Typography Quality 清理用户粘贴或模型生成内容中的行首 Markdown、Unicode bullet、复选框和编号标记，同时保护 C#、C++、no-answer、负数指标等技术文本。
- DOCX `_bullet` 在应用 Word 列表样式前执行最终净化，历史结果重新导出也不会出现“ - 内容”的双重项目符号。

## v0.6.11 技能证据聚合与输入模板精简

- 输入页删除“大模型 / Agent 经历”模板，AI / Agent 项目统一使用“项目经历”模板；目标岗位中的“AI / 大模型 / Agent”保持不变。
- 新增 `resume_skill_evidence_aggregation_service.py`，从所有 Experience Identity 与 Fact Ledger 聚合经过验证的技能证据。
- 项目正文继续严格遵守 Experience ID 边界，技能栏可以跨经历汇总；例如不同经历中的 Python 与 TypeScript 会统一呈现为“编程语言：Python、TypeScript”。
- FastAPI、SQLAlchemy、Pydantic、pytest、Django、Flask 可确定性支撑 Python；React 本身不能证明 TypeScript，Spring 本身不能证明 Java。
- 技能证据不会读取目标岗位、包装指令、知识清单或面试准备，避免把“想学/想投”误写成“已经使用”。
- 实习标题将缺少具体方向的“AI Agent 实习”规范为“AI Agent 开发实习”，并保留用户明确提供的测试、产品等具体岗位。
- 生成保存和历史 DOCX 导出使用同一技能聚合链路，同一技能只展示一次，不引入无证据的 Docker、Redis、MySQL。

## v0.6.10 最终投递质量门

- 新增 `resume_delivery_quality_gate_service.py`，在生成保存和 DOCX 渲染前统一复检空内容、无效经历、跨经历事实、重复事实、残句、异常字符、内部字段、教练话术和无证据技能。
- 高置信严重问题会按“同经历事实恢复 -> 确定性文本修复 -> 安全删除”处理；低置信语义相似或术语列表只记录，不做激进删除。
- 修复前后比较 Experience Fact Ledger 的高价值事实覆盖率；不同 `fact_id`、指标、动作或结果的相似句继续保留。
- 空技能、空职责和空技术详情不渲染对应 DOCX 标题，也不使用模板句或未知技能补足。
- 最终质量门之后不再运行 Fallback 或正文扩写服务，避免污染内容反弹。
- 脱敏日志位于 `backend/logs/resume_delivery_quality_gate.jsonl`，只记录问题代码、来源 ID、数量、覆盖率和修复动作。

核心回归：

```bash
python -m pytest tests/test_v06_delivery_quality_gate.py -q
```

## v0.6.0 Experience Entity Dedup

- 新增经历实体级去重：同一 `source_experience_id` 最终只保留一个正式经历对象。
- 项目标题会清理“我做过一个、我独立完成了、项目一”等口语或模板前缀，并谨慎归一化“系统 / 平台 / 工具 / 项目”等尾缀。
- 重复项目合并时回收双方独立高价值事实，再执行详情去重；不会简单删除整个副本。
- 两个项目仅共享 React、Python、RAG、FastAPI 等技术时不会被判为同一实体；低置信相似项只记日志，不自动合并。
- Fallback、Reconciliation、生成保存前和 DOCX 渲染前均执行实体唯一性检查，历史结果重新导出也能修复。
- 质量日志：`backend/logs/resume_experience_entity_dedup.jsonl`；生成质量报告新增实体重复、合并和事实回收统计。

句子去重解决“同一个项目里重复说”，Experience Entity Dedup 解决“同一个项目被生成两次”，两者不能互相替代。

## v0.6.8 项目层级识别

- 识别同一产品下的 MVP、阶段、版本、模块、子系统、原型、升级、演进和重构关系，避免父产品与具体阶段被重复输出为两个项目。
- 新增空壳项目检测：只有通用简介、通用职责和标题式 detail、缺少独立事实的项目不会直接进入 DOCX。
- 父子合并至少需要两个强关系信号，并要求同源、明确父项目引用或“空壳 + 相邻 + 阶段词”等核心证据；不会仅凭 RAG、React、FastAPI、SQLite 等共享技术栈合并项目。
- 合并后使用“主产品名称（具体阶段）”作为标题，保留双方不重复的高价值事实，并删除“名称｜身份｜时间”标题残片。
- 生成保存和历史 DOCX 导出都会执行项目层级复检；内部层级字段在返回前移除，不进入前端结果和 DOCX。
- 层级日志位于 `backend/logs/project_hierarchy.jsonl`，只记录空壳数量、关系数量、规范项目名、合并来源 ID 和低置信关系数量，不记录完整用户输入。

## v0.5.9 输出质量阶段收口

v0.5.x 已完成从事实边界到专业叙事的阶段建设，后续默认冻结 Experience ID、Fact Ledger、Fact Coverage、Dedup、个人优势、技能证据和 DOCX 正文规则。质量由黄金回归和结构化日志持续守护，不再通过无限叠加 Guard 提升。

- [v0.5 质量基线](docs/v0.5-quality-baseline.md)
- [v0.5 质量可观测性](docs/v0.5-quality-observability.md)
- [v0.5 阶段复盘](docs/v0.5-retrospective.md)
- [生成质量管线](docs/generation-quality-pipeline.md)

v0.6.x 在保持 v0.5 质量基线的前提下处理真实回归；v0.6.0 首先补齐经历实体唯一性，后续再推进等待、错误重试和前端体验。

## v0.5.8 黄金样例回归

- 将 v0.5.7 的高质量输出匿名化为黄金案例，固定事实、结构、经历边界、技能分类和 DOCX 投递不变量。
- 确定性回归使用固定 `GenerationPayload`，执行生产 Guard 与 DOCX 链路，不受真实模型随机性影响。
- 真实模型评测独立运行，只记录质量分数和退化项，不作为普通 `pytest` 的强制条件。
- 回归采用语义与结构断言，不要求逐字一致，避免把合理改写误判为退化。

运行确定性黄金回归：

```bash
python -m pytest tests/test_golden_resume_regression.py -q
```

生成固定基线评测报告：

```bash
python scripts/evaluate_golden_resume.py --mode mock
```

配置 LLM 后运行真实模型评测：

```bash
python scripts/evaluate_golden_resume.py --mode openai
```

新增黄金案例时，先匿名化输入与基线文本，再补充 `required_facts`、经历边界、技能分类和禁止项；不要提交姓名、联系方式、学校等个人信息。

## v0.5.7 信息分层与招聘者表达

- 个人优势调整为 1-2 条高度定位，避免复述全部项目和技术栈。
- 新增经历正文分层：项目简介负责定位，我的职责负责 ownership，技术细节负责新增事实和结果。
- 新增事实增量检查，删除近义重复，同时保护部署、评测、指标、用户反馈等独立高价值事实。
- 技能按编程语言、AI、前端、后端、数据库、测试评测和工程部署等招聘者常见分类校准。
- 内部字段与工程变量转换为招聘者可理解的系统能力，不直接暴露代码字段和调试标记。
- 新增日志：`backend/logs/resume_section_layering.jsonl`、`backend/logs/resume_skill_taxonomy.jsonl`。

## v0.5.0 事实簇去重与最终输出质量门

- 去重从单纯句子相似度升级为 Fact Cluster Dedup，结合 `source_fact_ids`、包含关系、事实动作、语义侧面和信息量评分选择最佳表达。
- 新增跨字段去重检查，明确 intro 负责项目定位、role 负责职责边界、details 负责独立技术事实，减少同一事实跨字段复述。
- 新增中文标点和异常字符净化，修复连续顿号、重复逗号、尾部标点和异常空格，同时保护 Query Intent、C++、Node.js、BAAI/bge-m3 等技术词。
- 新增只评分不改写的 Output Quality Gate，记录事实覆盖、经历边界、重复、语言专业度、标点、内部字段和投递就绪度七项分数。
- 新日志位于 `backend/logs/resume_dedup_quality.jsonl`、`resume_typography_quality.jsonl` 和 `resume_output_quality.jsonl`，并汇总进 generation quality 报告。

## v0.4.11 生成质量工程收口

- 完成 v0.4.x 生成与 DOCX 二次检查管线审计，明确每个 Guard 的写入职责和必要复检点，详见 `docs/generation-quality-pipeline.md`。
- 新增 10 类匿名真实案例和端到端回归测试，覆盖长输入、多 RAG 项目、真实实习、弱履历、负面边界、输入指令污染及高价值事实保留。
- 新增 `scripts/export_generation_quality.py`，汇总 fallback、Experience ID 绑定、事实覆盖、跨经历污染、事实去重、类型纠正和 DOCX 投递质量。
- 新增 v0.4 阶段复盘，记录从关键词分类到关系语义、从项目边界到事实 provenance 的演进及当前技术债务。

生成全部质量报告：

```bash
python scripts/export_generation_quality.py
```

生成最近七天报告：

```bash
python scripts/export_generation_quality.py --days 7
```

默认输出：`backend/reports/generation-quality-YYYY-MM-DD.md`。报告只包含聚合指标，不包含用户原始输入或完整简历正文。

v0.4.x 的核心质量日志位于 `backend/logs`：`generation_stability.jsonl`、`resume_section_fallback.jsonl`、`experience_boundary.jsonl`、`fact_coverage.jsonl`、`resume_fact_dedup.jsonl`、`experience_type_resolution.jsonl`、`resume_output_firewall.jsonl`、`resume_summary_quality.jsonl`、`resume_text_integrity.jsonl` 和 `docx_delivery_readiness.jsonl`。

v0.5.0 将从继续堆叠 Guard 转向统一输出质量评测，重点衡量事实正确率、经历覆盖率、重复率、包装增益和投递就绪度。

## v0.4.10 高价值事实保留式去重

- 事实去重同时使用文本包含关系、`source_fact_ids`、技术动作簇和高置信语义相似度，不再仅凭技术词重合删除内容。
- 同一组检索实验的近义复述会保留信息更完整的一条；RAG 实现、评测、Citation、部署和数据隔离等独立事实继续分别保留。
- 单段经历允许保留最多 8 条独立高价值详情，去重目标是降低重复率，不是机械缩短简历。
- 实习经历新增内部 `position` 字段，只从对应经历原文提取；DOCX 标题使用“公司｜实习岗位｜时间”，未提供岗位时保留 `[待填写]`。
- 项目标题使用“项目名称｜具体项目类型｜时间”，并优先识别个人项目、课程项目、团队项目、开源项目和科研项目。
- 去重日志位于 `backend/logs/resume_fact_dedup.jsonl`，只记录决策类型、相似度和内部事实 ID。


## v0.4.9 正式简历与教练方案分离

- 正式 DOCX 不再输出面试准备、知识补齐、Claim 风险、证据建议和降级表达，下载后只需补充个人信息并核对时间即可形成初步投递版本。
- DOCX 渲染前执行投递就绪检查，日志位于 `backend/logs/docx_delivery_readiness.jsonl`，不记录用户原始输入或完整简历正文。
- 导出页完整保留求职教练能力，并将内容分为面试问题、技术知识补齐、证据材料准备和表达边界四组。
- 新增 `copy_interview_group`、`copy_all_interview_plan` 和 `expand_interview_group` 埋点。


## v0.4.8 关系语义驱动的经历类型解析

- 经历类型从关键词命中升级为“作者 + 关系动作 + 经历对象”证据评分，区分作者任职、产品目标用户和招聘对象。
- “面向实习求职者、实习岗位推荐、实习面试准备”等业务语境不再被视为作者实习证据。
- 项目 ownership、产品定位、用户测试、部署和版本迭代可以形成项目经历正向证据。
- Reconciliation 只负责 source ID 匹配，不再修改 `project.meta`；DOCX Router 继续保持纯路由。
- 高置信类型写入内部类型锁，Fact Guard 与正文清理服务会保留 provenance，不再丢失 `source_experience_id`。
- 类型日志增加证据评分、排除语境、第二候选类型、分差和 resolver 版本。

## v0.4.7 类型路由、事实去重与 Section 完整性

- 经历类型由对应 `experience_id` 的局部标题和事实解析，类型确认与 DOCX Section Routing 解耦。
- 新增事实级语义去重，高置信重复合并、中置信相似保留，平衡 Dedup Precision 与 Recall。
- 修复 `result_cleanup` 全局替换独立 `summary` 导致的 `section 个人优势 chunk` 污染。
- Section Schema 只保留标准英文 key，中文模块名仅由 renderer 展示，合法技术语境中的 Chunk 不受影响。
- 新增生成阶段质量快照，可定位类型、重复和污染第一次出现的处理阶段。
- 日志位于 `backend/logs/experience_type_resolution.jsonl`、`resume_fact_dedup.jsonl` 和 `generation_stage_quality.jsonl`。

## v0.4.6 正式简历输出质量防火墙

- 将混合输入分为经历事实、目标岗位、包装指令、不确定说明、模板残片和噪声，只有事实可以进入正式简历。
- 新增句内污染切除，保留 CodeBuddy、虚拟机、回归分析等有效事实，同时移除“希望包装、想投、不要写成”等写作指令。
- 新增简历语言专业化，将“我做过、我写了、我调了、技术动作”等口语或内部标签转换为行动导向表达。
- 生成保存和历史 DOCX 导出阶段均执行输出防火墙，不通过整句删除牺牲用户事实。
- 防火墙日志位于 `backend/logs/resume_output_firewall.jsonl`，语言质量日志位于 `backend/logs/resume_language_quality.jsonl`。

## v0.4.5 候选人视角个人优势

- 新增个人优势质量检查，隔离“候选人、爱好者、可面试承接、建议补充”等求职教练话术。
- 每条个人优势必须由 `experience_id` 或 `fact_id` 支撑，并使用“能力 + 行动证据 + 价值”的候选人视角表达。
- 协作、量化结果和学习迁移能力按事实条件生成，不再用空泛积极词机械补满。
- 历史结果重新导出 DOCX 时也会执行清理，面试准备与简历正文各自承担清晰职责。
- 质量日志位于 `backend/logs/resume_summary_quality.jsonl`，仅记录修复统计和内部事实标识，不记录完整用户输入。

## v0.4.4 Experience Fact Ledger

- 按 `experience_id` 建立原子事实账本，并用内部 `fact_id` 追踪技术、功能、工程实践、证据和指标。
- 新增事实覆盖检查，高价值明确事实优先于通用包装句和重复内容。
- 项目详情只使用本段事实或本段允许的自然承接知识，跨经历内容会被移回正确经历或清理。
- 移除项目详情中的机械通用补句；输入越充实，正式简历承载的有效事实越完整。
- 覆盖日志位于 `backend/logs/fact_coverage.jsonl`，只记录统计和 fact_id，不记录完整用户输入。

## v0.4.3 经历类型与正文完整性

- 使用 `source_experience_id` 校准经历类型，避免个人项目被误分到实习经历。
- DOCX 在技能与能力之后优先展示真实实习经历，再展示项目、科研和竞赛经历。
- 内部裁剪摘要与用户可见正文隔离，避免省略号被误解为用户原文缺失。
- 生成与导出阶段检查截断提示，并从对应经历原文恢复完整语义。
- 完整性日志位于 `backend/logs/resume_text_integrity.jsonl`，不记录完整用户原文。

面向国内应届生和实习生的 AI 求职教练网页应用。

它不是普通的简历润色器，而是一个“经历定位 + 包装强度判断 + 面试承接准备 + 正式简历导出”的完整闭环工具。产品原则是：表达可以积极，但硬事实不能凭空改变；每一个强表达都应该能被证据、技术知识或面试回答接住。

## 项目定位

Resume Coach App 面向有项目、实习、开源、比赛或校园经历，但不知道如何表达的技术求职者。用户输入真实经历后，系统会帮助其完成：

- 识别经历中的可用事实和缺失信息。
- 根据目标岗位生成不同强度的包装表达。
- 标出 Claim 风险和面试追问。
- 给出知识补齐和证据准备方向。
- 生成可下载的正式技术简历 DOCX。
- 记录匿名埋点和反馈，支持后续投放复盘。

## 当前能力

- 引导式经历输入：目标岗位、经历类型、包装强度、示例模板、输入质量提示。
- 三档包装表达：基础增强、重点放大、边界测试。
- 结果工作台：定位总览、三档包装、承接检查、面试准备、简历预览。
- Claim 风险分析：green / yellow / red / black 四档风险。
- 面试承接：面试追问、补充追问、知识补齐、降级表达。
- 生成稳定性：LLM 输出经过结构校验、JSON 修复、结果清洗和简历结构兜底。
- 输出质量：支持多段经历识别和更高密度项目生成，避免长输入被过度压缩。
- 经历覆盖：支持项目、实习、科研、竞赛、开源、校园 / 社团等经历进入正式简历。
- 长输入稳定生成：长经历会先本地预处理为 compact context，再使用短 prompt 生成，降低 token 消耗、响应时间和 JSON 截断风险。
- 项目专属表达：清理多个经历之间重复出现的模板句，让通用能力进入个人优势 / 技能栈，具体经历保留差异化细节。
- 弱经历增强：对课程大作业、小项目、学生工作、竞赛参与等薄弱履历进行成长型包装，不伪造成实习或企业项目。
- 正文去负面化：清理“没有实习、未上线、没有获奖、只是作业”等自降表达，缺失事实进入面试准备而不是正式简历。
- Experience ID 边界：每段经历在内部绑定 `EXP-001 / EXP-002`，生成、fallback、guard 和 DOCX 导出前都会尽量按经历身份隔离事实。
- 混合输入语义分段：即使用户没有写标题或换行，系统也会结合新动作、组织、经历类型、主题变化和独立结果谨慎识别多段经历。
- 项目级内容对账：删除重复综合经历前先回收尚未覆盖的有效事实，将技术、指标和职责放回对应 experience_id。
- 候选人视角个人优势：个人优势只呈现事实支撑的已具备能力，求职教练诊断、包装方法和未来准备事项不会进入正式简历。
- 输出质量防火墙：求职意图、包装指令和模板残片不会进入简历，项目事实会被转换为更专业的行动表达。
- 可追踪类型与路由：长输入中的经历类型由局部证据决定，事实级去重与 Section 完整性检查降低重复和内部标记污染。
- 关系语义类型解析：只有作者与公司/岗位存在明确关系时才生成实习经历，产品用户中的“实习”不会污染项目类型。
- DOCX 导出：根据结构化简历生成正式技术简历，支持最多两页内容承载，并在结构为空时自动兜底，避免页面有内容但 DOCX 空白。
- 数据闭环：匿名用户、会话、事件、输入、生成结果、反馈、LLM 调用日志和 fallback 日志。
- 数据导出：将 SQLite 埋点导出为 Markdown 和 CSV 报告，并汇总 fallback 触发率。
- 移动端适配：支持手机完成输入、查看、导出、反馈流程。

## v0.1.x 功能列表

- v0.0：跑通输入经历、生成结果、展示、DOCX 下载、埋点和反馈。
- v0.1：接入真实 LLM 模式，保留 mock 模式。
- v0.1.1：新增数据汇总和导出脚本。
- v0.1.2：新增输入页敏感信息提醒。
- v0.1.3：优化结果页顶部介绍和项目经历展示中文化。
- v0.1.4：结果页改为 Tabs 工作台，Claim 支持展开查看。
- v0.1.5：输入页增加模板、质量提示，并将包装强度产品化。
- v0.1.6：新增后端结果清洗与稳定性兜底。
- v0.1.7：优化结果页阅读体验，长文本改为摘要和展开。
- v0.1.8：将面试准备清单移动到导出页，增强交付感。
- v0.1.9：完成移动端适配。

## v0.2.x 稳定性收口

v0.2.x 聚焦真实用户使用后的稳定性与可观测性。

- v0.2.0：清理三档包装、推荐版本、项目预览和面试准备中的英文内部字段名。
- v0.2.1：承接检查改为状态圆点，信息完整度增加“当前还缺什么”。
- v0.2.2：新增 Resume Section Fallback，修复页面有内容但 DOCX 空白的问题。
- v0.2.3：增强 fallback 可观测性，将触发阶段、补全 section、触发原因和来源字段写入日志并汇总到 analytics。

核心原则：

```text
结构合法不等于业务可用。
Fallback 是安全网，不是垃圾桶。
用户不该感知故障，但开发者必须能感知上游退化。
```

## v0.3.0 输出质量优化

v0.3.0 从“稳定性收口”进入“生成质量优化”，重点解决长输入和多段经历下的过度压缩问题。

主要能力：

- 支持多段经历识别：项目、实习、开源、比赛等主要经历应尽量分别保留。
- 支持更高密度项目生成：单段经历保留更多职责、技术细节、结果和证据。
- 长输入不再默认压成一段：除非经历高度重复或信息极少，否则不随意合并删除。
- 支持最多两页 DOCX：内容充足时优先完整承载关键项目，而不是强行压缩成一页。
- 继续遵守事实边界：可以大胆包装职责表达，但不凭空增加用户数、star、上线、性能提升、企业实习、模型训练等硬事实。

## v0.3.1 长输入抗失败修复

v0.3.1 针对真实长经历输入进行修复，重点处理“项目一｜项目名”“### 项目二｜项目名”等自然写法。

主要能力：

- 生成前增加经历分段预解析，将长输入拆成主要经历清单并注入 prompt。
- Fallback 支持中文冒号、英文冒号、竖线、全角竖线和破折号等标题分隔符。
- 长段落句号较少时，会进一步按逗号拆出可用技术细节，减少项目细节过少的问题。
- 默认 LLM 超时调整为 60 秒，默认输出上限调整为 8192 tokens，降低长输出被截断导致无法生成的概率。

## v0.3.2 事实防幻觉与包装增益

v0.3.2 继续优化输出质量，核心原则是：硬事实守住，软表达拉满。

主要能力：

- 硬事实防幻觉：用户未提供学校、专业、学历、公司、用户数、star、并发、奖项、模型训练等信息时，不编造、不暗示。
- 隐性硬事实清理：将“计算机相关专业”“科班背景”“企业级生产系统”“模型训练经验”等缺少事实支撑的表达降级。
- 软事实包装增强：对“写页面 / 调接口 / 修 bug / 写文档 / 做 RAG”等真实经历进行职责、技术动作和项目结构上的表达升级。
- 避免复述原文：当推荐版本或项目 details 与用户输入过于相似时，会基于已有事实重新组织成更正式、更岗位化的简历表达。

## v0.3.3 非项目经历覆盖

v0.3.3 增强实习、科研、竞赛、开源、校园 / 社团等非项目经历的识别和 DOCX 承载。

主要能力：

- 不改数据库和 API，继续用 `resume_sections.projects` 统一承载经历。
- 通过 `project.meta` 区分“项目经历 / 实习经历 / 科研经历 / 竞赛经历 / 开源经历 / 校园 / 社团经历”。
- Fallback 会从原始输入中补回被 LLM 漏掉的实习、科研、竞赛等经历。
- DOCX 输出按小标题分组展示，例如“项目经历”“科研经历”“实习经历”“竞赛获奖”。

## v0.3.4 长输入低 token 稳定生成

v0.3.4 解决长输入时响应慢、token 消耗高、JSON 截断和偶发无法生成的问题。系统不会把完整长原文和完整长 prompt 一次性丢给模型，而是先在本地做经历分段和关键词提取，再把压缩后的 compact context 交给短 prompt。

主要能力：

- 本地预处理：识别长输入、行数和主要经历段数，提取经历类型、标题、摘要、技术词、证据词和风险词。
- 长输入短 prompt：长输入模式下使用 `prompts/generate_resume_coach_result_long.md`，优先保证 `resume_sections.projects` 和 DOCX 可用。
- 输出控量：三档包装、Claim、面试准备和知识清单保持必要但不冗长，降低输出 token 和截断风险。
- 稳定 fallback：OpenAI 兼容接口失败、JSON 修复失败或 schema 校验失败时，不直接让前端报错，而是基于本地分段生成可用的保底结果。
- 事实边界：fallback 不调用 LLM，不编造学校、专业、公司、用户数、star、并发、奖项、模型训练等硬事实。
- 稳定性日志：每次生成写入 `backend/logs/generation_stability.jsonl`，记录是否进入长输入模式、是否使用短 prompt、是否触发 fallback 和耗时。

## v0.3.5 经历边界与自然承接知识

v0.3.5 解决多段经历之间事实串通，以及简历主体出现“Docker（如有）”“LangGraph（建议掌握）”这类不专业表达的问题。

主要能力：

- 内部 experience_id：长输入预处理会为每段经历生成 `EXP-001 / EXP-002 / EXP-003`，用于隔离事实边界，不暴露给用户。
- 防止跨经历串通：项目 A 的技术、数据、部署、star、用户数、论文、奖项等不会被写进项目 B / 实习 C。
- Supported inference：允许同一段经历内部写入自然承接知识，例如 RAG 测试集可以承接 Top-K、Retrieval、Chunk、Embedding 等表达。
- 面试承接同步：自然承接知识进入简历时，会同步进入 `interview_plan` 或 `knowledge_checklist`，提醒用户补齐解释口径。
- 不确定表达清理：简历主体不保留“如有 / 可补充 / 建议掌握 / 待补充”等口吻；不确定知识会转入面试准备，不写成已实现事实。

## v0.3.7 项目专属表达与重复模板句清理

v0.3.7 解决多经历简历中的另一个真实问题：事实没有串通，但表达仍然可能串通。比如同一句“围绕文档解析、切块、Embedding、向量检索和回答生成梳理 RAG 应用链路”被复制到多个项目、实习或竞赛经历中，会让简历显得模板化，也会让经历边界变得不可信。

主要能力：

- 新增项目专属表达守卫，检查不同经历之间 `intro` / `role` / `details` 的重复句和高度相似句。
- 对完全相同、去标点后高度相似、或包含同一组连续技术短语的表达进行清理。
- RAG、接口联调、组件化、状态管理等自然承接知识仍可写入简历，但必须结合该经历自身任务改写。
- 多个 RAG 经历可以同时保留 RAG，但侧重点必须不同，例如应用开发写检索问答链路，测试集写 Top-K / Recall / Groundedness，部署写服务链路和日志。
- DOCX 导出前也会执行项目专属表达清理，历史生成结果重新导出时同样能减少重复模板句。

## v0.3.8 弱经历用户增强策略

v0.3.8 面向更典型的校园用户：没有实习，只有课程大作业、简单小项目、学生工作、竞赛参与或校级材料。这类用户不是没有价值，而是需要把有限经历整理成“可投递、可解释、可继续补强”的成长型简历表达。

主要能力：

- 识别弱履历信号：输入较短、缺少实习 / 上线 / 用户数 / star / 数据指标、出现课程项目 / 大作业 / 课设 / 小项目 / 学生工作 / 竞赛参与等。
- 课程项目包装为“课程项目 / 软件工程实践 / 独立项目实践”，不写成企业项目。
- 简单小项目会围绕需求理解、页面开发、接口联调、材料沉淀和复盘优化进行正式化表达。
- 学生工作和社团经历会转化为组织协调、沟通推进、活动执行、材料沉淀和结果复盘能力。
- 竞赛参与会保留为竞赛经历，未明确提供奖项时不写“获奖”“排名”或证书。
- 面试准备中加入薄弱履历补强路线，提醒用户补充截图、仓库、PPT、实验报告、课程评分、活动规模等证据材料。

## v0.3.9 简历正文去负面化与实习幻觉防护

v0.3.9 修复弱经历增强后的两个问题：正式简历中不应出现“没有实习”“没有上线”“没有获奖”“只是课程作业”这类负面或自降表达；用户没有明确实习事实时，也不应生成“实习经历”模块。

主要能力：

- 新增简历正文净化器，清理 summary、项目名称、项目类型、项目简介、我的职责和技术细节中的负面表达。
- “没有实习 / 未上线 / 没有获奖”等边界事实不会进入正式简历正文，而是转入面试准备、追问或边界判断。

## v0.4.0 Experience ID 事实边界

v0.4.0 将多经历处理从“生成后修补”推进到“生成前分段、生成中绑定、生成后校验”。

主要能力：

- 每段经历在预处理阶段生成内部 `experience_id`，例如 `EXP-001`、`EXP-002`。
- prompt 中注入 experience_id 边界表，要求模型为每个简历项目绑定 `source_experience_id`。
- `source_experience_id` 只在后端内部使用，不展示给用户，也不会进入 DOCX。
- 后端边界守卫优先按 `source_experience_id` 校验；模型漏填时，再用项目名称、经历类型、技术词、证据词回匹配。
- Resume Section Fallback 和稳定 fallback 也会按 experience_id 逐段生成项目，避免把多段经历兜成一个“综合经历项目”。
- 新增 `backend/logs/experience_boundary.jsonl`，记录经历数、项目 source id 缺失数、跨经历污染修复次数和修复字段。

这一步的目标不是让系统更保守，而是让每段经历独立、真实、可包装、可承接。

## v0.4.1 混合自然语言经历识别

v0.4.1 解决用户把项目、校园活动、社会实践、社团工作和竞赛内容连续写在一段话中时，系统错误生成“综合经历项目”的问题。

- 显式标题仍然优先；没有标题时，后端根据标点、新经历动作、组织或角色变化、经历类型变化、主题变化和独立证据计算分段置信度。
- 功能列表和同一项目的技术链路不会仅因逗号而被拆散；相邻且信息较少的校园活动允许谨慎合并。
- 年级、个人背景和求职意向会从项目候选内容中剥离，不会成为项目名称或技术细节。
- 识别到多个 experience_id 后，LLM 和 fallback 都不能再用一个“综合经历项目”容纳全部内容。
- 无法可靠判断的关系进入 `missing_questions`，不会直接写成确定事实。
- 分段日志写入 `backend/logs/experience_segmentation.jsonl`，只记录长度、类型、置信度和截断标题，不记录完整用户原文。

## v0.4.2 项目级内容对账

v0.4.2 坚持“不过分修饰，也不刻意删减”：当模型已经生成具体项目，而 fallback 又产生“综合经历项目”时，系统不会直接保留重复项目，也不会把其中的有效细节一并删除。

- 修复空行在预处理阶段被压平的问题，并补充“独立设计 / 从零开发 / 在某公司实习”等经历起始信号。
- fallback 在已有项目时只补充未覆盖的 experience_id，不再从完整原文追加综合经历。
- 新增项目级 reconciliation：逐条判断综合经历中的技术、指标和职责属于哪个 experience_id，未覆盖的高价值细节回填到对应项目，重复和无来源内容不进入正文。
- source_experience_id 匹配不足时保持未绑定，不再按项目顺序强行绑定 EXP-001。
- 内容预算为单项目最多 8 条、主要项目合计最多 18 条，优先保留各项目基础信息，再分配剩余篇幅，服务最多两页 DOCX。
- generation 和 docx_export 都执行项目对账，历史结果重新导出时也能清理综合经历。
- 对账日志写入 `backend/logs/resume_project_reconciliation.jsonl`，仅记录数量、ID 和截断项目名，不记录完整用户原文。
- “只是课程作业”“简单小项目”“写了几个页面”“调了一些接口”等不专业原话会改写为“课程项目”“个人项目实践”“页面开发与交互流程实现”“接口联调与数据流转校验”。
- fact guard 增强实习幻觉防护：原文没有实习、公司、工作、岗位等线索时，`meta=实习经历` 会被降级为课程项目、个人项目、校园 / 社团经历、竞赛经历或项目经历。
- DOCX 导出前也执行正文净化和事实守卫，历史结果重新导出时同样不会把缺点写进正式简历。

## 本地启动

### 1. 安装依赖

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
pnpm install
```

后端建议使用虚拟环境：

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```powershell
copy .env.example .env
```

默认使用 mock：

```env
LLM_MODE=mock
```

接入真实 API：

```env
LLM_MODE=openai
OPENAI_API_KEY=你的 API Key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
LLM_TIMEOUT_SECONDS=75
LLM_MAX_TOKENS=8192
LLM_THINKING=disabled
```

`OPENAI_BASE_URL` 支持 OpenAI 兼容接口，例如 DeepSeek、OpenRouter 或自建兼容网关。

生成超时建议采用分层配置：模型调用 75 秒、Nginx 读取与发送超时 100 秒、浏览器等待 110 秒。外层超时应高于内层超时，避免前端仍在等待而代理或模型调用已经提前终止。Nginx `/api/` 可增加：

```nginx
proxy_connect_timeout 10s;
proxy_send_timeout 100s;
proxy_read_timeout 100s;
```

### 3. 启动后端

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app\backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果 8000 端口被占用：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：

```text
http://127.0.0.1:8000/api/health
```

### 4. 启动前端

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app\frontend
pnpm dev
```

如果后端使用 8001 端口：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8001"
pnpm dev
```

访问：

```text
http://127.0.0.1:5173
```

## 服务器部署

服务器推荐只作为部署环境，不直接修改源码。先在本地完成测试、提交与推送，再在服务器使用 fast-forward merge 拉取；不要用 `git reset --hard` 覆盖运行数据或本地环境配置。

```bash
cd /www/wwwroot/resume-coach-app
git fetch origin main
git merge --ff-only origin/main
cd frontend
pnpm build
nginx -t && systemctl reload nginx
systemctl restart resume-coach-backend
```

如果只改前端页面或样式，可以不重启后端：

```bash
cd /www/wwwroot/resume-coach-app
git fetch origin main
git merge --ff-only origin/main
cd frontend
pnpm build
nginx -t && systemctl reload nginx
```

如果改了后端代码、prompt、`.env` 或生成逻辑，需要重启后端。

## DOCX 输出

- DOCX 生成接口：`POST /api/resume/docx`
- 下载接口：`GET /api/files/{file_id}`
- 输出目录：`backend/outputs/`
- 文件会自动版本化命名。
- 未提供的个人信息保留 `[待填写]`，不会编造姓名、手机号、邮箱等信息。
- v0.3.0 起，DOCX 允许承载最多两页内容；当用户输入多段经历时，会优先保留关键项目，而不是为了压缩版面删除主要经历。

## 数据埋点与导出

v0.6.6 起，每次生成使用匿名 `attempt_id` 关联提交、等待、成功/失败、结果查看和 DOCX 下载。事件只记录输入长度、经历数量估计、技术/指标信号等统计特征，不再把完整 `raw_input` 写入埋点。

生成可靠性漏斗：

```bash
python scripts/export_generation_funnel.py
python scripts/export_generation_funnel.py --days 7
```

报告输出到 `backend/reports/generation-funnel-YYYY-MM-DD.md`。旧事件没有 `attempt_id` 时会标记为历史不可关联数据，不会被强行统计为失败。详细口径见 [数据指标定义](docs/analytics-metrics-definition.md)。

当前埋点包括：

- `visit_home`
- `submit_experience`
- `generate_success`
- `generate_failed`
- `view_claim_risk`
- `copy_result`
- `generate_docx`
- `download_docx`
- `submit_feedback`
- `view_result_tab`
- `expand_claim`
- `submit_followup`
- `change_packaging_level`
- `change_target_role`
- `fill_example_template`
- `input_quality_hint_shown`
- `view_export_interview_plan`

SQLite 数据库：

```text
backend/data/resume_coach.db
```

导出统计报告：

```powershell
python scripts\export_analytics.py
```

服务器运行：

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/export_analytics.py
```

默认输出：

```text
backend/reports/analytics-summary-YYYY-MM-DD.md
backend/reports/analytics-events-YYYY-MM-DD.csv
backend/reports/analytics-inputs-YYYY-MM-DD.csv
```

报告和 CSV 中展示的时间统一为北京时间。默认不会导出用户原始经历全文。

analytics 报告会同时汇总 Resume Section Fallback 触发情况，包括 fallback 调用次数、触发率、触发阶段、补全 section、触发原因和来源字段。Fallback 只作为安全网保护用户交付体验，如果触发率异常升高，需要回看 prompt、模型或结构化输出质量。

检查最近生成文件记录：

```bash
sqlite3 backend/data/resume_coach.db "select id, generation_result_id, file_type, file_path, created_at from generated_files order by id desc limit 10;"
```

## 日志位置

- LLM 调用日志：`backend/logs/llm_calls.jsonl`
- 结果清洗日志：`backend/logs/result_cleanup.jsonl`
- 简历结构兜底日志：`backend/logs/resume_section_fallback.jsonl`
- 长输入稳定性日志：`backend/logs/generation_stability.jsonl`
- 经历边界守卫日志：`backend/logs/experience_boundary.jsonl`
- 混合输入分段日志：`backend/logs/experience_segmentation.jsonl`
- 项目级内容对账日志：`backend/logs/resume_project_reconciliation.jsonl`
- Canonical 影子状态日志：`backend/logs/canonical_semantic_state.jsonl`
- Canonical owner 冻结日志：`backend/logs/canonical_fact_ownership.jsonl`
- Canonical Consumer Views 日志：`backend/logs/canonical_consumer_views.jsonl`
- 语义变更追踪日志：`backend/logs/semantic_mutation_trace.jsonl`
- Quality Repair Router 日志：`backend/logs/resume_quality_repair_router.jsonl`
- 项目层级关系日志：`backend/logs/project_hierarchy.jsonl`
- 生成文件：`backend/outputs/`
- 数据报告：`backend/reports/`

查看最近 LLM 日志：

```bash
tail -n 50 backend/logs/llm_calls.jsonl
```

查看最近清洗日志：

```bash
tail -n 50 backend/logs/result_cleanup.jsonl
```

查看最近简历结构兜底日志：

```bash
tail -n 50 backend/logs/resume_section_fallback.jsonl
```

查看最近长输入稳定性日志：

```bash
tail -n 50 backend/logs/generation_stability.jsonl
```

查看最近经历边界守卫日志：

```bash
tail -n 50 backend/logs/experience_boundary.jsonl
```

查看最近混合输入分段日志：

```bash
tail -n 50 backend/logs/experience_segmentation.jsonl
```

查看最近项目级内容对账日志：

```bash
tail -n 50 backend/logs/resume_project_reconciliation.jsonl
```

## 常见问题

### GitHub 拉取很慢或卡住

服务器访问 GitHub 可能不稳定。优先确认：

```bash
git ls-remote origin
```

如果 GitHub 网络不可用，可以临时上传 `frontend/dist` 和 prompt 文件，但长期建议保持服务器通过 GitHub 同步。

### 页面没有更新

常见原因：

- 本地代码没有 commit / push。
- 服务器 `git pull` 或 `git reset` 没有到最新提交。
- 前端没有重新 `pnpm build`。
- 浏览器缓存旧资源，需要强制刷新。
- 改了 prompt 或后端代码但没有重启后端。

### 生成结果仍出现英文内部字段

确认后端已重启，并检查：

```bash
tail -n 50 backend/logs/result_cleanup.jsonl
```

如果没有日志，说明最新后端清洗逻辑可能没有部署或服务未重启。

### DOCX 下载失败

检查：

- 后端服务是否运行。
- `backend/outputs/` 是否存在并有写入权限。
- Nginx `/api/` 代理是否正常。
- 浏览器是否拦截新窗口下载。
- 如果页面有内容但 DOCX 主体为空，检查 `backend/logs/resume_section_fallback.jsonl` 和 analytics 报告中的 Resume Fallback 监控。

### 数据导出没有内容

确认线上数据库路径：

```text
backend/data/resume_coach.db
```

并检查 events 表是否有记录：

```bash
sqlite3 backend/data/resume_coach.db "select count(*) from events;"
```

## v0.3 方向概览

v0.3 建议主题：输出质量优化。

优先方向：

- Prompt 分层：拆分经历解析、信息缺口诊断、岗位定位、三档包装、Claim 检查、面试准备和 resume_sections 生成。
- 输出质量评分：检查结果是否具体、岗位匹配、可承接、少空泛。
- 反空泛规则：减少“提升用户体验”“负责相关工作”等弱表达。
- 岗位化生成策略：同一段经历针对 AI Agent、后端、前端、数据分析等岗位突出不同重点。
- 真实案例回归集：把真实用户 case 固化为测试样例。
- DOCX 版式：继续接近正式技术简历，优化移动端下载提示。

详细检查见：

- `docs/launch-checklist.md`
- `docs/version-history.md`
- `docs/v0.2-retrospective.md`

## v0.5.1 自适应经历叙事

- 根据经历类型和已有事实选择叙事顺序，不强制套用统一模板。
- 明确 intro、role、details 的职责边界，减少跨字段重复。
- 使用 Information Gain 检查确保每条详情引入新的事实价值。
- 增加 Narrative Coherence 与 Template Language Guard，改善逻辑连贯和专业表达。
- 历史结果重新导出 DOCX 时同样执行叙事质量检查。
- 质量日志：`backend/logs/resume_narrative_quality.jsonl`。

## v0.5.2 语义单元与事实簇治理

- 使用 Semantic Unit Recovery 检查残句、依赖前文表达和被错误拆开的指标关系。
- 使用 Fact Cluster 区分核心链路、Citation、评测、检索优化、部署与可观测性等事实侧面。
- 同一事实簇只保留信息增量最高的表达，不同工程价值即使共享技术词也继续保留。
- 扩展 Information Density 与 Sentence Independence 评分。
- 质量日志：`backend/logs/resume_semantic_quality.jsonl`。
### v0.5.3：投递语言净化与技能证据

- 技能栏增加事实证据校验，岗位要求和知识补齐不再被当作已掌握技能。
- 不确定技能从正式简历移出，保留到追问或面试准备中。

### v0.5.5：技能栈结构化呈现

- 将技能证据校验与技能展示组织解耦：Evidence Guard 决定能否写，Presentation Service 决定如何专业地写。
- 将事实支持的裸技术词按编程语言、前后端、存储、AI 应用、工程化和测试等类别聚合，避免 DOCX 退化为关键词清单。
- 分类顺序随目标岗位调整；历史生成结果重新导出时也会自动恢复分类式技能栈。
- 技能呈现日志位于 `backend/logs/resume_skill_presentation.jsonl`。

### v0.5.6：职责事实化与兜底污染治理

- 移除 Boundary Guard、Resume Section Fallback 和 Stable Fallback 中面向系统的职责占位说明。
- 新增经历级职责恢复：只从对应 `experience_id` 的职责或动作事实生成“我的职责”，无法恢复时允许留空。
- Output Firewall 在最终保存和 DOCX 渲染前拦截“以用户原文为准”“参与相关任务”等内部话术，历史结果重新导出也会清理。
- 职责质量日志位于 `backend/logs/resume_role_quality.jsonl`，Section Fallback 日志同步记录职责恢复和留空数量。
- `python scripts/export_generation_quality.py` 会汇总职责 fallback 触发率、事实恢复数量、留空数量和内部占位清理数量。
- 增加中文引号、括号、书名号、方括号和反引号的配对完整性检查。
- 将内部字段枚举转换为招聘者可理解的工程价值表达。
- 增加 Recruiter Readability 检查，减少开发日志、文件清单和字段说明书式表达。
- 新增日志：`backend/logs/resume_skill_evidence.jsonl`、`paired_symbol_integrity.jsonl`、`recruiter_language.jsonl`、`resume_recruiter_readability.jsonl`。
### v0.5.4：语义空格与文本拼接治理

- 增加中文词内、中文标点、引号和括号内侧的异常空格清理。
- 识别不间断空格、全角空格、零宽空格和复制产生的特殊空白字符。
- 保护 AI Agent、JSON Schema、Resume Section Fallback 等多词技术短语。
- 空格治理位于 Text Integrity 与 Typography 之间，不改变 Experience ID、Fact ID 或事实边界。
- 质量日志：`backend/logs/resume_whitespace_quality.jsonl`。

### v0.6.1：技能恢复与薄履历增强

- 模型返回空技能栏时，从 Experience Fact Ledger 恢复用户明确提供的技术证据，再执行规范化和分类。
- 支持数据分析与建模、数据可视化、物联网与通信、地图与路线服务、安全机制、开发工具与环境等分类。
- 项目正文偏薄时优先恢复对应 `experience_id` 的目标、功能、技术、职责与结果，不从目标岗位反推技能，也不用通用模板句凑内容。
- `backend/logs/resume_skill_evidence.jsonl` 记录恢复和过滤情况；`backend/logs/resume_output_quality.jsonl` 记录技能证据遗漏、薄项目数量和项目事实覆盖率。

### v0.6.7：技术术语消歧与输出相关性

- 技能恢复不再依据孤立关键词分类，而是结合对应 `experience_id` / `fact_id` 的局部事实语境解析术语含义。
- 区分 Token 调用成本、Prompt 上下文和接口鉴权：只有 JWT、Bearer、鉴权、登录态或权限证据才进入“安全机制”。
- 模型、训练、部署、用户和测试等歧义词同步建立语境判定；低置信术语不进入正式简历，而进入信息缺口提示。
- 输出相关性检查会移动或删除错误技能分类，但不会删除项目正文中已经确认的指标和工程事实。
- 消歧日志：`backend/logs/technical_term_disambiguation.jsonl`；输出相关性日志：`backend/logs/resume_output_relevance.jsonl`。两类日志只记录术语含义、分类、置信度和来源 ID，不记录完整经历。

### v0.6.9：正式经历有效性硬门槛

- 分段阶段识别“名称｜身份｜时间”标题残片：能匹配正文时并回相邻经历，无法匹配时不创建 `experience_id`。
- Resume Section Fallback 和 Stable Fallback 只创建具有独立动作、功能、技术、职责、证据或结果事实的项目。
- 正式结果禁止使用“其他经历、其他项目、综合经历、综合经历项目、未命名经历”等通用项目名称。
- 生成保存和 DOCX 渲染前执行最终有效性检查；标题空壳优先吸收到对应真实项目，无法恢复时移出正文并写入信息补充问题。
- 普通实体去重阈值保持不变，共享 RAG 或全栈技术栈的两个真实项目不会因此被合并。
- 有效性日志位于 `backend/logs/resume_experience_validity.jsonl`，只记录空壳数量、处理结果和来源 ID，不记录用户完整输入或简历正文。
# v0.7.3：版本身份、问题编号与质量退化发现

- `X-Request-ID` 作为唯一用户问题编号，串联生成 attempt、结果和 DOCX 文件，不创建第二套 Trace ID。
- 结果页和各类失败提示支持复制问题编号；请求未到达服务器时明确提示暂未生成编号。
- `scripts/list_recent_quality_incidents.py` 支持按问题编号或结果 ID 查询脱敏质量事件。
- `scripts/run_public_smoke_test.py` 提供不调用模型的 shallow 模式和显式调用模型、自动清理数据的 full 模式。
- `scripts/check_operational_slo.py` 汇总成功率、耗时、队列、Redis、Fallback、事实覆盖、DOCX、备份、磁盘、证书和模型成本。
- `VERSION`、构建 commit 与构建时间统一进入后端健康接口、启动日志、前端页脚和发布检查。
- 生产使用说明见 [生产可观测性](docs/production-observability.md) 和 [问题响应手册](docs/incident-response.md)。

本地提交后、发布前，为当前 commit 生成确定性回归记录（工作区不干净时脚本会拒绝记录）：

```bash
python scripts/run_release_quality_gate.py
```

服务器查看最近质量事件：

```bash
python scripts/list_recent_quality_incidents.py --hours 24
python scripts/list_recent_quality_incidents.py --request-id req_xxxxxxxxxxxxxxxx --hours 72
```
