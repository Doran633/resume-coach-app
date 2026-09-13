# v0.9.14.1 Structured Experience Boundary Consistency

## 基线与证据边界

- 基线：main / `6d3e32970d0f7412367b120bf4465a0efe8ab93d` / v0.9.14。
- 开始时实际仓库无未提交改动；在隔离副本实施及运行测试，完成后只同步列明文件。不修改生产数据，不调用付费模型，不部署、不提交或推送。
- A—E 使用此前诊断保存的原文；另复用已有完整 902 字电子商务 fixture。A/B 仅改变换行，B/C 仅删除标题冒号，C/D 仅改变空白。E 是独立的单调查对照，不将其 Fact 集合与 A—D 比较。
- 以下前后对照均为当前代码固定重放，不是历史请求或 DOCX 的完整运行快照。本地 mock generation 可以证明实际后处理与保存链路的确定性行为，不能证明在线模型文案逐字一致。

## 修改前后

最早问题在冻结前的区块识别。旧实现 A/B 找到五个区块标记，C/D/E 无冒号时找不到标记，进入旧逐句评分：基本信息可建 owner，摄影社日期与正文分离，调查与社团混合。B 虽已正确分区，但独立标题可成为 Fact，换行使校园任职关系不匹配。旧路径重拼正文后也可能使来源位置不对应原文。

修改前首批新测试为 15 failed / 6 passed，未改旧断言。修复区块与 Claim 后，句内换行仍暴露 Ledger 二次按换行拆 Fact 的问题；报告该阻塞并获用户批准后，才增加这一处适配。

修改后的重放结果（区间为对应 fixture 的左闭右开原文位置）：

| 样本 | Experience source span | 各 owner eligible Fact 数 | 冻结类型 |
| --- | --- | --- | --- |
| A | [70,179)、[179,301)、[301,426) | 3 / 3 / 3 | 实习、校园/社团、项目 |
| B | [72,182)、[183,306)、[307,433) | 3 / 3 / 3 | 同 A |
| C | [71,180)、[181,303)、[304,429) | 3 / 3 / 3 | 同 A |
| D | [73,187)、[189,316)、[318,448) | 3 / 3 / 3 | 同 A |
| E | [40,184) | 8 | 项目（课程调查） |

A—D 的实质 Fact 文本、归属、eligibility、冻结类型和时间相等。96/89 只在调查 owner；摄影社与调查日期独立。完整输入另有标题换行、句间空行、句内换行及 CRLF 对照，逐 Claim/Fact 核对原文 source span。不要求不同排版中的 Fact ID 相同。

## 实际修改

| 文件 | 职责与最小变化 |
| --- | --- |
| semantic_experience_segmentation_service.py | 共享现有区块标签资格，增加无冒号独立标题行；已确认标题区块直接切片，不重新逐句评分 |
| input_semantic_role_service.py | 结构标题单独归 STRUCTURE_MARKER；区块正文按标点/显式列表切片，普通换行不建新事实；匹配时规范化排版，原文不变 |
| input_claim_resolution_service.py | Claim 保留原文片段和区间，角色及属性判定使用排版规范化文本，避免拆词绕过否定/计划约束 |
| experience_type_resolution_service.py | 同 owner 的 eligible Claim 按规范化文本匹配；校园描述标题加有效本地关系才支持校园类型，不拼接任意 Claim 猜测 |
| experience_fact_ledger_service.py | 已批准适配：仅 labeled_experience 的已选 Claim 不按换行二次拆分；先定位原文，再规范化 Fact 表达，区间按原文长度计算 |

不新增服务或状态真源。未修改 Name/Time/Header、Ledger 选择/重要性/eligibility、Binder、Projection、Coverage、Fallback、Gate、Router、DOCX、前端、Prompt 或公开 schema。Type Decision 仍为唯一冻结类型权威。

## 旧路径如何退出

确认结构标签后，现有 labeled-input 快路径覆盖到下一个合格标题；标题后的逗号、日期、空行及结果不再交给旧逐句评分器决定 Experience。没有合格区块结构的自由叙述仍走原路径，显式多项目标题保持原有优先级。

基本信息、教育/意向、技能仍保存在原始请求中，不改写 raw_input，也不附着到邻近 Experience。教育或技能后续是否充分展示，属于既有消费者职责，本阶段不新增消费者。

## 验证结果

- 新专项：34 passed，含 A—E、完整输入、排版对照、原文区间、否定/不确定/计划/指令换行反例、实际 create_generation 到临时内存数据库保存。
- 全量 pytest：698 passed，329 个既有 datetime.utcnow 弃用警告；包含 Boundary、Identity、Type、Projection、Immutable Revision 和 DOCX 回归。
- Golden Resume / Claim Resolution（mock）：经历保留 100%，类型/边界准确率 100%，高价值事实覆盖率 90%，DOCX 就绪；报告相对基线未发现退化。Claim owner、指令泄露、否定违规及计划完成化计数为 0。
- Python compileall 通过；最终 git diff --check 通过。
- 现有测试预期未修改；未安装依赖，未运行线上 shallow/full smoke。日志、临时数据库及黄金报告仅在隔离测试目录产生，不同步到业务仓库。

## 残留与验收限制

- NEW_FINDING / 已批准并处理：Ledger 对结构化 Claim 的换行二次切分及规范化前后区间长度不一致；没有扩大为事实选择策略修改。
- 非经历信息展示不足、岗位残缺、名称选择、职业方向偏移不在本版修复范围，仍需分别取证。
- 自由叙述路径及其旧来源定位机制保留，不声称本版修复全部无结构输入；不把任意短行、任意断开的标题或英文单词自动解释为同一内容。
- mock 保存链路确认没有把问卷移到摄影社，但线上模型输出仍需 A—E 验收。Smoke 通过仅证明其内置样本，不代表全部真实多经历质量通过。
- 回滚边界为本阶段五个业务文件及对应测试/版本文档；不涉及数据库迁移。提交后可 revert 本阶段提交并重新部署，未提交时不要用 reset/checkout 清掉其他人的改动。

## 本地提交（手动执行）

以下适用于 Windows PowerShell/CMD；不包含既有或临时诊断文件。

```text
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
git status --short
git diff --check
git add backend/app/services/semantic_experience_segmentation_service.py backend/app/services/input_semantic_role_service.py backend/app/services/input_claim_resolution_service.py backend/app/services/experience_type_resolution_service.py backend/app/services/experience_fact_ledger_service.py
git add tests/test_v09141_structured_experience_boundary.py tests/fixtures/v09141_ecommerce_a.txt tests/fixtures/v09141_ecommerce_b.txt tests/fixtures/v09141_ecommerce_c.txt tests/fixtures/v09141_ecommerce_d.txt tests/fixtures/v09141_ecommerce_e.txt
git add README.md VERSION docs/version-history.md docs/structured-experience-boundary-consistency.md
git diff --cached --stat
git commit -m "preserve structured experience boundaries across layout variants"
git push origin main
```

## 服务器部署、构建与重启

先在本地完成提交和推送。登录后不要再次 SSH 到自身。下面括号创建子 shell，某一步失败即停止后续部署；不自动清理服务器改动。

```bash
ssh root@47.116.25.130
```

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
git status --short
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo '服务器存在已跟踪文件改动，请先核对并备份；本次停止部署。'
  exit 1
fi
git pull --ff-only origin main
test "$(tr -d '\r\n' < VERSION)" = 0.9.14.1
COMMIT="$(git rev-parse HEAD)"
BUILD_TIME="$(date -Iseconds)"
set_kv() {
  if grep -q "^$2=" "$1"; then
    sed -i "s|^$2=.*|$2=$3|" "$1"
  else
    printf '\n%s=%s\n' "$2" "$3" >> "$1"
  fi
}
test -f /etc/resume-coach/resume-coach.env
test -f frontend/.env.production
set_kv /etc/resume-coach/resume-coach.env APP_VERSION 0.9.14.1
set_kv /etc/resume-coach/resume-coach.env BUILD_COMMIT "$COMMIT"
set_kv /etc/resume-coach/resume-coach.env BUILD_TIME "$BUILD_TIME"
set_kv frontend/.env.production VITE_APP_VERSION 0.9.14.1
set_kv frontend/.env.production VITE_BUILD_COMMIT "$COMMIT"
set_kv frontend/.env.production VITE_BUILD_TIME "$BUILD_TIME"
(cd frontend && pnpm build)
nginx -t
systemctl restart resume-coach-backend
systemctl reload nginx
)
```

确认新服务就绪（重启初期可能短暂 502；持续失败时停止验收并读 journal）：

```bash
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -fsS https://resume.doran633.com/api/health/ready && break
  sleep 3
done
systemctl status resume-coach-backend --no-pager
# 如未就绪：journalctl -u resume-coach-backend -n 80 --no-pager
```

## 部署后验收

下面专项测试仅用 mock 和临时内存数据库；full smoke 会实际创建并清理测试请求，沿用项目原有开启条件。

```bash
cd /www/wwwroot/resume-coach-app
DEPLOY_COMMIT="$(git rev-parse HEAD)"
.venv/bin/python -B -m pytest tests/test_v09141_structured_experience_boundary.py tests/test_v0914_experience_input_boundary.py -q -p no:cacheprovider
.venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode shallow --expected-version 0.9.14.1 --expected-commit "$DEPLOY_COMMIT"
cat backend/reports/public-smoke-shallow-latest.json
ENABLE_FULL_SMOKE=true .venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode full --expected-version 0.9.14.1 --expected-commit "$DEPLOY_COMMIT"
cat backend/reports/public-smoke-full-latest.json
```

再在网页使用五个 `tests/fixtures/v09141_ecommerce_[a-e].txt` 和完整 `v0914_ecommerce_input.txt`，保持目标岗位/模式/包装强度一致，逐次记录 result_id、request_id、attempt_id。A—D 核对三经历、E 核对一调查；摄影社与调查日期分别归属，96/89 只属于调查，基本信息和技能不建经历。网页与 DOCX 对应同一结果，比较内容归属，不比较字节或措辞完全相等。

```bash
# 填入该次真实请求的 ID，不复用历史 smoke 的 result_id。
REQ='填写本次request_id'
ATTEMPT='填写本次attempt_id'
.venv/bin/python scripts/list_recent_quality_incidents.py --request-id "$REQ" --json
.venv/bin/python scripts/list_semantic_mutations.py --attempt-id "$ATTEMPT" --show-transitions
.venv/bin/python scripts/list_canonical_projection_gaps.py --attempt-id "$ATTEMPT"
```

失败时保留具体 issue_code 和同一请求的阶段记录，不因编号与历史相同就宣称没有回归；不降低 Gate 或 smoke 标准。
