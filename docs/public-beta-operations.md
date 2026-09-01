# 公开测试运维手册

## v0.7.4 自动运维

服务器安装 `deploy/systemd/` 中的 hourly 和 daily service/timer 后，检查与报告会自动运行。日常只查看：

```bash
sed -n '1,240p' backend/reports/operations-status-latest.md
systemctl list-timers 'resume-coach-*'
```

统一报告包含版本一致性、备份、烟测、SLO、质量漂移、限流评估、数据库审计和当前告警。若报告没有按时更新，`check_operations_freshness.py` 会将“任务未运行”识别为异常。

部署后执行：

```bash
.venv/bin/python scripts/run_public_beta_operations.py \
  --mode post-deploy \
  --public-base https://resume.doran633.com \
  --backups /var/backups/resume-coach
```

真实模型 full smoke 只有在明确设置 `ENABLE_FULL_SMOKE=true` 或传入 `--full-smoke` 时运行。质量漂移与限流评估只告警，不自动修改生成结果、模型或环境变量。

## 日常任务

建议使用 systemd timer 或 cron，以服务账号执行。示例：

```cron
10 2 * * * cd /www/wwwroot/resume-coach-app && .venv/bin/python scripts/backup_production_data.py --out /var/backups/resume-coach >> /var/log/resume-coach-backup.log 2>&1
30 2 * * * cd /www/wwwroot/resume-coach-app && .venv/bin/python scripts/cleanup_retained_data.py >> /var/log/resume-coach-cleanup.log 2>&1
50 2 * * * cd /www/wwwroot/resume-coach-app && .venv/bin/python scripts/export_runtime_protection.py --days 1 --backups /var/backups/resume-coach --public-base https://resume.example.com >> /var/log/resume-coach-report.log 2>&1
0 * * * * curl -fsS http://127.0.0.1:8001/api/health/ready >/dev/null || logger -t resume-coach "ready check failed"
20 3 * * 1 cd /www/wwwroot/resume-coach-app && .venv/bin/python scripts/verify_production_backup.py --backups /var/backups/resume-coach >> /var/log/resume-coach-restore-check.log 2>&1
```

Certbot 通常自带续期 timer，另需确认 `systemctl status certbot.timer` 和 `certbot renew --dry-run`。运行防护报告会记录当前证书剩余天数。

## 每日查看

- 生成成功率与 P90 耗时是否突然恶化。
- 5 个并发和 15 个队列是否出现持续满载。
- 限流预计命中是否集中在正常校园共享 IP。
- 每日 Token 和估算成本是否接近预算。
- Redis 降级、越权下载、无效下载凭证是否异常升高。
- 数据清理是否执行、磁盘使用率是否上升、最近备份是否新鲜。

## 备份与恢复演练

`backup_production_data.py` 使用 SQLite 在线备份 API，不直接复制正在写入的数据库。每次备份完成后执行 `integrity_check`。

`verify_production_backup.py` 只把备份恢复到系统临时目录，检查完整性和业务表数量后自动删除临时文件，永不覆盖生产数据库。至少每周运行一次。

## 发布流程

1. 拉取已审核提交并安装依赖。
2. 执行后端测试和前端构建。
3. 先创建并验证一次生产备份。
4. 重启后端，重载 Nginx。
5. 运行 `launch_preflight.py`。
6. 人工走通首页、生成、结果、DOCX、反馈、隐私页面和删除测试账号。
7. 观察运行日志与错误率，再开始公开分享。

预检的 `FAIL` 阻止上线，`WARN` 需要人工确认。限流观察期允许 `RATE_LIMIT_DRY_RUN=true`，但生产密钥、Redis、数据库、备份、HTTPS、健康检查和前端构建不能带失败上线。
# v0.7.3 日常观测

每小时运行浅层烟测，每 15-30 分钟运行 SLO；部署后和每日低峰期运行完整烟测。完整命令和指标口径见 `docs/production-observability.md`。

收到用户问题编号后，优先执行：

```bash
.venv/bin/python scripts/list_recent_quality_incidents.py --hours 72 --request-id req_xxxxxxxxxxxxxxxx
```

不得要求用户发送完整经历或 Cookie。若页面显示“暂未生成问题编号”，按时间、操作类型和网络状态查询 runtime 日志，不将无编号请求强行关联到某个生成结果。
