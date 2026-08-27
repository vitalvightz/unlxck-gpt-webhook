# Technical Footwork Bank — reclassification and follow-ups

## What changed

`footwork_conditioning_bank.json` was reclassified to
`technical_footwork_bank.json` and removed from the conditioning **scoring
pool**. Previously it was merged into `get_conditioning_bank()` (via a
monkey-patch loader) so its drills competed as ordinary aerobic conditioning
and could be selected as a primary energy-system dose. That merge is gone.

The bank is now consumed through a dedicated, relevance-gated path that mirrors
the coordination-goal guarantee:

- `conditioning.get_technical_footwork_bank()` — standalone cached loader.
- `conditioning.select_technical_footwork_drill()` — gates on footwork
  relevance (goals/weaknesses), phase eligibility, per-drill `reactive_level`
  vs phase, `technical_complexity` in taper, equipment, and injury; ranks by
  sport + tactical function.
- `_insert_technical_footwork_drill()` — a best-effort guarantee poststep that
  fills a leftover drill slot for footwork-focused athletes. It is never scored
  against the energy-system pool; when it appears it carries the
  `technical_footwork_guarantee` reason code.

Each drill now carries meaningful per-drill metadata (phase eligibility,
`late_windows`, rpe, movement cost, honest `mech_*` tags) and a structured
taxonomy (`footwork_pattern`, `directionality`, `tactical_function`,
`reactive_level`, `braking_demand`, `elastic_demand`, `technical_complexity`,
`stance_transition`). Muay Thai/kickboxing and MMA locomotion were expanded
(teep retreat, check-and-return, switch-step, cage circle, level-change feint).

## Deferred, on purpose

These were intentionally **not** done in this branch because the current
conditioning taxonomy/selector do not yet support them cleanly. Each is a
separate design change.

### 1. Footwork speed / agility layer (audit §7-B)

Short (3–5 s) explosive angle bursts, reactive mirror steps, cue-based
pivot-and-exit, 45°/90° COD bursts. These are alactic/neural, not technical
rehearsal, and belong in a speed-dose channel. The conditioning module already
has a `speed_dose_allowed` path and an alactic quota; the clean home is the
alactic/speed-dose selector, not this technical bank. Adding `speed`/`reactive`
tags to this bank is explicitly blocked by
`test_footwork_drills_do_not_default_to_speed_or_reactive_work`.

### 2. Footwork conditioning layer (audit §7-C)

10–30 s repeated ring-movement / change-of-direction efforts, pressure-footwork
density intervals, stance-preserving shuttle bouts. These are a genuine
physiological dose and belong in the main conditioning bank, but only once the
conditioning taxonomy has a first-class `modality: combat_footwork` (or similar)
that the selector and late-fight dosage policy understand. Until then, adding
them would re-create the "practising movement vs. developing conditioning"
confusion this reclassification removes. Recommended approach:

1. Add a `combat_footwork` modality + energy-system entries to
   `conditioning_bank.json` with real work:rest, lactate, and impact costs.
2. Extend `conditioning_boxing._is_*` modality helpers if bespoke dosing is
   needed.
3. Gate/boost them by the existing footwork goal signal in
   `stage2_planning_brief` / `stage2_payload`.

### 3. Visible render channel for technical footwork

Today the conditioning block renders one primary drill per energy system.
Technical footwork surfaces visibly only when it fills an otherwise-open
energy-system slot (most often in taper). A dedicated, clearly-labelled
"Technical Footwork" render element (separate from the energy-system drills, and
excluded from dose accounting) would let its named drills appear for
footwork-focused athletes in all phases without ever reading as a conditioning
dose. This needs changes in `render_conditioning_block` and the grouped-drills
builder and would ripple into render snapshots, so it is deferred.

## Note on the late-camp golden snapshot

`tests/golden_snapshots/late_camp_selector_audit/after.json` was already stale
on the branch base (deterministic drift in both strength and conditioning,
predating this work — it was last regenerated at commit `63cec74`, before later
bank/selector changes). This branch does **not** regenerate it, to avoid
bundling unrelated strength drift into the footwork change. Removing footwork
from the conditioning pool does change that snapshot's conditioning candidate
lists; regenerate it in a dedicated pass with `tools/late_camp_selector_audit.py`.
