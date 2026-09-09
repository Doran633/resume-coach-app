# Presentation Field / Provenance Consistency

## Scope

`v0.9.9.2` makes presentation-only transformations preserve the relationship
between a surviving detail and its existing Fact / Claim attachment rows. It
does not create a new Fact, Claim, owner, type, eligibility result, recovery,
or projection candidate.

## Contract

- A detail is transformed as one row: text, `detail_fact_ids`, and
  `detail_claim_ids` are read using the same original index and are retained or
  removed together.
- A field-level attachment is exact only for the field row that already owns
  it. Project-level `source_fact_ids` and `source_claim_ids` remain aggregates;
  they cannot be used to guess an intro or role attachment.
- Two details may merge only where their explicit Fact provenance overlaps.
  A shared Fact can support a combined retained row; different or missing
  field provenance cannot.
- When a detail disappears, an aggregate attachment disappears only when it
  was directly attached to the removed detail and is no longer carried by a
  surviving detail or role. A surviving direct row can contribute to the
  project aggregate, but the reverse implication is forbidden.

## Affected Presentation Writers

- `resume_fact_dedup_service.py`
- `resume_dedup_quality_service.py`
- `resume_fact_cluster_dedup_service.py`
- `resume_output_firewall_service.py`

These writers remain presentation transformers. Canonical Coverage, the
Delivery Gate, Repair Router, and Projection Observer remain consumers and do
not gain new repair or provenance-inference authority in this version.

## Verification Boundary

The regression suite covers leading empty details, detail removal, claim-row
synchronization, same-text/different-source retention, role-only aggregate
preservation, idempotence, and the existing Sanitizer-to-Coverage contract.
This version intentionally does not address eligible Facts which were never
projected before the presentation pipeline; that is a later constrained
projection-completeness decision.
