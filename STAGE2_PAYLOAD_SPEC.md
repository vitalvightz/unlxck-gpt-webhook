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
- `pdf_url`
- `stage2_payload`
- `planning_brief`
- `stage2_handoff_text`

Suggested top-level shape:

```json
{
  "pdf_url": "string",
  "why_log": {},
  "coach_notes": "string",
  "plan_text": "string",
  "stage2_payload": {},
  "planning_brief": {},
  "stage2_handoff_text": "string"
}
```

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
          "why": "high force, lower knee demand than deep squat"
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
