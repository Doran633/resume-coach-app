# v0.9.15.1 Experience Type Evidence Integrity

## Scope and evidence

Baseline: main / bc4ed861 (v0.9.15), clean tracked worktree before this task.
The four supplied internet internship test inputs are preserved in
`tests/test_v09151_type_evidence_integrity.py::SAMPLES`. These are current-code
replays, not exact snapshots of the server requests that exported v159-v162.
No paid model calls, deployment, production database access, or Git commit/push
were performed. The 62% completeness display is explicitly out of scope.

Before: frontend/AI/testing samples froze their internship as project; backend
froze it as open source. All already had two correctly bounded experiences.
The initial regression run was 23 failed / 12 passed before business edits.

The first defect was a missing structural-evidence handoff: occupational
internship headings were correctly excluded from resume Facts but not used as
type evidence. Eligible duties did not repeat the internship relationship.
The second was evidence laundering: Spring matched the PR substring, a
provisional open-source type became a fallback Identity title, and the formal
resolver scored that generated title as an explicit open-source label.

## Changed flow

```
Existing owner block and original heading span
  -> confirmed owner-local structural Claim + eligible duties
  -> existing relation resolver, once per owner per Canonical Build
  -> frozen type decision
  -> existing projection / header / presentation / persistence consumers
```

Only two business files changed:

- `semantic_experience_segmentation_service.py`: PR gets Latin-token boundaries
  (Chinese adjacent text is allowed); no partition threshold, splitting or
  ownership rule changed.
- `experience_type_resolution_service.py`: Canonical scoring excludes generated
  Identity titles. Its existing local heading scan now verifies the same-owner
  structural Claim, original start position, confirmed positive state and
  structure-only exclusion. It shares that check with existing campus handling.
  An occupational internship heading needs eligible duties, not a job whitelist.
  Explicit declared types retain priority. Project implementation inside this
  verified internship is compatible activity, not a competing project type whose
  repeated keywords can defeat the employment context. PR/Pull Request and
  maintainer/contributor matching use token boundaries; contribution relations
  remain necessary when there is no explicit declared open-source type.

Canonical explicit-label scoring through generated title is unreachable; legacy
title/hint behavior remains only for legacy calls without ClaimResolution.
No new runtime module, IR, classifier, guard, observer, or recovery was added.
No Prompt, model call, Name/Time authority, Ledger eligibility, Binder,
Projection, Coverage, Fallback, Gate, Router, DOCX, frontend or API/schema edits.

## Preservation checks

All four samples now freeze as internship + project, including inline, colon
heading lines, no-colon heading lines, blank lines and CRLF variants. Source
spans refer to each variant's own original text; factual signatures remain equal.
The regression calls real Segmentation -> Identity -> Claim -> Type -> Build,
and real mock generation with an isolated in-memory database for persistence.

An in-memory comparison loading baseline functions from Git confirmed all four
samples preserve their full Ledger, Claim resolutions, time decisions and
original owner ranges. Name qualification values and statuses remain unchanged.
For the testing sample's second experience only, the rejected-name reason and
fingerprint change because its provisional fallback title changes from open
source to project. It still has the same pending display value; this is an audit
metadata difference, not a newly invented or lost name.

## Validation

- New targeted suite: 50 tests, including four actual mock generation tests and
  independent confirmed duties alongside future-intention counterexamples.
- Final full pytest: 782 passed, 369 existing datetime deprecation warnings,
  18.83 seconds. All DOCX and old type/boundary/header regressions are included.
- Python compilation: 222 files compiled in memory, no bytecode artifacts.
- git diff --check: passed (Git emits only LF/CRLF checkout-policy notices).
- Existing assertions were not changed.
- Both offline golden cases render DOCX and keep boundary/type accuracy at 100%.
  v057 fact coverage: 90%; v060 fact coverage: 100%.
- v060 skill-category accuracy remains 50%. The baseline two services were loaded
  from Git in memory and reproduced the same metric. This is NOT a fully green
  quality evaluation; it is an unchanged out-of-scope limitation.
- Test runs use LLM_MODE=mock, separate temporary database URLs, and temporary
  output directories. The live model's writing quality has not been tested.

## Remaining findings and rollback

NEW_FINDING-PLANNED-CLAIM: the existing Claim resolver can mark
"计划参与内部业务" as eligible/currently unknown rather than planned. This patch
does not change Claim eligibility or Ledger contents. Canonical type evidence
excludes the prospective clause, not the whole owner: an independent confirmed
duty still counts even when the user also describes a future job intention.
Broader Claim qualification remains separate work.

Existing name/time extraction limitations, 62% completeness, Prompt-side
duplicate semantic preparation and legacy type inference are not fixed here.
This patch does not claim the complete request has only one semantic build.

Rollback is the two business files plus this release's tests/version/docs, using
an explicit revert commit after deployment if needed, not reset/clean or a
database migration. Old persisted revisions are not rewritten. Reverting restores
the old misclassification; compare new requests, not pre-existing exports.

## Local commit (manual)

PowerShell, after reviewing the diff:

```powershell
cd C:\Users\lbc\Documents\Resume-coach\resume-coach-app
git status --short
git add -- backend/app/services/semantic_experience_segmentation_service.py backend/app/services/experience_type_resolution_service.py tests/test_v09151_type_evidence_integrity.py README.md VERSION docs/version-history.md docs/experience-type-evidence-integrity.md
git diff --cached --stat
git commit -m "fix canonical experience type evidence integrity"
git push origin main
```

## Deploy, build and restart (manual)

From your local terminal: `ssh root@47.116.25.130`.
On the server inspect `git status --short` first. Preserve any unrelated changes;
do not reset/clean or blindly apply old stashes. Paste the whole Bash block below,
including parentheses. It stops on the first failure and prints each phase.
No dependency installation is needed for this patch.

```bash
(
set -euo pipefail
cd /www/wwwroot/resume-coach-app
echo '[1/5] Check changes and update'
git status --short
git diff --quiet
git diff --cached --quiet
git pull --ff-only origin main
test "$(tr -d '\r\n' < VERSION)" = '0.9.15.1'
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
echo '[2/5] Build frontend with release metadata'
set_kv frontend/.env.production VITE_APP_VERSION 0.9.15.1
set_kv frontend/.env.production VITE_BUILD_COMMIT "$COMMIT"
set_kv frontend/.env.production VITE_BUILD_TIME "$BUILD_TIME"
(cd frontend && pnpm build)
echo '[3/5] Check nginx and set backend metadata'
nginx -t
set_kv /etc/resume-coach/resume-coach.env APP_VERSION 0.9.15.1
set_kv /etc/resume-coach/resume-coach.env BUILD_COMMIT "$COMMIT"
set_kv /etc/resume-coach/resume-coach.env BUILD_TIME "$BUILD_TIME"
echo '[4/5] Restart'
systemctl restart resume-coach-backend
systemctl reload nginx
echo '[5/5] Verify running release'
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
.venv/bin/python -c 'import json,sys; r=json.load(open(sys.argv[1])); c=r.get("commit", ""); assert r.get("ok") and r.get("version")=="0.9.15.1" and c and sys.argv[2].startswith(c), r' "$READY" "$COMMIT"
)
```

If any phase fails, stop and inspect its error. For readiness failure use
`systemctl status resume-coach-backend --no-pager` and
`journalctl -u resume-coach-backend -n 80 --no-pager` without sharing secrets.

## Acceptance

Run deterministic tests and smoke separately. Full smoke invokes the configured
live service and may incur model costs; do not interrupt it or read an older
report as proof of success. These server commands have NOT been run locally.

```bash
cd /www/wwwroot/resume-coach-app
.venv/bin/python -B -m pytest tests/test_v09151_type_evidence_integrity.py tests/test_v0915_input_partition_consolidation.py tests/test_v09141_structured_experience_boundary.py tests/test_v09121_canonical_experience_type_authority.py -q -p no:cacheprovider
DEPLOY_COMMIT="$(git rev-parse HEAD)"
REPORT_DIR="backend/reports/v09151-$(date +%Y%m%d-%H%M%S)"
.venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode shallow --expected-version 0.9.15.1 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-shallow-latest.json"
ENABLE_FULL_SMOKE=true .venv/bin/python scripts/run_public_smoke_test.py --base https://resume.doran633.com --mode full --expected-version 0.9.15.1 --expected-commit "$DEPLOY_COMMIT" --out "$REPORT_DIR"
cat "$REPORT_DIR/public-smoke-full-latest.json"
```

Print the exact four samples for real webpage submission, without manually
rewriting their contents:

```bash
.venv/bin/python -B -c 'import sys; sys.path.insert(0,"tests"); from test_v09151_type_evidence_integrity import SAMPLES; [print("\n=== "+k+" ===\n"+v) for k,v in SAMPLES.items()]'
```

Submit each separately, with the corresponding frontend/backend/AI/testing
target role, and retain request/attempt/result IDs plus its exported file ID.
Repeat a heading-line and blank-line variant without changing the words. Expect
two identified owners: internship first, project second; company/position fields
on internship, never on the project. Correct types do not guarantee the existing
company/position extraction has all values. Check dates and 12/8, 18/6, 40/15,
24/7 evidence stays with its own owner; no open-source internship merely because
Spring or GitHub appears. Compare the current saved revision and its DOCX.

For a failed or suspicious request, use its actual IDs:

```bash
REQ='replace_with_actual_request_id'
ATTEMPT='replace_with_actual_attempt_id'
.venv/bin/python scripts/list_recent_quality_incidents.py --request-id "$REQ" --json
.venv/bin/python scripts/list_semantic_mutations.py --attempt-id "$ATTEMPT" --show-transitions
.venv/bin/python scripts/list_canonical_projection_gaps.py --attempt-id "$ATTEMPT"
```

Smoke passing does not replace these owner/type/content acceptance checks.
