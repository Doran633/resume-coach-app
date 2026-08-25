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
- 生成稳定性：LLM 输出经过结构校验、JSON 修复、结果清洗和简历结构兜底。
- 输出质量：支持多段经历识别和更高密度项目生成，避免长输入被过度压缩。
- 经历覆盖：支持项目、实习、科研、竞赛、开源、校园 / 社团等经历进入正式简历。
- DOCX 导出：根据结构化简历生成正式技术简历，支持最多两页内容承载，并在结构为空时自动兜底，避免页面有内容但 DOCX 空白。
- 数据闭环：匿名用户、会话、事件、输入、生成结果、反馈、LLM 调用日志和 fallback 日志。
- 数据导出：将 SQLite 埋点导出为 Markdown 和 CSV 报告，并汇总 fallback 触发率。
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

## v0.2.x 稳定性收口

v0.2.x 聚焦真实用户使用后的稳定性与可观测性。

- v0.2.0：清理三档包装、推荐版本、项目预览和面试准备中的英文内部字段名。
- v0.2.1：承接检查改为状态圆点，信息完整度增加“当前还缺什么”。
- v0.2.2：新增 Resume Section Fallback，修复页面有内容但 DOCX 空白的问题。
- v0.2.3：增强 fallback 可观测性，将触发阶段、补全 section、触发原因和来源字段写入日志并汇总到 analytics。

核心原则：

```text
结构合法不等于业务可用。
Fallback 是安全网，不是垃圾桶。
用户不该感知故障，但开发者必须能感知上游退化。
```

## v0.3.0 输出质量优化

v0.3.0 从“稳定性收口”进入“生成质量优化”，重点解决长输入和多段经历下的过度压缩问题。

主要能力：

- 支持多段经历识别：项目、实习、开源、比赛等主要经历应尽量分别保留。
- 支持更高密度项目生成：单段经历保留更多职责、技术细节、结果和证据。
- 长输入不再默认压成一段：除非经历高度重复或信息极少，否则不随意合并删除。
- 支持最多两页 DOCX：内容充足时优先完整承载关键项目，而不是强行压缩成一页。
- 继续遵守事实边界：可以大胆包装职责表达，但不凭空增加用户数、star、上线、性能提升、企业实习、模型训练等硬事实。

## v0.3.1 长输入抗失败修复

v0.3.1 针对真实长经历输入进行修复，重点处理“项目一｜项目名”“### 项目二｜项目名”等自然写法。

主要能力：

- 生成前增加经历分段预解析，将长输入拆成主要经历清单并注入 prompt。
- Fallback 支持中文冒号、英文冒号、竖线、全角竖线和破折号等标题分隔符。
- 长段落句号较少时，会进一步按逗号拆出可用技术细节，减少项目细节过少的问题。
- 默认 LLM 超时调整为 60 秒，默认输出上限调整为 8192 tokens，降低长输出被截断导致无法生成的概率。

## v0.3.2 事实防幻觉与包装增益

v0.3.2 继续优化输出质量，核心原则是：硬事实守住，软表达拉满。

主要能力：

- 硬事实防幻觉：用户未提供学校、专业、学历、公司、用户数、star、并发、奖项、模型训练等信息时，不编造、不暗示。
- 隐性硬事实清理：将“计算机相关专业”“科班背景”“企业级生产系统”“模型训练经验”等缺少事实支撑的表达降级。
- 软事实包装增强：对“写页面 / 调接口 / 修 bug / 写文档 / 做 RAG”等真实经历进行职责、技术动作和项目结构上的表达升级。
- 避免复述原文：当推荐版本或项目 details 与用户输入过于相似时，会基于已有事实重新组织成更正式、更岗位化的简历表达。

## v0.3.3 非项目经历覆盖

v0.3.3 增强实习、科研、竞赛、开源、校园 / 社团等非项目经历的识别和 DOCX 承载。

主要能力：

- 不改数据库和 API，继续用 `resume_sections.projects` 统一承载经历。
- 通过 `project.meta` 区分“项目经历 / 实习经历 / 科研经历 / 竞赛经历 / 开源经历 / 校园 / 社团经历”。
- Fallback 会从原始输入中补回被 LLM 漏掉的实习、科研、竞赛等经历。
- DOCX 输出按小标题分组展示，例如“项目经历”“科研经历”“实习经历”“竞赛获奖”。

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
LLM_TIMEOUT_SECONDS=60
LLM_MAX_TOKENS=8192
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
- v0.3.0 起，DOCX 允许承载最多两页内容；当用户输入多段经历时，会优先保留关键项目，而不是为了压缩版面删除主要经历。

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

检查最近生成文件记录：

```bash
sqlite3 backend/data/resume_coach.db "select id, generation_result_id, file_type, file_path, created_at from generated_files order by id desc limit 10;"
```

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
- 如果页面有内容但 DOCX 主体为空，检查 `backend/logs/resume_section_fallback.jsonl` 和 analytics 报告中的 Resume Fallback 监控。

### 数据导出没有内容

确认线上数据库路径：

```text
backend/data/resume_coach.db
```

并检查 events 表是否有记录：

```bash
sqlite3 backend/data/resume_coach.db "select count(*) from events;"
```

## v0.3 方向概览

v0.3 建议主题：输出质量优化。

优先方向：

- Prompt 分层：拆分经历解析、信息缺口诊断、岗位定位、三档包装、Claim 检查、面试准备和 resume_sections 生成。
- 输出质量评分：检查结果是否具体、岗位匹配、可承接、少空泛。
- 反空泛规则：减少“提升用户体验”“负责相关工作”等弱表达。
- 岗位化生成策略：同一段经历针对 AI Agent、后端、前端、数据分析等岗位突出不同重点。
- 真实案例回归集：把真实用户 case 固化为测试样例。
- DOCX 版式：继续接近正式技术简历，优化移动端下载提示。

详细检查见：

- `docs/launch-checklist.md`
- `docs/version-history.md`
- `docs/v0.2-retrospective.md`
