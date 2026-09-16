# Canonical Post-Processing Evidence Preservation

## Baseline and evidence

- Version: 0.9.17.5. Baseline: main, 7ee52e611dbdc25024238b70ce0e0184624249a9, VERSION 0.9.17.4.2. Initial worktree was clean.
- Applicable ancestor instructions: C:/Users/lbc/AGENTS.md. Root conftest.py and existing receiver/isolation test helpers were inspected. No repository-specific harness file was found.
- Evidence below is current-code controlled execution, plus three newly authorized provider requests. It is not reconstruction of historical model responses or historical DOCX requests.
- Only network responses are controlled in offline generation tests; actual segmentation, Build, receiver, Binder, projection, postprocessing, Gate, persistence and DOCX execute against isolated data. Budget/log/output paths are isolated too.

## Before and after

| Control | Earliest observed baseline change | Current result |
| --- | --- | --- |
| Nine distinct eligible Facts, all in details | Reconciliation reduced nine to eight, losing EXP-001-F009 | Nine remain through observed stages, persistence and DOCX |
| Twenty-one details across three owners | Reconciliation total budget lost EXP-003-F007 | Twenty-one remain |
| Same Facts distributed among intro/role/detail | Previously avoided the same detail budget | Same complete fact set regardless of placement |
| Same Fact/Claim on two texts, one with a local-demonstration limitation | Legacy cluster dedup selected one row by information score | Cluster writer no longer called in Canonical generation; exact dedup preserves differing texts |
| Unsourced, nonnumeric activity work | Legacy increment removed the detail | Canonical preserves text and missing attachments without promoting trust |
| Valid named product containing the comprehensive-experience substring | Old Reconciliation predicate matches that name | Canonical bypasses that predicate; real Build and receiver retain the product |

The initial fifteen end-to-end controls had two business failures and thirteen passes. Observer-harness tuple handling and snapshots taken before input-row metadata association were corrected as harness defects, not counted as business failures. A later cluster counterexample justified the separately approved call exit. That defensive downstream counterexample is not a valid model placement response.

## Actual files and callers

Only three business files changed:

1. `generation_service.py`: removes early duplicate dedup and the Canonical calls to `layer_resume_sections`, `ensure_resume_fact_increment`, `ensure_information_gain`, `ensure_dedup_quality`, and the explicitly approved `deduplicate_fact_clusters`. Passes the same semantic_build to one `deduplicate_resume_facts` call. Model reception and initial projection are unchanged.
2. `resume_project_reconciliation_service.py`: Canonical projects are not selected by `_is_comprehensive`, and `_apply_detail_budget` is legacy-only. Existing canonical no-recovery/no-merge behavior remains. Nested Validity is not removed.
3. `resume_fact_dedup_service.py`: optional existing Build context selects the restricted Canonical branch. Local eligible IDs and exact Claim lineage are checked against the existing Ownership Index/Ledger. The aggregate helper now preserves both live intro and role sources while removing deleted rows' orphaned attachments.

The layering, increment, information-gain and dedup-quality service files were not edited: their competing calls exited the main chain instead. Cluster service remains unchanged for legacy callers. Existing imported aliases remain available; callable presence is not evidence of main-chain execution. A real-generation test makes every retired writer raise if invoked and verifies the remaining dedup is called once.

## Retained responsibilities

| Stage | Current Canonical responsibility | Remaining boundary |
| --- | --- | --- |
| Model reception and initial projection | Existing placement protocol, frozen text composition and proof checks | No protocol or recovery changes |
| Reconciliation | Existing owner/source coordination and validation | No detail budget, keyword-based comprehensive-project deletion, legacy merge or recovery |
| Coverage | Existing validation and necessary cleanup | Unchanged; no new source guessing |
| Adaptive narrative | Existing sorting | No new selection or composition strategy |
| Central fact dedup | Empty-row cleanup and provable exact redundancy only | Never information-score selection or partial-overlap merging |
| Firewall, language, Validity, entity dedup and final containment | Existing independently constrained consumers | Inspected and exercised, not globally declared safe or disabled |
| Gate and Router | Existing read-only validation and narrow repair | No lowered severity or changed failure policy |
| Saved revision and DOCX | Existing immutable delivery and rendering | Source/payload consumption unchanged |

Exact redundancy requires the same owner and the same exact Fact/Claim sets, including valid local eligibility and lineage, plus identical text after only whitespace normalization. Case, punctuation, quantities, negation and wording stay significant. This is redundancy evidence, not new semantic trust. Unknown or inconsistent provenance never grants deletion. Same text with different sources and overlapping multi-Fact expressions remain separate.

Intro/role and detail rows are inspected with their own attachments; project aggregates never prove a field. Original detail indices associate text and Fact/Claim rows during empty filtering. Deleting a proven duplicate clears its own field attachments while preserving attachments on the carrying row and other live fields. Existing logs add counts/reason codes, not raw titles or prose.

Legacy default calls retain existing selection/limit behavior, with the shared aggregate-helper correction preserving live intro sources. No blanket suspension of unsafe-content checks, source verification, or quality validation was made.

## Offline validation

- New `tests/test_v09175_post_processing_evidence.py`: 37 tests. Eight/nine and twenty/twenty-one boundaries run through real save/DOCX in detail, mixed and role placement variants.
- Controls include awards, nonnumeric work, owner-local negation, unknown/foreign sources, missing Claims, same-text/different-source, distinct limitations, partial overlap, cross-field exact duplicates, blank rows, live-field aggregates, idempotence, input immutability and private logging.
- Build/Views snapshots are compared from model reception onward. Existing association of the Build to the isolated input-row ID occurs before that boundary and is not a postprocessing mutation.
- A pre-existing reserved test-development/reading-tool fixture was first run after business changes; no production tuning followed its result.
- Related joint/golden/DOCX run before the final product-name test: 139 passed. No existing test assertions changed. Complete suite includes those same regressions.
- Final full suite: 1159 passed, 1084 existing deprecation warnings, 28.91 seconds. Changed Python files (three services and the new test) compiled successfully into a temporary directory. git diff --check passed; Git only noted configured LF/CRLF conversion warnings. No existing assertions were changed to hide failures.

## Real provider acceptance

User explicitly authorized two synthetic fixtures to api.deepseek.com, configured model deepseek-v4-flash, at most three requests including retries. All three were consumed; reservation records prevent resetting the budget across runs. No production database or production customer input was used, and no secret was printed or stored in the report.

Configuration was unchanged: full_resume, bold, normal input path, temperature 0.4, max_tokens 4096, timeout 30 seconds, thinking disabled. Provider reported deepseek-flash. Normal/long-input and retry invariants are covered offline; the three live requests do not establish live long-input reliability.

| Call | Input | Tokens in/out | Finish | Result |
| --- | --- | --- | --- | --- |
| 1 | Fixed course retrieval/device projects | 8053/4096 | length | Contract rejected: format_projects and missing_fact_assignment; required 10, assigned 0 |
| 2 | Retry, same fixed evidence | 8100/4096 | length | Contract passed, 10/10 assigned, seven verified fields; saved and DOCX exported |
| 3 | Reserved test-development internship/reading tool | 7504/3303 | stop | First-attempt contract passed and saved, six Facts retained |

The third call's first DOCX operation failed because the diagnostic script had not created its isolated output subdirectory. Creating that directory and replaying the saved third response offline produced DOCX without another provider request. This is a harness failure and replay result, not a fourth live call or an application fix.

Observed field text and Fact assignments persisted unchanged across the captured postprocessing stages: fixed sample 10/10, reserved sample 6/6. Both Gates passed with INCOMPLETE_SENTENCE observe/warning issues. In particular call 2 is NOT clean, untruncated full-response acceptance: existing JSON repair admitted a truncated response whose project contract was complete.

Temporary evidence is outside the repository: C:/Users/lbc/AppData/Local/Temp/v09175-live-acceptance-20260916 contains reservation records, provider finish/token metadata, synthetic prompts/responses, initial/stage/saved comparisons and DOCX. It is not production logging or a new runtime component. Additional full smoke or paid acceptance requires fresh authorization.

## Residuals and limits

- Output truncation and repaired/truncated-response success remain an explicit delivery-exit concern. This iteration did not change provider limits, parsing, fallback or Gate/persistence policy.
- The fixed device-registration project still freezes as research and has an unknown topic name; the reserved reading tool also has a pending name. These upstream authority outcomes are not repaired downstream.
- INCOMPLETE_SENTENCE remains in both real examples. Personal-summary variability and professional wording are not evaluated as solved.
- Validity retains its independent heading/action-evidence and shell classification. The exercised legal samples survived, but that does not prove every unfamiliar legitimate expression survives. No new confirmed blocking loss there was found in this iteration's fixtures; preserve it as a separate authority-review item rather than claim it was retired.
- Removing silent quotas can increase document length. No ranking, pagination budget or selection policy replaces them here.
- Sources existing on a row do not independently prove arbitrary prose. The receiver and existing downstream checks retain their roles; dedup neither creates trust nor repairs unsupported expressions.
- Controlled responses are not historical replay. Three paid requests are not a statistically meaningful success-rate guarantee. No production deployment, production smoke, commit or push was performed.

## Rollback boundary

Revert the three business changes and their version/test/documentation updates together if rollback is required; no schema or data migration is involved. The model placement protocol and saved API schema remain compatible. Rolling back reinstates known budget loss and competing legacy writers; it is not a correctness improvement. No uncommitted user files were overwritten. Stop here; v0.9.17.6 is not implemented.
