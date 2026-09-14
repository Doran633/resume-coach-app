# v0.9.16.2 Canonical Model Output Evidence Contract

## Scope and evidence

Baseline: main / 9918d964 / v0.9.16.1. This patch changes the model-return to initial-projection contract, not upstream eligibility or downstream recovery authority.

Historical requests 224/225/226 supply exact raw inputs and request identifiers. Their original model responses are unavailable. The fixture `tests/fixtures/v09162_request_inputs.json` preserves those inputs; controlled JSON responses are new experiments, not historical response snapshots. No paid model, production database, deployment, commit or push was performed.

Default business scope: generation_service.py, fact_guard_service.py and experience_slot_service.py. Approved extensions: result_cleanup_service.py for existing cleanup/source alignment, and resume_body_sanitizer_service.py for intro attachment preservation only. No new business module, IR, classifier or recovery was added. Existing test expectations were not changed.

## Failure and correction

| Boundary | Before | After |
| --- | --- | --- |
| generation_service.normalize_llm_payload | Project reconstruction discarded candidate owner and field attachments. | Whitelisted declarations survive; original detail indices carry Fact/Claim rows. Model-declared freeze flags are discarded. |
| experience_slot_service.validate_model_project_evidence | Owner identification did not establish field support. | Same-request ownership, eligibility, ID existence, Claim lineage and deterministic text support are checked before initial projection. |
| result_cleanup_service._clean_projects | Existing display cleanup reconstructed fields without consistent source rows. | Text and sources are transformed together; deleted or materially changed fields cannot retain evidence. Existing limits and cleanup policy are unchanged. |
| fact_guard_service | Field cleanup could discard legitimate attachments independently of surviving text. | Unchanged fields keep validated evidence; changed/deleted fields lose stale evidence. |
| resume_body_sanitizer_service | Surviving intro did not consistently participate in provenance preservation. | Intro attachments survive only with unchanged nonempty intro and participate in aggregate maintenance. No new rewrite authority. |
| experience_slot_service owner binding | Earlier candidates could occupy an owner regardless of evidence quality. | Existing validity/ownership rules plus verified support determine processing priority, with deterministic ties. Display order is unchanged; no attachments move between different bodies. |

Partial-invalid-field regression: a bad detail must not clear the owner of an independently valid intro/role. Invalid owner declarations are removed when no validated field evidence remains; independent valid fields retain their provenance.

## Contract limits

Model-declared IDs are not trusted evidence. Project aggregate source_fact_ids are not intro/role proof. Validation accepts literal resume_ready_text and supported literal multi-Fact composition, with limited whitespace/terminal punctuation normalization. It does not prove arbitrary semantic rewrites, similarity matches, identical numbers or shared technical vocabulary.

Missing or unverifiable references remain unresolved, without guessed bindings. Planner remains non-guessing, Coverage does not invent bindings, Gate remains read-only, and Router permissions are unchanged. Unknown or competing candidates do not acquire automatic recovery rights.

The existing real model protocol does not require complete field-level Fact/Claim rows and still permits free expression. Therefore normal model responses are NOT guaranteed to satisfy this contract. Controlled legal-reference tests demonstrate preservation and validation, not universal real-model coverage. Changing that protocol or eligibility requires a separate approved scope.

## Validation

The initial controlled reproduction had 20 failures and 3 passes. The final dedicated suite has 39 passes; final full pytest has 895 passes (540 existing deprecation warnings, final rerun 18.13 seconds). The final golden/DOCX selection has 49 passes and 846 deselected tests. In-memory Python compilation of all 97 backend/app Python files plus the dedicated test passed (98 files total), without writing bytecode. git diff --check passed; Git emitted only configured LF-to-CRLF conversion warnings.

Tests exercise actual normalization, cleanup, Guard, Binder and Planner. Network responses are controlled; Binder output is not injected. Memory SQLite and temporary DOCX output isolate save/render tests. The three exact inputs retain 2/2/3 owners, with eligible Fact counts 6+6, 6+6 and 6+4+4 in controlled supported-return experiments. Tests verify actual text and Fact/Claim lineage, not only counts.

Coverage includes forged freeze flags, malformed references, cross-owner and ineligible IDs, wrong lineage, valid IDs with unsupported text, missing field evidence, partial invalid fields, original-index filtering, literal one-field/multiple-Fact expressions, candidate order, repeated execution, input/Build immutability, log privacy and save/DOCX consumption.

## Why the architecture had a gap

Canonical input authority and model output evidence are different contracts. A trusted input cannot make a model rewrite trusted automatically. Older display normalizers discarded metadata, while Binder proved owner selection rather than per-field support. The downstream prohibition on guessing was appropriate but exposed this missing producer/transport contract.

Earlier audits focused on excessive mutation authority and input evidence. Some projection tests injected bound payloads through a mocked Binder; input-contract tests inspected prompts or public output structure rather than continuous field lineage. They did not cover the actual return-to-projection boundary. That was an audit/test coverage gap, not proof that each historical failure had the same cause.

## NEW_FINDING and remaining limits

- Request 225's planned multilingual-title research is still classified eligible upstream. This patch consumes existing eligibility without endorsing or changing it.
- Hard Fact Guard still has global raw-input keyword evidence in its legacy checks; this patch does not replace that policy.
- Existing cleanup project/detail limits remain unchanged. Downstream rewriting/deletion policies are not comprehensively closed here.
- Missing or unverifiable model evidence may still cause unresolved projection gaps. No final Trace critical is not equivalent to quality acceptance.
- Exact historical model responses are missing. No production or paid-model acceptance was run locally.

## Rollback

Review and revert the eventual complete patch commit on a normal branch if necessary; do not selectively remove validation while retaining its dependent consumers. No database migration or public schema change is involved. Preserve unrelated user edits; do not use reset --hard. Restore release metadata to the checked-out release and rebuild/restart when deploying a rollback.

## Local and server operations

The following commands are manual operations, not actions performed by this patch. Execute each numbered section separately; stop on any failure. A smoke pass does not replace real-input ownership and text verification.

### 1. Local validation and startup (PowerShell)

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
& D:\Anaconda\python.exe -X utf8 -B -m pytest tests/test_v09162_model_output_evidence_contract.py -q -p no:cacheprovider
& D:\Anaconda\python.exe -X utf8 -B -m pytest -q -p no:cacheprovider
git diff --check
```

Optional local backend, using mock mode and a separate local database (not production). This startup itself may create local runtime logs/files. It was not run during this patch:

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app\backend
$env:APP_ENV="development"
$env:LLM_MODE="mock"
$env:REDIS_URL=""
$env:DATABASE_URL="sqlite:///$($env:TEMP.Replace('\','/'))/resume-coach-v09162-local.db"
& D:\Anaconda\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

In a separate terminal:

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app\frontend
$env:VITE_API_BASE_URL="http://127.0.0.1:8001"
pnpm dev
```

Use another available port and update the frontend API address together if 8001 is occupied. Mock startup is not real model acceptance.

### 2. Local review, commit and push (manual)

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
git status --short
git add -- README.md VERSION docs/version-history.md docs/canonical-model-output-evidence-contract.md backend/app/services/generation_service.py backend/app/services/fact_guard_service.py backend/app/services/experience_slot_service.py backend/app/services/resume_body_sanitizer_service.py backend/app/services/result_cleanup_service.py tests/test_v09162_model_output_evidence_contract.py tests/fixtures/v09162_request_inputs.json
git diff --cached --stat
git commit -m "preserve and validate canonical model output evidence"
git push origin main
```

Review the staged list before committing. Do not include unrelated changes or the server's untracked `a` file.

### 3. Server login and pull

From the local terminal:

```bash
ssh root@47.116.25.130
```

After login:

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
git status --short
git diff --quiet
git diff --cached --quiet
git pull --ff-only origin main
test "$(tr -d '\r\n' < VERSION)" = "0.9.16.2"
git log -1 --oneline
)
```

A tracked-file change stops this block; inspect and preserve it, do not reset it. `?? a` alone is untracked and does not imply a failed pull. Do not delete it automatically. Parentheses run a fail-fast subshell without closing the SSH session on failure.

### 4. Build frontend

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
test "$(tr -d '\r\n' < VERSION)" = "0.9.16.2"
test -f frontend/.env.production
set_kv() {
  if grep -q "^$2=" "$1"; then
    sed -i "s|^$2=.*|$2=$3|" "$1"
  else
    printf '\n%s=%s\n' "$2" "$3" >> "$1"
  fi
}
set_kv frontend/.env.production VITE_APP_VERSION 0.9.16.2
set_kv frontend/.env.production VITE_BUILD_COMMIT "$(git rev-parse HEAD)"
set_kv frontend/.env.production VITE_BUILD_TIME "$(date -Iseconds)"
cd frontend
pnpm build
)
```

### 5. Backend metadata and restart

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
test "$(tr -d '\r\n' < VERSION)" = "0.9.16.2"
test -f /etc/resume-coach/resume-coach.env
nginx -t
set_kv() {
  if grep -q "^$2=" "$1"; then
    sed -i "s|^$2=.*|$2=$3|" "$1"
  else
    printf '\n%s=%s\n' "$2" "$3" >> "$1"
  fi
}
set_kv /etc/resume-coach/resume-coach.env APP_VERSION 0.9.16.2
set_kv /etc/resume-coach/resume-coach.env BUILD_COMMIT "$(git rev-parse HEAD)"
set_kv /etc/resume-coach/resume-coach.env BUILD_TIME "$(date -Iseconds)"
systemctl restart resume-coach-backend
systemctl reload nginx
)
```

### 6. Verify running release

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

Confirm version 0.9.16.2 and commit equal the deployed checkout. Brief restart 502 is not a successful readiness result; persistent failures require service diagnosis.

### 7. Dedicated regression and public smoke

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python -B -m pytest tests/test_v09162_model_output_evidence_contract.py tests/test_v0916_canonical_model_evidence.py -q -p no:cacheprovider
DEPLOY_COMMIT="$(git rev-parse HEAD)"
REPORT_DIR="backend/reports/v09162-$(date +%Y%m%d-%H%M%S)"
.venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode shallow --expected-version 0.9.16.2 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-shallow-latest.json"
ENABLE_FULL_SMOKE=true .venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode full --expected-version 0.9.16.2 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-full-latest.json"
```

Run full smoke only when ready for a real generation/model call on the server. Let it finish. After an interruption, do not treat a report from an older run as current acceptance.

### 8. Correlate the same attempt

```bash
REQ="$(.venv/bin/python -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8')).get('request_id') or '')" "$REPORT_DIR/public-smoke-full-latest.json")"
ATTEMPT="$(.venv/bin/python -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8')).get('attempt_id') or '')" "$REPORT_DIR/public-smoke-full-latest.json")"
test -n "$REQ" && .venv/bin/python scripts/list_recent_quality_incidents.py --request-id "$REQ" --json
test -n "$ATTEMPT" && .venv/bin/python scripts/list_semantic_mutations.py --attempt-id "$ATTEMPT" --show-transitions
test -n "$ATTEMPT" && .venv/bin/python scripts/list_canonical_projection_gaps.py --attempt-id "$ATTEMPT"
test -n "$ATTEMPT" && grep -F "$ATTEMPT" backend/logs/experience_slot_binding.jsonl
```

Record actual issue codes and model_evidence reason counts, not only final severity or the generic smoke failure code. The quality-incident script accepts request-id, not attempt-id.

### 9. Real-input acceptance

Print the exact input fixtures and their original parameters:

```bash
.venv/bin/python -c "import json; rows=json.load(open('tests/fixtures/v09162_request_inputs.json',encoding='utf-8'))['requests']; [print('\nRESULT_INPUT',r['result_id'],'TARGET',r['target_role'],'MODE',r['mode'],'PACKAGING',r['packaging_level'],'\n'+r['raw_input']) for r in rows]"
```

Submit each through the existing webpage, recording the NEW request/attempt/result/file IDs. These are new experiments, not replayed historical responses. Check 2/2/3 owner scopes and local fact ownership; fixed top-5 results, team prize and PR quantities must retain their meaning. 82 registration records must not become 82 unique users. Inspect saved fields and DOCX together. Treat the known planned-content eligibility issue as unresolved rather than changing the acceptance standard. An unverified free rewrite must not acquire trusted attachments merely because its IDs are legal.
