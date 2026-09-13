# v0.9.15 Experience Input Partition Consolidation

## Baseline and Evidence

- Branch: `main`; starting commit: `3adbd620`; starting version: `0.9.14.1`. Working tree was clean after permission-aware Git inspection.
- Applicable `C:/Users/lbc/AGENTS.md` was read. No additional repository AGENTS/harness was found. The existing root `conftest.py`, fixtures, generation integration tests and golden evaluator were used.
- All reproductions below are current-code fixed-input experiments, not historical production request snapshots. No paid model, production database, deployment, commit or push was performed.
- The exact historical internet A-E request texts for DOCX v154-v158 were not available as versioned fixtures. Those documents were not reverse-engineered into requests. Internship controls in the new test are new experiments.
- Existing full ecommerce and `v09141_ecommerce_a` through `e` fixtures are reused unchanged.

## Before and After

| Reproduction | Before | After |
| --- | --- | --- |
| Background + front/back-end development internship + course project | Internship title rejected by a substring deny-list; only course owner survives | Both real experiences survive; background and skills stay outside owners |
| Nine explicitly titled projects | Semantic segmentation yields nine; adapter/Identity yields eight | All nine reach Identity; no default identification cap |
| Project B integrates with named project A | Adapter moves B's paragraph into A without correcting spans | Paragraph remains in B with original coordinates |
| Course title with `个人项目，负责接口开发` | Heading-only predicates discard the whole body | One identity preserves the action text |
| Background removal / paragraph joins / leading whitespace | Reconstructed text carries offsets into a different string | `raw_input[start:end] == identity.raw_text` in the regression corpus |
| Logging enabled during Long Input preparation | Segmentation executed for logging, then again for adaptation | One result supplies log and adaptation; Identity reuses the context |

The initial new suite produced **13 failures and 7 passes**, before business edits. The identity-filter call itself is also checked using an already constructed context, rather than attributing every upstream drop solely to Identity.

## Callers and Authority

```text
generation.create_generation
  -> analyze_long_input
     -> segment_semantic_experiences (one partition result)
        -> existing structured or prose path
        -> existing segmentation log
     -> split_experience_segments (adapter only)
     -> enrich_segments / LongInputContext
  -> build_canonical_semantic_build(long_input_context=...)
     -> build_experience_identities (no second heading filter)
     -> unchanged Claim / Type / Name / Time / Header / Ledger processing
```

The existing adapter is also called by legacy context helpers and tests. Its callable API remains; `max_segments` is optional with no default cutoff. An explicitly requested limit now raises `ValueError` when exceeded rather than silently returning partial data. No current production caller supplies that limit.

Removed: the adapter's independent heading parser, title-based paragraph redistribution, second heading-only filter, default eight-segment slice, Identity's duplicate filter, and the semantic service's short-campus-length merger. Existing boundary scores and independent-anchor requirements remain. Related heading/body handling remains in segmentation, with final bodies selected from original ranges.

Explicit header names remain separate metadata. Experience body spans describe the actual body slice, rather than pretending header offsets are body offsets. This version does not rewrite Name/Time/Header extraction rules.

## Approved Scope Adjustments

### Legacy internship title

The full suite exposed `test_v04_quality_regression` losing an internship position: the corrected structural label recognition makes `某科技公司 AI Agent 开发实习` a structure marker, but legacy `resolve_resume_titles` formerly required all title claims to be eligible facts.

User approved the narrow additional file `resume_title_format_service.py`. Its legacy branch can consume a confirmed, positive, non-planned structural title from an explicit heading. It does not upgrade the claim to eligible, change owner, or modify the Canonical resolver. Negative, uncertain and planned semantics remain excluded from this allowance.

### Ambiguous detached self-introduction

The unchanged `v060_duplicate_regression_project` input ends project B with a separate paragraph independently introducing project A by its exact full name. The old adapter moved this paragraph. User approved treating it as ambiguous instead.

The existing segmentation result now carries `ambiguous_source_spans`, a count/log code `AMBIGUOUS_EXPERIENCE_SUPPLEMENT`, and existing clarification questions. The original request is unchanged. The conflicting supplement is not assigned to either owner before confirmation. Ordinary `与项目A对接...` references remain inside project B. This is not a general text-similarity router: only a terminal detached self-introduction naming another explicit entity is checked.

A prose context gap also cannot establish an owner by itself. A following clause without an independent anchor stays in a reported pending range instead of being joined across excluded context or receiving a new ID.

The old golden fixture and its output assertions were **not removed or weakened**. The test additionally verifies that the exact supplement remains in the original source, has a pending range, and is not moved to another segment.

## Validation

- Final all-tests run: **732 passed** (including existing DOCX and real mock-generation integration regressions); existing deprecation warnings remain.
- New partition tests plus v0.9.14.1 structured tests: **68 passed**.
- Golden `v057_ai_agent_full_resume`: required-fact coverage 90%, boundary/type accuracy 100%, DOCX ready.
- Golden `v060_duplicate_regression_project`: required-fact coverage 100%, boundary/type accuracy 100%, DOCX ready. Skill-category accuracy remains 50% and its evaluator reports that warning.
- A separate in-memory replay loaded the five original service modules from `git show 3adbd620:...` without changing the checkout. It confirmed the same 90%/100% fact coverage and the same v060 50% skill warning. The new result is not claimed to have passed every golden quality metric.
- Python source compilation and `git diff --check` pass. No existing test cache or user file was deleted.
- Tests use in-memory/temporary databases. Temporary test and golden artifacts are under `C:/Users/lbc/Documents/ChatGPT/GodSu/.tmp-v0915-*`; golden rendering uses the existing temporary DOCX helper.

## Residual Findings and Limits

- `NEW_FINDING-PROMPT-SEMANTIC-REBUILD`: model-input context builders still rebuild semantic state from raw input. This is the planned v0.9.16 scope, not fixed here. The one-partition assertion applies to the main Long Input -> Build path, not every call in an entire generation request.
- `NEW_FINDING-PENDING-QUESTION-DELIVERY`: pending ranges and clarification questions are observable through segmentation and the existing prompt context helper. Canonical Stable Fallback does not currently consume segmentation questions; this release does not guarantee every such question appears in persisted `missing_questions`. Do not treat a reported pending range as a recovered fact or completed user confirmation.
- Standalone background and skill blocks remain in the original request/stored input, outside experience scope. Existing model/skill consumers can still omit them; this version does not add their presentation recovery.
- Free narration remains heuristic. Repeated-name ambiguity detection is deliberately narrow. No promise is made about all unseen headings, arbitrary oral inputs, or word-for-word model output equality.
- Existing downstream projection limits and quality gates remain unchanged. Identifying nine owners does not promise all nine are selected for final presentation.
- Historical server/DOCX correlation and paid-model output for the five internet samples still require the original requests and request/attempt IDs. Local mock success is not server acceptance.

## Files and Rollback

Five business files: the four approved partition services plus the separately approved legacy title adapter. Two tests: new v0915 suite and added assertions in the existing golden suite. Documentation: README, VERSION, version history, this report.

Rollback is the whole v0.9.15 code change, not an individual adapter while leaving new record fields behind. There is no schema/data migration. Do not restore deleted paragraph-moving logic to make one sample green. If rolling back after deployment, prepare a reviewed revert commit, deploy it, restore matching release metadata, and re-run acceptance; do not reset the server worktree or delete input records.

## Local Commit (PowerShell)

Review the diff before staging. These commands do not push. Publish the reviewed commit through your normal workflow before running server pull.

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
git status --short
git diff --check
git add -- README.md VERSION docs/version-history.md docs/experience-input-partition-consolidation.md backend/app/services/semantic_experience_segmentation_service.py backend/app/services/experience_segmentation_service.py backend/app/services/long_input_service.py backend/app/services/experience_identity_service.py backend/app/services/resume_title_format_service.py tests/test_v0915_input_partition_consolidation.py tests/test_golden_resume_regression.py
git diff --cached --stat
git commit -m "consolidate experience input partition authority"
```

## Server Deploy, Build and Restart

Login from your local terminal only; do not SSH to the same server again from its shell:

```bash
ssh root@47.116.25.130
```

On the server, first inspect changes. If README or other files are modified, inspect and preserve them before continuing. Do not run reset/clean or blindly restore a stash. Untracked collisions also make Git pull stop.

```bash
cd /www/wwwroot/resume-coach-app
git status --short
git --no-pager diff --stat
```

Then paste this complete Bash block, including parentheses. It runs in a subshell and stops on the first error. It prints each phase, so an early stop is not mistaken for a successful build. No dependency installation is needed for this release.

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
echo '[1/5] Check tracked changes and update'
git diff --quiet
git diff --cached --quiet
git pull --ff-only origin main
test "$(tr -d '\r\n' < VERSION)" = '0.9.15'
COMMIT="$(git rev-parse HEAD)"
BUILD_TIME="$(date -Iseconds)"
test -f /etc/resume-coach/resume-coach.env
test -f frontend/.env.production
set_kv() {
  if grep -q "^$2=" "$1"; then
    sed -i "s|^$2=.*|$2=$3|" "$1"
  else
    printf '\n%s=%s\n' "$2" "$3" >> "$1"
  fi
}
echo '[2/5] Build frontend'
set_kv frontend/.env.production VITE_APP_VERSION 0.9.15
set_kv frontend/.env.production VITE_BUILD_COMMIT "$COMMIT"
set_kv frontend/.env.production VITE_BUILD_TIME "$BUILD_TIME"
(cd frontend && pnpm build)
echo '[3/5] Check nginx and set backend release metadata'
nginx -t
set_kv /etc/resume-coach/resume-coach.env APP_VERSION 0.9.15
set_kv /etc/resume-coach/resume-coach.env BUILD_COMMIT "$COMMIT"
set_kv /etc/resume-coach/resume-coach.env BUILD_TIME "$BUILD_TIME"
echo '[4/5] Restart backend and reload nginx'
systemctl restart resume-coach-backend
systemctl reload nginx
echo '[5/5] Wait for readiness and verify deployed commit'
READY="$(mktemp)"
trap 'rm -f "$READY"' EXIT
ready=false
for i in $(seq 1 20); do
  if curl -fsS --connect-timeout 5 --max-time 10 https://resume.doran633.com/api/health/ready > "$READY"; then
    ready=true
    break
  fi
  sleep 3
done
test "$ready" = true
cat "$READY"
.venv/bin/python -c 'import json,sys; r=json.load(open(sys.argv[1])); c=r.get("commit", ""); assert r.get("ok") and r.get("version")=="0.9.15" and c and sys.argv[2].startswith(c), r' "$READY" "$COMMIT"
)
```

If readiness fails, inspect `systemctl status resume-coach-backend --no-pager` and `journalctl -u resume-coach-backend -n 80 --no-pager`. A temporary restart-time 502 is not the same as successful readiness. Do not share environment secrets from diagnostic output.

## Server Acceptance

First run deterministic partition/build and old boundary tests; they do not call a paid model:

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python -B -m pytest tests/test_v0915_input_partition_consolidation.py tests/test_v0914_experience_input_boundary.py tests/test_v09141_structured_experience_boundary.py -q -p no:cacheprovider
```

Run smoke separately, without Ctrl-C. Each report is placed in a fresh directory so a previous successful file cannot be mistaken for this run. Full smoke uses the configured live generation service and may incur normal model cost; it has not been run by the local agent.

```bash
cd /www/wwwroot/resume-coach-app
DEPLOY_COMMIT="$(git rev-parse HEAD)"
REPORT_DIR="backend/reports/v0915-$(date +%Y%m%d-%H%M%S)"
.venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode shallow --expected-version 0.9.15 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-shallow-latest.json"
ENABLE_FULL_SMOKE=true .venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode full --expected-version 0.9.15 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-full-latest.json"
```

Full-smoke failures remain failures. Check the exact request and attempt, not a reused result ID:

```bash
REQ="$(.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1])).get("request_id", ""))' "$REPORT_DIR/public-smoke-full-latest.json")"
ATTEMPT="$(.venv/bin/python -c 'import json,sys; print(json.load(open(sys.argv[1])).get("attempt_id", ""))' "$REPORT_DIR/public-smoke-full-latest.json")"
if [ -n "$REQ" ]; then
  .venv/bin/python scripts/list_recent_quality_incidents.py --request-id "$REQ" --json
fi
if [ -n "$ATTEMPT" ]; then
  .venv/bin/python scripts/list_semantic_mutations.py --attempt-id "$ATTEMPT" --show-transitions
  .venv/bin/python scripts/list_canonical_projection_gaps.py --attempt-id "$ATTEMPT"
fi
```

Real-input acceptance: submit the unchanged full ecommerce fixture and A-D separately (E contains only the survey); retain each request/attempt/result ID and export the matching DOCX. Expect three scoped experiences for full/A-D, one for E; 96/89 only in the survey, dates owner-local, no background or skill-block owners. Repeat the new internship control with colon, standalone heading and CRLF, expecting internship plus course project. Compare membership and facts, not word-for-word generated prose. Also verify a normal integration reference remains with its current project. A reported ambiguous self-introduction is pending, not proof of recovered content. Smoke and pytest do not replace these live checks.
