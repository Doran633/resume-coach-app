# Resume Coach App

## v0.4.5 候选人视角个人优势

- 新增个人优势质量检查，隔离“候选人、爱好者、可面试承接、建议补充”等求职教练话术。
- 每条个人优势必须由 `experience_id` 或 `fact_id` 支撑，并使用“能力 + 行动证据 + 价值”的候选人视角表达。
- 协作、量化结果和学习迁移能力按事实条件生成，不再用空泛积极词机械补满。
- 历史结果重新导出 DOCX 时也会执行清理，面试准备与简历正文各自承担清晰职责。
- 质量日志位于 `backend/logs/resume_summary_quality.jsonl`，仅记录修复统计和内部事实标识，不记录完整用户输入。

## v0.4.4 Experience Fact Ledger

- 按 `experience_id` 建立原子事实账本，并用内部 `fact_id` 追踪技术、功能、工程实践、证据和指标。
- 新增事实覆盖检查，高价值明确事实优先于通用包装句和重复内容。
- 项目详情只使用本段事实或本段允许的自然承接知识，跨经历内容会被移回正确经历或清理。
- 移除项目详情中的机械通用补句；输入越充实，正式简历承载的有效事实越完整。
- 覆盖日志位于 `backend/logs/fact_coverage.jsonl`，只记录统计和 fact_id，不记录完整用户输入。

## v0.4.3 经历类型与正文完整性

- 使用 `source_experience_id` 校准经历类型，避免个人项目被误分到实习经历。
- DOCX 在技能与能力之后优先展示真实实习经历，再展示项目、科研和竞赛经历。
- 内部裁剪摘要与用户可见正文隔离，避免省略号被误解为用户原文缺失。
- 生成与导出阶段检查截断提示，并从对应经历原文恢复完整语义。
- 完整性日志位于 `backend/logs/resume_text_integrity.jsonl`，不记录完整用户原文。

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
- 长输入稳定生成：长经历会先本地预处理为 compact context，再使用短 prompt 生成，降低 token 消耗、响应时间和 JSON 截断风险。
- 项目专属表达：清理多个经历之间重复出现的模板句，让通用能力进入个人优势 / 技能栈，具体经历保留差异化细节。
- 弱经历增强：对课程大作业、小项目、学生工作、竞赛参与等薄弱履历进行成长型包装，不伪造成实习或企业项目。
- 正文去负面化：清理“没有实习、未上线、没有获奖、只是作业”等自降表达，缺失事实进入面试准备而不是正式简历。
- Experience ID 边界：每段经历在内部绑定 `EXP-001 / EXP-002`，生成、fallback、guard 和 DOCX 导出前都会尽量按经历身份隔离事实。
- 混合输入语义分段：即使用户没有写标题或换行，系统也会结合新动作、组织、经历类型、主题变化和独立结果谨慎识别多段经历。
- 项目级内容对账：删除重复综合经历前先回收尚未覆盖的有效事实，将技术、指标和职责放回对应 experience_id。
- 候选人视角个人优势：个人优势只呈现事实支撑的已具备能力，求职教练诊断、包装方法和未来准备事项不会进入正式简历。
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

## v0.3.4 长输入低 token 稳定生成

v0.3.4 解决长输入时响应慢、token 消耗高、JSON 截断和偶发无法生成的问题。系统不会把完整长原文和完整长 prompt 一次性丢给模型，而是先在本地做经历分段和关键词提取，再把压缩后的 compact context 交给短 prompt。

主要能力：

- 本地预处理：识别长输入、行数和主要经历段数，提取经历类型、标题、摘要、技术词、证据词和风险词。
- 长输入短 prompt：长输入模式下使用 `prompts/generate_resume_coach_result_long.md`，优先保证 `resume_sections.projects` 和 DOCX 可用。
- 输出控量：三档包装、Claim、面试准备和知识清单保持必要但不冗长，降低输出 token 和截断风险。
- 稳定 fallback：OpenAI 兼容接口失败、JSON 修复失败或 schema 校验失败时，不直接让前端报错，而是基于本地分段生成可用的保底结果。
- 事实边界：fallback 不调用 LLM，不编造学校、专业、公司、用户数、star、并发、奖项、模型训练等硬事实。
- 稳定性日志：每次生成写入 `backend/logs/generation_stability.jsonl`，记录是否进入长输入模式、是否使用短 prompt、是否触发 fallback 和耗时。

## v0.3.5 经历边界与自然承接知识

v0.3.5 解决多段经历之间事实串通，以及简历主体出现“Docker（如有）”“LangGraph（建议掌握）”这类不专业表达的问题。

主要能力：

- 内部 experience_id：长输入预处理会为每段经历生成 `EXP-001 / EXP-002 / EXP-003`，用于隔离事实边界，不暴露给用户。
- 防止跨经历串通：项目 A 的技术、数据、部署、star、用户数、论文、奖项等不会被写进项目 B / 实习 C。
- Supported inference：允许同一段经历内部写入自然承接知识，例如 RAG 测试集可以承接 Top-K、Retrieval、Chunk、Embedding 等表达。
- 面试承接同步：自然承接知识进入简历时，会同步进入 `interview_plan` 或 `knowledge_checklist`，提醒用户补齐解释口径。
- 不确定表达清理：简历主体不保留“如有 / 可补充 / 建议掌握 / 待补充”等口吻；不确定知识会转入面试准备，不写成已实现事实。

## v0.3.7 项目专属表达与重复模板句清理

v0.3.7 解决多经历简历中的另一个真实问题：事实没有串通，但表达仍然可能串通。比如同一句“围绕文档解析、切块、Embedding、向量检索和回答生成梳理 RAG 应用链路”被复制到多个项目、实习或竞赛经历中，会让简历显得模板化，也会让经历边界变得不可信。

主要能力：

- 新增项目专属表达守卫，检查不同经历之间 `intro` / `role` / `details` 的重复句和高度相似句。
- 对完全相同、去标点后高度相似、或包含同一组连续技术短语的表达进行清理。
- RAG、接口联调、组件化、状态管理等自然承接知识仍可写入简历，但必须结合该经历自身任务改写。
- 多个 RAG 经历可以同时保留 RAG，但侧重点必须不同，例如应用开发写检索问答链路，测试集写 Top-K / Recall / Groundedness，部署写服务链路和日志。
- DOCX 导出前也会执行项目专属表达清理，历史生成结果重新导出时同样能减少重复模板句。

## v0.3.8 弱经历用户增强策略

v0.3.8 面向更典型的校园用户：没有实习，只有课程大作业、简单小项目、学生工作、竞赛参与或校级材料。这类用户不是没有价值，而是需要把有限经历整理成“可投递、可解释、可继续补强”的成长型简历表达。

主要能力：

- 识别弱履历信号：输入较短、缺少实习 / 上线 / 用户数 / star / 数据指标、出现课程项目 / 大作业 / 课设 / 小项目 / 学生工作 / 竞赛参与等。
- 课程项目包装为“课程项目 / 软件工程实践 / 独立项目实践”，不写成企业项目。
- 简单小项目会围绕需求理解、页面开发、接口联调、材料沉淀和复盘优化进行正式化表达。
- 学生工作和社团经历会转化为组织协调、沟通推进、活动执行、材料沉淀和结果复盘能力。
- 竞赛参与会保留为竞赛经历，未明确提供奖项时不写“获奖”“排名”或证书。
- 面试准备中加入薄弱履历补强路线，提醒用户补充截图、仓库、PPT、实验报告、课程评分、活动规模等证据材料。

## v0.3.9 简历正文去负面化与实习幻觉防护

v0.3.9 修复弱经历增强后的两个问题：正式简历中不应出现“没有实习”“没有上线”“没有获奖”“只是课程作业”这类负面或自降表达；用户没有明确实习事实时，也不应生成“实习经历”模块。

主要能力：

- 新增简历正文净化器，清理 summary、项目名称、项目类型、项目简介、我的职责和技术细节中的负面表达。
- “没有实习 / 未上线 / 没有获奖”等边界事实不会进入正式简历正文，而是转入面试准备、追问或边界判断。

## v0.4.0 Experience ID 事实边界

v0.4.0 将多经历处理从“生成后修补”推进到“生成前分段、生成中绑定、生成后校验”。

主要能力：

- 每段经历在预处理阶段生成内部 `experience_id`，例如 `EXP-001`、`EXP-002`。
- prompt 中注入 experience_id 边界表，要求模型为每个简历项目绑定 `source_experience_id`。
- `source_experience_id` 只在后端内部使用，不展示给用户，也不会进入 DOCX。
- 后端边界守卫优先按 `source_experience_id` 校验；模型漏填时，再用项目名称、经历类型、技术词、证据词回匹配。
- Resume Section Fallback 和稳定 fallback 也会按 experience_id 逐段生成项目，避免把多段经历兜成一个“综合经历项目”。
- 新增 `backend/logs/experience_boundary.jsonl`，记录经历数、项目 source id 缺失数、跨经历污染修复次数和修复字段。

这一步的目标不是让系统更保守，而是让每段经历独立、真实、可包装、可承接。

## v0.4.1 混合自然语言经历识别

v0.4.1 解决用户把项目、校园活动、社会实践、社团工作和竞赛内容连续写在一段话中时，系统错误生成“综合经历项目”的问题。

- 显式标题仍然优先；没有标题时，后端根据标点、新经历动作、组织或角色变化、经历类型变化、主题变化和独立证据计算分段置信度。
- 功能列表和同一项目的技术链路不会仅因逗号而被拆散；相邻且信息较少的校园活动允许谨慎合并。
- 年级、个人背景和求职意向会从项目候选内容中剥离，不会成为项目名称或技术细节。
- 识别到多个 experience_id 后，LLM 和 fallback 都不能再用一个“综合经历项目”容纳全部内容。
- 无法可靠判断的关系进入 `missing_questions`，不会直接写成确定事实。
- 分段日志写入 `backend/logs/experience_segmentation.jsonl`，只记录长度、类型、置信度和截断标题，不记录完整用户原文。

## v0.4.2 项目级内容对账

v0.4.2 坚持“不过分修饰，也不刻意删减”：当模型已经生成具体项目，而 fallback 又产生“综合经历项目”时，系统不会直接保留重复项目，也不会把其中的有效细节一并删除。

- 修复空行在预处理阶段被压平的问题，并补充“独立设计 / 从零开发 / 在某公司实习”等经历起始信号。
- fallback 在已有项目时只补充未覆盖的 experience_id，不再从完整原文追加综合经历。
- 新增项目级 reconciliation：逐条判断综合经历中的技术、指标和职责属于哪个 experience_id，未覆盖的高价值细节回填到对应项目，重复和无来源内容不进入正文。
- source_experience_id 匹配不足时保持未绑定，不再按项目顺序强行绑定 EXP-001。
- 内容预算为单项目最多 8 条、主要项目合计最多 18 条，优先保留各项目基础信息，再分配剩余篇幅，服务最多两页 DOCX。
- generation 和 docx_export 都执行项目对账，历史结果重新导出时也能清理综合经历。
- 对账日志写入 `backend/logs/resume_project_reconciliation.jsonl`，仅记录数量、ID 和截断项目名，不记录完整用户原文。
- “只是课程作业”“简单小项目”“写了几个页面”“调了一些接口”等不专业原话会改写为“课程项目”“个人项目实践”“页面开发与交互流程实现”“接口联调与数据流转校验”。
- fact guard 增强实习幻觉防护：原文没有实习、公司、工作、岗位等线索时，`meta=实习经历` 会被降级为课程项目、个人项目、校园 / 社团经历、竞赛经历或项目经历。
- DOCX 导出前也执行正文净化和事实守卫，历史结果重新导出时同样不会把缺点写进正式简历。

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
- 长输入稳定性日志：`backend/logs/generation_stability.jsonl`
- 经历边界守卫日志：`backend/logs/experience_boundary.jsonl`
- 混合输入分段日志：`backend/logs/experience_segmentation.jsonl`
- 项目级内容对账日志：`backend/logs/resume_project_reconciliation.jsonl`
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

查看最近长输入稳定性日志：

```bash
tail -n 50 backend/logs/generation_stability.jsonl
```

查看最近经历边界守卫日志：

```bash
tail -n 50 backend/logs/experience_boundary.jsonl
```

查看最近混合输入分段日志：

```bash
tail -n 50 backend/logs/experience_segmentation.jsonl
```

查看最近项目级内容对账日志：

```bash
tail -n 50 backend/logs/resume_project_reconciliation.jsonl
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
