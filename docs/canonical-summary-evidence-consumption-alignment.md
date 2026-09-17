# v0.9.18.5 Canonical Summary Evidence Consumption Alignment

## 基线与证据性质

- 开始基线：main / 4831164 / VERSION 0.9.18.4。
- 工作区已有多批 `.pytest-*` 跟踪产物删除记录；未恢复、清理、提交或计为本轮改动。
- 读取适用 AGENTS，复用 v09162、v09172、v09174、v09176 的控制返回、真实 Build、内存 SQLite、保存及 DOCX harness；只替换网络，业务观察包装仍执行原函数。
- 复用 `tests/fixtures/v091811_normal_inputs.json` 三份完整普通用户输入。v197/v198/v199 缺少精确关联的历史请求参数、原始模型返回与保存快照，不能把当前实验解释为历史三份输出的完整根因。
- 未调用付费模型，未连接生产数据库，未部署或自动提交推送。临时诊断与日志隔离 runner 位于 GodSu 下 `diagnostics-v09185`，不是新运行时模块。

## 实际 summary 链路

| 边界 / 文件与函数 | 输入及权限 | 当前证据与本版处理 |
| --- | --- | --- |
| prompt_service._canonical_evidence_context / build_generation_prompt | 同请求 Views、完整 Fact/Claim、限制及已确认非经历范围，正常/长输入/重试 | 实际网络发送断言逐个核对原文、ID、范围与背景；没有发现本组材料缺失，不新增接线或摘要 |
| generation.build_llm_generation / normalize_llm_payload | 模型生成 summary 字符串列表；项目另用 Fact 位置协议 | 保留现有模型生成和规范化，项目验证不代表 summary 已获语义证明 |
| normalize_resume_section_schema / cleanup_generation_payload | 结构、空白、标签处理，已有精确相同 summary 去重 | 本组实验只观察，未发现截断或能力提升；不扩大修改 |
| fact_guard_service.guard_hard_facts | 全文 raw_input 得到 company/award/online 等布尔标志，原先改写 summary | 已复现跨 owner 奖项降级；Canonical summary 退出该替换，其他字段与 legacy 保留 |
| resume_section_fallback_service.fill_resume_sections | 现有 Canonical/legacy 分支 | Canonical 已不调用 `_build_summary`，空 summary 不会在这里补造；无修改 |
| resume_body_sanitizer_service.sanitize_resume_body | semantic_safe 分支仍对 summary 应用 NEGATIVE_DROP_PATTERNS | 已复现删掉“没有上线/不太熟”；只让 Canonical summary 保留限制，项目与其他字段不变 |
| resume_output_firewall_service.guard_resume_output → input_content_classification_service.strip_non_fact_fragments | generation 中三次 Firewall 调用，原先再次删除 UNCERTAINTY_PATTERNS | 第一处修复后再次失真；仅 Canonical summary 不运行限制删除，指令/目标/模板清理保留 |
| professionalize_resume_language / ensure_recruiter_facing_technical_language → ensure_recruiter_language | 既有全局文本匹配条件下的表达转换 | 本组合法对照未触发实质变更；匹配条件不是任意概括的证明，未启用新规则或关闭整个消费者 |
| paired symbols / section integrity / whitespace / typography | 符号、标记和格式整理 | 保留既有行为，逐阶段比较实质内容 |
| validate_resume_delivery_quality → route_quality_repairs → final Gate | 只读验证、现有窄项目去重、最终成功出口 | 没有新增 summary 修复权限；critical 仍拒绝成功保存和导出 |
| immutable revision → GenerationResult.result_json → DOCX | 正式交付字段的同一结果 | 合法对照核对保存 summary 与 DOCX 文本，不再加工历史结果 |

`resume_summary_quality_service.ensure_resume_summary_quality` 不在正常 Canonical 主链直接调用，旧可写 Gate 的空 summary 恢复分支仍可使用它。其“负责”等关键词触发独立推进概括、raw_input 重建及相似度筛选没有被本版激活，也没有被当作现成可信权威。

## 修改前后的具体证据

1. 新控制输入包含 A“团队获得三等奖”、B“没有获奖”，受控 summary 为“团队获得三等奖，承担调查结果整理工作。”。修改前 `guard_hard_facts` 首次变为“团队获得竞赛参与，承担调查结果整理工作。”；交换 owner 顺序也复现。修改后各观察阶段保持原奖项和团队归属。
2. “使用Python整理日志，工具没有上线，仅在本地运行。”原先经 sanitizer 成为“使用Python整理日志，工具，仅在本地运行”。首次窄修复后，又在 Firewall 同样失真；补齐实际重复写入点后完整限定保留。
3. “接触过Python，对异步编程不太熟。”原先成为“接触过Python，对异步编程”。修改后两处清理都保留熟练程度限定。
4. 模板污染对照“summary: 使用Python整理日志，工具没有上线。希望包装得更专业。”最终清理为“使用Python整理日志，工具没有上线”。不是全面关闭清理，也不是将求职指令保留为事实。
5. 三份正常输入的控制返回摘要分别表达前端参与、后端职责及团队获奖、科研整理及接触过 PyTorch。修复前后保存的整个 resume_sections 相同，项目正文及 Fact/Claim 附件没有因本版变化。
6. 未参与两处分支实现调试的保留输入是借阅记录检查工具、18条验证记录及“了解SQL”，合法概括保存与 DOCX 通过。

阶段观察记录在隔离测试输出中，包含 before/after。它们是本地受控实验数据，不是新增生产日志；本版没有向生产日志增加正文或限制原词。

## 最小修改及权限

- `fact_guard_service.py`：仅 Canonical summary 跳过全文布尔事实替换，不修改教育、技能、项目、其他输出及 legacy。
- `resume_body_sanitizer_service.py`：既有文本/列表清理透传可选 `preserve_limits`，仅 semantic_safe 的 summary 开启。格式整理、项目与 legacy 保持原调用。
- `input_content_classification_service.py`：`strip_non_fact_fragments` 可选保留限制，默认不变；`classify_input_content` 及其他既有调用仍用旧默认，不改变上游资格或冻结内容。
- `resume_output_firewall_service.py`：新增可选 `canonical_mode`，仅 summary 消费保留限制选项，不改变其他字段的清理。
- `generation_service.py`：三处既有 Firewall 调用传入该标志；调用次数、模型入口及最终 Gate 不变。

以上范围外文件的窄修改经用户两次批准。没有新增候选系统、后端概括、状态真源、Prompt 措辞、模型调用、来源结构或公开 schema。

## 验证

- 先固化失败：新专项在修正其“空 role 附件空键必须存在”的不当假设后，7失败、11通过；失败均指向批准的 summary 替换/限制删除。
- 首次两个分支改完后16通过、2失败，证明 Firewall 重复删除仍可达；没有把最终失败断言改成通过，而是报告并取得第二次最小接线批准。
- 最终专项22项通过；正常/长输入及截断后重试检查实际完整发送证据，禁止 Prompt 阶段重建和调用旧 Summary 候选器。
- 三份普通输入和保留样本走真实接收、整理、最终 Gate、保存及 DOCX。空 summary 和明确限制冲突仍失败、不保存成功结果、不导出。
- 运行中 Build/Views 检查：现有 shadow projection 在模型调用前写入 experience_input_id，会改变状态来源元数据与 fingerprint；冻结经历、Claim、Fact、资格及决定不变。从模型消费入口开始 Build/Views 完整保持不变。没有为此改动构建链路。
- 全量第一次运行遇到一项旧测试写仓库日志目录的 PermissionError；使用临时 pytest fixture 重定向既有日志路径后重跑，不改旧测试预期或业务日志实现。
- 相关联合176项通过；全量1528项通过；黄金/DOCX三个测试文件独立重跑12项通过；Python编译215个文件通过。本轮跟踪文件范围 `git diff --check` 通过；两个新增文件用 no-index 检查无空白错误（新增差异退出码1，另有既有CRLF转换提示）。未扫描或清理无关旧测试产物。
- 未进行真实模型验收，不以控制返回通过证明任意模型概括正确。

## 残留与风险

1. **模型原始夸大仍存在验证缺口。** 控制返回直接给出“独立主导企业整体技术架构。”，普通前端输入没有该依据；当前链路可保存，仅出现既有 INCOMPLETE_SENTENCE warning。失真在受控模型返回已经存在，本版未新增语义验证器或偷偷更换生成协议，不能声称已解决。
2. **能力匹配不是语义证明。** 个人优势仍为字符串列表，没有本版新增的逐条来源合同。旧专业化及招聘语言消费者的 `supports_global_text` 使用词面匹配；本组对照没有证明所有表达转换安全。
3. **保留限制不代表所有样例能交付。** 部分新控制输入仍触发原有 EXPLICIT_BOUNDARY_LOST / ELIGIBLE_FACT_UNPROJECTED 等问题，最早变化及 Gate 结果保留在 trace 中；本版不修改经历内容、边界或 Gate。不得以个人优势修正替代整份简历验收。
4. **生成措辞仍有限制。** 现有模板有 summary 去负面化要求，与完整限制表达的产品取舍需另行审阅；本版按约束未改写作要求，也未通过反复强化提示来解决清理问题。
5. 长摘要、经历复述、合理抽象范围、技能分类、排序与篇幅仍独立保留；未启用新的能力提升规则。v197/v198/v199 的历史表达成因仍缺少原始模型返回证据。

## 兼容与回滚

旧参数默认保留 legacy 行为；Canonical 是停止无依据改写，不是给未验证 summary 授予可信状态。现有有限否定检查与最终拒绝出口不变。保留的限制可能暴露既有 Gate 问题，不能承诺成功率不下降；真实模型与保留样本仍需单独验收。

回滚以本版五个业务文件、专项及版本文档为一组，不涉及数据库迁移、历史结果、DOCX renderer 或模型协议。回滚会恢复本次已确认的个人优势失真，应先明确影响；不清理用户已有工作区改动。
