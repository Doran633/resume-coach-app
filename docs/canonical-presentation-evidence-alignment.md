# Canonical Presentation Evidence Alignment

## Baseline and evidence

- Baseline: main / d29cc0e / 0.9.18.5.1. Existing deleted historical test artifacts were left untouched. Applicable ancestor AGENTS.md and existing pytest/receiver/SQLite/DOCX harnesses were inspected; no repository-specific harness instruction file was found.
- v200-v204 are historical output symptoms. Complete matching requests, parameters and raw model replies were not available. No input was reconstructed from a DOCX.
- The complete Java input in test_v091851_semantic_unit_boundary and historical research input in test_v09184_denied_claim_validation were reused. New narrow controls and a warehouse-tool holdout are explicitly current experiments.

## Confirmed boundaries

| Boundary | Before | After |
| --- | --- | --- |
| Claim qualification | `研究尚未形成论文，我也没有提出新的模型结构` was one positive/confirmed/eligible Claim | Two excluded negative Claims, with exact original spans |
| Positive action with a separate denial | A subject followed by `也没有` could remain attached to the preceding action | Independently negated clause separated using the existing clause boundary grammar |
| Evidence serialization | Eligible facts and excluded/withheld constraints already use separate existing fields | Unchanged; corrected Claims naturally enter internal constraints |
| Model placement and composition | Every eligible Fact assigned once, exact IDs, complete original text | Unchanged; no hidden placement, relaxed key set or model selection authority |
| DOCX | Renderer prepended fixed labels and nested later details | Neutral peer bullets, original order and content |
| Web | Intro/role/detail had fixed labels, empty fields displayed placeholder prose | Neutral nonempty rows; same first experience and first three details |

The qualification correction was explicitly approved as an extension to the original display-only scope. It only modifies input_claim_resolution_service.py; semantic-role classification, Ledger rules and eligibility contract are unchanged. The existing subject grammar gains the noun subject `研究`; independent negation accepts `也` after a subject. Neither rule depends on an award, model name, paper count or an action allowlist. Embedded objects such as `使用Python研究尚未分类的音频` remain positive controls.

## Actual consumers and permissions

- build_canonical_semantic_build uses the existing Claim resolver before freezing. No display consumer can change the frozen result.
- prompt_service._canonical_evidence_context already serializes eligible_facts separately from internal_constraints_not_resume_facts. No duplicate evidence view or prompt change was necessary.
- experience_slot_service.compose_model_fact_references still requires the exact eligible Fact set and derives body/Claim attachments from frozen facts. Normal/long requests and retries retain this contract.
- generation retains its receiver, initial projection, post-processing, final Gate, immutable revision and save path.
- docx_service.create_docx reads the saved GenerationResult and emits neutral bullets. It does not delete a saved detail merely because it mentions local use or a limitation. Existing label-only suppression remains; a saved label with actual prose remains visible.
- ResultPage.ProjectPreview reads the same result fields and renders original body strings as React text. It does not run the generic internal-field word replacer on project prose. No raw input, semantic call or database write is introduced.

## Preserved behavior and residuals

`工具仅在本地运行` and `仅供同学试用` remain eligible status facts and remain visible. Mixed action/qualification facts are not rewritten. A hidden constraint does not authorize the opposite assertion: a direct Gate control still rejects `研究形成论文` against the corrected denied Claim. This is a direct invalid-payload test, not a claim that such a response passes the reference receiver.

Name/date repetition is not fully resolved. The Java project first Fact contains the name, date and real implementation action in one original span. Header provenance does not provide an existing approved display-subspan contract. Removing a prefix would change a supported full Fact while attaching its old full proof. This release leaves that content intact rather than adding parsing, splitting facts or weakening support checks.

Historical saved results are not rewritten. Renderer-generated labels disappear on a new render, but a label already embedded in stored prose is preserved. Existing DOCX files are unchanged.

No general restriction classifier, ability expansion, arbitrary paraphrase validation, summary packaging, skill reclassification, sorting or length budget is added. Repeated names, dates and uneven bullet lengths therefore remain possible. Shared Claim grammar is used by legacy callers as well; the correction is not claimed to preserve the old erroneous qualification.

## Validation

Initial focused controls: 3 failed, 6 passed before business changes. Failures demonstrated incorrect qualification and renderer-added labels. The first collection error was a new-test helper name typo and was corrected before this failure baseline.

Focused tests include original spans, positive object counterexamples, format variants, separate positive/negative clauses, source preservation, retry with missing Fact rejection, unchanged Build/Views, direct Gate refusal, persisted DOCX rendering and a held-out warehouse sample. Only the network boundary is controlled in generation tests; receiver, compiler, projection, Gate, SQLite save and DOCX run normally.

Two existing tests expected the removed renderer-added technical label. Both were migrated with explicit approval; original content, List Bullet style, header format, metadata non-leakage and persisted-payload assertions remain.

Final results: 1,560 full-suite tests passed; the focused presentation plus existing model-evidence suite passed 54 tests; the separate golden/DOCX suite passed 15 tests. All 242 backend/test/script Python files compiled without writing bytecode. Frontend TypeScript/Vite build passed, retaining the existing large-chunk warning. Scoped git diff --check passed. New DOCX output was rendered and visually checked: neutral peer bullets, retained headers and no clipped text on the inspected page. Frontend verification covers build and source contract checks; browser visual/interactivity acceptance remains unperformed.

The first full run had 1,557 passes and two failures: one approved old-label contract migration and one pre-existing test writing an application log outside the sandbox. A temporary runner redirected service log paths to an isolated diagnostic directory; no application logging or existing test expectation was changed for that environment failure. The held-out test added one case before the final full run. No paid model or production database was used. Real model acceptance and matching historical request replay remain unperformed.

## Rollback

Rollback is limited to the Claim grammar, two rendering files, approved test migrations and version documentation. No schema or database migration is required. Existing revisions and attachments remain stored unchanged. Rolling back Claim grammar restores the demonstrated false eligibility; rolling back renderer mapping restores fixed labels. A release rollback must rebuild the frontend and use consistent backend/frontend version metadata.
