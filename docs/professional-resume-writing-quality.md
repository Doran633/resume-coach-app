# v0.9.19.8 Professional Resume Writing Quality

## Baseline and Scope

Started from `main / e6ae656f6cd80de4a527dd99fc0b2248c21dc8a3`, VERSION
`0.9.19.7`, with a clean tracked worktree. Read the applicable user AGENTS,
the generation-quality pipeline, candidate/review coordination, formal-bold
alignment, grounded-packaging stage and the existing delivery test harness.
No existing work was reverted. This stage does not roll back the previous UI.

Only three production files changed:

- `backend/app/services/prompt_service.py`: shared Canonical writing brief in
  the existing template selection, not a new writer or evidence preparation.
- `prompts/generate_resume_coach_result.md`: isolate redundant style/summary
  tasks behind the existing legacy marker; keep safety and format requirements.
- `prompts/generate_resume_coach_result_long.md`: the same summary-task exit;
  normal and long requests consume the same new writing brief.

No changes to model selection, A composition protocol, reviewer, receiver,
Binder, ledger, frozen semantics, qualification, Gate, post-processing, skills,
foundational facts, frontend, compatibility fields, database or DOCX renderer.
No model call, production database access, deployment, commit or push occurred.

## Evidence and Earliest Change

Retained exact inputs, writer requests/responses and stage snapshots were read
from `GodSu/v09195-97-implementation/extra20-197`. These are prior real
experiments, not newly executed model calls or historical production replays.
The latest uploaded DOCX files were symptom references, not reconstructed
requests. The four exact test inputs are now included in the new test fixtures.

| Sample / retained writer call | Observed first in writer response | Later stages |
| --- | --- | --- |
| Normal / call 3 | First-person Vue task narration; summary repeats degree, graduation date, project names and adds an independent-capability phrase | All four project expressions survive receiving, Binder, template guard, professionalization and final checks; summary loses only its terminal period |
| Thin / call 1 | Intro with only F001 borrows F002 responsibility; summary calls a job seeker an intern | Fails before a successful payload; no saved result is invented for this candidate |
| Limited / call 5 | Eight mostly literal project units; summary starts with education and a technology list | The project expressions survive; summary period cleanup is not the cause of catalog-style prose |
| Java / call 7 | Name/date opening bullets and first-person role narration; summary repeats education and job intention | Ten expressions survive the recorded chain; used only after primary implementation as this stage's holdout |

These observations locate the existing writing-quality symptoms at the writer,
not in a demonstrated new downstream corruption. They do not establish that
all reviewer refusals are mistakes. In particular, undeclared borrowing in the
thin candidate remains invalid. The normal summary's independent-capability
claim is not certified by project review receipts.

## Target Drafts and Boundaries

`tests/fixtures/v09198_writing_quality_cases.json` retains the three complete
normal/thin/limited inputs. Each human project unit lists the complete original
Fact texts supporting it. Tests resolve those texts against a real Build to
obtain Fact IDs and Claim lineage; no invented legal IDs are used. Offline
`summary_evidence` records the action sources for the human summary, not a new
runtime field, model trust flag or persistent source authority.

`v09198_writing_quality_holdout.json` retains the Java/backend and competition
input separately. Its targets were added after the primary implementation and
57-test joint run passed. The writing task was not retuned on this holdout.

Examples of the editorial standard:

- Normal: organize team participation, Vue page scope and peer-provided API
  into one clear work statement; keep the 18 test records and all checked
  states. Do not add independent ownership or interface design.
- Thin: keep the two-person collaboration, exclusive local page duties,
  supplied interface, empty-input/repeated-click checks and classroom demo;
  turn conversational narration into concise work description, not a longer
  invented engineering lifecycle.
- Limited: group 45 records and their metadata with 20 interface tests while
  retaining all named conditions; describe trial feedback as clearer prompts,
  not a measured usability gain. Keep deployed personal work separate from
  the other team's local-only demonstration.
- Holdout: explain tables, reservation states and cache invalidation as actual
  work; keep the 24 tests, front-end collaboration, 126 team questionnaires,
  five-person competition and team award without inventing causality.

The counterexamples add independent system ownership/deployment, interface
design/debouncing, a 30% conversion outcome, or omit repeated-click checking.
The uncertainty control keeps the same candidate but returns a major
uncertainty verdict. Those controlled replies test the unchanged rejection
plumbing; they do not prove that a real reviewer will correctly classify them.

## Writing Task and Permissions

The existing `_generation_template` now provides one `canonical_writing_brief`:

1. Lead with recognizable work and organize compatible, explicitly declared
   same-owner adjacent sources, without turning juxtaposition into causality.
2. Allow justified explanation and compression of auxiliary procedure. Preserve
   action, object, technology, quantity, result, ownership, scope and status.
3. Avoid a standalone name/date opening only when the qualified frozen header
   already delivers the exact corresponding source. Keep references and any
   body information required for meaning; do not strip text in a renderer.
4. Derive summary capability focus from representative actions and explicit
   background, not degree/project/technology catalogs or the job target alone.
5. Use one complete multi-source editorial example plus a purpose/result
   contrast. Example sources are explicitly not evidence for the current user.

This replaces three generic shared lines and the Canonical fixed summary
length/count and redundant style instructions. Existing safety, non-project
fields and explicit source protocol remain. The brief is more concrete, not
a claim that the whole prompt is shorter. No online quality gate was added.
Literal wording remains accepted when appropriate; successful literal delivery
is not packaging-quality acceptance.

| Responsibility | Unchanged boundary |
| --- | --- |
| Frozen Build/Views | Sole input evidence; candidate prose never writes back |
| Existing writer | Sole substantive project/summary writing call; current A protocol |
| Reviewer | Probabilistic verdict only, no replacement prose; unchanged v6 |
| Receiver / Binder | Same source and receipt validation, no guessed bindings |
| Post-processing / Gate | No added expansion, recovery, deletion or lower severity |
| Saved bold / DOCX | Same persisted structured expressions, no separate writer |

Default budgeting remains at most two writer calls and one review, with the
existing lower-total overrides and 8192/4096 role caps. Reviewer uncertainty,
overreach, coverage omissions, invalid source mappings, truncation and final
quality failures continue to use existing failure exits. Summary is not newly
covered by the per-project semantic review contract.

## Verification

Initial controlled regression: six actual-task tests failed because the new
shared brief was absent; seventeen delivery/rejection/compatibility controls
passed before production changes. All human target drafts were therefore
already deliverable under existing source/review plumbing. No demonstrated
review-task conflict justified modifying the reviewer.

New specialty coverage (26 tests):

- Three primary inputs, normal/long paths, actual network-bound writer tasks
  and a corrected JSON retry with unchanged frozen evidence.
- Primary and held-out targets with first unit in intro, role or detail:
  twelve real receiving/review/Binder/post-processing/final Gate/save/DOCX runs.
  Assertions compare actual prose, per-field Fact/Claim attachments and owner
  aggregates, not merely counts. Controlled verdicts test receipt handling.
- Five nearby overreach/omission/uncertainty failures: no successful result or
  DOCX, same two controlled calls, real rejection handling.
- Three full-original controls: no new online packaging refusal or needless
  review, retaining exact source attachments.

Approved old-test migrations, and only these:

- Two complete normal/long task snapshots in `test_v091741...` (16 cases).
  The entire actual tasks were reviewed, including retry additions and all
  still-active instructions. Protocol hash and legacy task hashes are unchanged.
- One task-location assertion in `test_v091921_task_consistency.py` (24 cases):
  check auxiliary/role limits in the unchanged actual `expression_scope`, and
  non-forced rewriting in the shared writing brief, not only the former block.
  Original inputs, source equality, forbidden competing permissions, retries,
  compatibility, rejection, saving and DOCX assertions remain.

Task hashes: normal
`5805d0dc0159f0c9e48cf8c7ae176ba45b17c0f96fe45c938203cedafecda5ad`, long
`7d1915ba53271f78ed59d059e4d70bc2370f7a37821af4c1f36758656c9c537d`.
The internal output-contract SHA-256 remains
`f8d1e5bde929484058e02931fb5c6eb44f0da360d7da422a99857e3444775c10`.

The isolated harness uses an in-memory database, private log/DOCX directories,
an offline provider key and a network failure sentinel. Test infrastructure
observers call the actual services; controlled provider replies replace only
network I/O. Artifacts and full request/stage snapshots are under
`GodSu/v09198-implementation`, not production logs.

Final offline results: new specialty 26 passed (included in the joint run),
specialty/related joint 133 passed, full pytest 1884 passed, golden/DOCX group
28 passed. Python compilation of `backend/app` and `tests`, plus
`git diff --check`, passed. The first full run's 24 task-location failures
were migrated only after approval. Warnings are existing SQLAlchemy UTC
deprecations and the isolated runner's already-imported pytest plugin warning,
not hidden failures. No frontend rebuild was needed or claimed: it is unchanged.

## Quality Acceptance and Remaining Work

No API authorization remains; this stage made zero real calls. Historical
candidates were not altered and are not treated as new-prompt output. The
anonymous `blind-editorial-pack.md` compares prior real candidates with human
target drafts under identical inputs; labels are separated into an answer key.
Independent human scoring is not performed or fabricated. This only calibrates
the intended target, not the real writer's improvement.

A separately authorized real-model evaluation must use the same four complete
inputs and parameters. Judge readability, organization, role relevance,
attractiveness and factual boundaries without exposing version labels; cite
specific improvements and failures. Count complete generations, retries,
review decisions, finish reasons, costs/latency and failures separately. The
old authorized 50 calls do not provide new budget. Do not retry until a pleasing
output appears or equate preservation of originals with competitive packaging.

Engineering compatibility can pass while actual packaging remains unproven.
If revised outputs still predominantly restate the input without organizational
or capability-presentation benefit, quality acceptance is not met. Reviewer
variation, summary overstatement, thin-input undeclared borrowing, boundary
prose defects and output burden remain risks; this prompt-only change does not
claim to solve them. More instruction text may also add prompt tokens/latency;
that cost is unmeasured without a real authorized run.

No broad new tracing, model switch, validation relaxation, layout edit or
automatic next-version implementation is included. Roll back only this stage's
three writer-task files and their reviewed snapshots/version documentation;
no schema or saved-result migration is necessary. Preserve all v0.9.19.5/6/7
budgeting, source checks, one-writer mapping and compatibility behavior.
