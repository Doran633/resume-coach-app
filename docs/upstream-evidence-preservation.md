# v0.9.16.1: Upstream Evidence Preservation

## 基线与证据类别

- 基线：main / 34bf7ec26ff66c82cdb5b3e9a821cbab60b77ed6 / v0.9.16。
- 开始时真实工作区干净；受限文件读取导致的旧 pytest 文件删除误报，已用只读 Git 核对排除，未清理或恢复任何用户文件。
- 读取适用的 C:\Users\lbc\AGENTS.md，复用现有 pytest、generation 模型拦截、黄金和 DOCX 测试，不建立新 harness。
- 下表是当前固定输入执行和隔离实验，不是线上历史请求、DOCX 的完整快照。本轮没有生产输入数据库或真实模型返回快照。

## 修改前后

| 当前重放 | 最早错误位置 | 修改前 | 修改后 |
| --- | --- | --- | --- |
| 项目一：文档问答助手。使用Python调用模型生成摘要并记录8条评测结果。以及第二个项目 | segmentation: EXPLICIT_HEADING_PATTERN / find_explicit_experience_boundaries | 整行是 title，body_start 到达正文末尾，两个 owner 消失；名称后仅增加换行则保留 owner | 两个标题与两段正文分别定位，owner、Fact、Claim 原文范围可核对 |
| 团队获得三等奖，我没有负责预测模型设计 | Claim: _claim_clauses / _attributes | 整句 excluded；角色为限制但 polarity 为 positive；模型无奖项事实 | 团队奖项 eligible；本人未设计模型为 negative/denied/excluded；模型分别收到事实与约束 |
| 两组实验都固定返回前5条检索结果，我没有调整返回数量 | 同上 | 固定数量事实随限制一起排除 | 固定数量保留，不改写成调整 Top-K |
| 团队获\n得三等奖 | split_semantic_units | 已确定 owner 内仍按换行截断 | Claim 保留原文完整切片，语义判定用现有 layout normalization |
| 人工提供上述完整带来源 Claim 后单独运行 Ledger | build_experience_fact_ledger_from_components | explicit_heading 再次按行切分，只剩“得三等奖”，团队主体消失 | 显式结构范围复用已有 split_lines=False 处理，原文定位后才规范化 |
| 并非独立完成，只负责页面 | Claim: _attributes / resolve_experience_claims | “并非”未正确否定，“只”被文本清理剥离 | 否定保持为限制；“只负责页面”原样进入 Claim、Fact 和模型事实 |

初始29项专项测试：22失败、7通过。失败已在业务修改前执行。
首次两个业务文件的修复后：28通过、1失败；全量842通过、2失败。
句内换行和旧 maintainer 测试冲突已报告，用户明确批准额外适配后才修改。

## 实际修改范围和权限

1. semantic_experience_segmentation_service.py：只修正显式标题与正文范围、编号区块的适配优先级；保留非经历分区、source span 和既有普通叙述路径。
2. input_claim_resolution_service.py：复用现有主语结构和否定词，修正逗号后的主语否定边界及属性；保留肯定职责的“只／仅”。resolve_claim_eligibility_contract、related_claim_ids 机制未改。
3. input_semantic_role_service.py（获批）：split_semantic_units 增加只由 Claim 调用使用的 preserve_layout 参数；默认 legacy 切分不变。返回源片段，不新增偏移映射系统或分类器。
4. experience_fact_ledger_service.py（获批）：已有 structured 条件同时覆盖 explicit_heading / legacy_explicit_heading，不修改 Fact 重要性、资格、选择或恢复规则。
5. 专项测试、获批的既有模型证据测试、README、VERSION、版本历史与本文。

没有修改 Prompt、模型调用、Type/Name/Time/Header Authority、Binder、Projection、Coverage、Fallback、Gate、Router、下游专业化、DOCX、前端、数据库或公开 API。没有新增业务服务、IR、Observer 或 Recovery。

旧错误路径退出方式：标题匹配不再消费句末标点后的正文；Claim 不再以整句否定代替局部断言；有结构的已选中 Claim 不再按排版换行第二次拆 Fact。并非将这些行为移到另一个恢复模块。

## 回归与验收限制

专项断言覆盖直接原文位置、owner、Fact/Claim、极性、资格及实际模型调用收到的材料；真实 generation 使用内存数据库和截获的模型调用，不 Mock 被检验的语义链路。
复用完整互联网、电子商务 A-E 以及科研/开源/竞赛/校园输入；不从导出文档反推输入。
反例包括否定获奖、入围、非独立完成、可能获奖、计划、指令和可能重复的82条报名记录。
仅改变换行、空行或 LF/CRLF 的已测结构化输入保持实质事实等价；不要求 Fact ID 跨格式相同，不保证任意自由口语和标点组合等价。

最终全量 pytest：**856 passed**，483条既有 datetime 弃用告警；本版本专项41项均包含在其中。相邻版本联合检查通过；单独筛选既有黄金/DOCX测试：**46 passed**。224个Python文件在内存编译通过，不生成字节码；git diff --check通过。

末轮额外固化了“正文日期不能否决已确认标题”的失败：带基本信息前缀、标题后日期范围及逗号时，旧适配检查整行导致0个owner。现检查仅针对标题候选，日期仍保留在本owner正文中，未修改Time Authority。原有v0.9.14无名称区块断言未改。

黄金 v057：经历保留100%，高价值覆盖90%，边界/类型/技能100%，DOCX就绪。
黄金 v060：经历保留、覆盖、边界、类型100%，DOCX就绪；**技能分类仍50%**，是既有不足，未降低标准或报告为完全质量通过。

临时 pytest 文件与黄金报告位于 GodSu 工作区的 .tmp-v09161-* 目录；既有测试可能写入被忽略的本地诊断日志。未连接生产数据库、调用付费模型、部署、提交或推送。

## NEW_FINDING 和残留

- 动作形状的名称仍有边界歧义，例如“测试记录工具”可被既有动作前缀识别当正文。本补丁覆盖“开发者工具平台”的名词化边界，但不宣称所有动作开头名称已解决。长正文长度测试使用“评测记录工具”，隔离长度问题，不将名称歧义掩盖为已修复。
- 独立否定分句不是通用矛盾消解器；“82条记录，其中可能重复”保持受限，不构造通用 Claim 依赖模型，也不推导独立人数。
- 既有共享 Semantic Analysis 的默认 legacy 切分保留；本补丁不统一所有历史消费者，模型材料继续以冻结 Claim/Fact 为来源。
- 上轮审计的全局否定误伤其他 owner、Boundary/Readability 清理后来源不齐、Firewall 子串改写、技术表达越权扩展、名称/岗位和技能缺失仍需各自证据验收。本补丁没有修改这些后处理者，最终简历仍可能受影响。
- 上游保全和测试通过不等于最终输出质量全部通过；必须检查本次真实 attempt 的保存内容和 DOCX，不能拿旧报告或相同 result_id 代替。

## 本地提交（用户执行）

在 Windows 终端执行。先检查下面暂存内容；不要使用 git add .，不要包括临时报告。

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
git status --short
git add -- README.md VERSION docs/version-history.md docs/upstream-evidence-preservation.md backend/app/services/semantic_experience_segmentation_service.py backend/app/services/input_claim_resolution_service.py backend/app/services/input_semantic_role_service.py backend/app/services/experience_fact_ledger_service.py tests/test_v09161_upstream_evidence_preservation.py tests/test_v0916_canonical_model_evidence.py
git diff --cached --stat
git diff --cached --check
git commit -m "preserve upstream experience evidence"
git push origin main
```

## 服务器部署（用户执行，本轮未部署）

### 1. 登录和拉取

```bash
ssh root@47.116.25.130
```

登录后单独执行下段。括号让出错只停止本段，不退出 SSH。
存在已跟踪改动会停止，不自动 stash/reset/覆盖；已有未跟踪文件 a 不删除。

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
git status --short
git diff --quiet
git diff --cached --quiet
git pull --ff-only origin main
test "$(tr -d '\r\n' < VERSION)" = "0.9.16.1"
git log -1 --oneline
)
```

只有看到新提交和 VERSION=0.9.16.1 后继续；拉取错误时不要修改版本环境变量冒充部署。

### 2. 构建前端

本补丁没有前端代码变更，重建只更新既有发布标识。不要输出整个环境文件。

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
test "$(tr -d '\r\n' < VERSION)" = "0.9.16.1"
test -f frontend/.env.production
set_kv() {
  if grep -q "^$2=" "$1"; then
    sed -i "s|^$2=.*|$2=$3|" "$1"
  else
    printf '\n%s=%s\n' "$2" "$3" >> "$1"
  fi
}
set_kv frontend/.env.production VITE_APP_VERSION 0.9.16.1
set_kv frontend/.env.production VITE_BUILD_COMMIT "$(git rev-parse HEAD)"
set_kv frontend/.env.production VITE_BUILD_TIME "$(date -Iseconds)"
cd frontend
pnpm build
)
```

构建失败先停止；chunk size 提醒不等于构建失败。

### 3. 后端标识与重启

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
test "$(tr -d '\r\n' < VERSION)" = "0.9.16.1"
test -f /etc/resume-coach/resume-coach.env
nginx -t
set_kv() {
  if grep -q "^$2=" "$1"; then
    sed -i "s|^$2=.*|$2=$3|" "$1"
  else
    printf '\n%s=%s\n' "$2" "$3" >> "$1"
  fi
}
set_kv /etc/resume-coach/resume-coach.env APP_VERSION 0.9.16.1
set_kv /etc/resume-coach/resume-coach.env BUILD_COMMIT "$(git rev-parse HEAD)"
set_kv /etc/resume-coach/resume-coach.env BUILD_TIME "$(date -Iseconds)"
systemctl restart resume-coach-backend
systemctl reload nginx
)
```

### 4. 就绪检查

```bash
(
for i in $(seq 1 20); do
  if curl -fsS --connect-timeout 5 --max-time 10 https://resume.doran633.com/api/health/ready; then
    printf '\n'
    exit 0
  fi
  sleep 3
done
systemctl status resume-coach-backend --no-pager
exit 1
)
```

短暂502后恢复可能是重启窗口；持续502必须检查服务。就绪返回版本应是0.9.16.1，commit应对应刚拉取的HEAD。

### 5. 离线专项和在线 Smoke

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python -B -m pytest tests/test_v09161_upstream_evidence_preservation.py tests/test_v0916_canonical_model_evidence.py tests/test_v09141_structured_experience_boundary.py tests/test_v0914_experience_input_boundary.py -q -p no:cacheprovider
```

通过后再执行 shallow。独立目录避免读取旧报告；full 实际会生成测试数据、可能调用线上模型并尝试清理，需等待完成，不按 Ctrl+C。

```bash
DEPLOY_COMMIT="$(git rev-parse HEAD)"
REPORT_DIR="backend/reports/v09161-$(date +%Y%m%d-%H%M%S)"
.venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode shallow --expected-version 0.9.16.1 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-shallow-latest.json"
```

shallow 验证版本与提交；full 使用既有质量标准，不代替发布身份检查：

```bash
ENABLE_FULL_SMOKE=true .venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode full --expected-version 0.9.16.1 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-full-latest.json"
```

若失败，按该次 request/attempt 查询，不仅凭 result_id：

```bash
REQ="$(.venv/bin/python -c "import json; print(json.load(open('$REPORT_DIR/public-smoke-full-latest.json'))['request_id'])")"
ATTEMPT="$(.venv/bin/python -c "import json; print(json.load(open('$REPORT_DIR/public-smoke-full-latest.json'))['attempt_id'])")"
.venv/bin/python scripts/list_recent_quality_incidents.py --request-id "$REQ" --json
.venv/bin/python scripts/list_semantic_mutations.py --attempt-id "$ATTEMPT" --show-transitions
.venv/bin/python scripts/list_canonical_projection_gaps.py --attempt-id "$ATTEMPT"
```

早期网络失败可能尚无 request/attempt，此时先看报告 error_code，不执行空标识查询。

## 真实输入验收

选择相同目标岗位、模式和包装级别，分别提交以下两个新验证输入。B仅在A的名称句号后换行，其余字符相同；不得用手改后的最终简历代替生成结果。

### A：名称和正文同行

```text
项目一：文档问答助手。使用Python调用模型生成摘要并记录8条评测结果。两组实验都固定返回前5条检索结果，我没有调整返回数量。
项目二：记账工具。使用Python完成支出分类并编写12条测试用例。并非独立完成，只负责页面。
```

### B：名称后换行

```text
项目一：文档问答助手。
使用Python调用模型生成摘要并记录8条评测结果。两组实验都固定返回前5条检索结果，我没有调整返回数量。
项目二：记账工具。
使用Python完成支出分类并编写12条测试用例。并非独立完成，只负责页面。
```

上游预期：两个owner分别保留；8条/固定前5条归项目一，12条和“只负责页面”归项目二；未调整、非独立完成保留为约束。检查网页/保存/DOCX对应同次结果；不要求逐字相同。若下游仍删掉固定数量或限定，登记该次issue和首次改变阶段，本补丁不能据此声称完整交付成功。

另用专项中的完整competition_campus输入验收：团队三等奖属于竞赛，未参与预测模型设计不能成为模型设计成果；校园报名记录不提升成独立人数。保留已有互联网和电子商务多经历对照。

## 回滚边界

没有数据库迁移或模型/API协议变更。保留用户工作区后，通过正常审阅的反向提交回退本版本四个业务文件、两份测试及版本文档；重新按上述步骤构建和写入实际版本元数据。不要 reset --hard、恢复其他用户改动或修改旧生成记录。本轮没有自动执行回滚、提交、推送或部署。
