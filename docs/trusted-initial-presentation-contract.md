# v0.9.17.1 Trusted Initial Presentation Contract

## Scope and baseline

- Baseline: main, v0.9.16.2, commit 6cfffda8063560ffd1813ec17a6b9b8586aebd96.
- The pre-implementation read-only check recorded a clean worktree. Later restricted Git checks can falsely report inaccessible tracked old test artifacts as deleted; no such files were restored or removed.
- Applicable instructions: C:/Users/lbc/AGENTS.md; existing pytest harness: root conftest.py. Temporary test databases and DOCX files use isolated test directories, not production data.
- Business changes: generation_service.py, prompt_service.py and experience_slot_service.py. The two existing normal/long prompt templates change internal output format only. No new runtime module, schema, IR or semantic authority.

## Evidence, not historical reconstruction

The supplied runtime record for request req_1dc94bf1be05434ba4a056df4710f343 reported 17 missing_field_reference fields and zero verified fields. Two existing projects caused ambiguous_field_provenance projection skips. This is historical log evidence, not an available raw model response.

Current experiments use the exact input fixtures for results 224/225/226 and controlled network JSON. They do not reconstruct the historical model output from DOCX. The first dedicated run had 36 failures and 3 passing supported-return controls. Missing owner/references, invalid IDs/lineage, unsupported body, absent body keys, malformed body types, empty projects, extra source rows and orphan blank-row references could continue under the old receiver.

The earliest acceptance error was build_llm_generation: normalization filled or removed fields, validate_model_project_evidence cleared untrusted attachments, and the receiver returned success regardless of evidence reasons. Binder can assign owner without proving individual fields. Planner and Coverage correctly do not invent that missing proof. These mechanisms were not connected by a required success condition.

## Data flow

Before:

    frozen evidence -> normal/long model request -> parse JSON
      -> normalize defaults and rows -> optional evidence cleanup
      -> success even with unverified body -> initial candidates/Binder/Planner

After:

    same frozen evidence + shared internal field protocol -> model request
      -> parse JSON -> inspect raw project/field/reference shape
      -> required existing evidence validation -> normalize original-index rows/schema
      -> only fully verified project body enters initial presentation
      -> on failure: existing bounded retry using the same evidence
      -> on exhaustion: explicit source-contract error, no result save

No semantic rebuild occurs during retry. Responses from separate attempts are not merged. Independent legitimate fields are not erased to make an invalid response appear valid. The existing standalone permissive validator remains available, but Canonical generation explicitly requests complete validation.

## Changes and authority

### experience_slot_service.py

- validate_model_output_structure checks actual source_experience_id, intro/role presence and string types, details string rows and source-row lengths before defaults or blank filtering.
- Nonempty fields require both Fact and Claim declarations. Empty body permits absent/empty references, never orphan IDs. A response cannot replace all projects or an eligible project's whole body with emptiness to claim success.
- Existing field validation remains responsible for owner-local eligible IDs, Claim lineage and deterministic support. Project aggregate IDs remain aggregate only.
- require_complete closes success when any field/reference remains invalid; default standalone behavior stays compatible. No new text matcher or threshold.
- Existing slot log adds request_id, model_attempt and contract_passed. Only fixed reason codes, counts and existing IDs are logged. Raw body, titles and model output are not logged.

### generation_service.py

- Raw structural and required support validation both precede normalize_llm_payload and schema defaults. An unrelated invalid completeness_score cannot conceal invalid IDs or unsupported body behind the JSON compatibility fallback.
- ModelEvidenceContractError is separate from parsing errors. Retry remains bounded by MAX_LLM_CALLS_PER_ATTEMPT and its existing maximum of two.
- Failure codes distinguish MODEL_EVIDENCE_FORMAT, MODEL_EVIDENCE_MISSING, MODEL_EVIDENCE_INVALID and MODEL_EVIDENCE_UNSUPPORTED. Reason counts retain mixed defects.
- A source-contract error remains sticky across a later invalid-JSON response, preventing accidental success through the existing JSON fallback branch.
- Pure parsing failures retain the pre-existing compatibility path. Independent legacy callers without Consumer Views retain optional-source behavior.

### prompt_service.py and existing templates

- One deterministic protocol description is used by both templates and retained on retry. It describes existing field keys, array alignment, owner-local lineage, aggregate-vs-field scope and the verifier's limits.
- Templates no longer call Canonical field provenance optional or describe detail references as project aggregate IDs.
- Packaging, style, role positioning, risk rules, provider JSON mode and number of model calls are unchanged. This is enforced at the receiver, not merely requested by wording.

## Verification and compatibility

The dedicated suite exercises the three exact inputs, normal/long paths, retries, malformed and missing declarations, forged freeze flags, cross-owner references, excluded Claim IDs, wrong lineage, legitimate IDs with unsupported text, multi-Fact literal rows, blank filtering and original-index alignment. It also checks retry limits, stable evidence, no semantic rebuild, privacy and actual save/DOCX with in-memory SQLite.

Complete existing internet, ecommerce and research/open-source/competition/campus fixtures use the actual sent evidence to construct offline protocol responses. These prove transport and validation behavior, not real model writing quality. Existing format-variant and input-evidence assertions remain intact.

Two older test files adapt intentionally:

- v0.9.16 network-success fixtures now declare sources from the actual outgoing evidence; their existing retry, frozen-type, save and API-filter assertions remain unchanged.
- Three v0.9.16.2 tests now require Canonical rejection, while retaining their original standalone non-upgrade assertions. Missing/invalid cases were not removed or converted to successful samples.

The initial final-review run additionally exposed three failures where an unrelated invalid completeness_score hid bad IDs, bad lineage or unsupported body behind schema validation. Moving the same existing evidence validator before normalization/schema closes this ordering defect without adding a second validator.

Final verification: 77 dedicated tests passed; 149 related tests passed; full pytest passed 972 tests with 585 existing datetime deprecation warnings. The golden/DOCX selection passed 52 tests and is also included in the final full run. In-memory compilation of 97 backend/app modules plus the three changed test files passed (100 files, no bytecode output). Tracked diff checks and new-file whitespace checks passed, with only configured LF-to-CRLF warnings.

No paid model, production database, deployment, commit or push was performed. Temporary isolated runs are under C:/Users/lbc/Documents/ChatGPT/GodSu/.tmp-v09171-*; no diagnostic scripts, business data or new runtime modules were added to the repository.

## Limits and NEW_FINDING

1. Existing support validation accepts literal resume_ready_text, presentation-neutral whitespace/terminal punctuation and ordered literal compositions with semicolons or full stops. It does not prove arbitrary professional rewriting. This limit is unchanged and now affects success rather than silently stripping provenance. Real-model failure rate may rise materially.
2. Existing writing instructions can request transformations beyond that verifier. The protocol now discloses this limit; no style instructions or verifier thresholds were loosened. Normal real-model returns have NOT been demonstrated to satisfy the contract. This requires separate authorized real-model acceptance before declaring rollout stable.
3. The raw historical response remains unavailable. The observed 17-field gap is not proof that every historical response omitted every key; current controlled experiments establish the receiver behavior.
4. Downstream deletion/rewrite/attachment risks remain outside this version. The known unsupported prize deletion belongs to v0.9.17.2. Display-name and internship-position issues remain separately tracked.
5. Provider mode remains json_object, not a provider-enforced field schema. The backend is responsible for rejecting protocol violations. Legacy and mock success do not demonstrate Canonical real-model success.

## Rollback and acceptance boundary

Rollback is the coupled receiver/slot/protocol/template/version/test change set. No database migration or data conversion is required. Reverting only strict reception while retaining mandatory-format messaging would reopen the old gap and is not an acceptable silent workaround.

Deployment and acceptance commands are deliberately not stored in this document. Deployment acceptance must record the new release commit and distinct request/attempt/result/file IDs, run shallow/full smoke and the three exact input cases, and inspect both received evidence logs and saved/DOCX body. Missing/illegal/unverifiable responses must fail observably, not be counted as successful output. Smoke success alone does not prove all samples or free rewrites are supported.
