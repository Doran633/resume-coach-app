# 问题响应手册

## 用户如何提供信息

请用户提供：

1. 页面显示的 `req_...` 问题编号。
2. 大致发生时间和操作：生成、DOCX、下载、反馈或删除。
3. 问题表现的简短描述。

不要让用户在公开渠道发送完整经历、Cookie、下载链接或 API 返回内容。网络完全未到达服务器时页面会显示“暂未生成问题编号”，此时使用发生时间、操作和浏览器网络状态排查。

## 第一轮定位

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/list_recent_quality_incidents.py \
  --hours 72 \
  --request-id req_xxxxxxxxxxxxxxxx
```

常见判断：

- 只有 `generation_task_failed`：检查模型超时、成本熔断、Redis 和队列。
- `CROSS_EXPERIENCE_FACT`：查看 Experience Boundary 是否已修复，以及同一 result 的最终质量门状态。
- `LOW_HIGH_VALUE_FACT_COVERAGE`：检查 Fact Coverage 是否恢复事实，避免简单归因于模型输出短。
- `RESUME_SECTION_FALLBACK` 频繁：上游结构化结果可能退化。
- `DELIVERY_QUALITY_GATE_FAILED` 或 unresolved critical：该结果未通过最终投递质量检查，应优先复现。
- DOCX 创建成功但下载失败：检查签名链接有效期、文件所有权和磁盘文件。

## 运行状态排查

```bash
.venv/bin/python scripts/check_operational_slo.py --hours 24 --public-base https://resume.doran633.com
.venv/bin/python scripts/run_public_smoke_test.py --mode shallow --base https://resume.doran633.com
```

先确认线上版本：

```bash
curl -s https://resume.doran633.com/api/health/live
git rev-parse HEAD
```

健康接口的 commit、前端页脚 commit 和服务器 Git commit 必须一致。代码已经拉取但服务或前端未重建时，版本检查会直接暴露错配。

## 严重级别

- critical：生成普遍失败、DOCX 失败率超过 10%、数据删除失败、未解决质量门问题、版本错配、完整烟测清理失败。
- warning：成功率低于 90%、P90 超过 60 秒、Fallback 超过 20%、事实覆盖低于 80%、队列偶发满。
- observe：样本不足、低置信语义问题或单次已自动修复质量问题。

## 处理原则

1. 先冻结继续发布，保留日志和问题编号。
2. 确认影响范围是单个结果、某种输入还是全站运行故障。
3. 使用匿名固定案例复现，不复制用户原文到报告。
4. 修复后运行相关单测、黄金回归、shallow/full smoke 和 SLO。
5. 生成新 commit 的发布验证记录。
6. `launch_preflight.py` 全部通过后再恢复发布。

上线工具不会自动回滚。若需要回退，人工选择最近具有黄金回归、烟测和 SLO 记录的稳定 commit，并按正常部署流程重建前端、重启后端和复检。
