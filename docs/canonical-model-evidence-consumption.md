# v0.9.16 Canonical Model Evidence Consumption

## Baseline and evidence

Baseline: main / 36ca42622ac46028292331f1d44d876e8f6f1fc8 (v0.9.15.1).
The worktree was clean before this task. Old unreadable pytest directories
initially appeared as deletions under the restricted shell; an elevated,
read-only Git check confirmed no actual deletions. Nothing was reset or cleaned.

These are current-code replays, NOT snapshots of historical server requests.
The four complete internet samples, original ecommerce input, A-E variants,
and the previously supplied research/course, open-source/personal-project,
competition/campus samples are reused. No inputs were inferred from DOCX.

Six regression failures were first recorded by intercepting the real
create_generation -> build_llm_generation -> call_openai boundary. Only the
network call and resource-accounting side effects were stubbed; partition,
Identity, Claim, type and Build logic ran normally against in-memory SQLite.

- Four internet samples froze EXP-001 as internship, while the actual prepared
  prompt repeated a provisional project type twice.
- Prompt preparation called build_segmentation_questions(raw_input), then
  additional Identity/Claim/Ledger/context builders, despite an existing Build.
- The full ecommerce long prompt omitted the graduation/background evidence.
- A separate long-fact test confirms the old fact-context helper selects eight
  facts and slices expressions at 140 characters. Another old context sends
  full expressions, so truncation in that helper alone does not prove a
  historical missing bullet was caused by that slice.

## Scope and data flow

Before:

```text
first partition -> Canonical Build -> Consumer Views
                                     (not supplied to model preparation)
request.raw_input -> legacy Prompt builders -> competing provisional summaries
                  -> normal/long template -> model -> existing delivery
```

After:

```text
first partition (same decisions, plus retained context ranges/questions)
  -> existing LongInputContext -> Canonical Build -> Consumer Views
  -> one deterministic serialization into the existing normal/long template
  -> model; JSON retry reuses that prompt with the existing retry instruction
  -> unchanged binding, presentation, gates, persistence and DOCX
```

Actual business edits, five existing files only:

| File | Change | Authority not added |
| --- | --- | --- |
| generation_service.py | Pass request-local Views to model preparation | No new model calls, fallback, or delivery changes |
| prompt_service.py | Serialize frozen headers, scoped facts and separate constraints/context | No classification, eligibility decision, rewriting, or recovery |
| canonical_consumer_view_service.py | Read existing Claims, questions and context slices | No new state source; no complement-of-owner inference |
| semantic_experience_segmentation_service.py | Record spans at existing non-experience exclusion decisions | No boundary predicate, threshold, numbering or merging change |
| long_input_service.py | Carry those spans and existing questions forward | No extra segmentation or context parser |

The two partition/context files were approved after reporting that the original
three-file scope could not retain background without either reparsing or
silently losing it. Their change is data transport, not a new decision maker.

## Contract

- Owner and type come from Consumer scope; display-ready header fields come
  from the existing compiled Header Decision (itself consuming Name/Time/Type).
  Provisional titles/types are not an alternative model authority.
- Each eligible Fact carries its owner, Fact ID, Claim ID, source ranges,
  complete resume-ready expression and original Claim text. Original Claim
  wording keeps objects, tools, counts and responsibility limitations available.
- Excluded/withheld Claims remain in a separate internal-constraint collection,
  with their existing polarity, certainty, time status and reason. The serializer
  does not re-evaluate their qualification.
- Background and skills are original slices of ranges already classified as
  non-experience. They are not newly declared eligible project facts. Request
  target role, mode and packaging level continue through their existing fields.
- Ambiguous/unassigned gaps are NOT recovered as background. Existing questions
  are passed through. This does not create a new profile parser or promise to
  recover context that the first partition never recognized.
- The original request hash must match the compilation; context ranges must be
  valid and outside owners. A mismatch fails before the model call, without a
  legacy raw-input rebuild fallback.
- No eight-fact cap or 140-character expression slice is used in Canonical
  model preparation. Compact JSON avoids unnecessary indentation overhead.
- Templates and packaging/risk instructions are byte-for-byte unchanged.
  Old template data slots reference the single evidence block rather than
  independently rebuilding summaries.
- Independent legacy build_generation_prompt/build_llm_generation callers
  without Views remain compatible. Canonical create_generation always supplies
  Views. This does not claim every other historical API has been removed.
- No second IR, runtime service module, Observer, Recovery, public API/schema,
  database migration, frontend change, or DOCX change was introduced.

## Validation

- Initial current-code test run: six intended failures, before business edits.
- Final full pytest: **815 passed**, 459 existing datetime deprecation warnings.
  New专项 suite: **33 tests**. Existing assertions were not edited.
- Actual model-call interception verifies headers/types, full Fact/Claim content,
  owner isolation, background ranges, normal/long equivalence, repeated output,
  forbidden Prompt-stage semantic rebuild, separate constraints and retries.
- An offline fixed model return is exercised through real generation and
  persistence; it is NOT an assessment of live model writing. Existing golden
  and DOCX regression paths also pass.
- In-memory loading of baseline Git code compared 13 complete samples/variants:
  all old partition fields, Identity, Ledger, Claim resolutions, type/name/time/
  header decisions and semantic state are equal. Only new context transport
  fields differ. No source checkout or rollback was used for this comparison.
- 223 Python files compiled in memory; no bytecode build artifacts required.
- git diff --check passes. Checkout-policy LF/CRLF notices are not errors.
- Offline v057 golden: fact coverage 90%, boundary/type/skill accuracy 100%,
  DOCX ready. Offline v060: fact coverage and boundary/type accuracy 100%,
  skill accuracy remains **50%**, DOCX ready. That known baseline limitation
  is not reported as fully green quality or changed to make this release pass.
- No paid model, production database, deployment, automatic commit or push.

Temporary comparison script, isolated test directories and golden reports were
created outside the repository under the local GodSu workspace. They are not
runtime modules or files to commit. Existing tests may write ignored local
diagnostics; no production business records were used or changed.

## Remaining findings and acceptance limits

1. **NEW_FINDING-CLAIM-ELIGIBILITY**: "我不是项目维护者" can still be an eligible
   Claim/Fact upstream. A regression explicitly records that this serializer
   does not secretly reclassify it. Truly excluded constraints are separated,
   but perfect semantic constraint isolation cannot be claimed while the
   upstream qualification is wrong. Fixing Claim rules needs separate scope.
2. Existing ambiguous names, missing company/position values, presentation
   selection and professionalization behavior are unchanged. Receiving complete
   evidence does not prove the model will choose or express every fact correctly.
3. Across the 13 replays the full prompt grows about 5%-26% in characters because
   complete evidence, provenance and background are retained. The full ecommerce
   input changes from 14,424 to 18,232 prompt characters. This is NOT a token/cost
   measurement. Existing request/model limits are unchanged; live token usage
   and output completeness need acceptance without silently truncating evidence.
4. Old normal/long templates retain their different writing/length instructions.
   Only their evidence source is now identical. This release does not promise
   word-for-word equal output, nor close all postprocessing writing permissions.
5. Historical DOCX symptom attribution remains unproven without matching request,
   model response and revision records. Smoke passing is not content acceptance.

## Rollback

This is one coherent code release: revert the five service files and its
test/version/docs together using a reviewed revert commit, rebuild metadata,
and restart. No database or saved-delivery migration is required. Do not remove
only the two context transport changes while leaving their consumer active.
No reset/clean, stash pop, dependency installation, or forced push is needed.
Old saved revisions are not rewritten; compare newly generated requests.

## Local commit and push (manual)

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
git status --short
git add -- backend/app/services/generation_service.py backend/app/services/prompt_service.py backend/app/services/canonical_consumer_view_service.py backend/app/services/semantic_experience_segmentation_service.py backend/app/services/long_input_service.py tests/test_v0916_canonical_model_evidence.py README.md VERSION docs/version-history.md docs/canonical-model-evidence-consumption.md
git diff --cached --stat
git commit -m "unify canonical model evidence consumption"
git push origin main
```

## Server deployment, build and restart (manual)

From the local terminal: `ssh root@47.116.25.130`.
After login, paste the complete Bash block, including parentheses. It stops at
the first error. Preserve unrelated changes; do not clean unknown files or
blindly restore old stashes. No dependency changes are needed.

```bash
(
set -Eeuo pipefail
trap 'echo "Deployment stopped; inspect the preceding error." >&2' ERR
cd /www/wwwroot/resume-coach-app
echo '[1/5] Check and pull'
git status --short
git diff --quiet
git diff --cached --quiet
git pull --ff-only origin main
test "$(tr -d '\r\n' < VERSION)" = 0.9.16
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
set_kv frontend/.env.production VITE_APP_VERSION 0.9.16
set_kv frontend/.env.production VITE_BUILD_COMMIT "$COMMIT"
set_kv frontend/.env.production VITE_BUILD_TIME "$BUILD_TIME"
(cd frontend && pnpm build)
echo '[3/5] Check nginx and set backend metadata'
nginx -t
set_kv /etc/resume-coach/resume-coach.env APP_VERSION 0.9.16
set_kv /etc/resume-coach/resume-coach.env BUILD_COMMIT "$COMMIT"
set_kv /etc/resume-coach/resume-coach.env BUILD_TIME "$BUILD_TIME"
echo '[4/5] Restart'
systemctl restart resume-coach-backend
systemctl reload nginx
echo '[5/5] Wait and verify release'
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
.venv/bin/python -c 'import json,sys; r=json.load(open(sys.argv[1])); c=r.get("commit", ""); assert r.get("ok") and r.get("version")=="0.9.16" and c and sys.argv[2].startswith(c), r' "$READY" "$COMMIT"
)
```

On failure inspect `systemctl status resume-coach-backend --no-pager` and
`journalctl -u resume-coach-backend -n 80 --no-pager`; do not share secrets.

## Server acceptance

Full smoke uses the live configured model and can incur cost. Do not interrupt
it, and do not mistake an old report for the current attempt. These commands
have NOT been run by the agent.

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python -B -m pytest tests/test_v0916_canonical_model_evidence.py tests/test_v09151_type_evidence_integrity.py tests/test_v09141_structured_experience_boundary.py -q -p no:cacheprovider
DEPLOY_COMMIT="$(git rev-parse HEAD)"
REPORT_DIR="backend/reports/v0916-$(date +%Y%m%d-%H%M%S)"
.venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode shallow --expected-version 0.9.16 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-shallow-latest.json"
ENABLE_FULL_SMOKE=true .venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode full --expected-version 0.9.16 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-full-latest.json"
```

Print existing exact samples for separate webpage submissions:

```bash
.venv/bin/python -B -c 'import sys; sys.path.insert(0,"tests"); from test_v0916_canonical_model_evidence import SAMPLES,MULTI_TYPE,FULL; [print("\n=== "+k+" ===\n"+v) for k,v in {**SAMPLES,**MULTI_TYPE,"ecommerce":FULL}.items()]'
```

Select the intended target role explicitly. Retain the actual request/attempt/
result/file IDs; smoke cleanup can allow result/file ID reuse. Four internet
cases should preserve internship + project; research/course, open-source/
personal project and competition/campus should retain their respective owners.
Ecommerce should retain three owners, with 96/89 only in the course survey.
Check each owner's dates and metrics, receipt of background/skills, constraint
leakage, and the same saved revision's DOCX. Repeat a heading-line/CRLF variant
without changing wording. Do not infer prompt correctness from a DOCX alone.

For one failed request:

```bash
REQ='replace_with_actual_request_id'
ATTEMPT='replace_with_actual_attempt_id'
.venv/bin/python scripts/list_recent_quality_incidents.py --request-id "$REQ" --json
.venv/bin/python scripts/list_semantic_mutations.py --attempt-id "$ATTEMPT" --show-transitions
.venv/bin/python scripts/list_canonical_projection_gaps.py --attempt-id "$ATTEMPT"
```

Report remaining concrete issue codes without relaxing Gate/smoke standards.
This release stops before v0.9.17.
