# v0.9.17.4.2 Canonical Fact Placement Contract

## 基线和边界

检查目录为 Resume-coach/resume-coach-app，分支 main，开始时 HEAD 为 317ae8584d2bf61db51f062c08dfadc5732db8a9、VERSION 为 0.9.17.4.1，工作区干净。读取了适用 AGENTS.md、conftest.py 和相关已有联合测试，未覆盖已有工作。

本版只更换 Canonical 项目模型返回的分配结构。没有修改输入分区、冻结语义、eligibility、Ledger、Binder、Planner、Coverage、Fallback 内容/策略、下游整理、Gate、Router、DOCX、前端或公开 API schema。没有新增业务服务、分类器或第二套事实真源。

## 原因与真实证据

上一轮新实验第三次真实模型响应保存在 tests/fixtures/v091742_real_model_response.json。内容与原始保存 JSON 对象核对完全一致（文件换行不作为语义证据）。该响应包含10个不同 Fact、20次引用：简介/职责使用的 Fact 再次完整进入详情。旧验证器给出 duplicate_fact_reference=10。这是本地真实模型实验，不是历史服务器失败请求的完整重放。

旧协议把项目定位、职责、详情分别表示为引用数组，再要求模型跨数组保持完整且互斥。0.9.17.4.1 已清理竞争任务，但真实返回仍重复。测试不能把“验证器能拒绝重复”当成“模型能稳定避免重复”。

本版先运行新增测试，结果35失败、10通过。真实响应在旧入口得到重复拒绝，新位置返回尚不能通过；重复 JSON 键也无法在原解码接口中被检出。

## 新旧结构

旧 Canonical 项目包含 source_experience_id、intro_source_fact_ids、role_source_fact_ids、detail_fact_ids。

新项目仅包含：

```json
{
  "source_experience_id": "EXP-001",
  "fact_placements": {
    "EXP-001-F001": "intro",
    "EXP-001-F002": "role",
    "EXP-001-F003": "detail"
  }
}
```

此 JSON 仅示意结构，不是模型返回样例或新增事实。fact_placements 的键必须精确等于该 owner 本次提供的 eligible Fact 集合，位置仅允许 intro/role/detail。未知、缺失、跨 owner、不可用引用、重复 owner、重复键、非法位置与额外字段均明确拒绝。

模型不再安排详情分组或组内排序。后端按冻结 source span 排序，同位置保持原证据顺序；详情一 Fact 一行，intro/role 的多个 Fact 沿用完整原句连接规则。没有分配事实的位置保持空正文。不同 Fact 共享 Claim 时仍各自保留，不按文本相同合并。位置声明不构成新的职责证明。

## 实际链路及权限

| 阶段 | 文件/函数 | 行为和修改范围 |
| --- | --- | --- |
| 编译 | 既有 Canonical Build/Views | 只读复用，不重建、重分类或裁剪证据 |
| 请求准备 | prompt_service.build_generation_prompt / _canonical_output_contract | 将内部字段和协议改为 canonical_fact_placements_v1；非项目包装、安全规则不变 |
| JSON 接收 | json_repair_service.parse_llm_json | 经用户批准增加可选 object_pairs_hook，并透传正常与修复两处 json.loads；默认行为不变 |
| 接线 | generation_service.build_llm_generation | 仅 Canonical 使用带重复键记录的解码钩子；原重试上限、预算及错误出口保留 |
| 验证组装 | experience_slot_service.compose_model_fact_references | 检查重复键、owner、精确集合、位置、lineage，使用现有冻结文本和表头组装原 Payload |
| 后续 | 既有来源校验、规范化、初始投影、保存和 DOCX | 代码未改，联合测试分别记录初始与下游状态 |

两份模板已经通过占位接线消费同一内部协议，本版无需修改模板文件。没有追加禁止重复的强调、包装示例或新模板机制。

## 重复键不能成为隐式去重

原 parse_llm_json 的两处 json.loads 会覆盖同名键，接收服务拿到 dict 后无法发现。用户已明确批准共享解析器最小接线调整；未复制 JSON 提取或修复逻辑。

ModelJSONObject 是本次解码的临时 dict 子类：在键覆盖发生时记录重复键名，再由项目协议拒绝。不是持久化 Schema、IR、可信标记或另一套业务数据。对于重复项目键，临时映射中的前值/后值都不构成可接受结果，整次返回失败，不据此选择一次引用保留。

检查范围包括包裹项目的 resume_sections/projects、项目对象及 fact_placements。重复的包裹键不能用后一份合法 projects 遮盖前一份。其他非项目字段的重复键、独立 legacy 默认解码契约保持原行为。Unicode转义同名键在标准解码后同样判重。

重复键使用固定原因 duplicate_project_key 和原 ModelEvidenceContractError 出口；重试后仍失败不保存。后一次解析失败也不能把前一次契约失败转换成 Stable Fallback 成功。纯 JSON 解析失败的既有兼容路径单独保留，不计为新协议成功。

## 测试迁移与证据

新增专项复用真实 Build、Views、接收器及保存/DOCX。控制返回仅在网络边界替换；budget/logs/数据库隔离不是语义替代。

- 正常/长输入的实际发送协议一致；重试只复用同份冻结证据。短样本强制选择长模板属于分支测试，不冒充自然长输入。
- 三份已有准确请求与完整课程双项目保留完整正文、限定及逐行 Fact/Claim；Build/Views 和返回输入不变。
- 普通 JSON、代码块、需闭合修复 JSON 中的重复 Fact键、转义同名键、owner、placements及包裹键全部拒绝。
- 已有合法返回的精确来源断言保留。旧三组引用的重叠反例现在按旧协议拒绝，不建立双轨成功入口。
- 新协议没有详情组合指令；原测试的同一行多个 Fact 改为后端一 Fact 一行的预期。原规范化对已有合并正文及附件的检查仍独立保留，不删除原能力测试。
- 非项目/legacy行为、伪造来源、非法lineage、同文异源、共享Claim、owner顺序、六项目、九详情与输入不变均有回归。
- 请求完整任务快照只因新字段与协议文本更新，非项目任务、legacy模板摘要及旧项目任务退出断言保留。

验证结果：新专项48通过（包含最终加入的保留样本）；相关协议/上游证据联合曾运行223项通过；专项与黄金/DOCX/初始证据联合曾运行102项通过；最终全量1122项通过。全量886条为既有 datetime.utcnow 弃用警告。10个改动Python文件编译通过；git diff --check通过。

新增 v091742_holdout_input.txt 为业务修改完成后准备的虚构测试开发实习/阅读工具保留样本，不从历史DOCX反推，也不用于调整本次业务规则。

## 真实模型验收状态

计划固定输入和保留输入共用本迭代最多三次付费调用额度，包含重试与已发出的失败请求，临时目录用独占创建的调用凭据跨进程计数，不随重跑清零。达到三次后不能发出第四次。

暂未调用：执行审批要求明确确认将两个测试文段发送到本地已配置的 api.deepseek.com / deepseek-v4-flash，已向用户请求确认。此状态不等同于已完成真实模型验收。

计划只在临时验收进程使用8192输出上限，隔离上一轮4096的截断风险，不改项目或服务器配置。需要报告模型、参数、finish_reason、首轮/重试结果和拒绝原因。即使这组调用通过，也不能证明4096配置、所有输入或端到端交付稳定。

## 下游残留

当前控制返回的九详情联合实验仍显示：初始九条完整，reconcile_resume_projects 在 generation 阶段变为八条，去掉 EXP-001-F009 / EXP-001-C009，保存八条。最终 Gate 两次 passed=true，同时有 INCOMPLETE_SENTENCE 和 ELIGIBLE_FACT_UNPROJECTED。没有修改相关规则或把 Gate通过当成完整交付证明。

科研误分类、个人优势自由表达、名称/岗位、输出额度和下游删除/交付出口继续独立保留。没有恢复被删除的内容来伪装本版成功。

## 回滚边界

内部协议必须成组发布或回滚：prompt_service、generation_service、experience_slot_service，加上已批准的共享解析可选钩子；对应测试与版本文档一起回退。不允许仅回退模板接线而保留新接收器，或反过来。

公开 Payload、数据库和 DOCX schema 未变，无迁移、无新增依赖。回滚会恢复旧三容器协议及其重复失败风险，应如实记录。未自动提交推送、未部署、未连接生产数据库，不进入下一阶段。
