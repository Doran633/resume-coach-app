# v0.9.14 Experience Input Boundary Correction

## 基线与证据

基线为 main / 5d80e48756bc14002f3911d2ffab6bf9796f2aec / 0.9.13.2。
沙箱内起初将不可读取的 `.pytest-*` 显示为删除；沙箱外只读复核确认它们没有实际删除。本版本未触碰这些路径，最终工作区仅包含本版本的 8 个文件变化。
当前代码重放与历史 v143 DOCX 是两类证据；本阶段没有生产请求快照，也没有调用模型。

测试 fixture 完整保留用户的 902 字电子商务输入，仅文件尾增加换行。第一组 9 个回归用例在原代码上全部失败；后补的短正文和无标签背景用例也先复现失败。

| 原始输入版本 | 原代码 | v0.9.14 |
| --- | --- | --- |
| 单段完整输入 | EXP-001 基本信息；EXP-002 实习加社团标题/时间；EXP-003 社团正文加调查和技能 | EXP-001 实习、EXP-002 社团、EXP-003 调查 |
| 只在原有标签前增加空行 | 4 个 owner，仍包含基本信息和最后经历中的技能 | 同样三个真实 owner，事实文本和归属一致 |

修正后原文区间采用 Python 的左闭右开索引：

| Owner | 经历 | 原文区间 | Ledger Fact 数 | 本地日期 |
| --- | --- | --- | --- | --- |
| EXP-001 | 内容运营实习 | [77, 419) | 8 | 2026年6月至2026年8月 |
| EXP-002 | 摄影社宣传 | [419, 633) | 5 | 2025年9月至2026年6月 |
| EXP-003 | 市场营销课程调查 | [633, 811) | 5 | 2026年3月至2026年5月 |

96份回收问卷、89份有效问卷仅在 EXP-003；每个 Claim 的 source span 在本样本中可直接取回同一原文。
原代码的 Fact 数为 3/9/12，其中混入背景、社团标题和技能；不能将这些非经历 Fact 的移除算作真实经历事实丢失。

## 修改与职责

仅两个业务文件变化：

- `semantic_experience_segmentation_service.py`：使用既有 ExplicitExperienceBoundary 结构描述标签位置；区分非经历标题与经历标题，以原文切片构建区块。既有独立标题优先，同一行的完整正文不误当标题；区块内部不再跑一次隐式分段评分。明确的背景/申请意向不作为首个 Experience。
- `experience_segmentation_service.py`：识别这一路径并原样传递内容及 source span，避免随后 legacy 显式匹配或补充段落移动再次改变边界。

没有新业务模块、数据模型或配置开关。既有完整显式标题且没有新的区块切换时继续走旧路径；无标签文本继续使用既有隐式解析，未重写自由口语解析器。
新标签使用类别结构而非样本实体/数字，冒号出现于项目职责、技术栈等字段时不建立新 owner。

非经历区块仅从 Experience 创建范围排除。请求 raw_input 不变，教育、意向、技能内容仍在原始请求和既有输入保存路径中；没有新增技能证据来源，也不承诺它们全部进入最终技能栏。
本版本不修改 Type/Name/Time Authority、Claim/Fact eligibility、Prompt、模型、Fallback、Binder、Projection、Coverage、Gate、Router、数据库或 Web/DOCX。

## 验证结果与残留

- 13 个专项用例，真实 Segmentation → Identity → Canonical Build，无分段/归属 Mock。
- 全量 pytest：664 passed，279 个既有 datetime 弃用告警；包含黄金与 DOCX 回归，既有测试断言未修改。
- 黄金评估（mock）：经历保留率、边界准确率、类型准确率 100%；高价值事实覆盖率 90%；重复与内部泄漏为 0；DOCX ready；报告无基线退化。
- Claim 黄金评估（mock）：eligible Fact 保留率 100%；owner violation 0；critical issue codes 为空。
- Python 编译通过；同步后原项目 13 个专项测试通过，沙箱外完整 git diff --check 通过（仅 CRLF 提示）。
- 测试在不含生产数据库、.env 和密钥的隔离副本中执行；没有模型费用或部署行为。

NEW_FINDING / 验收限制：

1. 正确 scope 下，名称资格仍选择实习中的“一次促销活动”以及社团中的多个活动名称，课程调查名称仍 pending。这是当前重放观察，未修名称权威。
2. 本轮保证独立技能区块不变成 Experience Fact；现有技能证据若仅消费 Ledger，独立技能的最终展示需在后续证据消费阶段核查，不能靠挂入最后一个 owner 解决。
3. Prompt helper 的重复 raw_input 构建本阶段没有修改；真实模型返回、历史 DOCX 对应请求和线上输出尚未验证。
4. 完全自由口语和已有 legacy 清洗后的 span/补充段落移动没有全局重写；当前精确 span 保证覆盖新标签路径及专项样例，不宣布全仓库字符溯源已修复。

## 本地检查与提交

Windows PowerShell，在原项目执行；使用本机可用 Python，无需安装新依赖：

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
python -B -m pytest tests/test_v0914_experience_input_boundary.py -q -p no:cacheprovider
git diff --check
git diff --stat -- backend/app/services/semantic_experience_segmentation_service.py backend/app/services/experience_segmentation_service.py README.md VERSION docs/version-history.md
git add backend/app/services/semantic_experience_segmentation_service.py backend/app/services/experience_segmentation_service.py tests/test_v0914_experience_input_boundary.py tests/fixtures/v0914_ecommerce_input.txt README.md VERSION docs/version-history.md docs/experience-input-boundary-correction.md
git diff --cached --stat
git commit -m "fix experience input boundaries for labeled sections"
git push origin main
```

提交前检查暂存区，仅包含明确的 8 个文件，不包含 `.pytest-*` 测试产物。以上命令供用户执行，本次不自动提交或推送。

## 服务器部署、构建、重启

本地提交并推送成功后登录。已经在服务器时不要再次 SSH 到自身。

```bash
ssh root@47.116.25.130
```

下面整段在服务器执行。拉取或构建失败即停止，不能把旧代码标成新版本。

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
git status --short
git diff --quiet
git diff --cached --quiet
test "$(git branch --show-current)" = main
git pull --ff-only origin main
test "$(tr -d '\r\n' < VERSION)" = 0.9.14
DEPLOY_COMMIT="$(git rev-parse HEAD)"
BUILD_TIME="$(date -Iseconds)"
BACKEND_ENV=/etc/resume-coach/resume-coach.env
FRONTEND_ENV=frontend/.env.production
test -f "$BACKEND_ENV"
test -f "$FRONTEND_ENV"
set_kv() {
  local file="$1" key="$2" value="$3"
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$file"
  fi
}
.venv/bin/python -B -m pytest tests/test_v0914_experience_input_boundary.py -q -p no:cacheprovider
set_kv "$BACKEND_ENV" APP_VERSION 0.9.14
set_kv "$BACKEND_ENV" BUILD_COMMIT "$DEPLOY_COMMIT"
set_kv "$BACKEND_ENV" BUILD_TIME "$BUILD_TIME"
set_kv "$FRONTEND_ENV" VITE_APP_VERSION 0.9.14
set_kv "$FRONTEND_ENV" VITE_BUILD_COMMIT "$DEPLOY_COMMIT"
set_kv "$FRONTEND_ENV" VITE_BUILD_TIME "$BUILD_TIME"
(cd frontend && pnpm build)
nginx -t
systemctl restart resume-coach-backend
systemctl reload nginx
READY=false
for i in $(seq 1 20); do
  if curl -fsS https://resume.doran633.com/api/health/ready | .venv/bin/python -c 'import json,sys; r=json.load(sys.stdin); assert r.get("ok") and r.get("version")=="0.9.14" and r.get("commit") and sys.argv[1].startswith(r["commit"]); print(json.dumps(r))' "$DEPLOY_COMMIT"; then
    READY=true
    break
  fi
  sleep 3
done
test "$READY" = true
)
```

如果停止，先检查 `systemctl status resume-coach-backend --no-pager` 和 `journalctl -u resume-coach-backend -n 80 --no-pager`。不要清理服务端本地改动来强行拉取。

## 部署验收

专项测试会同时运行完整原文、仅换行版、原文区间、问卷归属、非经历区块和内部任务等检查，无模型费用。

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python -B -m pytest tests/test_v0914_experience_input_boundary.py -q -p no:cacheprovider
DEPLOY_COMMIT="$(git rev-parse HEAD)"
.venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode shallow --expected-version 0.9.14 --expected-commit "$DEPLOY_COMMIT"
cat backend/reports/public-smoke-shallow-latest.json
ENABLE_FULL_SMOKE=true .venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode full --expected-version 0.9.14 --expected-commit "$DEPLOY_COMMIT"
cat backend/reports/public-smoke-full-latest.json
```

full smoke 会实际调用线上模型，按现有测试清理其记录。它不能替代电子商务归属验收。
将 `tests/fixtures/v0914_ecommerce_input.txt` 原文和仅在四个既有标签前加空行的版本分别在网页生成一次，记录各自 request/attempt ID。核对三个真实经历的正文归属、日期和问卷数字；名称 pending 不应被误记为边界回归。

```bash
ATTEMPT='这里填某一次网页生成的完整attempt_id'
REQ='这里填同一次网页生成的完整request_id'
.venv/bin/python scripts/list_canonical_projection_gaps.py --attempt-id "$ATTEMPT"
.venv/bin/python scripts/list_semantic_mutations.py --attempt-id "$ATTEMPT" --show-transitions
.venv/bin/python scripts/list_recent_quality_incidents.py --request-id "$REQ" --json
```

按同一次 request/attempt 关联保存结果和 DOCX，不仅靠可能复用的 result ID。出现 critical 必须记录具体 issue code，不降低检查标准。

## 回滚边界

生产改动只有上述两个分段文件，无数据库迁移、无新持久化状态、无双解析器运行开关。需要回退时通过版本控制撤回本版本提交、重建前端版本标识并重启；先保留现场证据，不自动执行 reset 或覆盖未提交变更。
回退不会重算已保存结果；历史生成也不会因部署 v0.9.14 自动修复。本阶段结束后停止，统一证据消费另行规划。
