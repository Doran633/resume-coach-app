# Immutable Delivery Revision

## Scope

`v0.9.11` closes the final delivery boundary after Canonical projection,
presentation, narrow deterministic repair, and ownerless-project containment.
It does not introduce another semantic state, database table, or public API.
`GenerationResult.result_json` remains the single persisted delivery object.

## Delivery Boundary

The final sequence is:

```text
Delivery Gate evaluate
-> narrow Repair Router
-> final Ownerless Containment
-> Delivery Gate final recheck
-> documented internal metadata strip
-> Immutable Delivery Revision
-> GenerationResult.result_json
-> Web / DOCX
```

The final Gate observes the post-containment payload.  The revision boundary
may remove only internal hierarchy and slot-control metadata.  It compares the
visible delivery fingerprint before and after that removal, so project order,
public fields, `source_experience_id`, and Fact/Claim attachments cannot change
at the boundary.

## Persistence And Rendering

The revision serializes once and writes that exact JSON to `GenerationResult`.
After commit, the service reads the saved JSON again and checks its fingerprint.
Both API response paths read the persisted revision.

DOCX reads the same saved payload.  It may perform deterministic typography and
whitespace formatting in memory, but it cannot rebuild semantics, silently drop
projects, or cap project/detail counts.  A saved result that requires project or
body removal during export is rejected with a delivery-source error instead of
being silently changed.

## Invariants

- No semantic writer is reachable after revision construction.
- A revision is deterministic for an identical final payload.
- Persisted JSON and returned payload represent the same revision.
- Web and DOCX consume the same saved project and detail collection.
- DOCX never mutates `GenerationResult.result_json`.
- Existing historical results are rendered as saved or explicitly rejected; they
  are not semantically repaired during export.
