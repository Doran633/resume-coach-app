# Canonical Experience Header Completeness Authority

v0.9.12.3 turns the existing Canonical type, display-name, and time decisions into one deterministic owner-scoped header contract. It does not add a new semantic source of truth and does not re-read `raw_input` after Semantic Compilation.

## Header Contract

| Canonical type | Required fields |
| --- | --- |
| 项目经历 | `项目`、`时间` |
| 实习经历 | `企业`、`岗位`、`时间` |
| 科研经历 | `课题`、`时间` |
| 竞赛经历 / 竞赛获奖 | `竞赛`、`时间` |
| 开源经历 | `项目`、`时间` |
| 校园 / 社团经历 | `活动/组织`、`时间` |

Every required field remains visible. A qualified value is rendered after its label; an unavailable value is rendered as `字段：【待填写】` and produces a neutral, field-specific missing question.

## Internship Qualification

Enterprise and position fields exist only for internship headers. A value must come from the current owner's explicit heading or eligible Claim and must express a local employment or internship relationship. Job intent, negative or uncertain statements, planned content, responsibilities, project partners, schools, communities, and competition organizers cannot establish either field.

If more than one local candidate remains and the authority cannot choose uniquely, the field stays pending. Values are never borrowed from another owner.

## Read-Only Consumption

`CanonicalConsumerViews.planner_view` exposes the frozen header decision. Canonical Project Projection and Canonical Title Resolution consume that decision without independently extracting names, times, enterprises, or positions. Header assembly does not change project count, owner, type, Fact/Claim eligibility, text, or provenance attachments.

The qualification log records aggregate field states, source categories, reason codes, owner counts, and a fingerprint. It never records raw names, enterprises, positions, times, titles, or body text.
