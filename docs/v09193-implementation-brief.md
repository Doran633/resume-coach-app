# v0.9.19.3 Implementation Brief: Canonical Evidence-Bounded Composition

Status: proposal only, approval required. VERSION remains 0.9.19.2.1.

Historical status above describes the original read-only brief. The subsequently approved implementation and offline results are recorded in [the implementation report](canonical-evidence-bounded-composition.md). Real-model acceptance remains incomplete.

## 中文结论

推荐方案B的窄版本：同owner、冻结顺序相邻、全部来源显式声明的表达单元；相邻只是结构条件，不能代替语义复核。
复用现有字段Fact/Claim数组、请求内复核凭据和集中验证入口，不新增事实权威或下游写作者。
明确阻塞在现有单Fact接收、复核映射及逐Fact文本拼接验证，不能仅凭数组存在宣称兼容。
方案A仍是可选的小改动方案，但须接受当前组织能力限制。方案B也不解决限定丢失、复核波动及summary/四版本语义问题。
本轮仓库1726项与隔离探针8项通过，专项/黄金/DOCX联合227项通过；新组合协议未实施、未验收，不建议据此部署。

Baseline: main / 5957d5ae1976119a99740bece414d0f6bf7d8262 plus existing uncommitted implementation.
This review changes no business source, prompt, configuration, API, or frozen semantics.
No external API calls, production database, deployment, commit, or push.

## 1. Evidence and decision

The eight-call and ten-call reports under GodSu are different experiments, not historical request reconstructions.
The earlier eight-call experiment saved five outputs but all five omitted four version fields; downstream supplementation introduced unsupported wording.
The existing uncommitted version-contract increment addresses the structural omission and exits that normal-path supplement call.
The subsequent ten-call experiment received complete versions in all four writer responses, but only one of four generations saved.
All ten calls ended with stop. This does not close long-input truncation or budget risk.

The normal sample's first candidate combined F001 (Python/FastAPI project development) with F002 (upload/search/display), while citing F001 only and separately expressing F002.
The limited sample's first candidate borrowed classroom-use status from F006. These are source-unit violations, not proof the user never did those things.
Dropping the exclusive scope from the Vue team's "only responsible for pages" is a separate, genuine qualification loss; composition must not legalize it.
Identical reviewer requests gave differing item verdicts. A valid excerpt and supported verdict are not deterministic semantic proof.
Cached held-out replay and three source-text controls were offline controls, not extra successful real-model samples or a proposed fallback.

Recommendation: approve a narrow B design, then implement and validate separately. Do not deploy on the basis of offline migration.

## 2. Options

| Option | Benefit | Cost / limit | Decision |
| --- | --- | --- | --- |
| A: keep one Fact per candidate | Current receipt and source protocol unchanged; smallest risk surface | Natural introduction often needs adjacent Facts; observed writers borrow facts and duplicate expression; responsibility ambiguity remains | Valid lower-cost alternative if limited organization is acceptable |
| B: explicit same-owner expression units | A sentence can cite all of its actual evidence without changing Ledger | Receiver, receipt, review mapping and final text verification must migrate together | Recommend a bounded first implementation |
| Arbitrary owner-wide synthesis | More freedom | Owner identity alone does not prove relationships, causes, achievement or responsibility; unclear per-field evidence | Not recommended |
| Silent deduplication, original-text recovery or extra reviewer votes | May improve apparent completion | Changes meaning, hides failures or treats consensus as proof | Reject |

B initially permits only contiguous Facts in frozen source order within one owner. Adjacency is a structural restriction, NOT proof they can be semantically fused.
The reviewer must still establish compatible actor, action/object, responsibility, time/status and qualifiers. Separate tasks or actors cannot become a shared result.
This smaller scope addresses the observed F001/F002 case. It does not promise to permit F001/F006 classroom-state borrowing.
Singleton units remain legal, including unchanged source wording. Do not force composition or impose a word-count expansion target.
If non-contiguous composition is required for the product, approve that separately with controls; do not silently treat all owner facts as one support pool.

## 3. Actual call chain and reuse

| Boundary and current caller | Current capability / assumption | Proposed treatment |
| --- | --- | --- |
| generation.create_generation -> Build -> build_canonical_consumer_views | Same-request frozen eligible facts, scope and lineage | Reuse read-only |
| prompt._canonical_evidence_context / _canonical_output_contract | All facts supplied, one Fact key -> position/text | Change internal output contract, not fact evidence |
| generation.build_llm_generation -> compose_model_fact_references | Exact owner/key set; duplicate JSON keys; each candidate keyed by one fid; details one fid each | Validate explicit unit partition before assembly |
| CanonicalExpressionReview.signature/pending/accept/text_for | Signature and decision keyed by one fid; source excerpt anchors in one source string | Extend this existing request-local receipt to a source tuple and unit text |
| prompt.build_expression_review_prompt | One source fact plus Claim context not additional support | Supply all and only cited support Facts separately, plus applicable restrictions/context |
| validate_model_project_evidence -> _validate_project_evidence | Arrays allow multiple IDs, but support is joining each fid's accepted text; no free multi-Fact sentence | Replace expression-mode text lookup with exact accepted unit/field composition lookup; retain literal legacy path |
| bind_projects_to_experience_slots | Calls the same _validate_project_evidence; complete verified fields can freeze declared owner | Reuse same validator, no new owner decision or title inference |
| canonical_project_projection._field_fact_evidence | Accepts list of valid Fact IDs with exact Claim lineage; missing facts may be appended | Reuse; complete units must result in no missing facts/additions; planner does not prove prose |
| Reconciliation | Canonical keeps concrete projects; old selection budgets are not an authorization for validated content | Keep existing branch, test no loss |
| organize_adaptive_narrative | Sorts detail records by existing text dimensions, moves Fact/Claim arrays together | Keep current behavior; no promise of frozen final row order, no new sorting strategy |
| deduplicate_resume_facts | Canonical exact normalized text AND exact source set; partial overlap retained | Keep; receiver already rejects repeated fact allocation |
| template guard / professionalization | preserve_project_expressions avoids competing project rewriting | Keep; no extra writer |
| final _check_final_expression_evidence before/after Router | Reuses validate_model_project_evidence, rejects changed body with DELIVERY_EXPRESSION_CHANGED | Adapt via the same support entry, not a second checker |
| Gate | Checks owner/lineage, restrictions and quality, not arbitrary paraphrase entailment | Read-only, rules unchanged; a pass is not semantic certification |
| immutable revision -> GenerationResult -> DOCX | Visible projection compares text and all field source arrays; renderer consumes saved payload | Reuse unchanged; export test must inspect text AND saved attachments |

Code anchors at this baseline: experience_slot_service.py:228,315,552,629,899; prompt_service.py:256,288;
generation_service.py:439,630,858,977,1082,1110,1161;
canonical_project_projection_service.py:53; resume_fact_dedup_service.py:278;
resume_adaptive_narrative_service.py:58; immutable_delivery_revision_service.py:30.
The existing arrays are sufficient for persisted attribution. The current receiver/receipt is NOT sufficient for newly composed prose.

## 4. Minimal internal protocol proposal

Use one explicit new server-selected protocol: canonical_fact_compositions_v1.
Replace fact_placements in Canonical responses, rather than keep a second competing allocation map:

```json
{
  "source_experience_id": "EXP-001",
  "expression_units": [
    {
      "fact_ids": ["EXP-001-F001", "EXP-001-F002"],
      "position": "detail",
      "text": "Candidate supported by the complete cited source set"
    }
  ]
}
```

Model must not return headers, Claim arrays, aggregate IDs, trust flags or reviewer conclusions.
Each owner occurs once. Unit facts are nonempty, unique, eligible, current-owner, in source order and contiguous.
The multiset union across all units must equal the eligible Fact set exactly, not merely have the same count.
Unknown, missing, repeated (inside/across units), cross-owner references and extra keys fail. JSON duplicate checks remain before overwrite.
Identical text with different Fact IDs is not merged. Shared Claim does not authorize dropping a distinct Fact.
intro/role may be unassigned. A detail unit becomes one detail row; multiple intro/role units are joined deterministically without a new connecting claim.
Backend orders units by earliest frozen source position and derives Claim rows and project aggregate unions from existing lineage.
Do not turn first/last ID into a range authorizing uncited facts. Do not generate causal connectors.

Reuse CanonicalExpressionReview, not a second IR. A unit identity can be derived from owner plus ordered full Fact-ID tuple; server can use its first Fact as a unique request-local lookup key after disjointness validation.
Bind receipt to Build object/fingerprint, protocol, ordered full source records, Claim lineage/restrictions, position and candidate text.
Any content/source-set/position change invalidates it; different request cannot reuse it.
Persist only existing payload fields and field arrays; request-local units/receipts die with the request. No database or public schema change.
For an intro/role with several units, support validates the deterministic composition of complete accepted units, never each Fact independently assigned the whole combined sentence.

Reviewer map remains backend-keyed but new review protocol must anchor a source issue to a cited Fact ID plus its exact excerpt (not an ambiguous concatenated source string).
Candidate issues anchor to that unit text. Complete map, no extra/missing keys, known verdicts and unique excerpts remain mandatory.
Source issue on a noncited Fact fails format/lineage validation. Reviewer supplies no replacement prose.
These additions require an explicit review protocol migration; v2 cannot silently certify v3-shaped sources.

## 5. Expression boundary and responsibility

| Category | General rule | Contrast |
| --- | --- | --- |
| Allowed | Reorganize sentences; identify already explicit action/object; explain supplied work without adding events | Rearrange Python document organization and recording fields, retain quantity and collaboration |
| Allowed composition | All participating Facts explicitly cited, complete, same applicable actor/scope; conjunction does not invent dependency | Development + implemented functions, both sources included and not separately duplicated |
| Prohibited | New action/tool/quantity/outcome, causality, ownership, proficiency or experience breadth | Testing becomes issue diagnosis; purpose becomes achieved improvement |
| Qualification | Equivalent meaning, not literal token retention | Only pages cannot become whole-system delivery; local demo cannot become rollout |
| Ambiguous | Sparse action statement does not settle organizational accountability or leadership | Did pages -> responsible for page development needs scope analysis, not automatic supported/rejected |
| Assistance | Preserve subordinate contribution and task boundary; participation alone may erase that distinction | Helped test -> assisted testing is clear; -> participated in testing is observationally ambiguous |

Judge responsibility along independent axes: actual action, object scope, autonomy, accountability, team attribution and completion/status.
Generic responsible is not automatically leadership, but cannot silently erase assistance/exclusivity. Stronger ownership requires source support.
Use these as shared writing/review criteria, not an additional keyword classifier or synonym list.
When uncertain, existing uncertain failure applies; do not force word replacement or use repeated voting as proof.
Review remains probabilistic risk assessment, not frozen fact creation. Added source IDs alone do not establish entailment.

## 6. Permissions

| Component | Permitted | Forbidden |
| --- | --- | --- |
| Compilation | Existing freeze/eligibility only | Changed by this iteration |
| Single writer | Select legal grouping/position and evidence-bounded prose | New factual content, skipping sources, owner transfer |
| Receiver | Exact partition, schema, lineage and receipt validation | Interpret new facts or repair candidate text |
| Reviewer | Risk verdict and anchored issue | Replacement text, new Fact or stronger eligibility |
| Assembler | Join accepted units, derive arrays, consume frozen headers | Invent summary/causal connectors or overwrite Ledger |
| Binder | Existing owner freeze via shared validation | Independently approve semantic support |
| Downstream | Existing bounded cleanup/synchronized ordering/exact dedup | New substantive rewriting; IDs as blanket authorization |
| Gate / revision | Read-only quality rejection and unchanged delivery freeze | Semantic recovery or lowering critical |

## 7. Files and exit strategy

Proposed business changes: prompt_service.py (writer/reviewer data and contract), experience_slot_service.py (partition/receipt/shared support/assembly), generation_service.py (existing receipt/log and failure wiring only if needed).
Templates: normal/long project task and review_canonical_expressions.md internal schema/boundary migration only.
Tests and phase documents also change during implementation. Consumer Views, Ledger, Binder owner algorithm, Planner, Gate, revision and DOCX remain read-only by default.
No new service, persistent state, global verifier, recovery system or public output field.
If actual composed-text tests expose a downstream blocker, report earliest writer and minimal scope before expanding. Do not bypass it in generation.

Canonical switches explicitly from expressions_v1 to compositions_v1; no format guessing or simultaneous permissive success paths.
Keep old responses as rejection fixtures. Independent legacy parsing/writing remains separate and must not receive composition trust.
Rollback is atomic across writer task, receiver/review schema and receipt validation, not a database change or whole-worktree reset.
Previously saved results continue to render from existing payload/revision fields.

## 8. Failure and budget

Reference/schema failures use existing evidence-format/invalid families with precise reason categories.
Review rejects, uncertain, malformed maps, timeout or insufficient budget use existing expression failure families, no successful save/export.
Postprocessing change -> DELIVERY_EXPRESSION_CHANGED; final Gate critical -> DELIVERY_QUALITY_FAILED.
Maintain total two model calls including retries and failures: writer + batch reviewer normally. A format retry may consume the review budget and fail.
No extra repair call, field deletion, response stitching or original-text fallback disguised as expression success.
Pure JSON downgrade remains separately tested and cannot absorb protocol/review errors or count as composition success.

## 9. Offline proof and required implementation tests

This round executes the CURRENT protocol, not the proposed one. GodSu/test_v09193_readonly_composition.py adds isolated current-chain probes.
It checks literal multi-Fact intro/role and one-Fact details through save/DOCX, validates all field lineage, rejects new expression_units format, and demonstrates valid arrays alone cannot authorize composed prose.
Missing/cross-owner controls and a controlled reviewer rejection of single-Fact borrowing remain separate from real-model evidence.
Existing full-suite controls cover normal/thin/limited samples, repeated JSON keys, same text in different owners, shared Claim, responsibility increase, fabricated result, missing qualification, mapping/receipt invalidation and two-call budget.
Simulated supported proves wiring only. Source-text controls prove preservation, not expression quality. No business function is mocked to declare the proposed protocol compatible.

Implementation acceptance must add the following genuine new-protocol controls after approval:
- F001/F002 combined once with both IDs saves; retaining F002 elsewhere rejects duplicate allocation.
- Same sentence with one cited ID rejects; same-owner but incompatible actor/task/time rejects review.
- Contiguous singleton/multi-unit arrangements in intro/role/detail preserve exact source sets and qualifiers.
- Same-text distinct sources and shared Claim retain all Fact obligations, deduplicated Claim lineage only.
- Necessary limitation loss, novel performance/result and expanded responsibility reject; substantial lawful restructuring supports under controlled review.
- Actual review data includes every cited source and applicable constraint, excludes uncited content as support.
- Original input, Build/Views and ledger unchanged; units cannot borrow a different request receipt.
- Record receiver, Binder, projection, each content transform, pre/post-Router check, Gate, saved revision and DOCX; no restoration can conceal first loss.

## 10. Real acceptance and open issues

No API authorization remains for this round; calls made here: zero.
Before later real acceptance, approve samples and a total budget including writer/reviewer/retries. Use normal, thin, limited and unused holdout inputs.
Report actual protocol errors, lawful rewrite false rejection, harmful rewrite missed rejection, unchanged-source rate, lost qualifiers, grouping/duplicate rate, cost and latency.
Direct fixed-candidate reviewer controls and real generation are separate denominators. Repeat controls measure variance, not voting-based proof.
Require no structural leakage or observed known harmful candidate acceptance in the fixed suite; record limited sample size and do not infer universal reliability.
If legal composition remains frequently rejected, stop and report capability; do not keep expanding rules or lower standards.

Separate backlog: summary and four-version semantic support, paragraph flattening in sanitizer/whitespace passes, skill display, overall ordering/length allocation, truncation and two-call conflict.
Neither B nor offline green closes these issues. Composition also does not solve genuinely sparse evidence or all responsibility ambiguity.
The final deliverable is this Brief and current-version offline report, not a release recommendation or v0.9.19.3 implementation.
