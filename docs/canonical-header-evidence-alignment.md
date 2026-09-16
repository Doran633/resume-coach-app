# v0.9.18.2: Canonical Header Evidence Alignment

## Baseline and scope

Branch main, commit61fae97, version0.9.18.1.1. Applicable AGENTS and existing upstream, name/time/header, placement and real-delivery harnesses were read. Scoped source/tests/docs were clean. Pre-existing inaccessible historical pytest artifacts were not cleaned, reverted or included.

Only the name/time/header evidence consumers and existing Canonical internship extraction were changed. The user approved passing the existing ExplicitExperienceBoundary record through SemanticExperienceSegment, ExperienceSegment, LongInputSegment and ExperienceIdentity. This is source metadata on existing objects, not another header decision, parser or semantic model. Partition conditions, body offsets and Identity decisions are unchanged.

## Failure evidence and earliest mismatch

The three full inputs in tests/fixtures/v091811_normal_inputs.json were replayed through the real Build. Initial focused results were9 failed /1 passed, before business edits. These are current-code controls, not historical original-model-response snapshots.

| Source | Before | After |
| --- | --- | --- |
| Course title for the campus study-room reservation system | Pending name | Exact explicit name |
| Personal title for the campus second-hand display site | Pending name | Exact explicit name |
| Programming society technical-sharing activity title | An action phrase about organizing three activities | Exact explicit activity name |
| Frontend internship at Xinghe company, in its development department | Department/connector included in position | Frontend development internship |
| Same-year March-to-May / June-to-August ranges | Start month only | Complete source range |

_heading_candidate previously accepted only some boundary labels and consulted inferred Identity fields. labeled_experience names did not enter that route. Even correct explicit names pointed to the owner's body span rather than their original title. The confirmed boundary record was lost across adapters, so changing a label whitelist alone could not repair provenance.

Position extraction reused a legacy regex that captured everything between a company suffix and internship, including department/verb text. Time extraction required a second year and therefore fell back to the first month. Additional controls showed a school-year range lost its school-year qualifier because the generic range matched before the term pattern. Source-backed tests exposed and corrected these within the same existing services.

## Actual changes and authority

- canonical_display_name_service.py: owner_heading_evidence reads and verifies the original region identified by the existing boundary. It does not discover boundaries or re-segment raw input. Names use exact local field spans; candidate source and Claim IDs are preserved. Body entity candidates must come from eligible confirmed Claims, rather than unrestricted raw-body matches. Explicit heading/naming evidence precedes body entities; different same-rank names remain ambiguous. Inferred Identity titles and aliases cannot overwrite the original heading.
- canonical_semantic_state_service.py: passes original input only during compilation to verify boundary evidence. Time candidates use verified heading or eligible local Claim offsets. Complete terms precede generic overlapping ranges; an invalid/ambiguous range cannot degrade to its start. Repeated equivalent date forms are not conflicts; competing intervals are pending. A completed task date contained inside an explicitly stated experience interval is an event, not another interval. Explicit task-date labels and graduation references are rejected. Arbitrary natural-language time interpretation is not claimed.
- resume_title_format_service.py: existing Canonical extraction now returns local value/span matches internally. Company and role are separate; anonymous employers, partner-only descriptions and duty phrases do not supply a concrete employer/role. Department/relational tokens are not position text. Only the already stated internship suffix is normalized; short role names are not expanded into a discipline or rank. Multiple independent candidates remain available for conflict decisions. Legacy title formatting and Canonical frozen assembly are not changed.
- semantic_experience_segmentation_service.py, experience_segmentation_service.py, long_input_service.py, experience_identity_service.py: approved source_boundary metadata pass-through only. The exact existing boundary object is reused. Body ranges, ownership/type resolution and Fact creation are unchanged.

Consumers still receive one frozen name/time/header result per owner. Header uncertainty uses existing pending labels and neutral questions. Non-internship headers do not acquire employer/position fields. No downstream code reads raw input again to repair names. No public API/schema or persistent-state migration is introduced.

## Preservation and tests

Complete serialized before/after comparisons of the three full Builds show identical Identity business fields, body spans, semantic analyses, Claim resolutions, full Ledger, type decisions and ownership index. Only the approved boundary metadata and header-related decisions differ. Owners remain2/2/2; eligible Fact counts remain10/10/8. These comparisons are stronger than equal counts or nonempty IDs.

Tests cover original and CRLF/blank/sentence-wrap/colon-heading variants; exact original title/field slices; English and punctuated names; names containing a negation-looking ordinary word; restricted names; ambiguous equal-authority names; local department/role boundaries; employer/role conflict; anonymous/partner/intent/negative controls; owner isolation; complete, abbreviated, single-month, ongoing, school-term and cross-year ranges; task/graduation/ambiguous/invalid dates. Build and consumer views remain unchanged by assembly, and repeat assembly/build is deterministic. Existing aggregate logs are checked for absence of field values.

Six full-input controlled deliveries use all-detail or mixed placement, real request preparation/reception, all existing writers, real Gates, isolated SQLite persistence and DOCX. Each stage preserves local substantive facts and attachments; the pre-existing leading first-person removal is checked explicitly by the shared harness. Saved header fields agree with frozen decisions and appear in DOCX. The reserved industrial sample uses different employer, role, named tool and a full cross-year period; it passed first use without tuning business rules.

Two old name tests requiring qualified field spans to equal whole body spans were changed, with approval, to exact original field assertions. Five parameterized Binder tests previously required a pending name for a now-qualified explicit project. With approval, their precondition now asserts the correct source name and a second parameter forces only the candidate display name to pending. All original valid/missing/foreign/rewrite/orphan binding assertions remain; no Binder implementation or threshold changes.

Final validation: all 1394 pytest cases passed, including 61 new header cases; the separate golden/DOCX selection passed 67 cases (1327 deselected). All 237 Python files under backend/app, tests and scripts compiled in memory without writing bytecode. Scoped git diff --check passed for source, tests, prompts, version and documentation. The unrestricted check returned success but reported permission warnings for pre-existing historical pytest artifacts; those artifacts were not modified. Existing datetime.utcnow deprecation warnings remain.

No real model was called; controlled network replies are not live success-rate evidence. SQLite, logs and generated DOCX are isolated under OS temporary directories. Full-suite log paths use an in-memory pytest plugin, not a production config change. No deployment or production DB connection occurred.

## Residuals and rollback

- Existing DENIED_CLAIM_ASSERTED Gate scope behavior, personal summaries, skill display and professionalization are outside this release. INCOMPLETE_SENTENCE warnings are not suppressed.
- Empty bare internship headings followed by certain prose can still yield no owner in the existing partition path. This appeared while adding field-negative controls; those controls use an unambiguous named internship heading to exercise the intended header layer. It is recorded as an upstream partition finding, not silently fixed or treated as successful header extraction.
- Arbitrary employer aliases, unknown role phrasing and free-form temporal ambiguity can remain pending. A syntactically recognized company still requires local employment evidence; not all organizational naming conventions are supported. A truthful pending field is preferable to invented specificity.
- Existing title resolver missing-question limits remain untouched. Reuse of current clarification behavior does not promise unlimited visible questions.
- Roll back the three evidence/extraction services and four approved metadata pass-through files together with this release's tests/version/docs after review. No data migration or historical result rewrite is required. Rollback restores the demonstrated header and source-span defects.
- Deployment/commit commands are intentionally not stored in this document. No automatic commit/push and no next-version work.
