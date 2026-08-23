# Resume Coach App v0.1

面向国内应届生和实习生的 AI 求职教练网页应用。v0.1 保留 mock 模式，并支持通过 OpenAI 兼容接口接入真实 LLM。

## 功能

- 输入经历
- 选择目标岗位和包装强度
- 生成普通包装版 / 大胆包装版 / 边界参考版
- 生成 Claim 风险分析
- 生成面试追问与知识补齐清单
- 生成并下载 DOCX 简历
- 记录匿名埋点和反馈
- 通过 `LLM_MODE` 在 mock / openai 之间切换

## 配置 LLM

复制 `.env.example` 为 `.env`，按需修改：

```powershell
cd C:\Users\lbc\Documents\ChatGPT\GodSu\resume-coach-app
copy .env.example .env
```

默认使用 mock：

```env
LLM_MODE=mock
```

接入真实 API：

```env
LLM_MODE=openai
OPENAI_API_KEY=你的 API Key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
LLM_TIMEOUT_SECONDS=30
LLM_MAX_TOKENS=4096
LLM_THINKING=disabled
```

`OPENAI_BASE_URL` 支持 OpenAI 兼容接口。

## 启动后端

```powershell
cd C:\Users\lbc\Documents\ChatGPT\GodSu\resume-coach-app\backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果 8000 端口被占用，可以改用：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：

```text
http://127.0.0.1:8000/api/health
```

## 启动前端

```powershell
cd C:\Users\lbc\Documents\ChatGPT\GodSu\resume-coach-app
pnpm install
cd frontend
pnpm dev
```

如果安装时提示 `ERR_PNPM_IGNORED_BUILDS`，先执行：

```powershell
pnpm approve-builds
pnpm install
```

如果后端使用 8001 端口：

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8001"
pnpm dev
```

访问：

```text
http://127.0.0.1:5173
```

## 当前说明

- v0.1 默认使用 mock generation service，配置 `.env` 后可切换到真实 LLM。
- 不做登录、不做支付、不做 PDF、不做简历上传。
- DOCX 文件保存到 `backend/outputs/`。
- SQLite 数据库保存到 `backend/data/resume_coach.db`。
- LLM 调用日志保存到 `backend/logs/llm_calls.jsonl`，并写入 `llm_call_logs` 表。

## 结果清洗与稳定性兜底

v0.1.6 在后端生成链路中加入统一清洗层。mock 和 openai 模式生成结果后，都会先经过结构校验，再进行展示清洗和风险兜底，最后保存到数据库并返回前端。

清洗范围包括：

- 用户可见正文中的内部字段名，例如 `question:`、`answer_points:`、`role:`、`details:`、`summary:`、`skills:`。
- 多余空格、连续换行、代码块标记和明显 JSON/Markdown 包裹痕迹。
- Claim 风险等级兜底，只允许 `green`、`yellow`、`red`、`black`。
- 空字符串的温和兜底文案。
- 过长数组的数量裁剪，避免页面被单次生成结果撑得过长。

清洗不会改变用户事实，也不会凭空编造经历；它只负责让模型输出更稳定、更像正式产品。

清洗日志保存到：

```text
backend/logs/result_cleanup.jsonl
```

## 数据汇总与导出

v0.1.1 提供轻量数据导出脚本，用于把 SQLite 埋点数据整理成 Markdown 和 CSV 报告。

本地运行：

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
python scripts\export_analytics.py
```

服务器运行：

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/export_analytics.py
```

只统计最近 7 天：

```bash
.venv/bin/python scripts/export_analytics.py --days 7
```

自定义数据库和输出目录：

```bash
.venv/bin/python scripts/export_analytics.py --db backend/data/resume_coach.db --out backend/reports
```

默认输出：

```text
backend/reports/analytics-summary-YYYY-MM-DD.md
backend/reports/analytics-events-YYYY-MM-DD.csv
backend/reports/analytics-inputs-YYYY-MM-DD.csv
```

报告和 CSV 中展示的时间统一为北京时间（UTC+8）。数据库底层仍使用 UTC 时间保存。

隐私说明：

- 默认不会导出用户 `raw_input` 原文。
- inputs CSV 只导出输入长度、目标岗位、包装强度、经历类型等元信息。
- Markdown 反馈摘录最多保留 120 字。

## 反馈问题

1. 你认为这个服务相比当前市场大模型效果如何？
   - 明显更好
   - 略好一些
   - 差不多
   - 不如直接用大模型

2. 你认为这样的服务价值多少？
   - 0元
   - 2.99元
   - 9.99元
