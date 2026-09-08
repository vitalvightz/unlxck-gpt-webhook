# Stage 2 Payload Spec

This document describes the **shapes** Stage 1 hands to Stage 2 and what Stage 2
does with them. Decision *authority* — who owns what, and who may withhold a plan
— lives in [`PLANNER_ARCHITECTURE_CONTRACT.md`](PLANNER_ARCHITECTURE_CONTRACT.md).
Where the two disagree, the contract wins.

## Purpose

Stage 2 is a restriction-aware finalizer, not a planner.

Its job is:

1. Render the already-decided calendar, session membership and effective doses.
2. Remove anything that violates a restriction.
3. Improve coaching clarity and specificity without changing training decisions.

Substitution rights depend on whether the role is **closed** or **open**:

- A role with `selected_exercise_assignments` is **closed**. That list is the
  deterministic planner's final session membership. Stage 2 renders every member
  once at its `effective_prescription`. An illegal member is dropped or held and
  the gap is left; it is never replaced, and never collapsed into one "primary"
  plus fallbacks.
- A role without `selected_exercise_assignments` is **open** and keeps the older
  contract: prefer the selected item, then same-slot alternates, and leave the
  slot thin rather than inventing new work.

Stage 1 still produces a strong candidate set with alternates, because composition
draws closed membership from that pool — but the pool itself is planning evidence,
not the plan.

## Stage 1 Return Contract

Stage 1 returns a complete Stage 2 handoff package:

- `plan_text` — the deterministic Stage 1 draft
- `why_log`
- `coach_notes`
- `pdf_url` (legacy compatibility field; always `null` for new plans)
- `stage2_payload`
- `planning_brief`
- `stage2_handoff_text` — the assembled Stage 2 prompt
- `parsing_metadata`

Top-level shape:

```json
{
  "pdf_url": null,
  "why_log": {},
  "coach_notes": "string",
  "plan_text": "string",
  "stage2_payload": {},
  "planning_brief": {},
  "stage2_handoff_text": "string",
  "parsing_metadata": {}
}
```

`stage2_pipeline.build_stage2_package` requires `planning_brief`, `stage2_payload`
and `stage2_handoff_text` and raises if any is missing.

### What the model actually reads

`stage2_payload` is **not** sent to the model as-is. `build_stage2_handoff_text`
assembles the prompt from:

1. `STAGE2_FINALIZER_PROMPT` + `UNLXCK_FINAL_RENDER_CONTRACT`,
2. payload-mode instructions for the resolved `payload_mode`,
3. the LOCKED SESSION RENDER MANIFEST (closed membership, when present),
4. the FINALIZER PACKET — `stage2_finalizer_packet` built from the
   `stage2_llm_boundary`-sanitised `planning_brief` plus `stage2_payload`,
5. the athlete profile, optional injury context and coach notes,
6. the Stage 1 draft `plan_text`, as candidate material only.

The FINALIZER PACKET, not the raw candidate pools, is the model's primary
authority. The validator likewise grades the final text against the
`planning_brief`, not against `stage2_payload`.

## Structured plan (schema-first, additive)

Beside the raw `plan_text`, Stage 2 can also emit a machine-readable
`StructuredTrainingPlan` (see `api/structured_plan_models.py`). This runs *next
to* the legacy flow and never replaces it:

- It is gated by `UNLXCK_STAGE2_STRUCTURED_PLAN` (**on by default**). Set it to a
  falsey value (`0`/`false`/`no`/`off`/empty) to disable it; the outcome is then
  recorded as `not_attempted` and the raw `plan_text` flow is the fallback.
- Conversion is triggered by `should_attempt_structured_plan`, which is driven by
  the canonical state machine, not by a Stage 2 status string. It requires all of:
  the env flag on, no `structured_plan` stored yet (idempotent), an approved
  `plan_text` to convert, and an athlete-displayable plan status — `ready` **or**
  `publishable_with_flags`. Held, blocked, medical-gated, review-required and
  archived plans are excluded, so nothing is published merely to derive a card.
- The finalizer asks the model to convert the markdown plan into a
  `StructuredTrainingPlan` JSON object (`build_structured_plan_prompt`), then
  validates it (`validate → one repair retry → raw-markdown fallback`, via
  `api/structured_plan_generation.py`).
- A valid (or repaired) plan is saved to `plans.structured_plan` with its
  `plans.schema_version`. An invalid result is dropped, `plan_text` stays the
  fallback, and generation is never blocked.

Model-call budget: the plan-text pass is one call plus **at most one** repair
call; the card conversion adds one call plus at most one repair call. So Stage 2
makes between one and four model calls, and the `max_model_calls=2` in the
`[stage2] package ready` log line counts the plan-text pass only.

Structured-card call behaviour is controlled by three further flags:

| Env var | Default | Effect |
|---|---|---|
| `UNLXCK_STAGE2_STRUCTURED_REPAIR` | on | One repair retry after a failed first structured pass. The main lever on worst-case card latency. |
| `UNLXCK_STAGE2_STRUCTURED_JSON_MODE` | on | Request `json_object` output mode, removing the "not valid JSON" failure class. |
| `UNLXCK_STAGE2_STRUCTURED_SCHEMA_MODE` | **off** (opt-in) | Send the strict `json_schema` built from `StructuredTrainingPlan` instead. Validated in-repo for structural compliance only; confirm against the live endpoint in staging before enabling, then the repair retry can be dropped. |

These apply only to the structured-card calls. The markdown plan-text pass never
uses an output-format parameter.

Result fields added to the Stage 2 return contract (all optional):

- `structured_plan` — validated plan object, or `null` when absent/invalid.
- `schema_version` — schema version of the saved structured plan.
- `stage2_validator_report.structured_plan` — admin debug:
  `{ "status", "errors", "schema_version" }` where `status` is one of
  `not_attempted` / `valid` / `repair_attempted_valid` / `invalid_fallback_used`.

The structured object must use machine-readable load objects (never `"85%"`
strings), self-report readiness only (no HRV/CNS/WHOOP/strain biometrics), and
weight-cut guidance expressed as supervised risk, never direct acute-cut
instructions.

## Review, repair and release

After the first pass, `review_stage2_output` validates the text against the
`planning_brief` and `apply_stage2_release_policy` attaches the release decision.
That policy is structurally incapable of holding — it only ever returns `publish`
or `publish_with_flags`. Findings alone never block a plan.

### The repair attempt (the "retry payload")

`build_stage2_retry` decides whether one repair is warranted and, if so, returns a
`repair_prompt` built by `stage2_repair.build_stage2_repair_prompt` from a
`prompt_safe_validator_report` (the findings are filtered; `generic_filler_phrase`,
`sport_language_leak` and `true_internal_system_leak` are never sent back to the
model). Its return shape:

```json
{
  "status": "PASS | WARN | FAIL",
  "validator_report": {},
  "summary": "string",
  "summary_lines": [],
  "needs_retry": true,
  "requires_planner_regeneration": false,
  "repair_prompt": "string or null"
}
```

`api/stage2_automation.finalize` calls it only when the first pass reports one of
four codes:

| Code | What happens |
|---|---|
| `missing_selected_conditioning_assignment` | Deterministic `reconcile_selected_conditioning_assignments` first; a model `render_repair` call only if that cannot fix it |
| `selected_conditioning_effective_prescription_mismatch` | Same |
| `late_camp_effective_prescription_exceeded` | Currently no repair fires — see the caveat below |
| `goal_preservation_render_mismatch` | Currently no repair fires — see the caveat below |

There is exactly one repair round. There is no loop.

> **Known gap.** `build_stage2_retry` gates the repair on
> `release_decision != "hold"`, but it re-runs `apply_stage2_release_policy` on the
> incoming report first, which always overwrites `release_decision` with `publish`
> or `publish_with_flags`. The `"hold"` branch is therefore unreachable, and the
> function early-returns `needs_retry: False` for anything that is not a
> conditioning-membership or goal-preservation finding. So the two dose codes above
> reach `build_stage2_retry` but never produce a prompt, and the
> `effective_dose_repair` attempt label in `api/stage2_automation.py` is currently
> dead. Tracked as debt item 9.3.7 in
> [`PLANNER_ARCHITECTURE_CONTRACT.md`](PLANNER_ARCHITECTURE_CONTRACT.md).

### Holds, and the release override

Four deterministic holds exist, and none is a validator opinion — each says the
deterministic plan itself is unusable. They are listed with their owners in
[`PLANNER_ARCHITECTURE_CONTRACT.md`](PLANNER_ARCHITECTURE_CONTRACT.md) §3.1:
planner preflight, structural integrity, conditioning-render, and goal-preservation
regeneration. A hold blanks `plan_text`, keeps the rendered text in
`final_plan_text`, and lands the plan in `review_required` with
`stage2_status = stage2_failed`. Inside Stage 2 that is final, and because
`should_attempt_structured_plan` requires an athlete-displayable status a held plan
gets **no structured card**.

`api/generation/persistence._release_held_plan_with_flags` then runs last and
releases it anyway: a held plan with usable content becomes
`publishable_with_flags`, with `plan_text` restored from `final_plan_text`. So the
athlete sees the plan on the raw markdown fallback, `stage2_status` stays
`stage2_failed` for admin triage, and the only genuinely withheld outcomes are
Stage 1 injury triage (a separate persistence path, not overridden) and an empty
result.

## `stage2_payload` Shape

Dated normal camp:

```json
{
  "schema_version": "stage2_payload.v1",
  "generator_mode": "restriction_aware_candidate_generator",
  "athlete_model": {},
  "injury_context": {},
  "restrictions": [],
  "phase_briefs": {},
  "candidate_pools": {},
  "omission_ledger": {},
  "rewrite_guidance": {}
}
```

Two variants replace `generator_mode` and add a `payload_variant` plus their own
fields:

| Path | `generator_mode` | `payload_variant` | Extra fields |
|---|---|---|---|
| Dated normal camp | `restriction_aware_candidate_generator` | *(absent)* | — |
| D-13 inward | `restriction_aware_candidate_generator_late_fight` | `late_fight_stage2_payload` | `payload_mode`, `effective_stage2_mode`, `days_out_payload`, `late_fight_plan_spec`, `late_fight_session_sequence`, `rendering_rules`, `late_fight_permissions` |
| Open / ongoing system | `restriction_aware_candidate_generator_open_ongoing` | `open_ongoing_stage2_payload` | `payload_mode`, `effective_stage2_mode`, `render_mode`, `open_plan_spec` |

All three carry `athlete_model`, `injury_context`, `restrictions`, `phase_briefs`,
`candidate_pools`, `omission_ledger` and `rewrite_guidance`.
`build_stage2_handoff_text` resolves the prompt's mode instructions from
`payload_mode` -> `effective_stage2_mode` -> `render_mode`, in that order, so the
dated normal camp falls through to `camp_payload`.

`fightcamp/main.py` then adds `input_parsing_metadata`, and
`plan_pipeline_rendering.build_stage2_outputs` adds `stage1_selection_summary`, to
whichever variant was produced.

### `planning_brief` vs `stage2_payload`

They are different objects and the field names differ. The brief is what the
finalizer packet and the validator are actually built from:

| `stage2_payload` | `planning_brief` |
|---|---|
| `schema_version: stage2_payload.v1` | `schema_version: planning_brief.v1` |
| `athlete_model` | `athlete_snapshot` |
| `rewrite_guidance` | `decision_rules` |
| `candidate_pools`, `omission_ledger`, `restrictions`, `phase_briefs` | same names, carried through |
| — | `weekly_role_map` (the resolved calendar, membership, doses and labels) |
| — | `priority_focus`, `limiter_profile`, `sport_load_profile`, `weekly_stress_map`, `week_by_week_progression`, `phase_strategy`, `fight_week_override`, `computed_support`, `goal_preservation` |

`weekly_role_map` is the part that matters for release: session count, day
ownership, `selected_exercise_assignments` and `effective_prescription` all live
there, and everything downstream treats it as authoritative.

## Field Definitions

### `athlete_model`

This should contain the inputs that materially change candidate choice.

```json
{
  "sport": "boxing",
  "status": "pro",
  "rounds_format": "5 x 3",
  "camp_length_weeks": 8,
  "days_until_fight": 56,
  "fatigue": "moderate",
  "age": 31,
  "weight_cut_risk": true,
  "weight_cut_pct": 4.2,
  "technical_styles": ["boxing"],
  "tactical_styles": ["pressure fighter"],
  "weaknesses": ["gas_tank", "neck_strength"],
  "key_goals": ["conditioning", "skill_refinement"],
  "mental_blocks": ["pressure", "rushing"],
  "equipment": ["barbell", "medicine_ball", "bands"],
  "training_days": ["Mon", "Tue", "Thu", "Sat"],
  "training_preference": "explosive med-ball and low-impact conditioning",
  "injuries": ["left knee irritation"],
  "short_notice": false,
  "readiness_flags": [
    "moderate_fatigue",
    "active_weight_cut",
    "lower_limb_caution"
  ]
}
```

### `restrictions`

Keep normalized restrictions explicit even if they are already present elsewhere.

```json
[
  {
    "restriction": "deep_knee_flexion",
    "source_phrase": "knee pain on deep squats",
    "region": "knee",
    "severity": "moderate",
    "blocked_patterns": [
      "deep bilateral squat",
      "full ROM lunge",
      "high impact landing"
    ]
  }
]
```

### `phase_briefs`

Stage 2 should preserve phase intent even when dropping items.

```json
{
  "GPP": {
    "objective": "build aerobic base and general force capacity",
    "emphasize": ["aerobic repeatability", "trunk/neck robustness"],
    "deprioritize": ["high fatigue glycolytic density"],
    "risk_flags": ["respect knee tolerance"],
    "session_counts": {
      "strength": 2,
      "conditioning": 1,
      "recovery": 1
    }
  },
  "SPP": {
    "objective": "increase fight-specific repeatability and power transfer",
    "emphasize": ["glycolytic repeatability", "rotational intent", "sport speed"],
    "deprioritize": ["excessive eccentric damage"],
    "risk_flags": ["manage cut stress"],
    "session_counts": {
      "strength": 1,
      "conditioning": 2,
      "recovery": 1
    }
  },
  "TAPER": {
    "objective": "maintain sharpness and freshness",
    "emphasize": ["alactic sharpness", "confidence", "low soreness"],
    "deprioritize": ["new drills", "high lactate exposure"],
    "risk_flags": ["protect freshness"],
    "session_counts": {
      "strength": 1,
      "conditioning": 1,
      "recovery": 2
    }
  }
}
```

### `candidate_pools`

Slot-based option reservoirs. This is the richest field, but it is **planning
evidence, not session membership**: `session_composition.py` reduces these slots
to the closed `selected_exercise_assignments` carried on each role in the
`planning_brief`'s `weekly_role_map`, and that list — not the pool — is what
Stage 2 renders for a closed role.

Each slot should expose:

- the role of the slot
- the selected primary item
- backup items already present in Stage 1
- relevant movement and risk tags
- score evidence from Stage 1 selection
- normalized selection metadata with conservative defaults for unknown fields
- a replacement hint that keeps Stage 2 inside the same role

```json
{
  "GPP": {
    "strength_slots": [
      {
        "slot_id": "gpp_primary_lower_force",
        "role": "lower_force",
        "purpose": "general force production with low novelty",
        "selected": {
          "name": "Trap Bar Deadlift from Blocks",
          "source": "exercise_bank",
          "movement_patterns": ["hinge", "bilateral", "axial_load"],
          "restriction_tags": ["hinge", "axial_load", "knee_friendly_partial_rom"],
          "prescription": "4x4-6 @ RPE 7-8",
          "why": "high force, lower knee demand than deep squat",
          "score": 8.4,
          "reason_codes": ["goal_match", "phase_match"],
          "penalties": 0,
          "restriction_hits": 0,
          "late_window_adjustment": 0,
          "score_evidence": {
            "score": 8.4,
            "reason_codes": ["goal_match", "phase_match"],
            "penalties": 0,
            "restriction_hits": 0,
            "late_window_adjustment": 0
          },
          "selection_metadata": {
            "movement_cost": "moderate",
            "impact_cost": "moderate",
            "eccentric_cost": "moderate",
            "cns_load": "moderate",
            "soreness_risk": "moderate",
            "late_windows": []
          }
        },
        "alternates": [
          {
            "name": "Heavy Sled March",
            "source": "exercise_bank",
            "movement_patterns": ["gait", "concentric", "low_impact"],
            "restriction_tags": ["low_impact", "knee_tolerant"]
          },
          {
            "name": "Split-Stance Isometric Mid-Thigh Pull",
            "source": "exercise_bank",
            "movement_patterns": ["isometric", "hinge", "unilateral_bias"],
            "restriction_tags": ["isometric", "joint_friendly"]
          }
        ],
        "replace_with_same_role": true,
        "priority": "high"
      }
    ],
    "conditioning_slots": [
      {
        "slot_id": "gpp_aerobic_base",
        "role": "aerobic_base",
        "purpose": "low-damage aerobic development",
        "selected": {
          "name": "Rowing (Steady State)",
          "source": "conditioning_bank",
          "movement_patterns": ["cyclical", "aerobic"],
          "restriction_tags": ["swap_to_bike_if_lower_limb_irritable"]
        },
        "alternates": [
          {
            "name": "Jump Rope Conditioning",
            "source": "conditioning_bank",
            "movement_patterns": ["reactive", "aerobic", "footwork"]
          }
        ],
        "replace_with_same_role": true,
        "priority": "high"
      }
    ],
    "rehab_slots": []
  }
}
```

### `omission_ledger`

This tells Stage 2 why sections may be thin.

```json
{
  "GPP": {
    "strength": [
      {
        "name": "Safety Bar Squat",
        "reason": "restriction_conflict",
        "details": "blocked by deep_knee_flexion"
      }
    ],
    "conditioning": [
      {
        "name": "Sprint Repeaters",
        "reason": "fatigue_or_cut_penalty",
        "details": "deprioritized due to moderate fatigue and active cut"
      }
    ]
  }
}
```

### `rewrite_guidance`

Simple machine-readable notes for Stage 2.

```json
{
  "selection_rules": [
    "Prefer selected item first, then alternates in listed order.",
    "If the selected item is removed, replace only with an alternate from the same slot when possible.",
    "Do not preserve volume by crossing roles unless the section would otherwise be empty.",
    "If a slot becomes empty after filtering, leave it thin rather than inventing a new item."
  ],
  "writing_rules": [
    "Keep the final plan athlete-facing and clean.",
    "Do not mention excluded items.",
    "Preserve phase objectives when rewriting text."
  ]
}
```

These `selection_rules` apply to **open** roles only. For a role carrying
`selected_exercise_assignments` they are overridden by closed-membership
precedence: no replacement, no restoration, no substitution, no collapsing to a
primary-plus-fallback. The live prompt (`STAGE2_FINALIZER_PROMPT` rules 1 and 3)
and the repair prompt (`stage2_repair.py` rule 3A) both state this explicitly, and
rule 3A is written to override every other repair rule that mentions pools,
alternates, restoration or substitution.

## Minimum Viable Payload

Historical note. When the payload was first introduced, the minimum useful set was:

- `schema_version`
- `athlete_model`
- `restrictions`
- `phase_briefs`
- `candidate_pools`

That is no longer sufficient. `build_stage2_package` requires `planning_brief`,
`stage2_payload` and `stage2_handoff_text`, and the validator grades against the
`planning_brief`'s `weekly_role_map`. A payload without a resolved role map cannot
be released.

## Stage 1 Content Conventions

### Build by slot, not only by section

Stage 1 emits slot reservoirs with alternates.

Examples:

- lower force
- upper pull
- trunk/neck
- rotational power
- aerobic base
- glycolytic repeatability
- alactic sharpness
- rehab priority 1

### Tag restriction-relevant movement patterns

Every candidate exposes movement and risk tags that make hard filtering easier:

- `hinge`
- `deep_knee_flexion`
- `overhead`
- `impact_landing`
- `change_of_direction`
- `cervical_loading`
- `axial_load`
- `high_grip_demand`
- `explosive_push`
- `long_lever_core`

### Use athlete inputs to shape candidate pools

These inputs influence the pool, not only the prose:

- `rounds_format`
- `record`
- `training_preference`
- `age`
- `weight_cut_pct`
- `fatigue`
- `days_until_fight`

## Stage 1 self-parity (making Stage 1 match live)

The Stage 2 LLM is graded by `fightcamp/stage2_validator.py` against the planning
brief. The closer Stage 1's *own* rendered draft already is to a plan that passes
that validator, the less structural work the finalizer has to do — and the closer
we get to skipping the LLM for clean cases.

`fightcamp/stage1_parity.py` makes that measurable. It runs the exact validator
the finalizer is graded by against Stage 1's own `plan_text` (using Stage 1's own
`planning_brief`):

- `review_stage1_self_output(stage1_result)` — full review result.
- `stage1_parity_breakdown(stage1_result)` — code-level counts (errors,
  blocking warnings, soft review flags).

This module is measurement-only. It deliberately does **not** expose an
LLM-bypass/gating helper: while soft review flags still fire, "publishable" (no
errors, no hard blockers) is not a confident enough signal to skip the
finalizer.

`tests/test_stage1_parity.py` locks in the baseline across representative
scenarios (standard camp, long pro camp, weight cut, injury, late-fight
countdown, fight week). Two invariants:

- **No hard blockers** — Stage 1's draft produces zero validator errors and
  zero hard blocking warnings everywhere. This must never regress.
- **Bounded soft gap** — every remaining soft review-flag code stays within
  `BASELINE_REVIEW_FLAG_CODES` in `tests/test_stage1_parity.py`. That set is the
  authoritative list; the codes in it today are:

  - structural: `missing_week_session_role`, `late_camp_session_incomplete`,
    `template_like_session_render`
  - lead-in: `missing_injury_lead_summary`, `missing_weight_cut_lead_summary`
  - wording: `generic_instruction_opener`, `sport_language_leak`,
    `conditional_conditioning_choice`
  - late-fight: `late_fight_missing_countdown_header`,
    `late_fight_active_role_overage`, `late_fight_block_overage`,
    `late_fight_meaningful_stress_overage`, `late_fight_forbidden_content`,
    `late_fight_hard_sparring_overage`, `late_fight_neural_power_stacking`

  The structural codes are the real gap — they are the week/day spine the
  finalizer still has to build. Read the baseline in the test rather than this
  list if the two ever disagree.

### Deterministic week-by-week schedule (built, not wired in)

> **Status: not in the production path.** `render_weekly_schedule_section` has no
> caller in `api/` or `fightcamp/` — only tests import it. The live Stage 1 draft
> is still the phase-level render produced by `plan_pipeline_rendering.py`
> (`## GPP` / `### Strength & Power` / `### Conditioning`), and only the
> late-fight path emits a deterministic day spine
> (`_render_late_fight_stage1_draft`, `## Countdown Sessions`). That is why
> `missing_week_session_role` and `late_camp_session_incomplete` are still in the
> parity baseline above. The rest of this subsection describes what the module
> does, so the design is not lost — it is not a description of current output.

`fightcamp/weekly_plan_render.py` renders the week->day->session spine
deterministically from data Stage 1 already owns, so the draft would read like the
final article instead of a phase-level exercise pool the finalizer must
restructure:

- each active week becomes `## Week N — PHASE (D-x → D-y)`,
- each session becomes `### <Weekday> (D-day) — <athlete_facing_label>` placed on
  the planner's chosen day (with `fill_missing_session_days` assigning any role
  the planner left dayless to a free declared training day, on the role map
  itself so the planning brief, the validator's authorised-day set, and the
  render stay consistent), and
- each session carries decisive, real work — strength doses via
  `strength._classify_prescription_type` + `_prescription_templates`,
  conditioning doses from each drill's own `duration`, coach-owned sparring as a
  minimal label + one freshness note — anchor-first, with crowded-week
  `forbidden_secondary_stressors` excluded (no hinge/contrast stacked on an
  anchor day).

It places real selected work onto real days. The only exception: when the planner
selected no drill for a required energy system, the slot renders a clearly
labelled `Default ... option` template (instead of an empty, incomplete session)
— these defaults are the one kind of rendered work that does not come from a
selected drill. The increment was scoped to dated normal camps; late-fight
countdown weeks were left on their existing path (they have their own strict
allowed-exercise contracts).

Wiring this in — or deleting it — is a behaviour change and needs its own
argument under the freeze rule in
[`PLANNER_ARCHITECTURE_CONTRACT.md`](PLANNER_ARCHITECTURE_CONTRACT.md) §12. It is
tracked as debt item 9.3.5 there.

### Deterministic session labels

Stage 1 already knows every session's `role_key`. `fightcamp/role_labels.py` maps
each `role_key` to a deterministic, validator-recognised `athlete_facing_label`
(e.g. `primary_strength_day` → "Strength", `alactic_sharpness_day` →
"Alactic sharpness"), stamped onto every rendered session role in the weekly role
map. This removes title invention from the LLM (a source of `role_key` leaks) and
gives the eventual deterministic renderer ready-made titles.

### Deterministic injury / weight-cut lead summary

The validator requires active injury or weight-cut context to be summarised
before the training detail (it scans the first plan lines for injury / weight-cut
keywords — `missing_injury_lead_summary` / `missing_weight_cut_lead_summary`).
`fightcamp/lead_summary.py` renders a short `## Readiness & Constraints` block
straight after the plan title, using the same active-injury / active-cut
detection the validator reads, so the context leads the plan at the source
instead of being lifted up by the LLM.

## Adoption Status

The original three-phase adoption path is finished, and went further than it
described:

| Phase | Original goal | Status |
|---|---|---|
| 1 | Emit `stage2_payload` without changing Stage 2 logic | Done |
| 2 | Teach Stage 2 to read `candidate_pools` slot by slot instead of inferring structure from prose | Superseded — Stage 2 now reads the finalizer packet and, for closed roles, a locked membership manifest, so it does not select from pools at all |
| 3 | Tighten Stage 1 selection so every high-priority slot has at least one viable alternate | Done for open roles; for closed roles the alternates feed `session_composition`, not Stage 2 |

The remaining known gap is the Stage 1 draft's week/day spine — see the parity
baseline and the "not wired in" note above.

## Example Minimal Payload

```json
{
  "schema_version": "stage2_payload.v1",
  "generator_mode": "restriction_aware_candidate_generator",
  "athlete_model": {
    "sport": "boxing",
    "status": "pro",
    "rounds_format": "5 x 3",
    "fatigue": "moderate",
    "weight_cut_risk": true,
    "weight_cut_pct": 4.2,
    "technical_styles": ["boxing"],
    "tactical_styles": ["pressure fighter"],
    "training_days": ["Mon", "Tue", "Thu", "Sat"],
    "training_preference": "explosive med-ball and low-impact conditioning",
    "injuries": ["left knee irritation"]
  },
  "restrictions": [
    {
      "restriction": "deep_knee_flexion",
      "source_phrase": "knee pain on deep squats",
      "region": "knee",
      "severity": "moderate",
      "blocked_patterns": ["deep bilateral squat", "full ROM lunge"]
    }
  ],
  "phase_briefs": {
    "SPP": {
      "objective": "increase fight-specific repeatability and power transfer",
      "emphasize": ["glycolytic repeatability", "rotational intent"],
      "deprioritize": ["excessive eccentric damage"],
      "risk_flags": ["manage cut stress"]
    }
  },
  "candidate_pools": {
    "SPP": {
      "strength_slots": [
        {
          "slot_id": "spp_power_slot",
          "role": "rotational_power",
          "selected": {
            "name": "Explosive Medicine Ball Scoop Toss",
            "source": "exercise_bank",
            "movement_patterns": ["rotation", "ballistic"]
          },
          "alternates": [
            {
              "name": "Band-Resisted Punch Step",
              "source": "exercise_bank",
              "movement_patterns": ["rotation", "reactive"]
            }
          ],
          "replace_with_same_role": true,
          "priority": "high"
        }
      ]
    }
  },
  "omission_ledger": {},
  "rewrite_guidance": {
    "selection_rules": [
      "Prefer selected item first, then alternates in listed order.",
      "If a slot becomes empty, leave it thin rather than inventing."
    ]
  }
}
```
