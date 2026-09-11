# Scoped Professionalization and Packaging Enhancement

v0.9.13.2 在已经冻结的 Canonical 语义之上开放有限的表达层权限。它提高简历语言强度，但不重新解释经历或创建可核验硬事实。

## 权限范围

Canonical Professionalization 只处理具有冻结 owner 和字段级 eligible Fact 的 `role` 与 `details`。当字段携带 Claim 行时，Claim 集合还必须与这些 Fact 的既有 lineage 完全一致。项目聚合 `source_fact_ids` 不能作为字段精确证据；当前 `intro` 没有独立附件，因此保持原文。

允许的软性推导包括职责抽象、设计与实现过程、验证与迭代过程，以及不带数字的交付价值。例如，“写了几个页面”可在大胆档表达为“参与前端架构设计与完整交互流程建设”。

禁止新增技术、框架、指标、企业、岗位、时间、奖项、上线状态、用户规模、团队关系，以及无证据的主导或独立负责声明。negative、uncertain、planned、withheld 和 instruction 内容不能进入正式表达。

## 三档包装

- `稳妥`：职业化同义改写，贴近原始动作。
- `大胆`：补全合理的设计、实现、验证和流程建设表达。
- `极限`：在同一事实方向内进一步强调完整流程与非量化交付价值。

公开 API 仍只有这三个包装选项。四个版本文本字段中的 `boundary_version` 保留事实边界用途；`normal_version`、`bold_version` 和 `recommended_version` 使用同一 owner-scoped 事实生成不同强度表达。

## 不变量

- 不修改 Experience 数量、顺序、名称、类型、时间、企业、岗位或 owner。
- 不修改 Fact/Claim ID、owner、eligibility、certainty、polarity、temporal status 或 attachment。
- 不修改 Canonical Build、Consumer Views、Ledger、Binder、Projection、Gate、Router 或 Immutable Delivery Revision。
- Canonical 路径不读取完整 `raw_input`，不新增 Prompt 或 LLM 调用。
- 同一输入和包装档位重复执行结果稳定；日志只记录脱敏计数、字段路径、owner ID 与档位。
