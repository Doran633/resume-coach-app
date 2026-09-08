# Presentation Provenance Preservation

v0.9.8.8.1 preserves the existing Fact and Claim attachments while presentation cleanup changes project fields.

`source_fact_ids` remains a project-level aggregate. It is not reinterpreted as proof that every individual field expresses every referenced fact. Field-specific provenance continues to use `role_source_fact_ids`, `detail_fact_ids`, `role_source_claim_ids`, and `detail_claim_ids`.

The Body Sanitizer treats each detail together with its corresponding Fact and Claim rows. It removes a row only with the detail it belongs to. Equal detail text is deduplicated only when its Fact and Claim rows are also equal; otherwise the later fact-aware deduplication stage makes the decision.

In Canonical mode, Fact Coverage validates existing attachments against the frozen owner scope and eligibility. It retains valid attachments when wording has been deterministically cleaned, instead of replacing them merely because a new text-match score is low. Attachments from another owner, an ineligible Claim, or an empty project body are removed and are not counted as coverage.

This contract does not create new facts, claims, owners, types, or text. It keeps provenance available to the existing Projection Observer and Delivery Gate while preserving the current public output filtering behavior.
