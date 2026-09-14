# v0.9.17.2 Canonical Initial Evidence Preservation

## Baseline and scope

- Baseline: main, v0.9.17.1, 68d5b7335d26d41b16e468666efa86d5e8bc24f8. The worktree was clean before implementation.
- Applicable instructions: C:/Users/lbc/AGENTS.md. Harness: root conftest.py; explicit temporary basetemp overrides its repository-local Windows default.
- Business changes are limited to result_cleanup_service.py, fact_guard_service.py and two generation_service.py call sites.
- No Prompt, model protocol, support matcher, semantic authority, eligibility, Ledger, Binder, Planner, Coverage, downstream writer, Gate, Router, renderer, database schema or public API changes.
- Tests use in-memory SQLite, controlled network returns and temporary logs/DOCX. No paid model, production database, deployment, commit or push was performed.

## Evidence and first failure

These are current-code controlled-return experiments, not historical raw model snapshots. Exact saved request inputs for results 224/225/226 are reused from the existing fixture; additional count and owner-scope samples are explicitly new experiments.

The initial dedicated run produced seven failures and three passing exact-input controls:

| Case | Before change | After change at the same boundary |
| --- | --- | --- |
| Empty intro/role, bound details | Cleanup inserted a request-to-regenerate message into both empty fields | Both fields remain empty |
| Five/six verified owners | Five retained; sixth removed before recovery | Every incoming project and its own body/source rows retained |
| Eight/nine verified details | Ninth text, Fact and Claim row removed | All incoming rows reach initial projection |
| Award owner + another owner without an award | Hard Fact Guard changed the award wording and cleared its source row | Award text and Fact/Claim row unchanged in both owner orders |

For the award counterexample, Compilation correctly produces the award Fact under one owner and the negative constraint under another. The receiver accepts exact local Fact text and references. The first factual corruption was guard_hard_facts, whose request-wide award flag was disabled by the other owner's negative sentence. This release removes that Canonical project rewrite, not the underlying negative constraint.

## Actual callers and authority

- create_generation constructs the same request's Canonical Build/Views before model preparation. After reception and schema normalization it explicitly calls Cleanup and Hard Fact Guard with canonical_mode=True.
- The switch is a server-side call argument, not a model-provided trust flag, public schema field or new semantic state. It grants no eligibility or binding.
- result_cleanup_service has one business caller, generation_service. Its default standalone/legacy behavior remains available for existing callers/tests.
- fact_guard_service also has a legacy Gate caller. That path still uses default behavior; the Canonical generation path is the only business caller opting out of project reinterpretation.
- Other Hard Fact Guard sections, including education, skills, summaries and coaching text, keep their existing behavior. This release does not claim their request-wide interpretation has been audited away.

## Before and after

Before:

    Canonical evidence -> bounded model reception/source validation
      -> normalize original rows
      -> Cleanup inserts body defaults and truncates projects/details
      -> Hard Fact Guard applies request-wide keywords to every project
      -> existing fallback/candidate binding/initial projection

After:

    same Canonical evidence -> unchanged reception/source validation
      -> normalize original rows
      -> Canonical Cleanup preserves empty body and all project/detail rows
      -> Canonical Guard leaves project content/attachments unchanged
      -> same fallback/candidate binding/initial projection

Default legacy cleanup still retains its old five-project/eight-detail limits and default body message. Default legacy Guard still performs its old hard-fact substitutions. They no longer compete with Canonical project decisions on the production generation call sites.

## Cleanup contract

- Empty intro/role remain empty; an empty details list stays empty. Existing name/time header handling is not changed.
- No Canonical project or detail selection is performed in Cleanup. Request length limits remain unchanged; no new ranking policy is introduced.
- Details and both attachment rows are processed by original index. Empty rows cannot shift later bindings.
- Existing provenance_text_unchanged determines whether a cleaned field may retain its existing references. A substantive marker replacement still clears that field's obsolete proof; unrelated rows survive.
- Project aggregate references are filtered only by the existing removal/survival logic. They are not promoted to intro or role references.
- This cleanup function is not an alternative source validator. Invalid declarations still fail in the real receiver before this stage.

## Guard contract

Canonical mode leaves the deep-copied projects intact rather than using _provided_facts(raw_input) to rewrite them. No owner-local keyword scanner, semantic reconstruction, new recovery, copied Fact or new binding is added.

The request-wide flags remain in use for unrelated sections and the legacy API. The model receiver still rejects missing owner/references, unknown IDs, cross-owner sources, incorrect lineage and unsupported text. A bypass of the old project rewrite is not a claim that an unverified field is now supported.

Normal, long-input and retry evidence handling is unchanged. Pure JSON parse failure still uses its existing Stable Fallback compatibility route; evidence-contract failure does not become a JSON failure and does not enter that fallback. Internally generated fallback content is not falsely reported as a verified model response.

## Verification

- Dedicated initial run before business edits: 7 failed, 3 passed, including direct pre-recovery count and text/source assertions.
- Final dedicated suite: 34 passed. It includes owner order reversal, award/online negatives, local responsibility limits, five/six and eight/nine boundaries, blank-row positions, header-only body placement, equal text under different owners, idempotence, input immutability, stale-proof clearing, legacy compatibility, receiver rejection, normal/long retries and parse fallback.
- Three accurate historical input fixtures use controlled returns through real reception, initial projection, saving and DOCX. The tests do not reconstruct historical model text.
- Full ecommerce and competition/campus fixtures were held out from this release's business implementation/debugging cases, then executed after the three business edits. Their initial text, owner and Fact/Claim lineage assertions passed. These are existing regression fixtures, not unseen real-model responses.
- Full pytest: 1006 passed, 749 datetime deprecation warnings. No existing test expectation was changed.
- Separate golden/DOCX selection: 21 passed. Python compilation of backend/app and the dedicated test passed with bytecode redirected to the system temporary directory. Git diff whitespace checks passed; configured LF-to-CRLF notices are not whitespace errors.

The network boundary is controlled; Binder, eligibility, verification, Planner, Gate, saving and DOCX logic remain real. The full isolated run forbids socket connections, redirects logs/output and uses a temporary pytest directory. Test count is not proof of arbitrary writing quality.

## Residual findings and acceptance limits

1. NEW_FINDING / confirmed residual: nine verified details now reach the initial Planner intact, but reconcile_resume_projects is the first later writer reducing them to eight in the diagnostic sample. Its nested budget behavior and later Layering/Increment caps remain unchanged. Final Gate reports ELIGIBLE_FACT_UNPROJECTED as warning and the result can be saved. The dedicated test records this separate stage evidence instead of pretending initial preservation guarantees final completeness.
2. Known residual: unverified_rewrite remains strict. This release does not solve the legitimate paraphrase versus literal-verification mismatch or establish production model success rate.
3. Known residual: downstream information-gain deletion, Validity project deletion and the critical-Gate-to-save success policy remain outside scope.
4. Non-project global Guard interpretation remains available. Header extraction, unknown names/positions and generic presentation quality are not addressed.
5. Initial projects can still be transformed by existing fallback, binding and later rendering preparation. Tests assert the precise changed boundary instead of requiring unrelated later fields to remain identical.

Deployment shallow/full smoke and real-model input acceptance have not been run. Smoke success cannot replace owner-local evidence checks, and historical failures cannot be declared fixed solely from controlled exact-text returns.

## Rollback boundary

The three business files, dedicated test, VERSION and release documentation form one local change set. No migration or data conversion is involved. Reverting this change set restores the prior Canonical call selection and legacy cleanup/Guard behavior, including the known loss risks. Do not revert unrelated user changes or restore historical inaccessible test artifacts.

No deployment commands are included in this document; they are supplied directly in the completion response.
