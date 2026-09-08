# Canonical Provenance Contract Closure

v0.9.8.9 closes the remaining ambiguity between field-local provenance and a project's aggregate source set.

`source_fact_ids` and `source_claim_ids` are project-level aggregates. They establish that a project has canonical support, but do not prove that `intro` or `role` expresses each listed item. Field-local evidence is limited to `role_source_fact_ids`, `role_source_claim_ids`, `detail_fact_ids`, and `detail_claim_ids`.

In Canonical mode, Fact Coverage reads only the frozen owner's eligible Fact scope. It does not compare a locally-bound detail against the global Ledger and cannot move that detail into another project. Existing eligible local attachments remain valid after deterministic wording cleanup.

The Repair Router removes an exact duplicate only when both visible fields carry the same field-local Fact and Claim attachments from the same frozen owner. A repeated field with only project-level aggregate provenance remains visible and is counted as an insufficient-provenance skip. This preserves a conservative repair boundary without inventing an attachment.

When a bound role or detail is removed, its Fact and Claim rows are removed with it. A project aggregate that existed only through a removed detail is also removed unless that attachment remains on another detail or the role field. The system does not infer that an aggregate must now belong to `intro`.

This change does not add Facts, Claims, owners, types, semantic compilation, recovery logic, or output text. It keeps the existing Delivery Gate read-only and leaves legacy raw-input APIs available for their existing callers.
