# 生产可观测性

## 三个关联标识

- `request_id`：HTTP 请求的问题编号，格式为 `req_...`。用户可以在错误区域或结果页复制。
- `attempt_id`：一次生成尝试。重试会产生新的值，烟测统一使用 `smoke_` 前缀。
- `generation_result_id`：生成成功后保存的业务结果 ID，现有质量日志通过它关联。

生成提交时，`generation_queue.jsonl` 同时记录 `request_id` 和 `attempt_id`；生成完成时再写入 `generation_result_id`。DOCX 创建日志写入 `request_id`、`generation_result_id` 和 `file_id`。Guard 不需要重复记录请求编号，服务器通过结果 ID 回接质量日志。

服务只接受符合 `req_[a-zA-Z0-9_-]{8,80}` 的请求编号。包含控制字符、换行或超长内容的请求头会被替换，避免污染日志。

## 按问题编号查询

查询最近 24 小时的 warning 和 critical：

```bash
.venv/bin/python scripts/list_recent_quality_incidents.py --hours 24
```

按用户提供的问题编号查询：

```bash
.venv/bin/python scripts/list_recent_quality_incidents.py \
  --hours 72 \
  --request-id req_xxxxxxxxxxxxxxxx
```

按结果 ID 查询或输出 JSON：

```bash
.venv/bin/python scripts/list_recent_quality_incidents.py --result-id 52 --json
```

旧日志缺少 `request_id` 时显示 `legacy`。质量日志只有在结果 ID 相同且与请求链日志相距不超过 10 秒时才回接问题编号，避免测试数据库和临时数据库重复使用 result ID 时误关联。输出只包含阶段、问题代码、ID 和修复状态，不包含用户输入或简历正文。

## 发布身份

版本号统一读取项目根目录的 `VERSION`。生产构建还必须配置：

```dotenv
APP_VERSION=0.7.3
BUILD_COMMIT=<完整 Git commit>
BUILD_TIME=<ISO 8601 构建时间>
VITE_APP_VERSION=0.7.3
VITE_BUILD_COMMIT=<相同 Git commit>
VITE_BUILD_TIME=<相同构建时间>
```

后端健康接口、启动日志和前端 HTML 元数据都会暴露版本、短 commit 和构建时间，但不会暴露密钥。`launch_preflight.py` 会比较当前 Git、后端健康接口和已部署前端，任一不一致都阻止生产上线。

## 烟测

浅层烟测不调用模型，适合每小时运行：

```bash
.venv/bin/python scripts/run_public_smoke_test.py \
  --mode shallow \
  --base https://resume.doran633.com \
  --expected-version 0.7.3 \
  --expected-commit "$(git rev-parse HEAD)"
```

完整烟测会调用模型，适合部署后和每天运行一次：

```bash
.venv/bin/python scripts/run_public_smoke_test.py \
  --mode full \
  --base https://resume.doran633.com
```

完整烟测使用独立匿名 Cookie 和 `smoke_` attempt，依次检查生成、结构、污染标记、Experience ID 绑定、未解决 critical、DOCX 和数据删除。清理在 `finally` 中执行；清理失败直接判定 critical。烟测不会打印完整模型输出，SLO 与真实用户漏斗会排除 `smoke_` 流量。

## SLO

```bash
.venv/bin/python scripts/check_operational_slo.py \
  --hours 24 \
  --public-base https://resume.doran633.com
```

返回码：

- `0`：healthy
- `1`：warning
- `2`：critical

样本少于 10 次时，生成成功率和 P90 只观察，不告警。固定阈值包括成功率 90%/80%、P90 60/90 秒、Fallback 20%、事实覆盖 80% 和 DOCX 失败率 10%。SLO 只统计能建立 `request_id` 与 `attempt_id` 关联的线上事件；pytest、临时脚本和旧版无法追踪的日志不计入线上成功率、队列满或质量退化阈值。SLO 只告警，不阻断用户生成。

## 发布质量记录

每次准备发布的 commit 都要在本地提交完成、工作区干净后运行确定性黄金回归并生成绑定记录：

```bash
.venv/bin/python scripts/run_release_quality_gate.py
```

记录位于 `backend/reports/release-verification-<commit>.json`。生成规则有变化时必须针对新 commit 重新运行，不能复制旧记录。上线检查失败时只报告上一稳定 commit，不自动回滚。

## 建议定时任务

- 每小时：shallow smoke。
- 每 15-30 分钟：SLO 检查。
- 每日低峰期：full smoke、备份、数据清理和运行防护报告。
- 每次部署后：release quality gate、shallow、full、SLO、launch preflight。

定时任务应使用服务账号、固定工作目录和同一生产环境文件，并将非零退出码交给 systemd/cron 日志。不要把 API Key 写入 unit 文件或命令行。
