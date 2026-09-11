# Immutable Delivery Rendering Consistency

v0.9.13.1 将 Web 预览与 DOCX 的最后一层展示映射限定为对不可变交付 revision 的确定性读取。

## 证据边界

固定 `GenerationPayload` 重放确认，`details` 的正式形状是 `list[str]`，而 `intro` 与 `role` 是字符串。独立的“技术细节：”空 bullet 由 DOCX renderer 自行添加，并非该固定 payload 的正文生产者生成。另一个固定 payload 证明实习项目已经保存 `position`，但旧网页映射没有展示该字段。

这些结论描述当前代码可达性与固定 payload 重放，不作为历史请求的完整快照。

## 展示契约

- DOCX 读取 `GenerationResult.result_json` 后，在本地渲染列表中忽略纯结构标签行，将“技术细节：”与第一条有效详情同行展示，并保持其余详情顺序。
- 带有实际正文的“技术细节：……”不是纯标签，不会被过滤。
- Web 对 `meta == "实习经历"` 的项目展示 `name`、`position`、`time`；其他类型展示 `name`、`meta`、`time`。
- 字段均被视为 display-ready。Renderer 不从正文、技术细节或目标岗位反向推断名称、企业、岗位、类型或时间。

## 不变量

- Web 与 DOCX 消费同一已保存 revision。
- 渲染前后 payload 完全一致，不回写数据库。
- Renderer 不读取 `raw_input`，不调用 Canonical Build、LLM、Fallback、Projection、Coverage 或 Repair Router。
- 结构标签过滤不改变 Fact/Claim attachment；所有有效详情按原顺序展示。
- 非实习经历不显示企业或岗位，实习岗位不再在 Web 预览中丢失。

## 保留范围

网页继续只预览首个项目和前三条详情。本阶段不实现完整简历编辑器、经历排序、篇幅分配或正文专业化。
