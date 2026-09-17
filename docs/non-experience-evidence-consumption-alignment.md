# v0.9.18.3 Non-Experience Evidence Consumption Alignment

## 基线与边界

- main / 807425d731b460959966795c13cb8ff1c5c8395f / 0.9.18.2。
- 开始时业务、测试及版本文档范围无未提交变更。保留仓库既有历史测试产物及其权限状态，不清理、不回滚。
- 适用约束为 C:/Users/lbc/AGENTS.md；复用 v09162 真实接收/内存数据库/DOCX harness，v09174 隔离 fixture、v091811 完整来源断言及 v0916 实际发送证据检查。
- 本轮仅求职目标、教育和技能消费。没有修改经历分区、owner、type、名称/时间/Header、Claim/Fact、eligibility、模型协议、Prompt、Gate/Router、DOCX、前端或公开 schema。
- 未调用付费模型、未连接生产数据库、未部署、未提交推送。测试网络使用控制返回，数据库与日志隔离在临时目录。

## 证据分层

历史 v191/v192/v193 只能证明展示症状；缺少其准确请求参数和原始模型返回，不能认定 v191 的后端方向就是模型擅改。

当前 InputPage 的目标来自 lastRequest、localStorage 或默认值，并把表单值写进请求。API 没有“主动选择/恢复/默认”标识，本轮不猜测用户操作、不改前端。

当前完整输入控制实验先固化四项失败：三份结果保留了模型错误目标，预计毕业未落入教育；技能分类丢弃限定和未知工具。修正聚合/Guard/分类后，逐阶段记录确认 relevance 又重新提取词表，丢失 HTML/CSS/Postman/Element Plus/Supabase，将 Spring Boot 缩短为 Spring，删除“接触过”等限定。此处获用户批准最小接线调整；不是后置恢复。

| 阶段 | 旧行为/失真 | 本轮行为 |
| --- | --- | --- |
| 同请求 Build/Views | 已有确认背景范围，但技能聚合仅读 Ledger | 抽取既有只读范围访问方法，校验请求 hash、原文位置、无 owner 重叠；不重新分区 |
| 模型准备 | 已传背景文本 | 不改模板；正常/长输入与重试仍消费同份冻结证据 |
| normalize 后 | 模型 target_role 可进入 payload | 写入本次请求目标；明确文本意向不同则中立追问，不合成第三种方向 |
| Hard Fact Guard 教育 | 全文词汇存在性辅助接受/替换模型字段 | 只读已确认背景原文，独立核对学校、专业、学历和时间，忽略无来源模型值 |
| 技能聚合 | 背景技能不进 Ledger，未进入技能证据 | 合并既有经历证据与明确声明，使用现有 AggregatedSkillEvidence 的最小来源扩展 |
| Skill Guard | 再从模型技能行找词，容易缩短/丢限定 | 从同份证据投射完整名称和限定，不补用户未提供的掌握程度 |
| Taxonomy | 再词表提取、去熟练程度前缀 | 仅使用 term 归类，原声明无损展示，未知工具使用现有“其他工具” |
| Output Relevance 两处 | 再次词表提取 | Canonical 停止重新提取；仍执行既有 Token 歧义判断 |
| Gate/Revision/保存/DOCX | 既有交付闭环 | 不变；控制实验走真实检查、保存和导出，同份持久结果不被 Renderer 回写 |

## 具体权限与来源

### 求职目标

generation 在最终检查前确定性应用 request.target_role。项目技术栈、个人优势和模型方向没有覆盖权。背景中明确求职句与请求文本不同会产生核对问题；它是保守的文本差异提示，不声称能证明两个职位名称语义冲突。没有自我介绍也可直接用请求目标。

### 教育

fact_guard_service 的现有教育职责消费确认背景片段，字段候选均带精确原文位置。支持明确就读/字段命名结构、专业学历陈述、预计毕业及明确就读范围；不补入学年份，“大三”不推成本科。计划申请、合作学校或经历日期不能作为教育来源。公共结构只支持一条学历，检测到冲突字段时整条保持待填写并追问，避免拼接不同对象。

这不是通用教育解析器，也没有增加多学历展示能力。当前字段匹配支持范围外的自由表达可能仍待填写；必须有准确原文后才能进一步判断。

### 技能

既有 AggregatedSkillEvidence 增加 declarations 列表，包含 source_kind、source_span、term_span、display_text、qualified。背景证据没有虚构 owner、Fact 或 Claim；经历证据仍指向原 Ledger Fact。

局部明确使用/熟悉/了解/接触声明保留原谓词和限定。逗号列举与紧接的“仅用于课程练习”保留作用范围；独立肯定与否定不整句互相覆盖。条件、计划学习、岗位要求和建议不产生已具备技能。已知技能的负向限定保留在原声明及核对问题中，而不是选最高熟练程度。

明确使用关系可保留未收录的拉丁工具实体，分类不以词表删除；中文技能实体仍受现有词表支持范围限制，不宣称任意技能均能识别。既有 Python 生态推断没有扩展，新代码未根据目标岗位补技能。

Canonical 技能入口缺失聚合证据时明确报错，不重新构建语义；不传 Canonical 参数的独立 legacy 调用保持原行为。Token 仍沿用现有解析结果与阈值，模糊项产生原追问，未关闭安全检查。

## 修改文件与调用者

业务文件仅七个：generation_service、canonical_consumer_view_service、fact_guard_service、resume_skill_evidence_aggregation_service、resume_skill_evidence_guard_service、resume_skill_taxonomy_service、获批的 resume_output_relevance_service。

generation 在一次 Build 后取确认背景并聚合技能，再创建 Views；现有 Guard/Taxonomy 和两处 Relevance 调用透传同份证据。没有新增服务、持久配置或第二套来源真源。Views 的背景访问与 generation 调用共用原校验，不复制分区逻辑。

测试新增 tests/test_v09183_non_experience_evidence.py；未修改既有测试预期。README、VERSION、version-history 与本阶段说明记录版本，不写部署指令。

## 验证记录

- 专项 56 项通过：三份完整前端/Java/科研输入，实际保存/DOCX，目标相同/冲突/无背景、伪造模型教育、技能限制与冲突、未收录名称、子串、独立标题、格式变体、精确原文范围、跨请求拒绝、正常/长输入和纠正后重试。
- 保留样本为虚构信息管理学生的阅读记录分析：预计2028年毕业、接触过 Metabase、Excel 基础汇总；实现之后首次执行，保存和 DOCX 通过，未据此修改业务逻辑。
- 测试逐阶段检查项目具体正文与 Fact/Claim 附件，不只比项目数；Build/Views 不变、重试证据相同，背景不建立 owner。
- 最终全量 pytest：1450 passed，44.17s；专项 56 项包含在全量内。黄金与 DOCX 单独复跑 15 passed，1.41s。
- Python 编译：backend/tests 共 213 个 Python 文件使用 compile 在内存中检查，无字节码写入。git diff --check 对本轮业务/测试/文档范围通过，新文件另行检查尾随空白通过。
- 全量隔离根目录：系统临时目录 v09183-release-full-6p5x42ch；黄金/DOCX：v09183-golden-docx-7ovv6d61；逐阶段控制数据：v09183-special-v2。未新增运行时审计模块。
- 既有 datetime.utcnow 弃用警告未在本轮改动。

## 残留与回滚

- 历史请求参数/返回不足；所有控制返回均为新的离线实验，不是历史完整重放。未执行真实模型与线上 smoke，不能以控制测试证明普遍稳定。
- 前端默认值来源不可区分；文本不同的目标提示可能包含同义职位，不自动改请求目标。
- 中文未知技能、复杂自由教育表述与多学历仍有限制；没有新增通用解析或宽泛资格放行。
- 个人优势、Gate 否定作用范围疑点、空实习标题、输出额度、专业化、排序与篇幅分配仍为独立待办。本轮不承诺解决全部生成失败。
- 回滚需一致回退七个业务文件及版本记录到此前发布提交；无数据库迁移，不改已保存历史结果。不单独回退 relevance 接线，否则会再次过滤新证据的完整名称和限定。
