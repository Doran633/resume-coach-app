# 投放前检查清单

这份清单用于校园墙、社群或小范围内测投放前的最后确认。目标是避免“代码没更新、服务没重启、API 没配置、数据没记录”这类低级问题影响第一批用户体验。

## 1. 代码状态

- GitHub 最新代码已经 push。
- 服务器代码已经同步到 `origin/main`。
- 服务器没有遗留本地改动。
- 当前提交符合本次投放版本预期。

服务器检查：

```bash
cd /www/wwwroot/resume-coach-app
git fetch origin main
git status --short
git log --oneline -5
```

如果确认服务器不需要保留本地改动，可以更新到 GitHub 最新版本：

```bash
git reset --hard origin/main
```

## 2. 前端部署

- 已进入 `frontend` 目录。
- 已执行 `pnpm build`。
- 构建后的 `dist/index.html` 已更新。
- Nginx 已 reload。
- 首页可以正常打开。
- 手机端可以正常完成主流程。

服务器命令：

```bash
cd /www/wwwroot/resume-coach-app/frontend
pnpm build
systemctl reload nginx
```

移动端至少检查：

- 390px 宽度下输入页可用。
- 430px 宽度下结果页 Tabs 可横向滑动。
- 768px 宽度下导出和反馈页排版正常。

## 3. 后端与 LLM

- 后端服务已启动。
- `/api/health` 返回正常。
- `.env` 中 `LLM_MODE=openai`。
- `OPENAI_API_KEY` 已配置。
- `OPENAI_BASE_URL` 与使用的模型服务匹配。
- `OPENAI_MODEL` 已配置。
- 后端代码、prompt 或环境变量变更后已 restart。

健康检查：

```bash
curl -i http://resume.doran633.com/api/health
```

重启后端：

```bash
systemctl restart resume-coach-backend
systemctl status resume-coach-backend --no-pager
```

## 4. 生成链路

- 输入一段真实或测试经历后可以生成结果。
- 结果页能看到定位总览。
- 三档包装可以正常展示。
- Claim 承接检查可以展开。
- 面试准备 Tab 可以正常阅读。
- 补充信息后重新生成可用。
- 页面中不应出现 `question:`、`answer_points:`、`role:`、`details:` 等内部字段名。

## 5. DOCX 下载

- 可以进入导出与反馈页。
- 可以生成 DOCX。
- DOCX 可以下载。
- `backend/outputs/` 中有新文件。
- 简历个人信息未提供时保留 `[待填写]`。
- 如果历史结果存在空 `resume_sections`，重新导出 DOCX 后不应出现主体空白。

服务器检查：

```bash
ls -lt /www/wwwroot/resume-coach-app/backend/outputs | head
```

检查最近生成文件记录：

```bash
sqlite3 /www/wwwroot/resume-coach-app/backend/data/resume_coach.db "select id, generation_result_id, file_type, file_path, created_at from generated_files order by id desc limit 10;"
```

## 6. 数据埋点

- 访问首页后 `events` 有 `visit_home`。
- 提交经历后 `events` 有 `submit_experience`。
- 生成成功后 `events` 有 `generate_success`。
- 查看结果 Tab 后 `events` 有 `view_result_tab`。
- 展开 Claim 后 `events` 有 `expand_claim`。
- 生成 DOCX 后 `events` 有 `generate_docx`。
- 下载 DOCX 后 `events` 有 `download_docx`。
- 提交反馈后 `feedback` 表有记录。

查看最近事件：

```bash
sqlite3 /www/wwwroot/resume-coach-app/backend/data/resume_coach.db "select id, event_name, created_at from events order by id desc limit 20;"
```

查看最近反馈：

```bash
sqlite3 /www/wwwroot/resume-coach-app/backend/data/resume_coach.db "select id, model_comparison, price_acceptance, created_at from feedback order by id desc limit 10;"
```

## 7. 数据导出

- analytics 脚本可以运行。
- 能生成 Markdown summary。
- 能生成 events CSV。
- 能生成 inputs CSV。
- 导出内容不包含完整用户原始经历。
- 报告时间为北京时间。
- Markdown 报告中能看到 `Resume Fallback 监控`。
- 如果 fallback 触发率异常升高，需要回看 prompt、模型和结构化输出质量。

服务器运行：

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/export_analytics.py
```

输出位置：

```text
backend/reports/analytics-summary-YYYY-MM-DD.md
backend/reports/analytics-events-YYYY-MM-DD.csv
backend/reports/analytics-inputs-YYYY-MM-DD.csv
```

## 8. 日志检查

- LLM 调用日志有记录。
- 结果清洗日志有记录。
- 简历结构兜底日志按需写入。
- 日志写入失败不影响生成主流程。

查看日志：

```bash
tail -n 50 /www/wwwroot/resume-coach-app/backend/logs/llm_calls.jsonl
tail -n 50 /www/wwwroot/resume-coach-app/backend/logs/result_cleanup.jsonl
tail -n 50 /www/wwwroot/resume-coach-app/backend/logs/resume_section_fallback.jsonl
```

## 9. 投放前完整路径

投放前至少完整走一遍：

1. 打开首页。
2. 选择目标岗位。
3. 填写经历。
4. 选择“重点放大”。
5. 点击生成。
6. 查看定位总览、三档包装、承接检查、面试准备、简历预览。
7. 补充一段信息并重新生成。
8. 进入导出与反馈。
9. 生成并下载 DOCX。
10. 提交反馈。
11. 在 SQLite 中确认事件和反馈写入。
12. 对一个历史空结构结果重新导出 DOCX，确认不再空白。
13. 导出 analytics 报告，并检查 Resume Fallback 监控。

## 10. 异常回滚

如果新版本上线后出现严重问题，优先回滚到上一个稳定提交：

```bash
cd /www/wwwroot/resume-coach-app
git log --oneline -5
git reset --hard <stable_commit>
cd frontend
pnpm build
systemctl reload nginx
systemctl restart resume-coach-backend
```

回滚后重新检查 `/api/health`、生成链路和 DOCX 下载。

## 11. v0.4 生成质量检查

- 完整 `pytest` 已通过。
- `tests/test_v04_quality_regression.py` 匿名真实案例回归已通过。
- `scripts/export_generation_quality.py` 可以导出报告。
- Resume Section Fallback 触发率没有异常升高。
- `source_experience_id` 绑定率不低于观察阈值。
- Fact Coverage 平均覆盖率没有低于 80%。
- 跨经历污染修复率没有突然升高。
- Dedup 删除率没有异常升高，并已抽查独立高价值事实仍然保留。
- DOCX 不包含重复事实、内部 ID、调试文本或面试准备清单。
- 存在真实实习时，技能之后优先展示实习经历，岗位缺失时保留 `[待填写]`。

生成质量报告：

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/export_generation_quality.py --days 7
```

查看报告：

```bash
cat backend/reports/generation-quality-$(date +%F).md
```

重点日志：

```bash
tail -n 20 backend/logs/generation_stability.jsonl
tail -n 20 backend/logs/resume_section_fallback.jsonl
tail -n 20 backend/logs/experience_boundary.jsonl
tail -n 20 backend/logs/fact_coverage.jsonl
tail -n 20 backend/logs/resume_fact_dedup.jsonl
tail -n 20 backend/logs/docx_delivery_readiness.jsonl
```

## 12. 黄金样例回归

- `python -m pytest tests/test_golden_resume_regression.py -q` 已通过。
- 黄金案例与文本快照已确认匿名化。
- 高价值事实覆盖率不低于 90%。
- 经历边界准确率和技能分类准确率均为 100%。
- 重复详情和内部字段泄露均为 0。
- 固定 Payload 可以生成非空 DOCX，且不包含面试准备清单和内部 ID。
- 修改 Prompt、Guard、Fallback、技能分类或 DOCX 服务后，必须重新运行黄金回归。

固定基线评测：

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/evaluate_golden_resume.py --mode mock
```

真实模型评测仅在已配置 API 时运行，不作为普通发布门禁：

```bash
.venv/bin/python scripts/evaluate_golden_resume.py --mode openai
```
