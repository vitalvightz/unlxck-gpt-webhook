# Conservative Rules Assessment

This document catalogues the planner's conservative training-load rules, classifies
each as **deliberate (safety, keep)** or **tunable (opt-in performance bias)**, and
points to the code and tests that enforce it.

It exists because a review flagged the planner as "too conservative" for a realistic
low-risk athlete (D-21, 3.5% cut, low fatigue, mild stable quad pain, primary goal
Power, weak area Mobility). Investigation showed that most of the stacked
conservatism is **deliberate, evidence-based, and test-protected** — not accidental.
Those safety rules (weight-cut + head-impact suppression, injury gating) are left
unchanged.

One genuine bug *was* found and fixed: a conflicting active-role cap (the bridge
baseline said 3, the binding late-fight role budget said 2). It is now unified into a
single source of truth (`_bridge_active_role_cap`) with a low-risk profile gate
(`fightcamp/performance_bias.py`), applied as the **default** for clean / mildly-
managed athletes.

## Summary

| # | Rule | Verdict | Where |
|---|------|---------|-------|
| 1 | D-14..D-21 routed into the bridge "taper-on-ramp" cap set | Deliberate | `stage2_payload_late_fight.py:_bridge_baseline`, `compute_bridge_rules` |
| 2 | Moderate cut + contact sport zeros hard sparring & glycolytic in bridge | Deliberate (safety) | `stage2_payload_late_fight.py:915-932` |
| 3 | D-17..D-0 converts all declared hard sparring to technical/rhythm | Deliberate (safety) | `sparring_dose_planner.py:_countdown_sparring_override` |
| 4 | Generic readiness compression counts *any* injury (incl. mild) | Deliberate | `stage2_role_map.py:_active_injury_is_moderate_plus`, `stage2_payload.py:_active_injury_affects_generic_compression` |
| 5 | Boxing crowded-week compression is severity-aware (mild excluded) | Deliberate (already nuanced) | `stage2_payload.py:_active_injury_is_moderate_plus` (line ~1946) |
| 6 | `mobility/stiffness` weakness → `tissue_state` limiter | Deliberate | `stage2_payload.py` / `stage2_planning_brief.py:_primary_limiter_key` |
| 7 | **Conflicting** D-14..D-21 active-role cap (baseline 3 vs budget 2) | **Fixed (unified)** | `stage2_payload_late_fight.py:_bridge_active_role_cap` |

## Unified active-role cap (implemented)

There were two sources of truth for the D-14..D-21 active-role cap:

- `compute_bridge_rules` baseline / `_bridge_target_active_roles` → **3**
  (render guidance), and
- `_late_fight_role_budget` → `_late_fight_max_active_roles` → **2**
  (the *binding* cap that actually limits role selection at allocation time).

The binding 2 silently overrode the bridge baseline of 3, shrinking plans for clean /
mildly-managed athletes even when fatigue was low and any injury was mild/stable.

**Fix:** one source of truth — `_bridge_active_role_cap(days, athlete_model)` — used by
the binding `_late_fight_role_budget`, with `compute_bridge_rules` guidance aligned to
match. In the D-21..D-18 window a **low-risk** athlete keeps **one extra low-risk
active role** (3 instead of 2); any safety signal drops back to 2. Applied as the
**default** (no opt-in flag).

Low-risk profile (`fightcamp/performance_bias.py:bridge_low_risk_profile`) requires
**all** of:

- fatigue low/none
- weight-cut bucket none/low/moderate (never high+)
- injury mode not `medical_hold` / `restricted_rehab_only` / `needs_review`
- no `red_flag_injury` / `severe_injury` readiness flag
- injury assessment: severity at most mild, no instability, no worsening, no daily
  symptoms, not high-risk (reuses `sparring_dose_planner._injury_assessment`)
- fight not D-7 or closer

The extra exposure is filled by low-risk work (alactic power / low-volume strength
touch / low-noise aerobic) **because the hard sparring and glycolytic caps are never
touched** by this rule — they stay exactly where the weight-cut / head-impact safety
rules left them.

Tests: `tests/test_performance_bias.py` — low-risk gate, binding-cap source of truth,
`compute_bridge_rules` guidance agreement, and an end-to-end allocation test proving
clean/mild athletes get the 3rd app-owned session while moderate-fatigue / moderate-
injury stay at 2. Existing safety tests in `tests/test_bridge_rules.py` and
`tests/test_late_fight_calendar_regression.py` remain unchanged and passing.

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

### 7. Conflicting D-14..D-21 active-role cap — Fixed (unified)

Two sources of truth disagreed (3 vs 2); the binding budget of 2 won and shrank
clean/mildly-managed plans. Now unified into `_bridge_active_role_cap` with a low-risk
gate, default 3-for-low-risk / 2-otherwise in D-21..D-18. See "Unified active-role
cap" above.

- Code: `stage2_payload_late_fight.py:_bridge_active_role_cap`,
  `_late_fight_role_budget`, `_bridge_target_active_roles`.
- **Verdict:** genuine conflict, resolved; conservative for every safety signal.

---

## Additional causes reviewed (from the second review pass)

| Cause | Verdict | Notes |
|-------|---------|-------|
| 1. `active_weight_cut` / `_is_high_pressure_weight_cut` fires within 28 days | **Fixed (softened)** | The `<=28`-day arm now `<=14` for the low-fatigue path, so a routine ~3.5% cut at D-21 with low fatigue is no longer "high-pressure". Aggressive cuts (≥5%) and moderate+ fatigue stay high-pressure at any distance. See "High-pressure cut sensitivity" below. |
| 2. Bridge cap conflict (3 vs 2) | **Fixed** | Unified active-role cap. |
| 3. Late-fight bans "development" wording | Deliberate, keep | Render-guidance flags (`allow_development_language=False`, etc.) keep the language honest about a taper-on-ramp. Cosmetic, not a load cap. `stage2_payload_late_fight.py` payload-mode dicts. |
| 4. Downgraded hard sparring still "crowds" the week | **Handled + freed-slot reallocation** | `_late_fight_active_role_count` already excludes coach-owned `hard_sparring_day` from the app budget. New: once sparring converts to technical from D-17, the freed slot is reallocated to one taper-appropriate alactic touch for low-risk athletes. See "D-17 freed-slot reallocation" below. |
| 5. Taper allocation is recovery-heavy (e.g. 1 strength / 1 cond / 3 recovery) | **Fixed (rebalanced)** | freq-5 TAPER `{1,1,3}`→`{1,2,2}`, freq-6 `{1,1,4}`→`{1,2,3}` in `training_context.allocate_sessions`. One recovery slot becomes conditioning (taper conditioning already carries TAPER-suitable tags). |
| 6. Finalizer cannot restore suppressed roles | Deliberate (safety), keep | Correct by design — the finalizer must not silently re-inflate what upstream safety logic suppressed. The right lever is the upstream cap, not the finalizer. |

---

## Third review pass — implemented

### D-17 freed-slot reallocation (cause #4 extension)

From D-17 the bridge converts all declared hard sparring to technical/rhythm, freeing
a coach-owned slot that the app budget excludes. For a **low-risk** athlete who
declared hard sparring, `_bridge_active_role_cap` now keeps the active-role cap at 3
through D-17..D-14, and `_late_fight_candidate_roles` adds **one `alactic_sharpness_day`**
(alactic = low metabolic fatigue, freshness-preserving) so the week is not under-dosed
once sparring drops out. Non-glycolytic, so it respects the bridge glycolytic
suppression. Athletes who never declared sparring (no freed slot) or who carry any
safety signal stay at the conservative 2.

- Code: `stage2_payload_late_fight.py:_bridge_active_role_cap`,
  `_late_fight_candidate_roles` (bridge block), bridge `allowed_role_keys`.
- Tests: `tests/test_performance_bias.py` (D-17..D-14 with/without declared sparring,
  end-to-end app-owned count).

### High-pressure cut sensitivity (cause #1)

`_is_high_pressure_weight_cut` (three lockstep copies: `athlete_model.py`,
`recovery.py`, `nutrition.py`) changed the low-fatigue days arm from `<=28` to `<=14`.
Aggressive cuts and moderate+ fatigue are unchanged. This stops a routine cut at
D-21 from over-triggering "protect freshness / remove optional fatigue / reduce
density / accessory volume" language.

- Tests: `tests/test_nutrition_recovery_weight_cut.py`,
  `tests/test_athlete_model_canonical.py::test_high_pressure_weight_cut_low_fatigue_boundary`.

### Taper reallocation (cause #5)

`allocate_sessions` freq-5/6 TAPER rows shift one recovery slot to conditioning
(totals unchanged). The late-camp selector audit golden (`tests/golden_snapshots/
late_camp_selector_audit/`) was regenerated to reflect the extra taper conditioning
session; `control_d28` stays stable. Note: the extra alactic taper conditioning
surfaces an `ambiguous_tag_gaps` entry for "Low Box Jump (Fast Reset)" in the audit —
a bank-tagging data-quality gap (not a safety issue) worth an explicit late-safe-intent
tag as a future follow-up.

- Tests: `tests/test_training_context.py::TestTaperAllocationReallocatedTowardConditioning`.
