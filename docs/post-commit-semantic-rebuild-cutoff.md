# Post-Commit Semantic Rebuild Cutoff

## Scope

`v0.9.9.1` removes legacy semantic rebuild entry points from the Canonical
production path after Canonical Slot Binding / Owner Freeze. It does not alter
the legacy APIs, the Canonical ledger, prompt construction, or the delivery
format.

## Canonical Path After Owner Freeze

The remaining consumers receive the existing `CanonicalSemanticBuild`, owner
index, and consumer views. They may validate, remove invalid content, or make
deterministic presentation changes within the frozen scope. They do not receive
the full `raw_input` for semantic reinterpretation.

The following legacy semantic creators remain available only to legacy callers:

- uncertain-expression cleanup
- project-specificity fallback
- weak-profile strengthening
- semantic-unit completion
- summary-quality recovery
- text-integrity recovery

Technical-term resolution is calculated once from the compiled Fact Ledger and
passed to skill evidence, taxonomy, and relevance processing.

## Invariants

- Post-Commit Canonical processing does not build a second Identity, Claim, or
  Fact Ledger from `raw_input`.
- Post-Commit Canonical processing does not create a project, concrete fact, or
  stronger responsibility through the removed legacy creators.
- Owner, type, Claim eligibility, and Fact ownership remain outside the
  authority of the remaining consumers.
- Legacy function signatures remain available for non-Canonical callers.
