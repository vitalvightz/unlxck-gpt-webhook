# Bug 11 — Tiered Sparring Injury Scoring Design

## 1. Current State Analysis

### What exists today

**Two parallel injury assessment systems** run independently:

| System | File | Purpose | Output |
|--------|------|---------|--------|
| Dose planner | `sparring_dose_planner.py::_injury_assessment()` | Decides **action** (convert / deload / none) | `{severity, worsening, instability, daily_symptoms, high_risk}` |
| Advisory scorer | `sparring_advisories.py::_sparring_injury_entries()` | Ranks advisories, picks labels, generates reason text | `{state_score: 0-10, worsening, improving, stable, ...}` |

The dose planner already uses categorical severity (`none/mild/moderate/high`) with flag-based
overrides — it is closer to the target model. **Bug 11 lives in the advisory scorer.**

### The additive scoring bug (`_sparring_injury_entries`, lines 213-237)

```
state_score = 0
if moderate:  state_score = 2
if severe:    state_score = max(state_score, 4)
if worsening: state_score += 2          ← can combine with improving
if stable:    state_score = max(0, state_score - 1)   ← can soften severe
if improving: state_score = max(0, state_score - 1)   ← can soften severe
if daily_symptoms: state_score += 2     ← double-counted (already in severe)
if instability:    state_score += 2     ← double-counted (already in severe)
if high_collision_region: state_score += 1  ← inflates severity from region
```

**Problems:**
1. `severe + improving` → 4 + 2 - 1 = 5. A severe improving injury scores barely above
   a moderate worsening injury (2 + 2 = 4). Severe should stay high regardless.
2. `stable` and `improving` subtract from structural risk. A severe stable injury
   should still be treated as serious for sparring.
3. `instability` and `daily_symptoms` are baked into the `severe` flag but then add +2
   again — double-counting inflates scores unpredictably.
4. Region adds to severity score instead of influencing sparring context separately.
5. Opposite signals (`worsening + improving`) don't short-circuit — both apply.
6. Clamping to 0-10 masks unreliable intermediate sums.

### Blast radius (why this is safe to change)

- `state_score` is **internal only** — it does not appear in API response models.
- The convert/deload decision is made by `sparring_dose_planner.py`, not by this score.
- `state_score` only affects:
  - `_injury_risk()` → ranking tiebreaker (4th of 5 fields in rank tuple)
  - `_highest_risk_entry()` → picks which injury to name in reason text
- Changing the score model cannot alter the advisory action, phase, days, or suggestion
  structure. It can only change which injury is highlighted and which week wins a tiebreak.

---

## 2. New Model Design

### 2a. Severity Tier (step 1 — base classification)

Classify the **structural severity** of the injury independent of trend or flags.
One exclusive tier per injury.

| Tier | Label | Criteria |
|------|-------|---------|
| High | `"high"` | Keywords: `severe`, `tear`, `rupture`, `fracture`, `cannot`, `can't`, `sharp` (when paired with function loss) |
| Moderate | `"moderate"` | Keywords: `strain`, `sprain`, `pain`, `tendon`, `tendonitis`, `tendinopathy`, `impingement` |
| Low | `"low"` | Keywords: `mild`, `soreness`, `stiffness`, `irritation`, `ache` — or no severity signal at all |

**Priority:** If multiple keywords match, the highest tier wins.
If guided injury input carries structured severity, that takes priority over keyword parsing.

> **Difference from current:** `instability` and `daily_symptoms` no longer inflate the
> base severity tier — they become override flags (step 2).

---

### 2b. Override Flags (step 2 — minimum risk floors)

These are **structural risk signals** extracted from details/notes text. Each one sets a
minimum risk floor that trajectory cannot soften below.

| Flag | Detected by | Minimum risk floor |
|------|-------------|-------------------|
| `instability` | `instability`, `giving way`, `buckled` | Red |
| `locking` | `locking`, `locked` | Red |
| `daily_symptoms` | `daily`, `rest pain`, `night pain`, `sleep`, `walking`, `stairs`, `constant` | Red |
| `cannot_load` | `cannot`, `can't` + load/punch/rotate/move context | Red |
| `sharp_with_function_loss` | `sharp` + (`cannot`, `can't`, `lose`, `loss`) | Red |
| `rest_pain` | `rest pain` | Red |
| `giving_way` | `giving way` | Red |

Every override flag forces a **minimum red** band. The band can still escalate to black
(e.g., with worsening trajectory), but cannot drop below red.

> **Key rule:** Override flags capture _what the injury does to the athlete_,
> not how bad the tissue damage is. They represent functional danger signals
> that must not be erased by a favorable trend.

---

### 2c. Trajectory (step 3 — modifier only)

One exclusive state per injury. Priority order if conflicting keywords appear:

1. `worsening` — `worsen`, `worsening`, `worse`, `flared`, `aggravated`, `regressing`
2. `stable` — `stable`, `managed`, `manageable`, `maintenance`
3. `improving` — `improving`, `better`, `settling`, `resolved`, `resolving`
4. `unknown` — no trend keywords detected (default, treated like `stable`)

> **Critical constraint:** Trajectory can **escalate** risk by one level or trigger
> hard rules (severe + worsening = black). It can **de-escalate** risk by at most one
> level, and only when no override flags are active.

---

### 2d. Collision Context (step 4 — sparring exposure lens)

Region determines **how much sparring exposes the injury**, not how bad the injury is.

| Context | Regions | Meaning |
|---------|---------|---------|
| `"lower_limb"` | ankle, knee, shin, hip, foot, achilles, groin | Footwork, kicks, stance changes directly load this |
| `"upper_body_collision"` | shoulder, neck | Clinch, punches, head movement directly load this |
| `"torso"` | lower_back, ribs | Rotation, body shots load this |
| `"low_collision"` | wrist, hand, elbow, or anything not above | Sparring loads this less directly |
| `"unspecified"` | No region parsed | Default to conservative (treat as high collision) |

Collision context is used to:
- Strengthen or weaken the sparring advisory language (not the base severity)
- Decide where `mild + stable` falls: `amber` in high collision, `green` in low collision
- Inform replacement focus text (already done by `_replacement_focus()`)

---

### 2e. Risk Band Resolution (step 5 — the decision)

**Phase 1: Severity base**

| Severity tier | Starting band |
|---------------|--------------|
| High | Red |
| Moderate | Amber |
| Low | Green |

**Phase 2: Override floor**

If any override flag is active → band is at least Red.

**Phase 3: Trajectory adjustment**

| Rule | Result |
|------|--------|
| Severe + worsening | → **Black** (hard rule) |
| Severe + improving | → stays **Red** (cannot drop below) |
| Severe + stable/unknown | → stays **Red** |
| Moderate + worsening | → escalate to **Red** |
| Moderate + worsening + high collision context | → **Red** (same, but noted for advisory wording) |
| Moderate + improving | → stays **Amber** (no de-escalation when base is moderate) |
| Moderate + stable/unknown | → stays **Amber** |
| Low + worsening | → escalate to **Amber** |
| Low + improving | → stays **Green** |
| Low + stable | → **Green** or **Amber** depending on collision context |
| Low + unknown | → same as stable |

**Phase 4: Collision context refinement (low severity only)**

| Severity + trajectory | Collision context | Final band |
|----------------------|-------------------|------------|
| Low + stable | lower_limb / upper_body_collision / unspecified | Amber |
| Low + stable | torso / low_collision | Green |
| Low + improving | any | Green |

---

### 2f. Numeric Score (step 6 — secondary tiebreaker)

Derived **after** the band is chosen. Used only for ranking tiebreaks when multiple
injuries or weeks compete. Never used for risk classification.

```
band_base = {"green": 0, "amber": 3, "red": 6, "black": 9}
score = band_base[risk_band]

# Minor adjustments for tiebreaking
if len(override_flags) >= 2:  score += 1
if trajectory == "worsening": score += 1
if collision_context in ("lower_limb", "upper_body_collision", "unspecified"):
    score += 0   # already reflected in band

score = clamp(score, 0, 10)
```

---

## 3. Key Decision Rules (summary table)

| Scenario | Severity | Trajectory | Overrides | Region | Band |
|----------|----------|-----------|-----------|--------|------|
| Severe + worsening ankle instability | High | Worsening | instability | lower_limb | **Black** |
| Severe + improving shoulder tear | High | Improving | — | upper_body_collision | **Red** |
| Severe + stable knee with daily symptoms | High | Stable | daily_symptoms | lower_limb | **Red** |
| Moderate worsening knee strain | Moderate | Worsening | — | lower_limb | **Red** |
| Moderate stable shoulder impingement | Moderate | Stable | — | upper_body_collision | **Amber** |
| Moderate improving ankle sprain | Moderate | Improving | — | lower_limb | **Amber** |
| Mild stable wrist soreness | Low | Stable | — | low_collision | **Green** |
| Mild stable ankle soreness | Low | Stable | — | lower_limb | **Amber** |
| Mild worsening shoulder stiffness | Low | Worsening | — | upper_body_collision | **Amber** |
| No injuries | — | — | — | — | _(short-circuit: no advisory from injuries)_ |

---

## 4. Implementation Plan (surgical patch steps)

### Step 0: Characterization tests (BEFORE any code changes)

Lock in the current behavior of `_sparring_injury_entries()` with snapshot tests:

- For each scenario in the table above (using current raw-text format), record the
  exact `state_score` the current code produces.
- Test `_injury_risk()` for multi-injury combinations.
- Test `_highest_risk_entry()` selection.
- Test `build_plan_advisories()` end-to-end for at least 3 representative briefs.

These tests ensure we can detect if the behavior shifts during the refactor.

### Step 1: Add new internal fields alongside old score

In `_sparring_injury_entries()`, compute and attach the new fields **without touching
the old `state_score` calculation:**

```python
entry = {
    # --- existing fields (unchanged) ---
    "raw": raw_text,
    "region": region,
    "injury_type": injury_type,
    "laterality": laterality,
    "state_score": state_score,         # ← KEPT as-is
    "worsening": worsening,
    "improving": improving,
    "stable": stable,
    "instability": instability,
    "daily_symptoms": daily_symptoms,
    "high_collision_region": region in _HIGH_COLLISION_REGIONS,
    "lower_limb": region in _LOWER_LIMB_REGIONS,
    # --- new v2 fields (added alongside) ---
    "severity_tier": severity_tier,      # "low" | "moderate" | "high"
    "trajectory": trajectory,            # "worsening" | "stable" | "improving" | "unknown"
    "override_flags": override_flags,    # list[str]
    "collision_context": collision_context,  # "lower_limb" | "upper_body_collision" | "torso" | "low_collision" | "unspecified"
    "risk_band": risk_band,              # "green" | "amber" | "red" | "black"
    "risk_band_score": risk_band_score,  # 0-10, derived from band
}
```

**No downstream code changes.** `_injury_risk()` and `_highest_risk_entry()` still use
`state_score`. The new fields are computed but not consumed yet.

### Step 2: Add v2 tests

Write tests that verify the new fields produce expected values for the decision table.
These run alongside the characterization tests (which verify old behavior is unchanged).

### Step 3: Add v2-aware ranking (shadow)

Add a `_injury_risk_v2()` function that uses `risk_band` instead of `state_score`:

```python
_BAND_RANK = {"green": 0, "amber": 1, "red": 2, "black": 3}

def _injury_risk_v2(entries: list[dict[str, Any]]) -> int:
    if not entries:
        return 0
    best = max(entries, key=lambda e: _BAND_RANK.get(e.get("risk_band", "green"), 0))
    return best.get("risk_band_score", 0)

def _highest_risk_entry_v2(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not entries:
        return None
    return max(entries, key=lambda e: _BAND_RANK.get(e.get("risk_band", "green"), 0))
```

These are defined but **not wired in** yet.

### Step 4: Switch

Once v2 tests are all green and characterization tests confirm no regressions in the
downstream advisory output shape, swap the callers:

- `_build_week_advisory()` uses `_highest_risk_entry_v2()` instead of `_highest_risk_entry()`
- `build_plan_advisories()` uses `_injury_risk_v2()` instead of `_injury_risk()`
- Optionally add `risk_band` to the advisory output dict for UI consumption later

### Step 5: Clean up

- Remove old `state_score` calculation (or keep as a deprecated field if needed)
- Remove `_injury_risk()` and `_highest_risk_entry()` (replaced by v2)
- Update characterization tests to use v2 expected values

---

## 5. Functions Changed (exact scope)

| Function | File:Line | Change | Risk |
|----------|-----------|--------|------|
| `_sparring_injury_entries()` | `sparring_advisories.py:184` | Add severity_tier, trajectory, override_flags, collision_context, risk_band, risk_band_score fields to each entry dict. Old state_score kept. | None — additive fields only |
| `_injury_risk_v2()` | `sparring_advisories.py` (new) | New function, not wired until step 4 | None — unused until switched |
| `_highest_risk_entry_v2()` | `sparring_advisories.py` (new) | New function, not wired until step 4 | None — unused until switched |
| `_build_week_advisory()` | `sparring_advisories.py:364` | Step 4 only: swap `_highest_risk_entry` → `_v2` | Low — only affects injury label text |
| `build_plan_advisories()` | `sparring_advisories.py:513` | Step 4 only: swap `_injury_risk` → `_v2` | Low — only affects ranking tiebreak |

**Functions NOT changed:**
- `_pressure_score()`, `_fatigue_score()`, `_cut_score()` — unrelated
- `_replacement_focus()` — already region-aware, works fine
- `_build_week_advisory()` internals (reason text, suggestion text) — output unchanged
- `sparring_dose_planner.py` — completely separate system, untouched
- API models — `PlanAdvisory` schema unchanged

---

## 6. Out-of-Scope Items (noted but deferred)

These items from the suggestion are valid but belong in separate patches:

1. **"Movements to avoid" should affect planning restrictions, not severity.**
   The `avoid` field from GuidedInjuryInput feeds into restriction parsing, not into
   `_sparring_injury_entries()`. Verify this is already correct; if not, it is a
   separate fix in `input_parsing.py` / `restriction_parsing.py`.

2. **"Do not show 'No restrictions reported' while injury fields are partially filled."**
   This is a UI rendering concern. Belongs in `web/` or in plan rendering logic.

3. **"If 'No current injuries' is checked, short-circuit immediately."**
   Already effectively handled: empty injuries list → `_sparring_injury_entries()` returns
   `[]` → `_injury_risk()` returns 0. Advisory can still fire from fatigue/cut/week
   pressure alone, which is correct behavior (you can be injury-free but still need a
   deload in taper with high fatigue).

4. **Aligning the two injury assessment systems** (`sparring_dose_planner._injury_assessment`
   vs `sparring_advisories._sparring_injury_entries`). The new v2 fields bring them closer
   in vocabulary. Full unification is future work.

---

## 7. Test Plan

### Characterization tests (step 0)

```
test_state_score_characterization_for_representative_injury_texts
  - "mild stable shoulder soreness" → record current state_score
  - "worsening ankle instability" → record current state_score
  - "severe improving shoulder tear" → record current state_score
  - "moderate worsening knee strain" → record current state_score
  - "stiffness in wrist" → record current state_score
  - "sharp knee pain cannot walk rest pain daily" → record current state_score

test_injury_risk_characterization_for_multi_injury
  - Single injury → record _injury_risk()
  - Two injuries → record _injury_risk() (max + 1 multi-bonus)

test_highest_risk_entry_picks_highest_state_score
  - Two injuries with different scores → verify max is selected
```

### V2 field tests (step 2)

```
test_severity_tier_classification
  - "tear" → high
  - "strain" → moderate
  - "soreness" → low
  - "instability" text → severity stays based on injury type, NOT elevated by instability

test_trajectory_exclusive_state
  - "worsening and improving" → worsening wins (conservative)
  - "stable" → stable
  - no trend keywords → unknown

test_override_flags_detection
  - "instability" → ["instability"]
  - "daily rest pain giving way" → ["daily_symptoms", "rest_pain", "giving_way"]
  - "mild soreness" → []

test_collision_context_classification
  - "knee" → lower_limb
  - "shoulder" → upper_body_collision
  - "wrist" → low_collision
  - no region → unspecified

test_risk_band_key_rules
  - severe + worsening → black
  - severe + improving → red (NOT amber or green)
  - instability flag → minimum red
  - daily_symptoms flag → minimum red
  - moderate + worsening + lower_limb → red
  - moderate + improving → amber
  - mild + stable + lower_limb → amber
  - mild + stable + low_collision → green

test_risk_band_score_derives_from_band
  - green → 0-2
  - amber → 3-5
  - red → 6-8
  - black → 9-10
```

### Advisory integration tests (step 4)

```
test_v2_ranking_selects_same_or_better_advisory_as_v1
  - Run both old and new ranking on same multi-week brief
  - Verify v2 picks a reasonable "best"

test_advisory_output_shape_unchanged_after_v2_switch
  - Same input → action, phase, days, title, disclaimer all unchanged
  - Only reason text and week selection may differ
```

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| New fields break existing dict consumers | Very low | Low | New fields are additive; no existing code reads them until step 4 |
| Tiebreaker ranking changes which week is "best" | Medium | Very low | The "best" advisory is already a soft preference; any qualifying advisory is valid |
| Injury label text changes in reason | Medium | Low | Label comes from same raw text; only selection order might change |
| Regression in advisory output structure | Very low | Medium | Characterization tests catch shape changes before merge |

**Overall risk: LOW.** The scoring model is an internal detail that does not affect API
contracts, dose planner decisions, or advisory output structure.
