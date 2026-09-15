# v0.9.17.4 Canonical Fact Reference Composition

## Baseline and evidence

- Repository: `C:\Users\lbc\Documents\Resume-coach\resume-coach-app`.
- Baseline: main, v0.9.17.2, commit `92e1fe7589c92cef41993f91259c7d0048791b8c`; initial Git status was clean.
- v0.9.17.3 was a read-only brief, not an implemented release.
- Historical request `req_2483c2870d1845f4b6c289d67cc08db2` failed with `MODEL_EVIDENCE_UNSUPPORTED`: first attempt had 1 verified / 10 unverified fields, second had 0 / 8. The original model responses are unavailable.
- The current controlled-response experiments use the saved accurate inputs for results 224/225/226. They are not historical model-response snapshots.
- Initial new-suite run: 11 failed, 14 passed. Literal evidence was accepted by the old verifier, but reference-only returns could not enter the old receiver. The verifier still rejects both an unsupported harmless paraphrase and responsibility inflation; this release does not loosen that verifier.

## Responsibility and protocol

The old mismatch was between a request to write project prose and a receiver able to establish only literal or narrowly composed support. The replacement changes what the model supplies, not what counts as proof.

Canonical project objects have exactly these keys:

```json
{
  "source_experience_id": "EXP-001",
  "intro_source_fact_ids": [],
  "role_source_fact_ids": [],
  "detail_fact_ids": [["EXP-001-F001"]]
}
```

This is a shape example, not a fabricated valid runtime ID. Runtime IDs must exist in the same request's eligible view.

The model arranges the provided facts, but cannot write project prose, generate headers, select facts for omission, assert Claim attachments, or declare trusted/frozen state. Every provided eligible Fact is required exactly once across all fields and projects. Exact set membership and duplicate occurrences are checked, not just counts. Different Facts sharing a Claim remain distinct.

The backend validates owner, Fact availability, eligibility through the existing view, Claim lineage and source order, then materializes full frozen `resume_ready_text`. A single Fact is unchanged. Multiple same-owner Facts are joined with a deterministic semicolon after terminal sentence punctuation normalization compatible with the existing support verifier. Words and limitations are not removed. Source order is checked within each combined field; separate fields may be arranged by the model. Empty intro/role are allowed. Field placement itself is not proof of a new role or semantic category.

Claim rows and project aggregate sources are derived from the referenced Facts. Aggregates never become field proof. Header text comes only from frozen header decisions. The existing payload and public API remain unchanged; there is no new business service, IR, classifier or state authority.

## Actual changed call path

| Location | Change | Authority retained |
| --- | --- | --- |
| `prompt_service._generation_template` | Select paired static legacy-project blocks by caller mode | No input parsing or semantic decision |
| `prompt_service._canonical_output_contract` and both generation templates | Same reference-only task for normal/long input; remove conflicting project prose/selection requirements from Canonical rendering | Non-project writing style remains unchanged |
| `generation_service.build_llm_generation` | Parsed response -> reference composition -> existing evidence validation -> normalization | Same request Build/Views and retry limit |
| `experience_slot_service.compose_model_fact_references` | Validate complete references and deterministically materialize existing payload | Frozen text, owner and lineage are not model assertions |
| `experience_slot_service.bind_projects_to_experience_slots` | Approved narrow direct binding using fully verified local field evidence | No new trust flag, no permissive path for incomplete/invalid fields |

The Binder adjustment was a real integration blocker, not a speculative extension: six existing joint regressions failed after the new protocol used frozen headers. In controlled input 224, owner EXP-002 survived normalization, Cleanup, Hard Fact Guard and initial validity, then lost its owner in Binder because `项目：【待填写】` failed Identity title similarity. Containment removed it. Input 226 had the same issue for two owners. The user approved binding the same declared owner when every nonempty field passes existing Fact/Claim/text validation and no new evidence rejection is recorded. Five positive/negative tests cover complete proof, missing proof, foreign proof, unsupported text and orphan attachments.

## Failure and compatibility

- Extra project keys, including old prose/header/Claim/aggregate/trust fields, are protocol errors; they are not silently ignored and replaced.
- Missing references, unknown/foreign IDs, duplicates, missing assignments, unavailable facts and invalid lineage fail before normal project cleanup or projection.
- Retry reuses the same prompt and frozen evidence with the existing call limit. It does not combine responses or build semantics again. Exhausted contract errors do not save a generation result.
- A prior contract failure followed by malformed JSON cannot escape through Stable Fallback.
- Independent legacy callers keep their existing prose interface. Pure JSON parsing failure retains the old fallback behavior and is tested separately; it is not reference-contract success.
- Existing `experience_slot_binding.jsonl` distinguishes `generation_model_fact_references_composed` from `generation_model_evidence_received`, with request/attempt/model-attempt linkage, protocol, required/assigned counts and rejection codes. No project prose or names are added to logs.

## Tests and results

All tests used controlled network returns, real segmentation/Build/receiver/Binder/Planner, isolated SQLite and temporary logs/DOCX outputs. No paid model, production database or deployment was used.

- Full suite: **1048 passed**, 838 existing deprecation warnings, 29.15 seconds.
- New suite: 42 cases, including normal/long input for all three accurate inputs, valid/invalid mixtures, missing/foreign/duplicate IDs, forbidden old fields, source order, shared Claim, empty rows, retries, privacy, immutable inputs and real save/DOCX.
- Existing tests for six owners and nine details now send references from the real Build; their exact initial-body and Fact/Claim assertions remain in force.
- Four existing test files update controlled network fixtures to the new internal protocol. The old free-prose fixtures remain available for legacy/normalization/validator tests. Unsupported rewrite checks remain explicit, so rejecting old protocol fields does not substitute for testing the unchanged support verifier.
- Actual generated prompts are inspected for the new contract and exclusion of conflicting project prose tasks. Mock boundaries do not replace the tested Binder, validator or Planner.
- Dedicated new-suite/golden/DOCX/immutable-delivery run after the version update: **63 passed**. All 8 changed Python files compiled to an isolated temporary directory. `git diff --check` passed; Git's LF/CRLF conversion notices are not whitespace errors.

## Remaining findings and limits

1. Initial completeness is not final completeness. The real nine-detail control preserves all nine at the initial boundary, but `reconcile_resume_projects(stage='generation')` subsequently drops F009/C009 and saves eight. Gate reports `ELIGIBLE_FACT_UNPROJECTED` as a nonblocking issue in this experiment. No downstream behavior or threshold was changed.
2. Accurate controls 224/225/226 first undergo detail ordering in Reconciliation, then adaptive narrative ordering; rows move with their attachments in the observed controls. Input 226 also undergoes professionalization (for example removal of first-person wording). These later transformations are recorded, not certified as covered by the literal initial proof.
3. Frozen name qualification can still yield a pending project name. The new reference protocol consumes that decision rather than inferring a name from body text. Name/position issues remain separate work.
4. Upstream eligibility remains authoritative even if incorrect. Known planned-language qualification issues are not reclassified by serialization.
5. The contract applies to `resume_sections.projects`, not every other generated summary, coaching field or skill sentence. Pure parse-fallback and final delivery behavior remain separate paths.
6. Exhaustive Fact assignment may make output longer and may increase model omissions on large inputs. No real-model success rate is claimed. There is no guarantee that model reference arrangement chooses the best intro/role placement.

## Real-model release acceptance

Run normal and long inputs, fixed inputs and previously unused holdout inputs, with repeated generations. Include internship/project pairs, competition/campus and research/open-source cases, plus six-owner/nine-detail controls. Record first-attempt and retry success separately, protocol rejection counts, final failures and same-request required/assigned Fact sets. No omission may be reclassified as acceptable merely to improve success rate.

Inspect the actual sent reference contract and received protocol outcome. Then compare the first materialized fields, initial projection, downstream changes, saved revision and DOCX. A successful smoke or a synthetic valid reference response cannot replace this acceptance. Historical missing model responses cannot be reconstructed from DOCX.

## Rollback boundary

The receiver, prompt adapter and both templates form one deployment unit. Revert the release as a unit after preserving unrelated work; do not deploy new templates with the old receiver or the reverse. Reverting restores the earlier free-prose/unsupported-rewrite risk rather than resolving it. No database or public schema migration is needed. Frozen semantic authorities and downstream services were not changed. The approved Binder branch can be reviewed separately but is needed for valid frozen-header controls to reach initial projection.

Deployment instructions are intentionally not stored in this document.
