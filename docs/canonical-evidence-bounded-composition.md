# v0.9.19.3 Canonical Evidence-Bounded Composition

## 基线与证据

- 工作分支 main，HEAD 5957d5ae1976119a99740bece414d0f6bf7d8262；进入本轮时 VERSION 为 0.9.19.2.1，已有未提交实现。本轮不覆盖或回退已有工作。
- 方案依据为 v09193-implementation-brief.md。上一轮真实调用暴露单 Fact 表达借用相邻 Fact、限定丢失及复核波动，不能将这些历史返回迁移成新协议后称为真实模型验收。
- 初始新专项在旧实现上为11失败、10通过；实现后先21项通过，再扩展到47项。实验为控制网络返回，数据库和日志隔离于 GodSu；未调用API、生产数据库或部署。

## 最小协议变化

Canonical 项目仅返回 source_experience_id 和 expression_units。每个单元包含 fact_ids、position、text；位置仍为 intro/role/detail。Fact ID 集合精确覆盖本 owner 提供的全部合格 Fact，且每个 Fact 只分配一次。单元内必须按冻结来源顺序连续排列；后端按冻结顺序组装，不按模型列表顺序排序事实。

相邻只是结构许可，不证明可以语义融合。主体、职责、对象和状态须兼容；不得新增因果、成果、责任等级或技术工作。原句及无损拼接沿确定性路径，非字面候选仍使用独立批量语义复核。详情一单元一行，intro/role 可确定性连接完整单元，允许空字段。

复核版本为 canonical_expression_review_v3：单元以首 Fact ID 定位，sources 明列全部原句及来源，问题对象增加 source_fact_id，片段必须在相应来源唯一定位。未知或缺失映射、错误片段、替代正文和未知结论拒绝；范围合法不代表语义判定可靠。

## 调用者与权限

| 位置 | 实际职责 | 本轮变化 |
| --- | --- | --- |
| prompt_service 的现有写作和复核准备 | 消费同请求 Build/Views | 单Fact任务改为显式完整多Fact单元；不增加一份摘要 |
| experience_slot_service.compose_model_fact_references | 校验引用、候选并派生附件 | 校验连续来源、精确覆盖，确定性组装 |
| CanonicalExpressionReview | 请求内支持结果 | 凭据绑定协议、Build指纹、原输入、owner、有序Fact/Claim及来源、位置、正文和约束 |
| _validate_project_evidence | 接收器、Binder、最终检查共用 | 完整单元匹配；不允许只取已审单元部分来源或挪用位置 |
| generation现有写作/复核/保存接线 | 唯一写作入口、总预算、失败出口 | 本轮无需新增业务修改，继续传同一验证对象 |
| 后处理、Gate、DOCX | 原职责 | 不获新改写权；实际正文变化使凭据失效 |

本轮新增业务改动为 backend/app/services/prompt_service.py、backend/app/services/experience_slot_service.py、prompts/review_canonical_expressions.md。正常/长模板使用现有动态项目契约，无须再增加模板分支。工作区 generation 和其他模板的既有改动属于前版，不能计作本轮新增。

## 旧路径、失败与兼容

- Canonical 不猜测旧 fact_placements 协议；旧返回明确拒绝，独立 legacy 行为保留。
- 两次总调用上限不变；格式重试占满预算时不能再复核。拒绝、不确定、截断或凭据失效不通过原句回填、删除失败项或降级伪造成功。
- 原始 Fact、Claim、eligibility、Authority 不变，复核只作表达风险评估，不回写 Ledger。
- 不新增服务、IR、持久状态或正文写作者。共享 Claim 的多个 Fact 可保留，附件由现有 lineage 派生，不由模型自报。

## 测试迁移与验收

旧全量首次301失败、1446通过，主要因旧控制返回停在新协议入口。经用户明确批准，将测试控制返回逐 Fact 等价迁移为单 Fact expression_units，保留原文、位置、输入及各项业务断言；复核对象增加 source_fact_id，更新完整任务快照和凭据断言。历史真实返回未修改，仍明确拒绝；其首次失败可能提前到输出契约入口，不冒称旧语义复核已被执行。

迁移涉及共享 helper test_v09162/test_v0916、旧协议专项 test_v09171/test_v09174/test_v091741/test_v091742、消费者 test_v09175/test_v09176/test_v09183/test_v09191、表达专项 test_v09192/test_v091921 系列。其他前版已修改的测试不在本轮重写。

新增 test_v09193_evidence_bounded_composition.py 共47项：正常/长输入及字段位置；多Fact合法组合；缺失、重复、跨owner、逆序、非连续、非法字段和旧协议；错误复核映射；限定丢失、职责扩大和虚构成果拒绝；凭据被正文、位置、来源或Build变更后失效；六项目/九详情；同文异源；正常、单薄、限定及保留样本逐阶段来源检查；真实保存与DOCX。

控制实验逐阶段观察 compose、normalize、Cleanup、Hard Fact Guard、Binder、初始投影、Reconciliation、正文清理、去重、Firewall、专业化及格式整理，检查具体正文、完整Fact/Claim行和owner，不以最终数量或后续补回替代证明。模拟复核通过只能证明接线。

最终全量1773项通过（85.98秒，1848条既有弃用等警告）；专项加黄金/DOCX联合62项通过（3.85秒）；Python编译通过。README、VERSION、backend/app、prompts、tests、docs范围的 git diff --check 通过，仅有换行风格提示。仓库其他既有 .pytest-* 状态不属于本轮，不清理、不回退。

隔离证据文件：GodSu/v09193-red.txt、v09193-stages.txt、v09193-full-before-migration.txt、v09193-migrated.txt、v09193-final.txt、v09193-golden.txt。最终运行禁止外部网络；API调用为0。

## 残留与发布边界

未进行真实模型验收，不能宣称合理表达误拒、职责扩大漏放或真实成功率已经改善。下一次外发须重新确认样本与调用额度；固定及保留样本应分别记录原句率、组合率、首轮/复核结果、限定变化、截断、成本和延迟，包含相同候选重复复核对照。

两次调用预算和完整输出负担仍存在。相邻限制可能拒绝语义合理但不连续的组合，本版保守保留；任意跨Fact总结不被授权。summary、四版本语义证明、段落格式、技能展示、排序与篇幅优化未解决。没有新增通用语义证明。

回滚必须同时恢复项目契约、复核模板和请求内支持结果逻辑，不能混用新写作协议与旧接收器。无数据库迁移，不回写历史已保存 revision。保留前版未提交改动，不以整仓重置回滚。离线通过不等于发布验收通过，本轮不建议部署。
