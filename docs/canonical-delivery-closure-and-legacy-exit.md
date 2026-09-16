# Canonical Delivery Closure and Legacy Exit

## Baseline and boundaries

- Baseline: main / 9c2293171e17deffb2a9b02c1ded5799077bcd9b / VERSION 0.9.17.5. Initial worktree clean, no user changes overwritten.
- Applicable ancestor AGENTS.md and root conftest.py inspected. Existing isolated receiver/test runners reused; no additional applicable harness file found.
- Three business files changed: generation_service.py, llm_service.py, immutable_delivery_revision_service.py. No new runtime module or state source.
- No Prompt, provider limits, model protocol, frozen authority, Fact eligibility, Ledger, Gate, Router, Fallback content, renderer, database schema or public API changes.
- No deployment, production database access, commit or push. New experiments use synthetic authorized inputs, temporary logs/outputs and in-memory SQLite.

## Evidence and first failures

| Evidence | Before | After |
| --- | --- | --- |
| Actual generation on background/skills only, real Gate and Router | Both Gate checks returned EMPTY_VISIBLE_SECTION critical, yet one GenerationResult was saved; DOCX later rejected it | DELIVERY_QUALITY_FAILED before Revision/save; input record remains, result/file absent |
| Complete legal project JSON with length/unknown/missing/filtered/tool finish | End status discarded and response accepted | Rejected before JSON repair; bounded retry then explicit failure |
| Truncated response followed by complete stop | First response accepted before retry | Second response consumed, same evidence and prompt, success only after stop and existing checks |
| Intro attachment changed at revision boundary | Visible comparison did not include intro Fact/Claim rows | Both are included and mismatch is detected |

Initial focused run: nine failures and one positive success. The first Gate experiment initially raised from DOCX after the erroneous save; the harness was adjusted to record that export rejection and expose the saved row explicitly. This was not a production fix.

The exact saved second provider response from the previous iteration is now a fixture, with its provider metadata and existing exact course-project input. It ended with length at 4096 output tokens. It is not a historical server request reconstruction. Its original status is rejected before parsing. A separately labeled counterfactual test changes only metadata to stop and demonstrates the existing repair path can still parse and save it: syntax repair and project reference completeness are not proof of a normal provider completion.

## Actual chain and responsibility

| Boundary | Actual responsibility and conditions | Failure behavior |
| --- | --- | --- |
| llm_service.call_openai | Returns text, usage and provider finish_reason; no semantic decisions | Existing transport failure behavior unchanged |
| generation.build_llm_generation | Canonical stop check before parse_llm_json, followed by existing placement and evidence verification | length: MODEL_OUTPUT_TRUNCATED; missing/unknown/other non-stop: MODEL_FINISH_INVALID; same maximum two attempts |
| JSON parsing and existing fallback | Existing syntax/schema failure handling remains for otherwise normal completions | A prior completion or evidence failure cannot be hidden by a later parse failure |
| Initial projection and postprocessing | Existing frozen fact composition, restricted dedup, sanitation and sorting | No new recovery, selection or semantic inference |
| Router and final Gate | Existing narrow repair followed by real validation of actual pending payload | Gate false becomes DELIVERY_QUALITY_FAILED, with correlated log/observer evidence |
| Revision | Existing metadata removal and serialization, including intro attachment comparison | Visible/source mismatch still rejects |
| Persistence and queue | Only checked payload saved; existing queue catches GenerationServiceError and preserves its code | No successful task/result/file for rejected delivery; input/task records may remain |
| DOCX | Existing persisted revision consumption | Rendering unchanged; historical results untouched |

Only explicit stop is accepted in Canonical mode. Missing/unknown values are not guessed from JSON shape. The currently configured API reports stop for normal completion; other vendors require an explicit compatibility review rather than silent acceptance. Unknown provider strings are logged as unknown, not copied verbatim. Independent legacy calls without Consumer Views keep the previous completion-status policy, and LLMResult's new default is None, not stop.

Truncation retries do not introduce a new writing instruction, raise token limits or add calls. A successful later complete response can recover; otherwise a completion failure remains a failure even if the next attempt encounters a pure parse error. Source-contract failures retain their existing codes. Usage accounting remains transport usage, while the separate completion_passed flag records admission; transport success is not delivery success.

Gate rejection records request_id, attempt_id, existing issue codes/counts and DELIVERY_QUALITY_FAILED in generation_stability.jsonl; pending mutation and projection evidence is flushed without a result ID. It does not produce success Revision logs. This is not a promise of zero database writes: an input row has already been created. Existing queue failure handling required no code change.

## Old paths and remaining permissions

- Retired success paths: ignore finish status and accept repaired truncated output; ignore final Gate false and save anyway; miss intro provenance changes in the revision comparison.
- The five writers retired in 0.9.17.5 remain absent from the Canonical chain. Tests forbid both generation aliases and service entry points for layering, increment, information gain, quality dedup and cluster dedup.
- Reconciliation's budget and nested entity merge remain legacy-only. Entity dedup returns without renaming/merging in Canonical mode; legacy eight-detail merging remains outside that branch.
- Canonical Reconciliation still calls Validity. Validity retains shell/action-evidence classification and possible project removal. This iteration's complete fixtures did not reveal a new confirmed legitimate-fact loss there; it remains a restricted-review risk, not a claim of universal safety.
- Exact fact dedup still removes proven redundancy or empty rows with attachments. Adaptive narrative retains existing sorting. Firewall, sanitation, containment and other guarded presentation consumers remain; they are not all disabled.
- Gate is read-only and Router's narrow permissions are unchanged. Tests forbid presentation writers after final Gate and compare checked delivery fields/attachments against persistence. The remaining output-quality evaluation is read-only scoring/logging.
- Public renderers keep the same revision. No old functions were deleted merely to reduce module count; compatibility functions are not evidence of competing Canonical execution.

## Test migration and validation

The full suite initially exposed nine older cases depending on Gate-false persistence. User explicitly approved their contract migration; no input or Gate decision was changed:

| Existing tests | Confirmed final critical | Preserved assertions |
| --- | --- | --- |
| v09151 frontend/backend/AI mock cases (3) | DUPLICATE_FACT | Two owners, frozen types and typed headers, now checked at final Gate |
| v092 type-freeze case | DUPLICATE_FACT | Exactly one application and one read-only validation |
| v0986 observer case | DUPLICATE_FACT | All pre-save checkpoints and flushed evidence, explicitly no generation_persisted |
| v0973 ownerless case | EMPTY_VISIBLE_SECTION | No invalid owner survives; no saved output |
| v0993 controlled initial projection | EMPTY_VISIBLE_SECTION | Selected Fact retention and final Fact IDs, no saved-stage log |
| Long-input JSON fallback and v09172 JSON fallback (2) | Existing final quality rejection; v09172 includes COACH_LANGUAGE_LEAK | Fallback and canonical cleanup still execute, but failure cannot become saved success |

The shared test-only helper observes the real Gate without modifying its result, asserts DELIVERY_QUALITY_FAILED, one input row and zero result/version/file rows, then exposes the checked payload for original semantic assertions. It is not a runtime module or fabricated successful response. Independent successful save/DOCX tests remain.

Seven existing receiver test files only acquire explicit stop in their controlled complete LLMResult responses. This metadata migration is separate from the nine approved assertion changes. Production missing-state rejection has its own negative test.

New focused tests cover non-stop status, absent status, complete and repairable truncation, same-evidence normal/long retries, sticky contract errors, legacy compatibility, warning success, real queue status, no failed Revision/save/export, both intro attachments, private correlated logging and nested retired writers. Existing multi-owner, nine/twenty-one-detail, limitation, same-text/different-source and attachment regressions execute unchanged.

Focused tests: 24 passed. Focused plus golden/DOCX/immutable regressions: 45 passed. Full suite: 1183 passed with 1108 existing deprecation warnings. All 18 changed/new Python files compiled into a temporary directory; git diff --check passed with only configured line-ending conversion notices. Existing datetime.utcnow deprecation warnings were not suppressed. No business logic was mocked in the new closure tests; only transport, infrastructure isolation and read-only observation hooks were used. A parser-unreachable control deliberately makes that entry raise to prove truncated responses never reach it.

## Authorized real acceptance

Two existing synthetic fixtures were explicitly authorized for api.deepseek.com. This iteration used two of at most three calls, including retries; no retries were needed. Durable reservation files enforce the per-iteration budget across processes.

Unchanged configuration: deepseek-v4-flash (provider reports deepseek-flash), full_resume, bold packaging, max_tokens 4096, timeout 30 seconds, temperature 0.4, thinking disabled. Both use the normal-input path; live long-input behavior is not established by these calls, while its completion/evidence wiring is covered offline.

| Call | Sample | Input/output tokens | Finish | Result |
| --- | --- | --- | --- | --- |
| 1 | Reserved synthetic testing internship/reading tool | 7504/3627 | stop | First attempt, Gate passed with two INCOMPLETE_SENTENCE warnings, saved and DOCX exported |
| 2 | Course retrieval assistant/device registration projects | 8053/3533 | stop | First attempt, Gate passed with one INCOMPLETE_SENTENCE warning, saved and DOCX exported |

Fixed sample Fact IDs remain 10/10 from initial reception to saved output; reserved sample remains 6/6. The device project still has research type/pending topic name; the reading project still has a pending name. The prior iteration's two truncated responses remain genuine adverse evidence: this version rejects them, not prevents truncation. Two fresh successes do not establish a success-rate guarantee or prove every summary sentence is supported.

Temporary evidence: C:/Users/lbc/AppData/Local/Temp/v09176-live-acceptance-20260916. It contains only the authorized synthetic experiment's prompt/response, provider metadata, reservation, stage/initial/saved data and DOCX. No API key was printed, no persistent configuration changed. Online smoke and production acceptance were not executed.

## Residuals, release risk and rollback

- Stricter rejection can lower apparent success. Providers lacking finish metadata now fail Canonical admission. With an unchanged 4096-token budget, long responses may still truncate repeatedly and fail; this is not solved by these changes.
- Gate coverage is not proof of all prose quality. Type/name/position, personal summaries, professionalization and output-budget design remain separate work.
- Pure normal-finish JSON failures can still use the existing deterministic fallback, but it must pass final Gate. Such a result is degraded delivery, not a normal model-contract success.
- No new confirmed valid Fact loss was found in this iteration's tested consumers. Validity and other residual rights still require evidence-based review, not blanket removal or a universal safety claim.
- Roll back the three business files and version/test/documentation changes together, without a database migration. The public payload remains compatible. Rollback reopens known false-success paths and is not a correctness improvement; existing persisted rows are not rewritten.
- No deployment commands are stored in this document. Stop after this iteration; do not start another release automatically.
