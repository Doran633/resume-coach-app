# 数据指标定义

本文件定义 Resume Coach 的内测数据口径。所有统计默认使用匿名身份，不在事件和报告中输出用户完整经历。

## 核心实体

- **匿名用户**：由 `anonymous_user_id` 标识。同一用户可以创建多个会话和多次生成。
- **会话**：由 `session_id` 标识，表示一次浏览器会话范围。
- **生成尝试**：用户主动提交一次生成或补充后重新生成，使用唯一 `attempt_id` 标识。
- **生成结果**：后端成功保存到 `generation_results` 的一条结构化结果。
- **生成文件**：后端成功保存到 `generated_files` 的一份 DOCX 文件记录。

## 事件口径

| 事件 | 含义 | 主要关联字段 |
|---|---|---|
| `visit_home` | 页面被访问 | anonymous_user_id、session_id |
| `submit_experience` | 用户提交一次初始生成 | attempt_id |
| `submit_followup` | 用户补充信息并提交新生成 | attempt_id、上一 generation_result_id |
| `generation_wait_stage` | 请求进入关键等待阶段 | attempt_id、elapsed_ms |
| `generate_success` | 后端结果返回前端并可展示 | attempt_id、generation_result_id |
| `generate_failed` | 本次尝试失败 | attempt_id、error_type |
| `view_generation_result` | 用户实际进入结果页 | attempt_id、generation_result_id |
| `generate_docx` | DOCX 已在后端生成 | attempt_id、generation_result_id、file_id |
| `download_docx` | 浏览器已触发文件下载 | attempt_id、file_id |
| `submit_feedback` | 反馈成功写入 | generation_result_id、attempt_id |

## 关键区别

- API 请求数不等于用户数；同一用户可以生成和重试多次。
- 生成成功数不等于 DOCX 下载数；用户可能只查看网页结果。
- `generation_results` 数量表示后端保存的生成结果，不等于文件数量。
- `generated_files` 数量表示生成过的 DOCX，不保证浏览器最终保存成功。
- `download_docx` 表示前端触发下载，不代表用户已经阅读文件。
- 重试是一次新的生成尝试，必须使用新的 `attempt_id`。

## 转化率

- 请求级生成成功率：成功 attempt 数 / 已提交 attempt 数。
- 请求级 DOCX 转化率：生成 DOCX 的 attempt 数 / 成功 attempt 数。
- 用户级生成成功率：至少成功一次的用户数 / 至少提交一次的用户数。
- 用户级 DOCX 转化率：至少生成一次 DOCX 的用户数 / 至少成功一次的用户数。

## 历史数据

v0.6.6 之前的事件可能没有 `attempt_id`，无法可靠判断一次提交对应哪个成功、失败或下载事件。历史数据只能作为独立计数展示，不能将“API 请求数减去 DOCX 数”直接解释为失败数。

## 隐私边界

事件与汇总报告可以记录：输入长度、经历数量估计、是否包含数字、是否包含技术词和错误类型。

事件与汇总报告不得记录：完整 `raw_input`、完整推荐版本、完整简历正文、API Key、模型地址、内部异常堆栈或个人联系方式。
