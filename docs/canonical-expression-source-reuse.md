# v0.9.19.3.1 Canonical Expression Source Reuse

## Baseline and authority

Implemented on main at 5957d5a with working VERSION 0.9.19.3 and existing uncommitted v0.9.19.3 files. No previous changes or historical test artifacts were reverted. The local decision record is `GodSu/local-expression-contract-decision.md`; its controlled returns are not historical request snapshots.

Frozen Fact, Claim, owner, eligibility, header and qualification decisions are unchanged. The model still has one project-body writing entry. The independent reviewer judges each nonliteral unit but cannot write replacement text or promote a candidate into a frozen Fact. The two-call total remains unchanged.

## Contract change

The internal project protocol is `canonical_fact_compositions_v2`, retaining the same `source_experience_id` and `expression_units` shape. Every eligible Fact must be expressed completely at least once. An owner-local Fact may be explicitly cited again in another final field or detail row. Each unit has unique IDs, complete source order, its own candidate text and support check. Multiple units inside the same intro or role cannot overlap because the existing field attachment is flat. The same position, ordered sources and exact text cannot be submitted as a duplicate unit.

The receiver distinguishes coverage set from reference count. Request-local review keys distinguish units sharing a first Fact; receipts bind the Build fingerprint, owner-local frozen sources, position and text. Validation consumes the complete field text and precise field attachment, so a changed candidate cannot inherit another receipt. Fact/Claim field rows are derived from existing lineage, while aggregate sources remain a distinct union. Unknown, foreign, missing, ineligible, duplicate JSON keys, bad lineage, unsupported text and old project formats still fail. Source reuse neither authorizes partial summaries nor guesses missing citations.

## Downstream blocker and narrow resolution

Controlled full delivery showed the first loss at `ensure_recruiter_readability`: its similarity rule deleted two independently sourced detail rows already expressed in intro, without transforming their Fact/Claim rows. The final evidence check correctly refused this as `DELIVERY_EXPRESSION_CHANGED`. With explicit approval, Canonical normal-model projects now use readability assessment without detail deletion. The direct legacy and mock/fallback cleaning behavior remains. Exact duplicate content continues to face the existing receiver/dedup/Gate rules; no new recovery or post-hoc attachment binding was added.

## Evidence and limitations

Before change, an intro comprising F001/F002 plus F001 and F002 detail rows failed at `duplicate_fact_reference`, while a nonoverlapping complete composition passed. After change, controlled network-return generation keeps the explicit cross-field rows and their Claim lineage through Binder, later transforms, Gate, save and DOCX. Independent nonliteral expressions sharing F001 require distinct review decisions and cannot exchange receipts. Same-intro overlap, same-unit repetition, missing, foreign, unsupported and old-format controls remain rejected.

The previously captured real `normal_A` and `limited_A` writer/reviewer pairs were re-read without calling the API. Their F001 candidate borrowed an unlisted Fact; both still raise `MODEL_EXPRESSION_REJECTED` with `expression_review_added_claim`. This is a new offline replay of archived real returns, not the historical request itself. Partial overviews, ambiguous responsibility wording, true model compliance, semantic-review reliability and packaging quality remain outside this patch. Similarity-based readability scoring still observes repeated text; it no longer gets to delete sourced Canonical rows.

## Validation and rollback

Targeted receiver, golden and DOCX selection: 67 passed. Full isolated pytest: 1784 passed (existing deprecation warnings). Python compileall and scoped `git diff --check` passed. Tests use SQLite in memory and controlled network responses. The initially reused temporary test directory caused fixture setup errors; rerun in a fresh isolated directory passed. No paid model or production DB was used.

Rollback boundary: revert this version's protocol, review/coverage logic, Canonical readability wiring, templates, tests and version documents together. Do not roll back only the receiver: a v2 task with v1 duplicate handling would reject legitimate reuse; do not roll back only the readability exception: downstream would silently remove sourced rows again.
