# 投放前检查清单

这份清单用于校园墙、社群或小范围内测投放前的最后确认。目标是避免“代码没更新、服务没重启、API 没配置、数据没记录”这类低级问题影响第一批用户体验。

## 0. v0.7.2 上线硬门槛

先运行：

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/launch_preflight.py \
  --env /etc/resume-coach/resume-coach.env \
  --frontend-env frontend/.env.production \
  --public-base https://resume.example.com \
  --backups /var/backups/resume-coach
```

以下 `FAIL` 必须阻止公开推广：

- 生产环境仍使用默认密钥，或域名/Origin 白名单错误。
- Redis 不可用或监听非本机地址。
- SQLite `integrity_check` 失败。
- 日志、输出、报告或备份目录不可写。
- 没有最近七天内且可恢复验证的备份。
- 可用磁盘低于 500 MB，HTTPS 证书不足 7 天，或健康检查失败。
- `frontend/dist` 缺失，DOCX API 路由缺失，Nginx 配置错误或存在重复 `server_name`。
- 公网首页或签名匿名 Cookie 无法访问。

`RATE_LIMIT_DRY_RUN=true`、ICP 尚未配置、备份超过 48 小时但不超过 7 天属于 `WARN`。观察期可以保留限流 dry-run；正式公开推广前应完成备案信息确认。

还应确认：

- 隐私政策、服务条款、AI 说明和删除入口可访问。
- 删除测试账号后，其 DOCX 同步消失，其他匿名账号仍可访问自己的结果。
- 已执行一次 `cleanup_retained_data.py --dry-run`，数量符合预期。
- 已完成一次备份和临时目录恢复验证。
- 已配置每日备份、每日清理、每日运行报告和每小时健康检查。

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
- `LLM_TIMEOUT_SECONDS=75`，或使用经过验证的等价配置。
- Nginx `proxy_read_timeout` / `proxy_send_timeout` 高于模型调用超时，建议 100 秒。
- 浏览器等待上限高于 Nginx，当前为 110 秒。
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
- 新生成事件的 `payload_json` 含 `attempt_id`，且不含 `raw_input`。
- 进入结果页后 `events` 有 `view_generation_result`。
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
.venv/bin/python scripts/export_generation_funnel.py --days 7
```

输出位置：

```text
backend/reports/analytics-summary-YYYY-MM-DD.md
backend/reports/analytics-events-YYYY-MM-DD.csv
backend/reports/analytics-inputs-YYYY-MM-DD.csv
backend/reports/generation-funnel-YYYY-MM-DD.md
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
- 使用“平均 Token 消耗从 1400 降低到 600”回归，确认指标保留且技能栏不出现“安全机制：Token”。
- 使用“JWT Token 完成接口鉴权”回归，确认真实安全机制不会被误删。
- `technical_term_disambiguation.jsonl` 与 `resume_output_relevance.jsonl` 不包含完整用户经历。

固定基线评测：

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/evaluate_golden_resume.py --mode mock
```

真实模型评测仅在已配置 API 时运行，不作为普通发布门禁：

```bash
.venv/bin/python scripts/evaluate_golden_resume.py --mode openai
```

## 13. v0.5.x 收口检查

- Python 编译检查与全部 `pytest` 已通过。
- 黄金案例、固定 Payload 和文本快照已确认匿名化。
- 经历保留率 100%，高价值事实覆盖率不低于 90%。
- 经历边界、经历类型和技能分类准确率均为 100%。
- 重复详情和内部字段泄露均为 0。
- 固定 Payload 可以生成非空 DOCX，且不包含面试准备清单。
- Fallback 触发率、Guard 修复量和 Dedup 删除率没有异常升高。
- 前端 TypeScript 检查与生产构建通过。
- 真实模型评测只在需要抽查时运行；未运行时明确记录，避免无意消耗 API Token。
- 进入 v0.6.0 后，前端改动不得绕过或复制后端生成质量逻辑。

## 14. v0.6.0 经历实体唯一性

- `python -m pytest tests/test_resume_experience_entity_dedup.py -q` 已通过。
- 黄金回归中的回归分析计算器只出现一次，智能停车系统保持独立。
- 每个非空 `source_experience_id` 最多对应一个 project。
- 规范化项目标题不存在高置信重复。
- 合并后数据导入、回归算法、智能制图和模型推荐等独立事实仍被保留。
- DOCX 不出现“我做过一个……”等口语项目标题，也不展示 Experience ID / Fact ID。
- 检查 `backend/logs/resume_experience_entity_dedup.jsonl` 中的合并和低置信判定。
- 运行 `python scripts/export_generation_quality.py --days 7`，检查“经历实体去重”统计。

## 15. v0.6.10 最终投递质量门

- `python -m pytest tests/test_v06_delivery_quality_gate.py -q` 已通过。
- 黄金样例和 v0.4 / v0.6 真实案例回归已通过，高价值事实覆盖率没有下降。
- 生成结果和历史结果重新导出的 DOCX 均不包含空壳项目、跨经历指标、内部字段、教练话术、HTML 实体、零宽字符和确定性残句。
- 空 skills、role、intro 或 details 不渲染空标题，也不通过未知技能或模板句补足。
- 相似但绑定不同事实、指标、动作或结果的详情仍然保留。
- 质量门重复执行结果不变，最终质量门之后没有 Fallback 或正文扩写服务。
- 检查 `backend/logs/resume_delivery_quality_gate.jsonl` 中 `gate_passed`、严重问题数、修复数和高价值事实覆盖率。

查看最近质量门日志：

```bash
tail -n 20 backend/logs/resume_delivery_quality_gate.jsonl
```
# v0.7.0 公开测试安全检查

- [ ] `APP_ENV=production`，Cookie设置Secure。
- [ ] `ANONYMOUS_COOKIE_SECRET`、`DOWNLOAD_SIGNING_SECRET`、`IP_HASH_SECRET`均为独立强随机值。
- [ ] `REDIS_URL`可用，`/api/health/ready`中Redis检查通过。
- [ ] `ALLOWED_ORIGINS`和`ALLOWED_HOSTS`只包含正式域名。
- [ ] Nginx生成接口为60次/分钟/IP、`burst=30`，请求体不超过128KB。
- [ ] 全站生成并发为5，等待队列为15。
- [ ] `MODEL_MAX_CONCURRENT_CALLS` 不高于模型供应商实际并发额度。
- [ ] 刷新生成页面后，同一 `attempt_id` 可以恢复且不会重复调用模型。
- [ ] 输入2,000字显示提醒，4,001字被前后端拒绝且草稿保留。
- [ ] 用户A无法读取、导出或下载用户B的结果。
- [ ] 下载链接过期、篡改或身份不匹配时返回404。
- [ ] 模型供应商后台已设置账单告警或消费上限。
- [ ] `LLM_INPUT_PRICE_CNY_PER_MILLION`与`LLM_OUTPUT_PRICE_CNY_PER_MILLION`已按当前供应商填写。
- [ ] 日志目录、数据库目录和输出目录均不能经Nginx直接访问。
- [ ] 运行防护报告不包含用户输入、Prompt、简历正文、Cookie、Token、API Key和明文IP。
- [ ] 上线前三天保持`RATE_LIMIT_DRY_RUN=true`并观察校园共享IP误伤情况。
- [ ] Redis短时故障进入1并发保守模式，持续故障后暂停新生成；已有结果和下载仍可用。
- [ ] `runtime-protection`报告可正常导出，队列P90超过60秒时不继续扩大队列。
- [ ] 已按 `docs/v0.7-launch-security.md` 检查环境变量、systemd、Nginx和目录权限。
# v0.7.3 发布可观测性检查

- [ ] `APP_VERSION` 与根目录 `VERSION` 一致。
- [ ] `BUILD_COMMIT` 为当前完整 Git commit，`BUILD_TIME` 为本次构建时间。
- [ ] 前端 `VITE_APP_VERSION`、`VITE_BUILD_COMMIT`、`VITE_BUILD_TIME` 与后端相同。
- [ ] `python scripts/run_release_quality_gate.py` 已为当前 commit 生成通过记录。
- [ ] 最近 2 小时 shallow smoke 通过。
- [ ] 部署后 full smoke 通过，且测试匿名数据删除成功。
- [ ] 最近 2 小时 SLO 没有 critical。
- [ ] 健康接口、前端页脚和服务器 Git 的 commit 一致。
- [ ] 用户可在错误区和结果页复制 `req_...` 问题编号。
- [ ] `list_recent_quality_incidents.py --request-id` 可以回接 attempt、result 和 file。
- [ ] 烟测 attempt 已从真实用户 SLO 与漏斗中排除。
- [ ] `launch_preflight.py` 没有 failed 项。

# v0.7.4 自动运维与质量漂移

- [ ] hourly 和 daily systemd timer 已启用，`systemctl list-timers 'resume-coach-*'` 可见下次运行时间。
- [ ] `operations-status-latest.md` 已生成且版本、commit、健康状态一致。
- [ ] 最近 shallow smoke、SLO、质量漂移和备份未超过新鲜度阈值。
- [ ] full smoke 未启用时明确处于 observe；部署后已显式运行一次 full smoke。
- [ ] 输出质量漂移无 critical，高价值事实覆盖率和 Experience ID 绑定率没有明显下降。
- [ ] 当前稳定质量基线来自不少于 10 次非烟测样本，且写入时没有 critical。
- [ ] 限流报告已评估校园共享 IP，未自动修改 `RATE_LIMIT_DRY_RUN`。
- [ ] 数据库完整性为 ok，最近备份可以恢复。
- [ ] 数据库可迁移性报告已生成；当前未修改 schema 或生产 `DATABASE_URL`。
- [ ] 回滚准备报告能识别上一稳定 commit，但没有执行自动回滚。
