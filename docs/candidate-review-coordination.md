# v0.9.19.5 Candidate and Review Coordination

## Baseline and Evidence

- Baseline: main / 6a413187, VERSION 0.9.19.4.2. Existing tracked pytest artifact deletions were preserved.
- The previous planning probe used a separate authorization. Its 22 calls are not included in the new 30-call implementation authorization.
- The header sample's full F004 original text was previously reviewed again and reported omitted. The Java sample used both calls for writing and could not review the second candidate. These are new recorded experiments, not historical production response replays.
- New red controls: five failures before implementation, with three near-neighbor controls passing. Initial projection, Binder, Gate, persistence and DOCX remain real; only network responses are controlled.

## Responsibilities and Changes

- `generation_service.py`: Canonical permits at most two writers and one reviewer, total default three. Explicit lower caps remain effective; legacy is capped at two. Daily budget checks remain before every dispatch. Review rejection does not authorize another repair call.
- `llm_service.py`: explicit per-call roles choose writer/reviewer limits (8192/4096 defaults). Legacy consumes the existing shared limit. The model, temperature and timeout are not changed.
- `experience_slot_service.py`: complete literal units provide existing deterministic text support and coverage. A second probabilistic completeness verdict is not requested for those facts. Every nonliteral unit still requires independent support review, including one that reuses a literal fact.
- Review v6 preserves strict decision/coverage mappings and exact issue anchors. `editorial_observe` requires all five substantive checks true and records identifiers/positions, not text. Uncertain major factual changes, unsupported actions, hard claims, responsibility/state changes and unresolved coverage still reject.
- No fact is changed, hidden or restored. Receipts bind all candidate text, source lineage and position; downstream changes invalidate them. Binder and final checks consume the same request-local evidence.

## Compatibility and Risks

- Project writing remains `canonical_fact_compositions_v2`. Public schemas and four version fields are unchanged. Gate severity and Fallback policies are unchanged.
- Approved test migrations only change role-compatible network controls, v6 labels, and the obsolete requirement to re-review a complete original. True omission uses a partial F004 candidate and still rejects; original input and persistence/DOCX assertions remain.
- Increasing output and retry allowance may increase latency and cost. Existing daily call/token/cost controls are retained; they are not a prepaid hard reservation for the next response. Missing price configuration produces zero estimates, not proof of free calls or a working monetary ceiling. Failed network calls may lack supplier token usage.
- Semantic review and editorial observations are bounded probabilistic assessments, not deterministic fact proofs. This stage does not promise professional packaging quality, does not align bold text with DOCX yet, and does not certify summary or four-version semantics.

## Validation

- Focused and related real-chain controls: 129 passed, including save/DOCX, truncated first writer followed by normal retry, exact-text coverage, partial omission and hard-claim refusal.
- Full suite: 1837 passed; separate golden/DOCX/immutable-rendering regression: 15 passed. Backend application and tests compiled; scoped diff check passed. The unrestricted diff command reported permission warnings for pre-existing pytest artifacts; those were not altered or restored.
- Fresh API acceptance: 8 calls (four writers, four reviewers), all `stop`, writer/reviewer wire limits 8192/4096, unchanged timeout 30 seconds and model `deepseek-v4-flash`. Header, normal and limited samples saved and exported; the thin sample failed with `MODEL_EXPRESSION_REVIEW_INVALID` and saved no result. Its review JSON lacked a closing brace and also reported a lost responsibility qualifier. No review repair or extra call was performed.
- All four executed generations retained frozen identities, type/claim/header decisions, Ledger and ownership index. Attaching the input record ID changes request metadata/state fingerprint, not frozen semantics.
- The first limited harness label failed request validation before any API dispatch because the fixture container was passed instead of its raw string. The harness was corrected and used a new label; neither event is described as a model failure.
- Successful bodies preserve quantities, tools, team scope and local-demo status, but remain mostly near-original. This stage does not satisfy the later packaging-quality goal. A malformed review remains a refusal condition; the observed failure is disclosed, not hidden by the three successful controls.
- Price configuration was unavailable: supplier token counts are recorded, monetary estimates are not billed costs. No production database, deployment, commit or push was used.

## Rollback

Revert this stage's service/template/test/document changes together and restore legacy total caps if desired. Frozen records, public schema and historical results are not migrated. Restoring old v5 coverage reintroduces exact-original false rejection and the second-writer review-budget failure. Do not roll back by accepting unsupported text or bypassing Gate.
