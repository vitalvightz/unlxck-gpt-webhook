# Injury Triage Precedence Spec (decision doc)

**Status:** awaiting product/clinical decision. Once the rules below are confirmed,
the implementation in `fightcamp/injury_triage.py` is mechanical and the ~27
failing triage tests become the executable spec.

**Why this exists.** The triage code and its tests have drifted (the repo's git
history is a single squashed root commit, so we cannot tell which moved). The
failing tests encode a coherent, intended behavior; the current code diverges in
**both** directions — it *over*-blocks resolved/historical injuries **and**
*under*-escalates some confirmed-serious ones. Because triage is a medical-safety
gate, the precedence rules are a product/clinical decision, not something to pick
unilaterally. This doc states the rules the tests imply so you can confirm or
amend them once.

> The dangerous **under-block of neurological symptoms** (numbness/tingling/
> weakness → `full_plan`) is already fixed separately in PR #1706 and is **not**
> part of this decision.

---

## 1. The four signal classes

| Class | Meaning | Examples |
|---|---|---|
| **S — Serious structural** | A named/strongly-implied serious diagnosis | fracture, dislocation, ACL/achilles/tendon rupture, complete ligament tear, "broke it", "snapped" |
| **C — Current danger symptoms** | Active, present-tense severity | significant pain, swelling, *cannot bear weight*, giving-way/buckling, **worsening** trend, severity=high, neuro (numb/tingle/weak) |
| **R — Resolution / negation markers** | Says the thing is past or absent | "old", "history of", "healed", "fully recovered", `cleared=yes`, `timeframe=old_cleared`, "ruled out", "no fracture", "not broken" |
| **B — Benign qualifiers** | Explicitly downgrades severity | "no pain", "no swelling", "can walk", joint **noise only** (pop/snap/crack/click) with nothing else |

## 2. Mode scale (most → least restrictive)

`MEDICAL_HOLD` → `RESTRICTED_REHAB_ONLY` → `NEEDS_REVIEW` → `FULL_PLAN`

---

## 3. Proposed precedence rules (← the decisions)

These are derived from the failing tests. **Confirm, amend, or reject each.**

### RULE 1 — Resolution/negation down-gates a structural word, *unless* current symptoms are present
`S + R + no C → FULL_PLAN`. But `S + R + C → block` (current symptom wins).
- Drives: "old tendon rupture, now healed" → full_plan; but "old tendon rupture healed **but pain today**" → block (this one already passes).
- **Decision D1:** Confirm that an explicit resolution/negation marker fully clears a structural term when there are no current symptoms.

### RULE 2 — Joint-noise needs a current symptom to escalate
`noise(pop/snap/crack/click) alone or + B → FULL_PLAN`. `noise + C → block`.
- Drives: "ankle popped but no pain, no swelling, can walk" → full_plan; "heard a snap and **cannot bear weight**" → block.
- **Decision D2:** Confirm noise words are not, by themselves, a blocking signal.

### RULE 3 — Severity proportionality (the under-block half)
- Confirmed serious structural / `high + worsening` / "muscle rupture" → **`RESTRICTED_REHAB_ONLY`** (not `needs_review`).
- Vague or uncertain elevated signal, lone recent-history → **`NEEDS_REVIEW`**.
- Fully resolved (RULE 1) → **`FULL_PLAN`**.
- **Decision D3:** Confirm the mapping — in particular that `high+worsening` vague guided injuries and `muscle rupture` should be **restricted**, not merely review. (Today the code returns `needs_review`.)

### RULE 4 — Category labeling
- Emit the **specific** category (`fracture`, `tendon_rupture_or_avulsion`, `complete_ligament_tear`, `dislocation`, …) whenever identifiable; use the generic `structural_high_severity` **only as a fallback**.
- Apply `TRIAGE_CATEGORY_ALIASES` (e.g. `ligament_tear → complete_ligament_tear`) to **parsed-injury** `injury_type`, not just free text.
- **Decision D4:** Confirm the specific-category-preferred policy and parsed-injury aliasing. (Note: the *mode* is already correct in these cases; only the category label differs — lower stakes, but it's a contract several callers read.)

### Likely-bugs (probably no policy call needed — confirm to "just fix")
- **D5a:** Default **chest** red flags (`chest_pain`/`breathing_pain`) over-fire when a parsed injury already exists — the nerve path guards this with `use_guided_diagnosis_fields` but the chest path doesn't. (`test_triage_no_default_chest_red_flags_when_parsed_injury_exists`)
- **D5b:** `cannot_bear_weight` / `structural_function_red_flag` are dropped when a *resolved* parsed injury is present. (`test_triage_guided_safety_signals_still_apply_with_resolved_parsed_injury`)

---

## 4. Case table (current vs intended)

Mode legend: FP=full_plan, NR=needs_review, RR=restricted_rehab_only. ✅PR#1706 = already fixed.

| # | Input | Current | Intended | Rule | Direction |
|---|---|---|---|---|---|
| 1 | "Scan ruled out fracture after I thought I broke it" | RR | FP | R1 (negation scope) | over-block |
| 2 | "neck cracked but no pain" | RR | FP | R2 | over-block |
| 3 | "knee snapped while stretching but no pain" | RR | FP | R2 | over-block |
| 4 | "ankle crack sound only, no pain or swelling" | NR | FP | R2 | over-block |
| 5 | "ankle popped but no pain, no swelling, can walk" | RR | FP | R2 | over-block |
| 6 | "ankle popped but no pain…" (benign pop) | RR | FP | R2 | over-block |
| 7 | "heard a snap and cannot bear weight" | blocks, cat=`structural_high_severity` | blocks, cat must incl `fracture` | R4 | label |
| 8 | parsed `injury_type=ligament_tear` (knee) | cat=`[]` | RR, cat incl `complete_ligament_tear` | R4 (alias) | label/under |
| 9 | "old tendon rupture, now healed" | NR | FP | R1 | over-block |
| 10 | "history of shoulder dislocation, now cleared" | RR | FP | R1 | over-block |
| 11 | "prior grade 3 ligament tear years ago, fully recovered" | NR | FP | R1 | over-block |
| 12 | "history of ACL tear" (no current symptoms) | NR | FP | R1 | over-block |
| 13 | guided dislocation `old_cleared, cleared=yes, [relocated_yes,recurrent_no]` | RR | FP | R1 | over-block |
| 14 | guided fracture `old_cleared, cleared=yes` ("old cleared ankle fracture") | RR | FP | R1 | over-block |
| 15 | guided "no fracture in the last month, mild soreness only" | RR | FP | R1 (negation) | over-block |
| 16 | structured fracture `old_cleared, no symptoms` | RR | FP | R1 | over-block |
| 17 | "muscle rupture" | NR | RR | R3 | under-block |
| 18 | guided knee `high + worsening`, notes "pain" | NR | RR | R3 | under-block |
| 19 | 2nd guided card `high + worsening` | NR | RR | R3 | under-block |
| 20 | structured tendon/ligament `high + worsening` | blocks, cat=`structural_high_severity` | blocks, cat incl `tendon_rupture_or_avulsion` | R4 | label |
| 21 | multi-card w/ `avoid: hard cutting/jumping` | routing missing `avoid_high_load` | routing incl `avoid_high_load` | R4-ish | routing |
| 22 | parsed hyperextension + guided cannot-bear-weight | red_flags=`[]` | incl `cannot_bear_weight` | D5b (bug) | under |
| 23 | guided chest_breathing + parsed injury exists | `chest_pain` present | `chest_pain` absent | D5a (bug) | over |
| — | "neck pain with numbness and tingling" | FP | NR | ✅PR#1706 | (fixed) |
| — | guided `nerve_symptoms` worsening | FP | NR | ✅PR#1706 | (fixed) |

(Two integration tests — `test_blocked_modes_do_not_reach_stage2_or_normal_pipeline`,
`test_full_plan_response_does_not_include_blocked_output` — are downstream of the
modes above and should pass automatically once the modes are corrected.)

---

## 5. Implementation plan once decided

1. **R1** — make resolution/history/negation markers (`R`) set a "resolved" flag on
   the matched structural category; in the final resolution, a resolved category
   does **not** block unless a current symptom (`C`) co-occurs in the same chunk.
   (Hook points: `_apply_structured_injury_signals` `old_and_cleared`/`has_current_concern`
   already exist for guided; extend the free-text `_has_structural_break_signal` /
   `_has_recent_structural_history_signal` paths to honor the same gate.)
2. **R2** — gate joint-noise tokens behind a co-present `C` before adding `fracture`.
3. **R3** — in the combo/severity resolution, route confirmed-serious & `high+worsening`
   to `RESTRICTED_REHAB_ONLY`; keep vague/uncertain at `NEEDS_REVIEW`.
4. **R4** — prefer specific categories; only fall back to `structural_high_severity`;
   apply `TRIAGE_CATEGORY_ALIASES` to parsed-injury `injury_type`.
5. **D5a/b** — guard the chest default red-flags with `use_guided_diagnosis_fields`;
   preserve guided function-loss signals even when a resolved parsed injury exists.
6. Each rule lands as its own small PR with the corresponding tests flipping green,
   so the safety behavior is reviewable in isolation.

**One question worth flagging for clinical sign-off:** RULE 1 trusts athlete-reported
resolution ("healed", "cleared", "ruled out"). If you'd rather have *any* serious
structural mention always reach at least `NEEDS_REVIEW` (coach eyeballs it) even
when the athlete says it's resolved, that's a one-line change to R1 (down-gate to
`NEEDS_REVIEW` instead of `FULL_PLAN`) — but it conflicts with the current tests,
which expect `FULL_PLAN`. **This is the single most important call to make.**
