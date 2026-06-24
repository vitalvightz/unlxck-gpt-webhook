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
| 1. `active_weight_cut` / `_is_high_pressure_weight_cut` fires within 28 days | Deliberate, **tunable-future** | `weight_cut_risk=True` adds `active_weight_cut`; `_is_high_pressure_weight_cut` treats it as high-pressure if fatigue moderate+ **or** ≤28 days. The ≤28-day arm is intentionally sensitive. Not changed here (it drives freshness/density language, not the active-role count). Candidate for a separate gated knob. `athlete_model.py:_is_high_pressure_weight_cut`. |
| 2. Bridge cap conflict (3 vs 2) | **Fixed** | This change. |
| 3. Late-fight bans "development" wording | Deliberate, keep | Render-guidance flags (`allow_development_language=False`, etc.) keep the language honest about a taper-on-ramp. Cosmetic, not a load cap. `stage2_payload_late_fight.py` payload-mode dicts. |
| 4. Downgraded hard sparring still "crowds" the week | **Already handled** | `_late_fight_active_role_count` excludes coach-owned `hard_sparring_day` from the app's active-role budget, so a downgraded/technical-touch sparring day does **not** consume an app S&C slot. Test: `test_late_fight_calendar_regression.py::test_active_role_count_excludes_coach_owned_sparring`. |
| 5. Taper allocation is recovery-heavy (e.g. 1 strength / 1 cond / 3 recovery) | Deliberate, **tunable-future** | This is the role-map taper allocator (>21-day camps), outside the D-21..D-18 scope agreed for this change. Intentional taper shape; candidate for a future gated knob. |
| 6. Finalizer cannot restore suppressed roles | Deliberate (safety), keep | Correct by design — the finalizer must not silently re-inflate what upstream safety logic suppressed. The right lever is the upstream cap (fixed in #2), not the finalizer. |
