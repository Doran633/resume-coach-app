# v0.9.19.2.1 Expression Task Consistency

## 2026-09-21 离线收尾结果

本节覆盖下方历史段落中的“待批准迁移”和“未再次调用API”状态，不删除历史证据。
当前基线main / 5957d5a，VERSION保持0.9.19.2.1；保留全部先前未提交实现及无关pytest产物删除。
本轮只修改测试和验收文档，未改业务源码、Prompt、配置、API或真实返回fixture，未调用API、部署、提交或推送。

### 已批准迁移明细

| 文件 | 本轮变化 | 保留内容 |
| --- | --- | --- |
| test_v091741_canonical_project_task_cleanup.py | 两份Canonical完整任务快照更新为当前字段清单 | legacy全文、项目协议哈希、输入/重试及事实断言 |
| test_v09192_evidence_bounded_expression.py | expression_sample四版本由空串改为本样本完整冻结Fact文本 | 项目候选、复核、来源、预算、拒绝和保存断言 |
| test_v09185_summary_evidence_consumption.py | control四版本补齐本样本Fact文本 | 原summary、输入及各阶段写入/拒绝断言 |
| test_v09191_presentation_evidence.py | 两处控制返回四版本补齐本样本Fact文本 | 原展示、Fact、限制、保存/DOCX断言 |
| test_v091911_type_relation_evidence.py | 控制返回四版本补齐本样本Fact文本 | 类型、表头、附件、保存/DOCX断言 |
| test_v091742_fact_placement_contract.py | Canonical重复版本明确断言异常code为MODEL_OUTPUT_CONTRACT_INVALID | 同一返回经独立legacy解析仍取后值；不改变真实返回 |

控制版本使用当前样本已有完整事实，只为使隔离其他功能的测试满足新结构契约，不代表四版本表达质量或语义复核已达标。
没有统一替换其他失败码，也没有修改项目正文/Claim/Fact/输入来取得通过。

### 实际运行

- 迁移前最近记录：1642通过、84失败；16快照、67空版本控制、1重复版本旧成功契约。
- 本轮首次全量：1725通过、1失败，1733 warnings，102.25秒。唯一失败是新断言误用消息regex检查异常code；改为检查异常.code，业务拒绝标准不变。
- 最终全量加隔离探针：1734通过，1766 warnings，100.59秒。仓库本身1726项，GodSu只读探针8项，分别计数。
- 专项/相关联合/黄金/DOCX独立运行：227通过，216 warnings，12.92秒。
- Python compileall通过，字节码隔离GodSu。全仓git diff --check退出0，但无关旧.pytest产物有Permission denied提示；对README、VERSION、backend/app、prompts、tests和docs限定检查退出0，无空白错误，仅LF/CRLF提示。不把不可读旧产物计为已检查。
- 数据库为sqlite内存，日志/测试临时文件隔离GodSu。网络外发禁用，仅控制模型网络返回；未Mock被验证业务。
- 对上轮repository-before哈希记录中的业务、模板、VERSION和fixture核对113项，无变化。

日志：GodSu/v09193-close-tests.txt、v09193-final-tests.txt、v09193-focused-tests.txt。
只读探针：GodSu/test_v09193_readonly_composition.py；检查现行协议字段拼接、原文限定及保存/DOCX，拒绝新格式和未受支持改写。不是新组合协议的联合验收。

### 真实证据与发布状态

八次真实调用报告：五次保存但全漏四版本，旧版本补写和summary独立职责问题可达。
随后的十次真实调用报告：四份写作版本完整，三次表达复核失败，一次保存；相同复核请求出现不同逐项判定。
缓存重放、三份候选改回原句的离线控制、真实调用分别统计，不能混称成功样本。
本轮离线迁移没有解决真实单Fact借用、资格丢失、复核概率性和薄履历表达改善，仍不建议部署。
v0.9.19.3只读设计见[v09193-implementation-brief.md](v09193-implementation-brief.md)，等待批准；未升VERSION或实施。

### 本轮回滚边界

只回退上述六个测试文件本轮差异及本节/README/版本历史/Brief文档即可撤销本轮工作；不得把整个工作区恢复HEAD以覆盖之前实现。
原始真实实验及失败日志保留。没有数据库迁移、生产状态或API行为变更。

## 四版本接收契约及补写调用退出（最新增量）

2026-09-20，经用户批准只补齐四版本返回契约及退出已确认的版本补写，不扩展个人优势、复核或项目表达权限。仍为未发布的0.9.19.2.1，保留工作区已有实现。

### 本轮之前的8次真实验收

五次生成均保存并导出，其中两次薄履历为同输入重复；另外三次调用为两次配套复核和一次独立正反对照复核。全部finish_reason=stop，但五份写作返回全部遗漏四版本字段。正常和两次薄履历全部回传项目原句，含限定和保留样本只进行了轻度改写。32处最终字段Fact/Claim关联核对通过，不能推导全局字段正确。

薄履历缓存返回沿真实链路重放确认：normalize_llm_payload补空字符串，Cleanup补占位，ensure_packaging_gain调用既有professionalize_text，在大胆/推荐版新增“问题定位与交付质量保障”。正式项目正文没有新增这些内容；个人优势另有模型原始返回“独立完成”且被保存的风险，本轮不修复。

真实验收证据在GodSu/v091921-task-acceptance8/report.md及原请求、返回、字段阶段记录。该授权8次已耗尽；下面的实施阶段真实API调用为0，没有生产数据库访问、部署或提交。

### 修改与权限

- prompt_service.py和普通/长输入模板：将四个必需版本列入实际JSON字段清单，明确非空字符串；保留既有表达范围，不添加包装规则。legacy模板标准化内容不变。
- generation_service.py：原始解析后、Fact组装及任何默认值补齐前检查normal_version/bold_version/boundary_version/recommended_version。缺失、空白、错误类型及重复字段记录脱敏field_reasons，复用既有两次总调用预算重试；耗尽使用MODEL_OUTPUT_CONTRACT_INVALID，不落入纯JSON降级成功。后续若只剩一次写作且仍需复核，依旧MODEL_EXPRESSION_REVIEW_BUDGET失败，不增加第三次调用。
- 正常Canonical模型成功路径退出ensure_packaging_gain调用，不再以版本短于80字符作为补写授权。未删除函数，mock、纯JSON降级和独立legacy兼容保留；这不表示这些旧兼容路径获得新表达证明。
- 未修改enhancement_guard_service或专业化服务，不在generation复制替代写作者。Fact/Claim、owner、项目协议、语义复核及Gate不变。非空字符串仅证明结构完整，不证明版本语义；个人优势与其他全局字段验证仍有边界。

### 离线证据和待批准迁移

先固化34项失败，再修改；34项转绿，补充真实受控复核保存及独立legacy对照后专项36项通过。专项/黄金/DOCX联合48项通过。测试仅替换网络返回，验证接收、既有业务、保存和导出；不删除历史真实返回或降低原来源断言。

第一次全量：1640通过、84失败、1617 warnings，42.71秒（GodSu/v091921-version-full.txt）。84项的旧契约冲突已报批、尚未修改：16项来自两份完整任务快照；67项的旧控制返回把四版本置空，用于隔离其他功能，现在先被新接收契约拒绝；1项要求Canonical重复normal_version取后值成功。申请仅迁移快照、给控制返回补齐有原文依据的版本、将Canonical重复字段改为拒绝且保留legacy解析对照。全部原项目/复核/Gate断言必须保留，迁移后还需重跑，不能将当前全量记录为通过。

### 残留与回滚

尚未做本次修改后的真实模型验收；四版本恢复完整生成后可能再次触发输出截断，重试耗尽复核预算仍是已知限制。薄履历表达改善、个人优势未支持的职责升级没有被本轮解决。不能凭这批控制返回或之前五次保存判定发布。

回滚本增量需共同撤销实际字段清单、接收校验和正常模型补写调用退出及配套测试；不恢复HEAD覆盖此前未提交工作，不改数据库。文档不包含部署命令。

## 任务一致性收敛（最新增量）

本节记录2026-09-20后续收敛；下方原实现及真实验收记录保留历史含义，不覆盖失败证据。
本次起点main / 5957d5a，工作区已有0.9.19.2.1未提交代码与测试，保留所有已有改动。
阅读GodSu/v091921-ten-probe/report.md、narrow-contract-audit.md、适用约束及既有harness。
本次真实API调用为0，没有生产数据库访问、部署、提交或推送。

### 失败依据与作用域

普通/长输入、首轮/来源错误重试四项网络边界测试均捕获竞争任务。
普通实际发送有职责拉高、核心模块贡献、页面扩成联调/状态流转、强制与原文不同、自然承接知识授权；
长输入实际发送有软事实包装、自然承接、无依据的弱履历能力展开和强制行动格式。
这证明任务不一致，不证明每次模型越界都仅由这些段落造成。

新增辅助表达保存测试最初因精确匹配末尾句号失败：实际保存保留“协助开展测试工作”及正确附件，
仅移除末尾句号。新测试据实接受该既有无损格式变化，没有修改业务正文或旧契约。

### 本次实际修改

- prompt_service.py：复用既有模板分支，增加成对legacy-expression标记；先处理该外层块，再处理已有legacy-project块。不按关键词删除任意文本，不新增模板引擎或事实解释服务。
- 普通/长输入模板：冲突段落明确保留在legacy分支，Canonical退出职责升级、动作补写、强制扩写、负面词一律隐藏及岗位清单自动补能力的任务；保留已有安全、格式、技能、个人优势和追问要求。
- Canonical使用一份字段任务说明：项目遵从原expression_scope；普通/大胆/推荐版本仅调整表达和重点；边界版本用于标注风险；面试知识不是事实授权。四版本仍为必需字符串字段，不清空、不合并、不改变API。
- 专项test_v091921_task_consistency.py：六份输入、普通/长输入、首轮/重试共24组实际发送对照；legacy、辅助表达保存、三类违规拒绝与不完整标记检查。

本次没有再次修改generation、experience_slot、复核模板、验证器或下游。它们相对HEAD的改动属于此前未提交实现，不能计为本轮额外改动。
VERSION保持0.9.19.2.1，不为同一未发布版本重复加号。

### 完整任务审阅与测试

已逐段审阅网络边界捕获的普通/长输入完整任务（证据和项目契约另有逐Fact不变检查）。
legacy标准化全文哈希仍通过；Canonical普通/长输入全文快照按设计变化，经用户明确批准，仅迁移两个已逐段审阅的任务哈希。legacy哈希、项目协议哈希、原输入、引用、事实与重试断言保持。
任务数据不裁剪，Fact文本、span、Claim来源及重试证据保持。原句、未知/跨owner/重复/缺失引用、复核映射、预算耗尽等沿用既有联合测试。
新增任务专项31项通过；专项及表达/黄金/DOCX联合117项通过。
迁移批准前全量1674通过、16失败、1707条warnings，53.58秒；16项均为既有普通/长输入全文快照哈希。该结果保留作为契约迁移依据，不描述为业务验证失败已被放宽。
批准后仅更新两处哈希，重新全量验证：1690通过、1707条warnings，44.40秒。日志为GodSu/v091921-task-approved.txt。
Python compileall与git diff --check通过（仅Git换行提示）；warnings主要来自现有datetime.utcnow弃用。
迁移前日志隔离于GodSu/v091921-task-final.txt，数据库使用sqlite内存，未调用真实API。
控制supported只证明接线，不证明真实复核准确；不能把有16项待审批失败写成全量通过。

### 残留与回滚

发布继续阻塞：本次未运行修改后真实模型验收，旧截断、错误引用、复核过严/写作越界风险没有被宣布关闭。
长输入既有多版本长度建议和面试输出负担未调整；两次调用内写作重试后无法再复核的问题未解决。
四版本都有实际消费者，且推荐文本与DOCX正文不同；四版本仍存在Guard/清理及短内容补齐，不自动继承项目逐Fact复核。
辅助→参与属于需明确的表达边界，不以单个样例提高通过率。若明确合法表达仍持续被拒绝，应报告能力限制，不继续堆规则。
仅回滚本次增量时，应共同回滚模板标记与prompt_service对应分支及任务测试；不能直接恢复HEAD而丢失此前工作区改动。
整个0.9.19.2.1回滚仍须按下文原协议/模板配套边界处理，无数据库迁移。

## 状态和基线

2026-09-20，main / 5957d5a / VERSION 0.9.19.2 起始。
读取适用 AGENTS.md、根 conftest.py、既有请求/保存/DOCX harness、v09192 brief 和 v091921 只读证据。
保留原有历史 pytest 产物删除，不自动暂存、提交、推送、部署，不连接生产数据库。
本轮实现限定范围内的契约调整；版本号表示工作树代码版本，不表示真实发布验收已通过。
**真实发布验收仍阻塞，不建议发布。**

## 历史、新实验与控制返回

历史 req_5df27fa883034b9b95b9afa1b68139e9 只有脱敏计数，缺少原始候选，不能完整重放。
先前获授权的五次调用是独立的新实验，其额度已耗尽；本轮另获四次授权，不重置旧计数。
两个阶段都保留完整输入、原始写作/复核返回；测试中回放这些返回仍不等于历史生产请求快照。

## 修改前后的证据流

此前：写作者读取完整冻结证据，复核器只有单 Fact 和所有 noneligible Claim；结构标题也进入限制。
表达范围在两个位置分别维护；复核只返回 verdict 字符串，拒绝日志仅有数量。

现在：同一个 `_expression_scope` 用于写作契约与复核；`_owner_expression_claims` 只按已有角色
区分结构与限制，不重新分类、不改变资格。写作者完整保留两组证据，复核器读取同一 owner 的
限制、冻结表头和来源 Claim 上下文。上下文仅用于理解，不增加当前 Fact 的支持范围。

独立否定可以不展示，但不得反向写为成果。肯定事实中的职责、团队归属、数量、状态及限制
必须等义保留；不是要求保留同一个词。允许充分句式调整和已有工作的说明性展开，不能新增
具体步骤、技术、效果、责任等级或熟练程度。工作目的不能冒充已经实现的效果。

## 内部协议

项目协议仍为 `canonical_fact_expressions_v1`，owner/Fact集合、位置、正文及附件派生均未改。
仅复核升级为 `canonical_expression_review_v2`，由服务器选择模板，不由模型自报可信状态。

```json
{"decisions":{"EXP-001-F006":{"verdict":"changed_qualification","source_excerpt":"只用于","candidate_excerpt":"用于"}}}
```

- supported：两个片段均 null。
- added_claim：候选片段必填，来源片段 null。
- omitted_fact：来源片段必填，候选片段 null。
- changed_qualification：两个片段必填。
- uncertain：至少一个片段必填，保持明确无法判断出口。

片段必须在对应当前 Fact 文本或候选文本中精确且唯一出现；不存在、重复歧义、空白、错类型、
额外字段、缺项或重复 JSON key 均拒绝。不能从其他 Fact、背景或限制列表借片段。
后端产生范围，不要求模型手数中文字符。范围是 Fact/candidate 字符串的局部半开区间，
**不是原始输入全局位置**，不以归一化后的局部偏移冒充原文偏移。
原 Fact 的 source_span 和 Claim 来源仍原样保留。

定位仅是审查依据，不证明语义正确；supported 仍是概率性判断。不能因片段合法放行任意改写。
新评估开始时清空旧接受结果；任何新评估失败都不能沿用先前的受信任状态。
验证签名包含复核协议版本，同请求 Build、Fact/Claim、候选及限制绑定仍保持。

## 调用与权限

| 位置 | 本轮修改 | 保留边界 |
| --- | --- | --- |
| prompt_service | 共享表达范围；冻结证据分组；复核上下文只读访问 | 不编译新语义、不裁剪 Fact、不跨 owner |
| experience_slot_service / CanonicalExpressionReview.accept | 严格对象映射与片段定位；请求级结果失效 | 不推断正文真假、不提供替代文字、不改 Binder 归属算法 |
| generation_service | 既有复核日志加入协议和问题范围；重试清理定位结果 | 不增加调用、重试、恢复或降级，不改 Gate |
| 既有复核模板 | 使用共享表达范围和定位格式 | 不写正文、不生成新事实、不担任第二写作者 |

复核日志复用 `llm_calls.jsonl`，包含 request/attempt、review_protocol、review_issues 中的
Fact/owner ID、判定类别及局部位置；不保存问题片段、候选正文或密钥。
格式无效仍用 MODEL_EXPRESSION_REVIEW_INVALID，明确否决用 MODEL_EXPRESSION_REJECTED，
无法判断用 MODEL_EXPRESSION_REVIEW_UNCERTAIN。调用预算和其他失败分类不变。

独立 legacy 和其他字段生成保持；未恢复旧项目模板前缀和 SOFT_DERIVATIONS 写入。
最终正文变化仍使验证失效；不得后置回填原句伪装包装成功。

## 离线验证

新增专项先红：8失败/7通过，确认结构限制混杂、旧判定和定位缺口。
批准迁移前三类旧契约后保留输入、来源和拒绝语义：
1. 19项证据测试检查结构和限制两组并集精确完整，不丢 owner/span/eligibility。
2. 16项重新审阅完整 Canonical任务并固定哈希；legacy 哈希不变。
3. 18项旧复核用例改为判定对象，保留责任扩大、限定丢失、未保存、预算和附件断言。

专项覆盖精确范围、脱敏日志、非法或歧义片段、旧字符串拒绝、重复key、已接受结果失效、
正常/长输入、重试冻结证据不变及 intro/role/detail 的来源一致性。
真实业务处理至保存/DOCX，只有网络返回受控。控制 supported 只证明接线，不证明模型复核准确。
两份本轮真实失败返回也固定为回归，不通过更改预期把它们改成成功。

最终全量 **1659通过，46.06秒**；专项 **29通过**；包含专项的黄金/DOCX联合集 **41通过**。
Python编译和git diff --check通过。初次全量1592通过/53失败；三类迁移后、新增两项实际返回
回归前全量1657通过。1684条测试警告为既有 datetime.utcnow 弃用，不等于交付失败。

## 本轮四次真实调用

本地配置 api.deepseek.com / deepseek-v4-flash，返回 deepseek-flash，temperature 0.4，max_tokens 4096，
thinking disabled。新独立目录和持久预登记计数，失败/重试均累计。SQLite内存、日志与DOCX隔离。

| 调用 | 场景 | finish_reason | 输入/输出 token | 网络耗时 | 结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | 课程问答/设备登记，写作 | length | 7907/4096 | 16625 ms | 截断，未进入修复成功路径 |
| 2 | 同份证据写作重试 | stop | 7907/3751 | 15422 ms | 引用不存在的 EXP-002-F003，拒绝，无剩余复核额度 |
| 3 | 薄课程网站，写作 | stop | 6996/2984 | 12437 ms | 进入语义复核 |
| 4 | 薄课程网站，复核 | stop | 1750/97 | 1109 ms | 新格式有效，2处拒绝，未保存 |

总24560输入/10928输出token。实际账单未取得，不将配置估算为0解释成免费。
两次生成均未保存或导出，未完成真实成功闭环。四次额度用完，没有第五次调用。

复杂样本最终代码为 MODEL_OUTPUT_TRUNCATED：现有耗尽出口优先保留先前 completion_error；
第二轮非法引用可在阶段日志看到。这一旧错误优先级未在本补丁扩改，不能只看最终码忽略第二轮。
复杂样本没有进入复核，不能用它评价新复核格式的准确率。

薄样本的实际定位：
- `我做了页面` -> `负责网站页面的开发与实现。`：added_claim。
- `我帮忙测试` -> `参与项目功能测试工作。`：changed_qualification。

前者可能涉及责任含义如何解释，后者至少存在合理表达误拒疑点；“功能测试”细化是否受支持也需
单独判断。模型只给出类别和片段，没有足够证据将所有表达问题都归因于用户或写作者。
本补丁改善了可核查性，但没有证明复核能稳定接受合理包装。没有加入样例白名单或临时放宽检查。

## 发布阻塞、残留与回滚

**代码和离线契约调整不等于发布验收通过。** 当前缺少最终模板下正常、单薄、含限定及保留样本
的真实成功闭环，也未完成新协议下的重复复核稳定性评估；不得用先前旧协议重测代替。
输出额度风险、writer非法引用和reviewer可能过严分别登记，不能通过本补丁无限扩大权限解决。
跨Fact融合、个人优势、技能、排序、篇幅、模型选择或调用额度不在本版。

回滚应将三个业务文件、复核模板和相应测试/文档一起回滚到5957d5a，不混用新模板与旧解析器。
无数据库迁移，不重写历史结果；请求级验证结果不持久化。版本分支未自动提交或部署。
发布必须另经真实验收结论确认；部署命令不写入本文。

## 实际文件

业务：backend/app/services/{prompt_service,experience_slot_service,generation_service}.py。
模板：prompts/review_canonical_expressions.md。
新增：tests/test_v091921_expression_scope.py；tests/fixtures/v091921_real_expression_returns.json；
tests/fixtures/v091921_acceptance_returns.json。
批准迁移：tests/test_v0916_canonical_model_evidence.py、tests/test_v091741_canonical_project_task_cleanup.py、
tests/test_v09185_summary_evidence_consumption.py、tests/test_v09192_evidence_bounded_expression.py。
文档：README.md、VERSION、docs/version-history.md、本文。

隔离实验和脱敏前的本地原始返回：GodSu/v091921-real-acceptance；任务全文审阅：GodSu/v091921-task-review。
这些是获授权的虚构/用户提供测试输入，不是生产数据库内容。
