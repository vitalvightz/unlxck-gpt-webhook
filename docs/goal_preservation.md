# Universal goal preservation

`fightcamp/goal_preservation.py` owns the deterministic contract for dated camps,
including normal, short, ultra-short and fight-day plans. `PriorityProfile` owns
which goals were selected and their primary/secondary hierarchy. Weak areas do
not become extra selected goals.

The initial obligations live in `compressed_priorities.goal_preservation`.
The existing short-camp `primary_targets`, `maintenance_targets`,
`embedded_support` and `deferred` buckets still describe **session framing**.
For example, deferring standalone skill work does not mean technical practice
embedded in a scheduled session disappeared. Both payload entry points now use
one short-camp classifier. No second goal-selection or scoring system is added.

The planning brief adds:

```json
{
  "goal_preservation_version": "goal_preservation.v1",
  "goal_preservation": [{
    "goal": "strength",
    "priority": "secondary",
    "initial_state": "maintain",
    "state": "maintain",
    "reason_codes": ["secondary_goal"],
    "required_intent": "meaningful_strength",
    "evidence": [{
      "week_index": 1,
      "phase": "SPP",
      "session_index": 1,
      "role_key": "strength_touch_day",
      "d_day": 16,
      "slot_id": "spp_strength_1_deadlift",
      "name": "Deadlift",
      "intents": ["meaningful_strength"],
      "quality_class": "anchor_loaded",
      "effective_prescription": "3 x 3 @ RPE 6-7 max",
      "dose_authority": "scheduled_countdown_overlay",
      "sets": 3,
      "reps": 3,
      "minimum_rpe": 6,
      "development_capable": true,
      "development_quality": true
    }],
    "coverage_requirements": [{"min_d_day": 8, "max_d_day": 20}],
    "missing_coverage": [],
    "constraints": [],
    "repair_attempts": [],
    "satisfied": true
  }]
}
```

The final list also replaces the initial list inside `compressed_priorities`.
Those fields are projections of the same decision, not independent inputs.

## Authority and evidence

Reconciliation runs after calendar allocation, compression, fillers, finished
late-fight tails, scheduled-day morphing and effective strength resolution.
Direct countdown plans use their final visible session sequence, never their
earlier weekly mirror. Normal camps require evidence on a day present in the
resolved calendar. Strength slots keep an explicit `strength_session_index`,
so removing an earlier strength role cannot reassign its candidate group to a
different role accidentally.

Primary goals default to `build`; secondary goals default to `maintain`.
Fight proximity (D-13 inward), high fatigue and aggressive cut pressure reduce
development expectations. Safety constraints remain authoritative.

The v1 coverage minimums are conservative planner gates, not promises of an
individual physiological response:

- Build: a development-quality exposure in each seven-day window through D-14.
- Maintain: a qualifying exposure in each fourteen-day window through D-8 for
  strength and D-2 for other physical goals. Shorter windows still need evidence.
- Recovery and weight-cut support use their deterministic daily support plans.
- Strength requires at least two working sets, positive reps/hold duration,
  meaningful working intensity (RPE 6+ or 60%+ loading), and a loaded anchor
  class. Force isometrics additionally need `real_strength_maintenance=true`.
- Effective no-loading flags, insufficient effective sets, support/rehab classes,
  and pure power classes cannot pay for meaningful strength.
- Speed and conditioning use actual structured work/rest/duration metadata and
  the existing conditioning semantic helper. Recovery and rhythm morphs cannot
  pay for conditioning. Explicit conditioning-maintenance inserts can maintain,
  but do not claim development.
- Candidate eligibility, declared exercise locks, restrictions and late-window
  eligibility remain authoritative. Exercise names and final prose never decide
  which goal a stimulus serves.

One witness per required coverage window is selected deterministically. Multiple
exercises on one day cannot cover different chronological windows. A single
early-camp exposure cannot justify a multi-week development claim.

## Repair and deferral

The role map retains `goal_repair_candidates` from its own phase/safety-approved
selection, before calendar/compression losses. Repair can restore a qualifying
candidate in its original week, inside both its original category budget and
the athlete's session cap. The existing canonical calendar policy checks every
destination, including contact adjacency across week boundaries. The existing
morph/prescription owners run again on the trial schedule. A repair is accepted
only if it improves goal coverage without removing another effective stimulus.

Hard-suppressed candidates, intentionally compressed weeks, protected recovery
days and finished D-13 tails are not reopened. In particular,
`two_hard_spar_days`, immediate post-contact restrictions and
`between_hard_contacts_tight_gap_meaningful_stress` are unchanged.

An unresolved goal can become `defer` only with a live constraint for **every**
uncovered window. The structured constraint cites its authority, original reason
code, affected week and role where applicable. Supported causes include existing
calendar/compression decisions, fight proximity, and effective dose reductions
caused by readiness. A missing candidate, an unexplained empty schedule or an
arbitrary injury flag alone is not a deferral reason: that remains a blocking
build/maintain obligation.

## Finalization and publication

The finalizer packet carries the final contract. Required named witnesses are
render decisions; general LLM freedom to reselect candidates cannot replace
them. Explicit deferrals must be explained in athlete-facing Lead notes.

Stage 2 independently recomputes evidence and deferral reasons. It rejects
missing goals, duplicate states, stale evidence, unsupported downgrades and
unjustified deferrals with `goal_preservation_failed`. The legacy
`intent_validation` and its summary are corrected after prescription resolution.

Render validation checks the scheduled identity and dose of named witnesses with
the existing exercise/dose parsers. This is fidelity checking against a
deterministic decision, not semantic inference from LLM prose. Missing or reduced
witnesses produce `goal_preservation_render_mismatch`.

Both codes retain diagnostic severity but cannot veto release. Automation records
pre-render and rendered-witness findings in the existing validator report and
releases usable Stage 2 content as `publishable_with_flags`. No automatic model
repair or planner regeneration is triggered solely by these findings.
`Stage2GoalPreservationError` is historical compatibility only. Runtime/provider
failures without usable output and persistence failures remain terminal.

## Compatibility and scope

- Additive planning-brief and finalizer-packet fields; existing schema versions
  and short-camp bucket shapes remain compatible.
- `plans.planning_brief` already stores JSON text (migration
  `20260427120000_stabilize_generation_runtime.sql`). No SQL, RLS, environment,
  exercise-bank or UI change is required.
- Old saved plans remain readable. Re-finalizing/publishing an old dated brief
  with selected goals and no contract retains the diagnostic finding.
- Open ongoing systems retain the initial universal selection classification.
  They do not currently have a deterministic executable session calendar; this
  PR's resolved-camp publication gate applies to dated camps. Adding an executable
  contract to that separate planner is outside the normal/short-camp gap here.
- Incomplete goal coverage stays observable without discarding usable plans.

## Verification

`tests/test_goal_preservation.py` covers classification, semantic evidence,
restoration, safety, stale contracts, explicit deferral, chronological coverage,
determinism, and renderer fidelity. The synthetic MMA fixture in
`tests/fixtures/goal_preservation/sheyi_like.json` runs through real intake,
selection, calendar, prescriptions and handoff in
`tests/test_goal_preservation_e2e.py`. `tests/test_stage2_automation.py` verifies
flagged publication, original findings, and absence of validator-driven retries.
