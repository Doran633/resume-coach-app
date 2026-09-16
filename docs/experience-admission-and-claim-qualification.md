# v0.9.18.1.1: Experience Admission and Claim Qualification Correction

## Baseline and evidence boundaries

Branch main, commit 5df9beae52cec64d42901a2dbe01b4f54ea5e01e, version0.9.18.1. Applicable user-level AGENTS and the existing upstream, evidence preparation and delivery test harnesses were read. Scoped business/test/document changes were initially clean. Existing inaccessible historical pytest artifacts were not cleaned or reverted.

The three complete ordinary-user frontend, Java and research inputs are stored in tests/fixtures/v091811_normal_inputs.json. They are current-code replay inputs, not recovered historical model responses. Historical DOCX was symptom evidence only. Network responses in delivery tests are controlled Fact placements from the real Canonical Build, not historical snapshots.

Before changes, the unlabeled Java introduction entered the first-experience default path. Its graduation year, requested internship and skill statements entered an owner; the requested backend internship plus a separate interface-testing skill could satisfy type evidence. The exact same real experiences without that introduction remained valid. The independent clause “目前尚未开展相关实验” was positive/confirmed/eligible, while the preceding research plan was already withheld. Initial new tests recorded35 failures and5 passes before business changes.

## Actual responsibility and changes

1. semantic_experience_segmentation_service.py: segment_semantic_experiences still owns partition decisions. _experience_source_ranges identifies local context assertions, preserves their original offsets and passes complementary original slices onward. Skill/background prefixes followed by independently supported performed work do not erase that work. A conjunction alone is insufficient; intent operators are not stripped to manufacture a performed action. _has_initial_experience_evidence replaces the unqualified first-fragment default with existing anchors or local action/object and completed/passive relation evidence. Unknown fragments remain ambiguous_source_spans with clarification questions. Structured/explicit paths propagate pending preambles rather than dropping those records.
2. input_semantic_role_service.py: shares the existing partition context predicate for local career intent rather than interpreting it as a structural internship label. Negation is anchored to a local assertion with optional subject/current-time context; a negation-looking object noun alone does not negate its governing action.
3. input_claim_resolution_service.py: existing clause boundaries recognize independent career intent and aspect negation. Current-time context cannot override “尚未/还未”. The same eligibility function remains authoritative; negative/denied Claims are excluded, not erased. Necessary dependent qualifications retain their existing treatment.
4. experience_type_resolution_service.py: removes the combination of a role anywhere in an owner with arbitrary duties elsewhere. A descriptive internship phrase must connect to local duties, or use the existing source-backed heading/duty route. Explicit labels and all other type relations retain their authority.

Actual callers remain Semantic Segmentation -> Identity/Long Input -> Claim Resolution -> Canonical Type/Build -> existing read-only model evidence. No Identity, Long Input, Ledger, Prompt or downstream writer was edited. No second owner, classifier or semantic state was added. Legacy consumers use the same corrected functions; existing independent APIs are retained.

These are bounded deterministic language relations, not a universal parser. They still use regular expressions and existing lexical signals. No claim is made that arbitrary free prose or every future paraphrase is covered. Ambiguous text must not be promoted merely to improve coverage.

## Exact outcomes and preservation

| Full input | Real owners after correction | Frozen types | Eligible Facts |
| --- | --- | --- | --- |
| Frontend | 2 | Internship / Project | 10 |
| Java | 2 | Project / Competition | 10 |
| Research | 2 | Research / Campus-society | 8 |

Each corrected full input has the same owner-local substantive Fact signature as its version with only the self-introduction removed. The2027 graduation year is absent from owners/Claims and remains in non_experience_context_not_project_facts with an exact original slice. Background removal can renumber old erroneous owners and their IDs; preserving those old incorrect IDs is not a requirement. Real local dates, facts and limitations are checked against each input's source spans.

Inputs beginning directly with real, unheaded internship prose remain internships. Mixed background and real work preserve the latter. Context-only inputs produce no owner/Fact. Unknown fragments remain pending before later titled experiences. The aspect-negation controls retain completed data work while excluding the independent unperformed experiment; model constraints still carry the restriction. Compound object names and “我负责未完成订单的复查” remain eligible.

## Test contract and experiments

Tests execute real Segmentation, Identity, Claim, Type, Build, Views and request preparation. They inspect full model evidence, local source ranges and restrictions, prohibit semantic reconstruction during preparation and check deterministic repeated builds. LF/CRLF, blanks, sentence wrapping and selected in-word wrapping are compared without changing content. Full delivery controls run real reception, processing, Gate, persistence and DOCX against isolated SQLite and filesystem outputs; only network/infrastructure are controlled.

The industrial-engineering reserved sample was first used after the initial implementation and was not used to tune the rules. With and without its background,37 inspection records stay in the real internship and the unverified improvement remains excluded. Additional review exposed two missed cases after an initially passing full suite: ability-only “能够使用Python” admitted an owner, and “熟悉Vue并完成工单页面开发” lost actual work. Six failing controls were added before correcting local ability/context scope; the original passing “会使用” control was retained.

The user approved two narrowly scoped old time-test changes: the unchanged pure instruction “请写成2024年3月开始的数据分析项目。” and pure future statement “计划上线2025年3月的数据分析工具。” now assert no owner/time decision plus retained pending source/clarification. Negative/uncertain time cases retain their previous assertions. This is not a general claim that every planned phrase is filtered at admission; work inside an existing scope still reaches Claim qualification.

Six complete-input placement controls cover all-detail and mixed intro/role/detail. Before existing professionalization, every frozen Fact is present verbatim with correct field and aggregate lineage. In Java/research, the first observed later transformation is professionalize_resume_language: leading “我负责” becomes “负责”. Tests explicitly distinguish this established downstream transform from initial exact-text preservation, and continue checking every substantive clause and Fact/Claim attachment through saved payload and DOCX. No downstream behavior was changed or hidden by equal-count assertions.

Final validation:59 new tests passed;68 new plus Time Authority tests passed; full suite1328 passed with1227 existing datetime deprecation warnings; golden/DOCX selection61 passed. All236 Python files under backend/app, tests and scripts compiled in memory without bytecode. Scoped git diff --check and new-file whitespace checks passed. Full-suite logging constants were redirected by a temporary in-memory pytest plugin after collection, avoiding an existing llm_calls.jsonl permission failure without modifying any business configuration or assertion.

All six full delivery controls passed both real Gates and saved/exported. Final warning counts were5/2/4 for frontend/Java/research all-detail and3/2/3 for mixed placements; the only issue code was INCOMPLETE_SENTENCE. These remain warnings, not silently repaired findings. All runtime experiment output is in OS temporary v091811-* directories; logs and SQLite are redirected away from business data. The repository-wide status includes old inaccessible pytest artifacts, which remain outside this change.

## Residuals and rollback

- The separate Gate DENIED_CLAIM_ASSERTED scope defect is not fixed; a correctly excluded negative Claim may still interact with downstream validation. No claim that every formerly failing generation now succeeds.
- Names, positions, time-range display, skill display, personal summaries and professionalization remain in their existing planned stages. Current INCOMPLETE_SENTENCE warnings are not suppressed.
- Existing type-level prospective exclusions remain because equivalence with all Claim qualification forms has not been established. No duplicate filter was removed without evidence.
- No paid model call, production DB connection, deployment, commit or push occurred. Controlled delivery is not real-model success-rate evidence; live acceptance remains separate.
- Roll back the four business files together with this release's version/tests/docs after review. No schema or persistent-data migration is involved. Rollback restores the demonstrated admission and qualification mistakes; no automatic rollback is performed.
- Commit and deployment commands are intentionally not stored here. Stop at this release, without0.9.18.2 work.
