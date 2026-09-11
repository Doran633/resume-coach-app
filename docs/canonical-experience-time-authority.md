# Canonical Experience Time Authority

## Purpose

v0.9.12.2 makes one owner-scoped time decision during Semantic Compilation.
It is a read-only compiled result, not another semantic source of truth.

## Authority Boundary

- Candidate time text is considered only inside the owner's source span or its eligible Claim lineage.
- The decision does not change owner, type, name, Claim eligibility, Fact eligibility, or provenance attachments.
- Canonical Project Projection and Canonical Title Resolution consume the decision; neither re-reads raw input or extracts time independently.
- Legacy callers remain outside this Canonical path for compatibility.

## Qualification

Qualified sources include explicit year-month values, explicit ranges, semesters,
academic years, and an explicit start paired with `至今` or `目前`. Version
numbers, metrics, competition sessions, and model, paper, or dataset years are
rejected. Claims that are instruction, negative, uncertain, planned, withheld,
or otherwise ineligible cannot support a decision.

When no local candidate qualifies, the owner remains visible with
`时间：【待填写】` and a neutral request for the missing time. The system does
not infer an end date, company, or position.

## Privacy and Verification

`canonical_experience_time_qualification.jsonl` contains only owner-safe
aggregate source and reason counts plus fingerprints. It never contains raw
input, time text, titles, Fact text, or Claim text. The regression suite covers
owner isolation, rejected false positives, stable repeated execution, and
preservation of existing Fact/Claim attachments.
