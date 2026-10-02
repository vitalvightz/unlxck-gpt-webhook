# Live rehab prescription bundles

## Current flow and bottleneck

The rehab bank supplies canonical drills and demand metadata. Clinical policy
prescriptions bind each drill to its bank hash, stage, severity, instructions,
dose, stop rules and cadence. `resolve_injury_policy` validates those bindings,
filters candidates, keeps the greatest prescription priority and selects one
drill. Its singular output was the smallest live boundary forcing one
prescription to equal one drill.

`schedule_rehab` gates that episode's prescription using accepted work,
cadence, readiness, response history and the day's training demand.
`reconcile_session_prescription` projects due prescriptions onto Today and
enforces the existing allocation ceiling. Today also counts accepted blocks in
its daily reservation tally; both boundaries now use the same allocation helper.
Today renders the projected ordinary
blocks and freezes the accepted session. Completion resolves each bank drill
occurrence from that snapshot and records distinct exposures sharing one
injury response group.

## Minimal extension

A policy may explicitly opt in with `stage_bundles`, for example:

```json
{"stage_bundles": {"restore": ["reviewed_control", "reviewed_loading"]}}
```

These are compatible combinations to be reviewed as policy content, not ranked
alternatives to be automatically accumulated. The list supplies the exact count
and order. Every member must have a policy prescription in that same activated
stage, share its scheduling frequency, match its bank hash and pass the existing
eligibility filters. An ineligible member refuses the whole combination.

Each member keeps its own reviewed instructions, stop rules, context-reduced
dose and bank metadata. The prescription's aggregate loading flag is true if
any member loads the injury. Its gap is the maximum member gap; that gap is
frozen on every accepted member. Previous work on any member spaces the block.

Each member becomes an ordinary rehab block with a drill-specific stable id.
An optional shared `rehab_allocation_id` counts these blocks as one allocation.
Single-drill policies retain their output shape, ids, priority selection and
content hashes. The scheduler, allocation ceilings and progression rules remain
in place. The database trigger also counts raw rehab blocks, so one function-only
migration is required to group bundle allocations there as well. No tables or
columns are added; existing locks, episode and cadence checks are preserved.

Completion already supports multiple occurrences: distinct exposure ids, one
injury prompt and a shared response-group id. Self-paced work remains
unquantified. Changed/stopped work retains the existing conservative partial
amount-unknown semantics; there is no drill-level partial-dose capture. Positive
response copies must not be counted as independent assessments.

## Shipped policy audit

No production policy bundle is enabled by this change.

- Chest strain CALM has one recovery-support prescription; RESTORE has one
  comfortable-movement prescription. A bundle is not supported by current data.
- Ankle sprain CALM has one gentle-movement prescription.
- Ankle sprain RESTORE has supported balance (daily, one-day gap) and heel
  lowering (two-day gap), with different functions. This is the only existing
  candidate for a compact two-drill combination. Individual instruction reviews
  do not explicitly establish combined workload or compatibility. Enabling a
  combination requires reviewing that combination and updating the policy
  version/hash; this change does not invent that approval.
- LOAD, DYNAMIC and RETURN remain disabled. There is no reviewed live coverage
  supporting three- or four-drill later-stage blocks.

The camp-generation adapter still emits one primary reviewed line per episode.
This work changes live reconciliation, not camp generation or scheduler design.
Delayed feedback remains exposure-addressed; multiple exposures can produce
multiple next-day prompts. That existing UX is deliberately unchanged. Bundle
loading checks every exposure in the latest response group, so answering one
member cannot release siblings whose delayed response is still unknown.
