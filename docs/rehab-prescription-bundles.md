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

The bundle engine initially shipped without activating production bundles.
Ankle sprain policy version 4 now activates one RESTORE combination:
`ankle_sprain_supported_balance`, then `ankle_sprain_heel_lowering`.

- Chest strain CALM has one recovery-support prescription; RESTORE has one
  comfortable-movement prescription. A bundle is not supported by current data.
- Ankle sprain CALM has one gentle-movement prescription.
- Ankle sprain RESTORE combines only the two existing reviewed prescriptions:
  supported balance (control) and heel lowering (gentle calf strengthening).
  [Whittington's ankle-sprain leaflet](https://www.whittington.nhs.uk/mini-apps/leaflet/Default.asp?id=53&print=1)
  recommends a programme of flexibility, strength and balance exercises, starting
  with small comfortable amounts, and describes basic balance with stable support.
  [East Cheshire's ankle-sprain guidance](https://services.eastcheshire.nhs.uk/physiotherapy-service/self-help/ankle-and-foot-pain-physiotherapy-self-help)
  includes gentle eccentric heel drops alongside stability and strengthening work,
  with up to two sets per session on alternate days. Compatibility of this exact
  pair is an inference from those programmes, not a source-defined fixed-dose
  protocol or clinician sign-off. Both existing comfort prerequisites must apply:
  comfortable standing/weight bearing and comfortable gentle calf movement.
  Each drill retains its reviewed instructions, stop rules and self-paced dose;
  no repetitions, balance duration or additional sets are prescribed. The block
  takes the strictest member gap (two days), including after prior work on either
  member. Balance is not separately added on recovery days. Readiness holds,
  unknown delayed responses, demanding same-region training and allocation limits
  continue to gate the whole combination.
- Ankle CALM remains gentle seated movement alone. Foam-pad balance, banded
  circles and the other ankle bank entries have no reviewed live prescription
  for this policy; bank presence does not establish eligibility. No third drill
  is justified in the reviewed RESTORE stage.
- Chest policy version 3 and its content hash remain unchanged. Its attached
  [NHS sprains-and-strains guidance](https://www.nhs.uk/conditions/sprains-and-strains/)
  supports protection followed by comfortable movement, but supplies no reviewed
  resisted chest routine or combination. Wall pushes and band flies remain
  unreviewed and excluded. CALM and RESTORE are distinct stages, so their single
  interventions are not combined into a cross-stage bundle.
- LOAD, DYNAMIC and RETURN remain disabled. There is no reviewed live coverage
  supporting three- or four-drill later-stage blocks.

- Hamstring strain policy version 1 has no bundle: CALM is one bent-knee
  movement routine and RESTORE is one standing wall isometric. The candidate
  companion bridge is `bilateral_only`, and its completion cannot be attributed
  to a one-sided episode. See [rehab-policy-hamstring-strain.md](rehab-policy-hamstring-strain.md).

The scheduler is unchanged; the bank changes only the two reviewed hamstring drills' metadata. The pilot seed script reproduces this
policy content and hash. No additional database migration is required beyond
the bundle-allocation support already shipped with the engine. Clinician
clearance remains an execution ceiling and cannot advance a rehab stage.

The camp-generation adapter still emits one primary reviewed line per episode.
This work changes live reconciliation, not camp generation or scheduler design.
Delayed feedback remains exposure-addressed; multiple exposures can produce
multiple next-day prompts. That existing UX is deliberately unchanged. Bundle
loading checks every exposure in the latest response group, so answering one
member cannot release siblings whose delayed response is still unknown.
