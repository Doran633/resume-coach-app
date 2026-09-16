# Canonical Claim Qualification and Type Evidence Correction

## Baseline and scope

- Version 0.9.18.1; baseline main / 0201ceae40944b512bb5d404a59dcad8b59e714e / 0.9.17.6, clean working tree.
- Repository and ancestor instruction locations were checked. No repository-specific AGENTS.md or separately named harness was found. Existing conftest, Claim contract, compilation tests, network-boundary capture, isolated SQLite and delivery trace helpers were reused.
- Business edits are limited to input_claim_resolution_service.py and experience_type_resolution_service.py. No runtime module, semantic state, classifier, Prompt, model protocol, Ledger rule or downstream authority was added or changed.
- User-exported exact inputs for results 224/225/226 and the complete course-project fixture are reused. Builds below are current-code replays, not historical provider response snapshots. No historical raw model response has been recovered.

## Failure evidence and first authority

| Input / boundary | Before | After |
| --- | --- | --- |
| Request 225, EXP-002-C006, source span [475,488), text `后续计划研究多语言标题处理` | RESUME_FACT, positive, confirmed, current, eligible; included as a Fact | Same text, role, polarity, certainty, owner and source; planned, withheld, planned_work; retained as an internal constraint, absent from model eligible Facts |
| Request 225 next Claim [489,495), `目前尚未实现` | Excluded constraint | Still excluded and retained; not converted into a positive Fact |
| Course input EXP-002, first body Claim [271,328) | `实验室设备登记系统 ... 在三人小组中负责` matched the organization-near-action branch: research16 vs project12 | No research-task evidence: research0 vs project12; frozen project type |
| Course input complete Ledger | Two owners, ten Facts | Two owners, exact same Ledger including Claim/Fact text, IDs and spans |

The first error is in _attributes: planned syntax missed the leading future context and research activity, after which CURRENT_PATTERN accepted the word 后续. The type consumer's prefix exclusion did not match this sentence either. Ledger correctly consumed the wrong qualification; it was not a model rewrite.

The second error is in resolve_identity_type: an organization word inside a product name was accepted as research evidence simply because a duty verb occurred nearby. The Canonical builder then froze that decision. It was not a renderer reclassification.

Both failures were demonstrated before business edits. Tests initially also exposed two test-harness mistakes: MappingProxy-backed Views cannot be deep-copied, and an explicit 项目一 label must retain its declared-type priority. New tests were corrected to snapshot Views via repr and use a descriptive heading for relation tests; a separate assertion preserves actual explicit-label priority. No existing assertion was changed.

## Changes and actual callers

build_canonical_semantic_build resolves each Identity's Claims, builds type/time/name/header decisions, then builds the Ledger from the same components. _build_experience_type_decision invokes resolve_identity_type with that owner's ClaimResolution. These call sites and consumers are unchanged.

Claim Resolution now shares a local prospective-prefix expression between comma-boundary qualification and temporal classification. It accepts source-backed subject/future context and uses existing activity syntax, with participation/research and prepositional role relations. This is not a universal Chinese parser: an intent-looking substring alone is insufficient. Compound nouns, model fitting and completed preparation controls remain eligible. Independent subject uncertainty is scoped separately, while dependent limitations and exclusive responsibility remain intact. The eligibility function is unchanged.

Type Resolution no longer gives research points for a bare lab/group word near any duty action. It requires participation in a research-task object with a clause boundary, or an explicit local organization/participation/research relation. Product names such as topic/research management systems cannot supply that relation. Actual research can still involve development; accumulating ordinary project words cannot displace established research evidence. Existing declared type and other type rules remain.

The type consumer's existing prospective-prefix exclusion is NOT retired. Attempted removal caused the old `计划前端开发实习` regression to become an internship. Claim parsing does not yet fully qualify that elliptical role expression, so equivalence is unproven. The exclusion remains at its original location rather than being copied to another guard. This is a retained limitation, not a successful removal claim.

## Preservation and exact differences

- For exact requests224 and226, complete serialized builds before/after were equal.
- For request225, Identity, names, times, headers and types are unchanged; Facts change12 to11 solely by excluding the planned multilingual-title work from formal Facts. Its Claim remains. Existing temporal related_claim_ids no longer include it as current; no dependency semantics were added. Other Claim qualifications and texts are unchanged.
- For the course input, Identity, Claims, full Ledger, names and times are unchanged. EXP-002 changes from research to project; the existing Header consumer changes the pending label from topic to project. The name value remains pending, not silently repaired.
- Model preparation excludes the planned Fact from eligible evidence but retains its text/owner in internal constraints. Existing Claim lineage and Fact source spans remain local and checkable against each format's original input.
- Limits are not removed from legitimate Facts, and the existing Gate, Router and final refusal policy are unchanged.

## Verification

New tests exercise actual segmentation, Identity, Claim, type, Build, Views, Prompt preparation, model reception, all delivery writers, final Gate, saved revision and DOCX. Only the network response and infrastructure are controlled. SQLite and log/output paths are isolated. The shared trace helpers observe actual business calls without replacing their return values.

Controls include completed/planned mixed clauses, subject uncertainty/negation, dependent limitations, compound-name and fitting/preparation counterexamples, research products versus research tasks, research with development, real explicit type priority, owner isolation, source-backed snapshots, deterministic output and immutable Build/Views. Original, CRLF, blank-line and sentence-line variants use unchanged content. Existing internship/open-source/competition/campus and ecommerce regressions are retained.

The synthetic reserved fixture pairs a laboratory equipment tool with an acoustic research experience; it was executed after the initial implementation and was not used to tune the business rules. It passed qualification, type, ownership and real saved-revision controls on first use. The exact course and225 fixtures also reached save/DOCX with every eligible Fact and attachment checked at each observed stage.

Final validation: 86 new focused/reserved tests passed; 202 focused plus Claim/Type/upstream regressions passed; full suite 1269 passed with 1149 existing datetime deprecation warnings; golden/DOCX selection 61 passed. All 235 Python files under backend/app, tests and scripts compiled in memory without bytecode. Scoped git diff --check and new-file trailing-whitespace checks passed. No existing test expectation was changed.

The course, request225 and reserved control returns passed both real Gates and saved/exported. Their final Gate records still contain 4, 6 and 2 INCOMPLETE_SENTENCE warnings respectively. Stage data confirms local Fact/Claim preservation, not just equal counts. No paid model, production database or deployment is used. Controls prove deterministic processing, not historical generation reproduction or general live success rate.

## Residuals and rollback

- Elliptical prospective role headings still require the retained type exclusion; no claim of complete plan-language coverage is made. Free-form wording outside the explicit local relation patterns may require separate evidence review.
- The device project's pending display name remains; personal summaries, output budgets, position extraction and professionalization are not fixed here.
- Existing semantic-role/attribute differences such as the excluded `目前尚未实现` retaining positive/confirmed attributes are not reinterpreted as a positive Fact. Its exclusion is preserved; broader attribute normalization was not expanded into this release.
- Legacy callers share the corrected resolver functions but retain their original invocation contracts; no forced Canonical context is added. Existing legacy and declared-type tests remain unchanged.
- Roll back the two business files with this release's tests/version/docs as one reviewed change. There is no schema migration; persisted historical results are not rewritten. A rollback restores the demonstrated mistaken qualification/type decisions, so it is not an accuracy improvement.
- Temporary before/after full builds and diagnosis script live in the OS temporary directory as v09181-before.json, v09181-after.json and v09181_diagnose.py. Test artifacts use v09181-* temporary directories. These are not release files.
- Deployment and commit commands are intentionally omitted from this document. Stop after this iteration; do not implement0.9.18.2.
