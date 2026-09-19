# v0.9.19.2 Canonical Evidence-Bounded Expression

## 当前状态

实现已完成，真实模型完整验收仍有限制。基线 main / 7bd1cc6 / 0.9.19.1.1。
保留既有工作区改动及历史 pytest 产物；不提交、不部署、不连接生产数据库。
旧契约迁移已获批准；真实样本外发已获授权，本轮累计3次调用已用完。
VERSION 已更新为0.9.19.2；离线通过不能替代最终模板的真实写作/复核/保存验收。

## 证据与区别

复用 GodSu/v09192-implementation-brief.md、v09192-brief-evidence/results.json，
以及完整 Java 实习、课程网站薄履历、设备登记系统限定对照。
它们是固定输入和网络控制返回，不是 v200-v204 的历史原始模型快照。

旧链路拒绝合理改写与职责扩大时均使用字面支持判断；拒绝本身不证明识别了语义差异。
薄履历的冻结 Fact“我帮忙测试”却可经后置专业化增加“问题定位、交付质量保障”，
附件保持不变并保存。这证明接收和后置写入采用不同的授权标准。

新控制链路将该 Fact 表达为“参与测试工作”，独立复核返回 supported 后，
接收、Binder、模板清理、专业化、最终检查、保存和 DOCX 保留相同正文与来源。
字面回传“我做了页面”不再被模板前缀规则改为“完成页面”。
限定对照“只负责”改为“仅负责”可通过受控复核；职责扩大、事实遗漏和限定变化的
拒绝控制均不保存成功结果。模拟 supported 仅证明接线，不证明真实复核器可靠。

## 单一写入与验证责任

| 位置 | 权限及边界 |
| --- | --- |
| prompt_service.build_generation_prompt | 读取同请求冻结证据，要求单 Fact 候选表达；不重新构建语义 |
| 模型写作调用 | 唯一新增项目表达入口；不改 Fact、owner、表头、资格，不跨 Fact 融合 |
| experience_slot.compose_model_fact_references | 精确校验 owner、Fact 集合、重复键及 position/text；派生附件，按冻结顺序组装 |
| 独立批量复核 | 仅返回逐候选 verdict；不提供替代正文，不参与冻结，不授予新事实资格 |
| CanonicalExpressionReview | 现有 slot 服务内的请求级验证结果；绑定 Build 对象、指纹、Fact/Claim、限定和候选，不持久化 |
| validate_model_project_evidence / Binder | 复用同一支持入口和请求级结果；ID 合法不能代替正文支持 |
| guard_template_language | 新项目表达路径退出前缀改写及通用正文删除；其他污染检查仍由原链执行，legacy 保留 |
| professionalize_resume_language | 新项目正文退出固定专业化及 SOFT_DERIVATIONS；非项目字段不获得本版复核结论 |
| 最终 Gate 前及 Router 后 | 再核对实际待交付正文与已接受表达、字段来源及完整 Fact 集合；变化导致明确失败，不恢复正文 |
| Gate / Revision / DOCX | 沿用原权限；Gate 只读，保存仍要求通过现有质量检查，renderer 不参与改写 |

未新增业务服务、语义 IR 或持久化真源。既有下游整理没有获得新的表达权限；
其他正文写入若导致来源验证失效，会被拒绝，而不是自动重新复核或补回。

## 内部协议

Canonical 主链明确使用 canonical_fact_expressions_v1。项目仅有
source_experience_id 和 fact_placements。映射的每个 Fact 键对应：

```json
{"position":"detail","text":"对应单个 Fact 的候选正文"}
```

position 只允许 intro、role、detail；两个前置位置可不分配 Fact。
每个 owner 最多一个项目，Fact 键集合必须精确等于该 owner 的全部 eligible Fact。
详情一 Fact 一行；intro/role 多 Fact 只按冻结顺序连接，不作综合推断。
不返回表头、Claim、聚合附件或可信标记；旧字符串位置成功入口退出。
JSON 重复键在普通解码覆盖之前保留并拒绝。独立 legacy 解析契约不变。

原句及既有无损格式变化仍由 provenance_text_unchanged 判定，未放宽比较函数。
其他候选批量发送到独立 review_canonical_expressions.md；每项仅包含该 Fact、
候选及本 owner 的现有限制，不向复核器提供其他 Fact 作为补写依据。
复核要求 decisions 的键集合精确等于待复核候选，值为 supported、added_claim、
omitted_fact、changed_qualification 或 uncertain。复核 JSON 不修复；额外字段、
替代正文、重复键、未知值、漏项和多余 ID 明确失败。

## 调用与失败

总调用预算最多两次，写作、重试、复核、超时和失败都计入。
全部原句时只需一次写作；通常一次写作加一次复核。
格式重试后仍有非字面候选，没有复核预算则失败，不追加第三次请求。
每次写作前清空上一轮验证结果，不跨响应拼接。成功统计累计实际调用的 token、
供应商报告成本及调用耗时；未知失败调用成本不能当作已知实际零费用。

| 内部失败码 | 含义 |
| --- | --- |
| MODEL_EVIDENCE_* | 项目结构、引用、owner、lineage 等原来源契约失败 |
| MODEL_EXPRESSION_REVIEW_BUDGET | 无剩余调用预算复核非字面候选 |
| MODEL_EXPRESSION_REVIEW_INVALID | 复核映射/JSON 不合法，或复核后的输出不符合 schema |
| MODEL_EXPRESSION_REJECTED | 复核认定新增、遗漏或限定/职责变化 |
| MODEL_EXPRESSION_REVIEW_UNCERTAIN | 复核明确无法判断 |
| MODEL_EXPRESSION_REVIEW_FAILED | 复核调用超时或其他客户端错误 |
| MODEL_OUTPUT_TRUNCATED / MODEL_FINISH_INVALID | 写作或复核结束状态不正常 |
| DELIVERY_EXPRESSION_CHANGED | 待交付项目正文/附件不再满足已接受表达的来源检查 |

复核失败不静默换回原句、不通过 Fallback 伪造表达成功。
原纯 JSON 解析降级路径单独保留，仍经过现有 Gate，不计为新表达协议成功。
日志仅记录阶段、请求/attempt、数量、固定原因及调用元数据，不记录候选原文、
限制原词或密钥。独立复核为概率性风险评估，不是冻结事实证明。

## 验证进展

- 新专项：45 项通过，网络受控，包含真实保存和 DOCX。
- 黄金/DOCX及模板、专业化 legacy 对照：22 项通过。
- 首轮全量：1423 通过、197 失败；测试返回仍大量使用旧协议。
- 经批准迁移共用及调用端返回格式后：1603 通过、25 项失败。
- 五类契约迁移另获批准：旧删前缀预期、字段说明、任务指纹、日志阶段与协议名、
  旧真实截断返回伪设 stop 的成功预期。保留 length 拒绝及新协议正常保存对照。
- 五类迁移后全量1630项通过；最终写作目标文字及版本对齐后再次运行，全量仍1630项通过（45.24秒）。
- 覆盖正常/长输入、同份证据重试、单薄样本、保留限定、不同 owner 同文、六项目、
  九详情、复核格式错误、预算耗尽、超时、跨请求验证结果隔离及最终正文变化拒绝。
- Python compileall覆盖backend/app与tests通过；最终版本修改范围内git diff --check通过。

## 真实模型验收

供应商api.deepseek.com，请求模型deepseek-v4-flash；temperature=0.4，max_tokens=4096，
沿用本地配置、不调整持久配置或输出额度。数据仅为获授权测试样本，SQLite内存数据库，
日志/输出隔离于GodSu/v09192-real-acceptance。call-reservations.jsonl在发出请求前持久化预约，
跨进程累计，不因超时或重跑清零。本轮共3次，全部正常stop，无截断。

| 调用 | 实验 | 结果 | 输入/输出token | 耗时 |
| --- | --- | --- | --- | --- |
| 1 | 薄履历真实写作及实际保存/DOCX | 3/3 Fact原句回传，字面校验通过，未调用复核；1次即保存 | 6855 / 2170 | 9781ms |
| 2 | Java合理改写、限定丢失、职责扩大的独立真实复核 | supported、changed_qualification、added_claim，映射完整；整批按已有契约拒绝，不写替代正文 | 814 / 34 | 870ms |
| 3 | 明确主动改善口语目标后的同薄履历真实写作 | 三条均改变表面表达；“我做了页面”变为“负责页面开发”，“我帮忙测试”变为“参与测试工作”；仅剩1次授权预算，MODEL_EXPRESSION_REVIEW_BUDGET，不保存 | 6878 / 2351 | 10312ms |

第一轮原句回传暴露了“允许改写”不足以验证包装效果，因此仅明确既有写作目标：
对明显口语主动改善，不把逐字回传作为默认；原文清楚或缺乏依据时仍允许不改写。
没有新增示例事实、放宽复核或强制每条扩写；正常/长输入的任务指纹相应复核更新。

三次合计14547输入token、4555输出token；本地价格配置给出的估算为0，不能解释为免费，
实际账单费用未取得。本轮未重试，无重复键/遗漏等协议错误；合理改写复核1例未误拒，
职责扩大1例与限定丢失1例被拒绝，仅是这组样本结果，不是误报/漏报率的统计保证。
最终模板的真实写作加真实复核再保存未完成；正常长输入、重复采样和更多改写领域也未完成。
第三次候选没有偷偷换回原文；没有发出第四次请求。所有候选原文、模型原始返回和中间结果
保留在隔离目录，不发布到生产日志或当作历史请求快照。

## 修改文件与兼容

业务仅修改generation_service.py、prompt_service.py、experience_slot_service.py、
resume_template_language_guard_service.py、resume_language_professionalization_service.py。
新增独立复核模板review_canonical_expressions.md。正常/长输入模板文件无需修改，
使用既有占位接线；独立legacy模板指纹仍保持不变。测试使用已有真实网络边界控制工具，
新专项test_v09192_evidence_bounded_expression.py与旧协议测试迁移共同验证。
版本及说明修改README、VERSION、version-history及本文，不包含部署命令。

## 风险、残留与回滚边界

合理表达可能被复核误拒，职责扩大可能被复核漏放；单一模型的两次独立调用不是
统计独立的专家证明。长输入的复核成本、输出截断、失败率与延迟需要真实样本验收。
薄履历不强制扩写；同时不能仅凭全原句回传就宣称包装改善。
个人优势、技能、推荐版本、跨 Fact 综合、排序和篇幅分配不在本版。

回滚应作为同一内部协议整体回滚：请求准备、接收与验证结果接线、两处项目改写退出、
独立复核模板及对应测试/版本文档一并还原。无数据库迁移，不回写历史结果；
不能只回滚接收器而保留新版任务，也不能仅恢复后置包装绕过新正文检查。
