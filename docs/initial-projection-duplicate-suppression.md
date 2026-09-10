# v0.9.10.1 Initial Projection Duplicate Suppression

This patch applies only while Canonical Resume Section Fallback constructs an
initial candidate.  When a recovered role has exactly the same normalized
display text and the same Fact and Claim lineage as the known intro or a
detail row, the role is left empty.  Existing content is retained.

Similarity alone, aggregate project provenance, cross-owner evidence, and
unknown field provenance are insufficient.  The post-commit Repair Router and
all other authority boundaries remain unchanged.
