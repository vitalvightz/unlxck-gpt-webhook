# Conservative Rules Assessment

This document catalogues the planner's conservative training-load rules, classifies
each as **deliberate (safety, keep)** or **tunable (opt-in performance bias)**, and
points to the code and tests that enforce it.

It exists because a review flagged the planner as "too conservative" for a realistic
low-risk athlete (D-21, 3.5% cut, low fatigue, mild stable quad pain, primary goal
Power, weak area Mobility). Investigation showed that most of the stacked
conservatism is **deliberate, evidence-based, and test-protected** — not accidental.
Rather than weaken those safety rules, we added an **opt-in performance-bias layer**
(`fightcamp/performance_bias.py`) that only changes eligible low-risk cases.

## Summary

| # | Rule | Verdict | Where |
|---|------|---------|-------|
| 1 | D-14..D-21 routed into the bridge "taper-on-ramp" cap set | Deliberate | `stage2_payload_late_fight.py:_bridge_baseline`, `compute_bridge_rules` |
| 2 | Moderate cut + contact sport zeros hard sparring & glycolytic in bridge | Deliberate (safety) | `stage2_payload_late_fight.py:915-932` |
| 3 | D-17..D-0 converts all declared hard sparring to technical/rhythm | Deliberate (safety) | `sparring_dose_planner.py:_countdown_sparring_override` |
| 4 | Generic readiness compression counts *any* injury (incl. mild) | Deliberate | `stage2_role_map.py:_active_injury_is_moderate_plus`, `stage2_payload.py:_active_injury_affects_generic_compression` |
| 5 | Boxing crowded-week compression is severity-aware (mild excluded) | Deliberate (already nuanced) | `stage2_payload.py:_active_injury_is_moderate_plus` (line ~1946) |
| 6 | `mobility/stiffness` weakness → `tissue_state` limiter | Deliberate | `stage2_payload.py` / `stage2_planning_brief.py:_primary_limiter_key` |
| 7 | Bridge active-role target drops to 2 under any non-clean signal | **Tunable** | `stage2_payload_late_fight.py:_bridge_target_active_roles` |

## Tunable knob (implemented)

**`fightcamp/performance_bias.py`** — opt-in via the `performance_bias` flag on the
athlete model (default **off**). When opted in *and* the low-risk eligibility gate
passes, the bridge window (D-21..D-18) preserves **one extra low-risk performance
exposure** (alactic power, low-volume strength touch, or low-noise aerobic). It does
**not** restore hard sparring or hard glycolytic work, and it is a no-op for any
unsafe profile.

Eligibility requires **all** of:

- fatigue low/none
- weight-cut bucket none/low/moderate (never high+)
- injury mode not `medical_hold` / `restricted_rehab_only` / `needs_review`
- no `red_flag_injury` / `severe_injury` readiness flag
- injury assessment: severity at most mild, no instability, no worsening, no daily
  symptoms, not high-risk (reuses `sparring_dose_planner._injury_assessment`)
- fight not D-7 or closer

The knob only touches `_bridge_target_active_roles` headroom
(`_bridge_apply_performance_bias`), bumping `max_active_roles` and
`max_meaningful_stress_exposures` by **one each**, bounded by the bridge baseline.
Internal guards in `compute_bridge_rules` re-check every safety precondition, so the
bias can never raise caps for an unsafe combination even if a caller passes
`performance_bias=True` incorrectly.

Tests: `tests/test_performance_bias.py` (eligibility gate, defaults unchanged,
active-only-for-eligible, never overrides safety). Existing safety tests in
`tests/test_bridge_rules.py` remain unchanged and passing.

---

## Detailed findings

### 1. Bridge "taper-on-ramp" cap set (D-14..D-21) — Deliberate

`timing_state()` classifies 14–21 days as `TIMING_STATE_BRIDGE` and
`_bridge_baseline()` applies the tighter cap set (max 3 active roles, 3 meaningful
stress exposures, 1 strength touch, freshness mandatory). This is an intentional
evidence-based "on-ramp into taper," not normal-camp logic.

- Code: `stage2_payload_late_fight.py:_bridge_baseline` (lines ~691-721),
  `compute_bridge_rules`.
- Tests: `tests/test_bridge_rules.py::TestTimingStates`,
  `TestBaselineNormalCamp`, `TestBridgeCapTransitions`.
- **Verdict:** keep. Tunable headroom is delivered narrowly via the opt-in knob (#7).

### 2. Moderate cut + contact sport zeros hard sparring & glycolytic — Deliberate (safety)

In the bridge window, a moderate cut on a contact/combat sport sets
`hard_sparring_cap = 0` and `glycolytic_touch_max = 0` (full plan still allowed —
technical / rhythm / strength-touch remain). The code comment cites the evidence
review (head-impact + dehydration risk).

- Code: `stage2_payload_late_fight.py:915-932`, reason code
  `weight_cut_moderate_bridge_contact_sport_zero_hard_spar`.
- Tests: `tests/test_bridge_rules.py::TestBridgeModerateCutContactSports`,
  `test_bridge_d20_boxer_with_moderate_cut`.
- **Verdict:** keep. The performance bias explicitly does **not** touch
  `hard_sparring_cap` or `glycolytic_touch_max`.

### 3. D-17..D-0 converts all hard sparring to technical/rhythm — Deliberate (safety)

- Code: `sparring_dose_planner.py:_countdown_sparring_override` (returns
  `convert_all` for 0..17), `stage2_payload_late_fight.py:_declared_hard_spar_cap`.
- Tests: `tests/test_bridge_rules.py::TestBridgeCapTransitions`,
  `TestHardSparStatusForCountdownOffset`.
- **Verdict:** keep. The knob is range-gated to D-21..D-18 and never applies here.

### 4. Generic readiness compression counts any injury — Deliberate

`_compute_readiness_compression` adds a compression point for any active injury via
`_active_injury_is_moderate_plus` (role map) / `_active_injury_affects_generic_compression`
(payload). Despite the role-map helper's name, this path **intentionally** counts
mild injury.

- Code: `stage2_role_map.py:1819`, `stage2_payload.py:1938`.
- Test that pins this on purpose:
  `tests/test_stage2_planning_brief.py::test_compute_readiness_compression_still_counts_mild_injury_in_generic_path`
  (asserts `== 1` for "mild shoulder irritation").
- **Verdict:** keep (test-protected). Note this path governs **normal camps
  (>21 days)**, which is outside the opt-in knob's D-21..D-18 scope, so it was left
  untouched per the agreed scope.

### 5. Boxing crowded-week compression is severity-aware — Deliberate (already nuanced)

The boxing crowded-week trigger uses a *separate*, severity-aware
`_active_injury_is_moderate_plus` (`stage2_payload.py` ~line 1946) that **excludes**
mild injury — contradicting the review's claim that "any injury is treated like
moderate+".

- Test: `tests/test_stage2_planning_brief.py::test_boxing_crowded_week_does_not_treat_mild_injury_as_moderate_plus_signal`.
- **Verdict:** already correct; no change.

### 6. `mobility/stiffness` weakness → `tissue_state` limiter — Deliberate

`_primary_limiter_key` returns `tissue_state` when the weakness set contains
mobility/stiffness/knee/shoulder/neck, before the goal fallback.

- Code: `stage2_payload.py:527`, `stage2_planning_brief.py:661`.
- Tests: `tests/test_stage2_planning_brief.py::test_build_planning_brief_uses_tissue_state_for_stiffness_or_injury_driven_cases`
  (stiffness → `tissue_state`) **and**
  `test_strength_slots_share_session_metadata_and_injury_pressure_does_not_force_tissue_state`
  (mild injury + performance goal does **not** force `tissue_state`).
- **Verdict:** keep. The "Power buried under Mobility" concern is partially already
  handled (performance-goal guard). Changing limiter precedence further would break
  the stiffness test and was therefore left out of the agreed opt-in scope. Flagged
  here as a candidate for a future, separately-gated limiter knob if desired.

### 7. Bridge active-role target drops to 2 — Tunable (this change)

`_bridge_target_active_roles` returns 3 only for a *clean* athlete
(`fatigue in {none,low}` and `cut in {none,low}`); any moderate cut (or other
non-clean signal) drops it to 2 — removing one low-risk exposure even when fatigue is
low and the injury is mild/stable. This is the single lever the opt-in performance
bias relaxes, by exactly one exposure, for eligible low-risk athletes in D-21..D-18.

- Code: `stage2_payload_late_fight.py:_bridge_target_active_roles`,
  `_bridge_apply_performance_bias`.
- **Verdict:** tunable; relaxed only behind the opt-in eligibility gate.
