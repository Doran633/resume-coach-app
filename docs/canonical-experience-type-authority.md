# Canonical Experience Type Authority

## Scope

v0.9.12.1 closes the type-authority gap between semantic segmentation and
Canonical Semantic Compilation. It does not modify segmentation boundaries,
names, facts, presentation, fallback, projection, or rendering.

## Authority

`SemanticExperienceSegmentation._infer_type` remains a useful provisional
hint for early structure work. It is not a formal type decision.

After Claim Resolution, Canonical Semantic Compilation calls the existing
relation-aware type resolver once for each `experience_id`. The resolver may
read only that Identity and its own eligible Claims. The resulting
`CanonicalExperienceTypeDecision` is the type consumed by Canonical routing
and then frozen for the rest of the request.

## Evidence rules

- Explicit experience labels have highest priority.
- Internship requires an explicit label, an organization and employment
  relation, or a role-shaped internship name plus local duties.
- Open-source experience requires an external contribution relation, such as
  a merged PR, issue fix, maintainer, or contributor relationship. A GitHub
  repository alone is not enough.
- Campus, research, and competition require both their local scene/entity and
  an author participation or responsibility relationship.
- Project evidence includes a local project/product entity with development,
  design, construction, iteration, or an explicit course-project relation.
- A weak keyword does not accumulate into a stronger type. When no type is
  uniquely supported, the resolver uses the existing conservative project
  default and records `ambiguous_default` as its source category.

## Boundaries and observability

The decision never changes owner, source span, Fact, Claim, eligibility, name,
or user-visible text. Existing `experience_type_resolution.jsonl` records only
type categories, confidence, aggregate signal categories, and internal IDs;
it does not record raw input, titles, or Claim text.

The old raw-input resolver remains for legacy callers. Canonical routing is
given the compiled type-decision mapping and does not invoke that branch.
