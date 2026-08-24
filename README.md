# Resume Coach App

面向国内应届生和实习生的 AI 求职教练网页应用。

它不是普通的简历润色器，而是一个“经历定位 + 包装强度判断 + 面试承接准备 + 正式简历导出”的完整闭环工具。产品原则是：表达可以积极，但硬事实不能凭空改变；每一个强表达都应该能被证据、技术知识或面试回答接住。

## 项目定位

Resume Coach App 面向有项目、实习、开源、比赛或校园经历，但不知道如何表达的技术求职者。用户输入真实经历后，系统会帮助其完成：

- 识别经历中的可用事实和缺失信息。
- 根据目标岗位生成不同强度的包装表达。
- 标出 Claim 风险和面试追问。
- 给出知识补齐和证据准备方向。
- 生成可下载的正式技术简历 DOCX。
- 记录匿名埋点和反馈，支持后续投放复盘。

## 当前能力

- 引导式经历输入：目标岗位、经历类型、包装强度、示例模板、输入质量提示。
- 三档包装表达：基础增强、重点放大、边界测试。
- 结果工作台：定位总览、三档包装、承接检查、面试准备、简历预览。
- Claim 风险分析：green / yellow / red / black 四档风险。
- 面试承接：面试追问、补充追问、知识补齐、降级表达。
- 生成稳定性：LLM 输出经过结构校验、JSON 修复和结果清洗。
- DOCX 导出：根据推荐版本生成正式技术简历。
- 数据闭环：匿名用户、会话、事件、输入、生成结果、反馈、LLM 调用日志。
- 数据导出：将 SQLite 埋点导出为 Markdown 和 CSV 报告。
- 移动端适配：支持手机完成输入、查看、导出、反馈流程。

## v0.1.x 功能列表

- v0.0：跑通输入经历、生成结果、展示、DOCX 下载、埋点和反馈。
- v0.1：接入真实 LLM 模式，保留 mock 模式。
- v0.1.1：新增数据汇总和导出脚本。
- v0.1.2：新增输入页敏感信息提醒。
- v0.1.3：优化结果页顶部介绍和项目经历展示中文化。
- v0.1.4：结果页改为 Tabs 工作台，Claim 支持展开查看。
- v0.1.5：输入页增加模板、质量提示，并将包装强度产品化。
- v0.1.6：新增后端结果清洗与稳定性兜底。
- v0.1.7：优化结果页阅读体验，长文本改为摘要和展开。
- v0.1.8：将面试准备清单移动到导出页，增强交付感。
- v0.1.9：完成移动端适配。

## 本地启动

### 1. 安装依赖

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
pnpm install
```

后端建议使用虚拟环境：

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env`：

```powershell
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

`OPENAI_BASE_URL` 支持 OpenAI 兼容接口，例如 DeepSeek、OpenRouter 或自建兼容网关。

### 3. 启动后端

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app\backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果 8000 端口被占用：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：

```text
http://127.0.0.1:8000/api/health
```

### 4. 启动前端

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app\frontend
pnpm dev
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

## 服务器部署

服务器推荐只作为部署环境，不直接修改源码。

```bash
cd /www/wwwroot/resume-coach-app
git fetch origin main
git reset --hard origin/main
cd frontend
pnpm build
systemctl reload nginx
systemctl restart resume-coach-backend
```

如果只改前端页面或样式，可以不重启后端：

```bash
cd /www/wwwroot/resume-coach-app
git fetch origin main
git reset --hard origin/main
cd frontend
pnpm build
systemctl reload nginx
```

如果改了后端代码、prompt、`.env` 或生成逻辑，需要重启后端。

## DOCX 输出

- DOCX 生成接口：`POST /api/resume/docx`
- 下载接口：`GET /api/files/{file_id}`
- 输出目录：`backend/outputs/`
- 文件会自动版本化命名。
- 未提供的个人信息保留 `[待填写]`，不会编造姓名、手机号、邮箱等信息。

## 数据埋点与导出

当前埋点包括：

- `visit_home`
- `submit_experience`
- `generate_success`
- `generate_failed`
- `view_claim_risk`
- `copy_result`
- `generate_docx`
- `download_docx`
- `submit_feedback`
- `view_result_tab`
- `expand_claim`
- `submit_followup`
- `change_packaging_level`
- `change_target_role`
- `fill_example_template`
- `input_quality_hint_shown`
- `view_export_interview_plan`

SQLite 数据库：

```text
backend/data/resume_coach.db
```

导出统计报告：

```powershell
python scripts\export_analytics.py
```

服务器运行：

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python scripts/export_analytics.py
```

默认输出：

```text
backend/reports/analytics-summary-YYYY-MM-DD.md
backend/reports/analytics-events-YYYY-MM-DD.csv
backend/reports/analytics-inputs-YYYY-MM-DD.csv
```

报告和 CSV 中展示的时间统一为北京时间。默认不会导出用户原始经历全文。

analytics 报告会同时汇总 Resume Section Fallback 触发情况，包括 fallback 调用次数、触发率、触发阶段、补全 section、触发原因和来源字段。Fallback 只作为安全网保护用户交付体验，如果触发率异常升高，需要回看 prompt、模型或结构化输出质量。

## 日志位置

- LLM 调用日志：`backend/logs/llm_calls.jsonl`
- 结果清洗日志：`backend/logs/result_cleanup.jsonl`
- 简历结构兜底日志：`backend/logs/resume_section_fallback.jsonl`
- 生成文件：`backend/outputs/`
- 数据报告：`backend/reports/`

查看最近 LLM 日志：

```bash
tail -n 50 backend/logs/llm_calls.jsonl
```

查看最近清洗日志：

```bash
tail -n 50 backend/logs/result_cleanup.jsonl
```

查看最近简历结构兜底日志：

```bash
tail -n 50 backend/logs/resume_section_fallback.jsonl
```

## 常见问题

### GitHub 拉取很慢或卡住

服务器访问 GitHub 可能不稳定。优先确认：

```bash
git ls-remote origin
```

如果 GitHub 网络不可用，可以临时上传 `frontend/dist` 和 prompt 文件，但长期建议保持服务器通过 GitHub 同步。

### 页面没有更新

常见原因：

- 本地代码没有 commit / push。
- 服务器 `git pull` 或 `git reset` 没有到最新提交。
- 前端没有重新 `pnpm build`。
- 浏览器缓存旧资源，需要强制刷新。
- 改了 prompt 或后端代码但没有重启后端。

### 生成结果仍出现英文内部字段

确认后端已重启，并检查：

```bash
tail -n 50 backend/logs/result_cleanup.jsonl
```

如果没有日志，说明最新后端清洗逻辑可能没有部署或服务未重启。

### DOCX 下载失败

检查：

- 后端服务是否运行。
- `backend/outputs/` 是否存在并有写入权限。
- Nginx `/api/` 代理是否正常。
- 浏览器是否拦截新窗口下载。

### 数据导出没有内容

确认线上数据库路径：

```text
backend/data/resume_coach.db
```

并检查 events 表是否有记录：

```bash
sqlite3 backend/data/resume_coach.db "select count(*) from events;"
```

## v0.2 方向概览

v0.2 建议主题：真实用户验证与生成质量提升。

优先方向：

- 生成质量：根据真实样例优化 prompt 和结构化输出。
- Prompt 分层：拆分经历解析、包装生成、Claim 检查、面试准备。
- 反馈闭环：把用户反馈和生成结果关联分析。
- 数据分析：增强投放漏斗、转化率、用户输入质量统计。
- DOCX 版式：继续接近正式技术简历，优化移动端下载提示。
- 稳定性：完善异常提示、超时处理、重试策略。
- 部署标准化：形成固定发布流程，避免服务器本地改动污染。

详细检查见：

- `docs/launch-checklist.md`
- `docs/version-history.md`
