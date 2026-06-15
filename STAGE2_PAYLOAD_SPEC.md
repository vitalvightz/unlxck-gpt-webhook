# Stage 2 Payload Spec

## Purpose

Stage 2 is a restriction-aware finalizer, not a full planner.

Its current job is:

1. Remove anything that violates restrictions.
2. Build the final athlete-facing plan only from the remaining Stage 1 items.
3. Prefer alternatives already present in Stage 1 instead of inventing new work.

Because of that, Stage 1 should produce a strong candidate set with clear intent and backup options.

## Recommended Return Contract

For the current backend flow, Stage 1 should return a complete Stage 2 handoff package:

- `plan_text`
- `why_log`
- `coach_notes`
- `pdf_url` (legacy compatibility field; always `null` for new plans)
- `stage2_payload`
- `planning_brief`
- `stage2_handoff_text`

Suggested top-level shape:

```json
{
  "pdf_url": null,
  "why_log": {},
  "coach_notes": "string",
  "plan_text": "string",
  "stage2_payload": {},
  "planning_brief": {},
  "stage2_handoff_text": "string"
}
```

## Structured plan (schema-first, additive)

Beside the raw `plan_text`, Stage 2 can also emit a machine-readable
`StructuredTrainingPlan` (see `api/structured_plan_models.py`). This runs *next
to* the legacy flow and never replaces it:

- It is gated by `UNLXCK_STAGE2_STRUCTURED_PLAN` (off by default — structured
  generation is a second model call). When off, nothing changes.
- On a passing plan, the finalizer asks the model to convert the markdown plan
  into a `StructuredTrainingPlan` JSON object (`build_structured_plan_prompt`),
  then validates it (`validate → one repair retry → raw-markdown fallback`, via
  `api/structured_plan_generation.py`).
- A valid (or repaired) plan is saved to `plans.structured_plan` with its
  `plans.schema_version`. An invalid result is dropped, `plan_text` stays the
  fallback, and generation is never blocked.

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

## `stage2_payload` Shape

```json
{
  "schema_version": "stage2_payload.v1",
  "generator_mode": "restriction_aware_candidate_generator",
  "athlete_model": {},
  "restrictions": [],
  "phase_briefs": {},
  "candidate_pools": {},
  "omission_ledger": {},
  "rewrite_guidance": {}
}
```

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

This is the core field. Stage 1 should emit slot-based option reservoirs.

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
          "name": "Steady-State Cardio (Run / Bike / Row)",
          "source": "universal_gpp_conditioning",
          "movement_patterns": ["cyclical", "aerobic"],
          "restriction_tags": ["swap_to_bike_if_lower_limb_irritable"]
        },
        "alternates": [
          {
            "name": "Jump Rope Endurance (Footwork Conditioning)",
            "source": "universal_gpp_conditioning",
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

## Minimum Viable Payload

If implementation needs to stay small, start with:

- `schema_version`
- `athlete_model`
- `restrictions`
- `phase_briefs`
- `candidate_pools`

That is enough to materially improve Stage 2 selection quality.

## Recommended Stage 1 Changes

### Build by slot, not only by section

For Stage 2, Stage 1 should emit slot reservoirs with alternates.

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

Every candidate should expose movement and risk tags that make hard filtering easier:

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

These inputs should influence the pool, not only the prose:

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
- `stage1_can_bypass_llm(stage1_result, require_clean=False)` — the gating
  primitive. `True` when Stage 1's draft already clears the publish gate (no
  errors, no hard blockers); with `require_clean=True` it also requires zero
  soft review flags.

`tests/test_stage1_parity.py` locks in the baseline across representative
scenarios (standard camp, long pro camp, weight cut, injury, late-fight
countdown, fight week). Two invariants:

- **Gating precondition** — Stage 1's draft produces zero validator errors and
  zero hard blocking warnings everywhere. This must never regress.
- **Bounded soft gap** — every remaining soft review-flag code stays within
  `BASELINE_REVIEW_FLAG_CODES`. The structural gap to close (the work the LLM
  currently redoes) is dominated by `missing_week_session_role`,
  `sport_language_leak`, `late_fight_unapproved_exercise_rendered`,
  `late_camp_session_incomplete`, `template_like_session_render`, and the
  `missing_{injury,weight_cut}_lead_summary` codes.

### Deterministic session labels

Stage 1 already knows every session's `role_key`. `fightcamp/role_labels.py` maps
each `role_key` to a deterministic, validator-recognised `athlete_facing_label`
(e.g. `primary_strength_day` → "Strength", `alactic_sharpness_day` →
"Alactic sharpness"), stamped onto every rendered session role in the weekly role
map. This removes title invention from the LLM (a source of `role_key` leaks) and
gives the eventual deterministic renderer ready-made titles.

## Suggested Adoption Path

### Phase 1

Emit `stage2_payload` without changing Stage 2 logic.

### Phase 2

Teach Stage 2 to read `candidate_pools` slot by slot instead of inferring structure from prose.

### Phase 3

Tighten Stage 1 selection so every high-priority slot has at least one viable alternate when possible.

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
