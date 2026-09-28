# v0.9.19.4.2 Header-Aware Expression Coverage

## Evidence and scope

Baseline: main / `31eb838` / v0.9.19.4.1. The unrelated existing `.pytest-*` deletions were not touched. For test 2's exact raw input, the real Canonical Build gives EXP-001-F001 source span `(34, 65)`, a qualified name span `(34, 40)` and a qualified time span `(41, 48)` containing `2026年5月`. EXP-001-F004 span `(153, 173)` has no matching header evidence. The production request `req_6df5ad1df500430bb691b5e2f5254a8b` logged coverage omissions for F001 and F004, but its original candidate text was not retained. Controlled returns here demonstrate the current behavior and wiring, not a complete replay of that request.

## Contract

The writer still declares all eligible Fact sources using `canonical_fact_compositions_v2`. The v5 reviewer still returns only per-unit `decisions` and per-Fact `coverage`; it does not write replacement text. For overall Fact display coverage, it may count a name or time already displayed in the same owner's frozen, qualified header only when the field's exact source span lies within that Fact and its value matches that source slice. No inferred, pending, cross-owner or aggregate project source can substitute. Action, quantity, responsibility, status and necessary qualifications remain subject to the existing per-unit and overall checks. In particular, F004's classroom-display and non-operation statement is not covered by F001's header.

The request-local receipt binds the approved header evidence and verifies the corresponding actual project header before final delivery. Changing or deleting that header invalidates the receipt; it cannot be used to excuse a changed body. Build, Fact, Claim, eligibility, owner, Gate, model selection and the two-call budget are unchanged. Legacy has no new header-covering authority.

## Verification and limits

Failure-first tests established that the previous review input lacked the header evidence and accepted a receipt after the time header was changed. New tests use the exact test 2 input and real Build/Views, check qualified/pending and F004 contrasts, reject F004 omission and per-unit overclaim, and run controlled network returns through reception, review, Binder, later processing, Gate, SQLite save and DOCX. The saved F001 detail omits the date while the delivered header retains it; each surviving detail keeps its own Fact/Claim line. The downstream detail order may change with attachments together.

The focused v0.9.19.4.1/v0.9.19.4.2 suite passed 21 tests. The full isolated suite passed 1824 tests; the golden/DOCX-focused suite passed 17. A first full run had one sandbox-only log-write failure; redirecting that log outside the repository made the original assertion pass without changing its test. Controlled reviewer `complete` demonstrates contract wiring, not reviewer semantic accuracy. The original F004 candidate remains unknown, so its historical omission is unresolved. Real-model acceptance should repeat the exact test 2 input and healthy holdouts, inspect both v5 coverage verdicts and delivered content, and count failures separately; it was not run in this iteration.

Rollback scope is the header evidence supplied to the v5 review, its request-local receipt check and the matching template text. Rolling back only the receipt or only the prompt would leave the coverage interpretation inconsistent. No deployment or paid model call was made.
