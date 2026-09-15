# Weight-cut severity architecture

## One score, two scales

`compute_cut_severity_score(cut_pct, days_until_fight)` is the single numeric
authority:

```
3.2 * cut_pct^1.15 * (1 + 1.8 * exp(-days_out / 15))
```

That one score is read through two deliberately different scales, because a cut
poses two unrelated questions.

| | `cut_health_bucket` (strain) | `cut_severity_bucket` (capacity) |
|---|---|---|
| Question | How hard is this cut on the body right now? | Does this cut justify deleting training days? |
| Boundaries | 5 / 15 / 35 / 55 / 85 | 10 / 25 / 50 / 75 / 95 |
| Drives | warnings, supervision, stop-and-report, volume, RPE ceilings, glycolytic exposure, strength dose, sparring dose | weekly session count only |

Keeping them apart is what lets the planner **reduce dose before deleting
calendar**. Recalibrating capacity severity must never quietly relax medical
escalation or load shaping, so strain keeps its original, stricter thresholds.

Health escalation additionally keeps a magnitude floor at `>= 6%` independent of
days-out (`weight_cut_risk_band`, `weight_cut_supervision_required`).

## Capacity boundaries in cut percentages

What the capacity scale means at useful countdown points:

| boundary | D-28 | D-21 | D-16 | D-14 | D-7 | D-3 | D-1 |
|---|---|---|---|---|---|---|---|
| none/low | 2.2 | 2.0 | 1.8 | 1.7 | 1.4 | 1.2 | 1.1 |
| low/moderate | 4.8 | 4.3 | 3.9 | 3.8 | 3.1 | 2.7 | 2.5 |
| moderate/high | 8.8 | 7.9 | 7.2 | 6.9 | 5.7 | 5.0 | 4.6 |
| high/critical | 12.5 | 11.3 | 10.2 | 9.8 | 8.1 | 7.1 | 6.6 |
| critical/extreme | 15.4 | 13.9 | 12.5 | 12.0 | 9.9 | 8.7 | 8.1 |

Sanity-checked against combat-sport evidence: UFC data on 616 athletes recorded
average mass above class of ~6.7% at 72 h, ~5.7% at 48 h and ~4.4% at 24 h before
weigh-in, and the 2025 ISSN combat-sport position stand treats ~2-4% acute water
loss in the final 24 h as a practice seen in appropriately supervised
professional contexts. The previous capacity boundaries put moderate/high at
5.3% at D-16 and 3.4% at D-1 — i.e. they classified the *median* competitive cut
as "high" and deleted training for it.

This is a calibration of planner severity, not an endorsement of aggressive
dehydration.

## Training consequences by severity (capacity scale)

| bucket | weekly slots removed | intended handling |
|---|---|---|
| none / low | 0 | no training consequence |
| moderate | 0 | preserve frequency; adjust volume, density, RPE ceiling, glycolytic dose, recovery emphasis |
| high | 1 | preserve usable days; shed volume, soreness cost, glycolytic density, eccentric and collision load first |
| critical | 2 | may remove one meaningful stress exposure |
| extreme | 2 | may suppress high-risk training, escalate on safety |

`weight_cut.cut_training_compression_points()` is the **only** place a cut
subtracts weekly capacity. No other module may charge the same cut again.

Goal deferral (abandoning power, footwork, skill refinement rather than reducing
their dose) requires `cut_justifies_goal_deferral`, i.e. critical or extreme.

## Deferred: weigh-in timing

The model is keyed on `days_until_fight`. Research-based weight management
actually depends on time until *weigh-in* and the recovery window from weigh-in
to competition — a 24 h weigh-in and a same-day weigh-in at the same cut
percentage are not equivalent risks.

Intentionally **not** built in this change, because it needs intake and schema
work well beyond the stacked-penalty fix:

- `weigh_in_datetime`
- `hours_until_weigh_in`
- `hours_weigh_in_to_competition`
- `weigh_in_format` (`same_day` / `12h` / `24h` / `36h_plus`)

**The seam:** `compute_cut_severity_score(cut_pct, days_until_fight)` is the only
function that converts a countdown into cut severity. When weigh-in timing lands,
it gains an optional weigh-in argument and derives its time term from
`hours_until_weigh_in` (falling back to `days_until_fight * 24`), while
`weigh_in_format` scales the recovery allowance — a same-day weigh-in should
raise severity for the same percentage, a 36 h+ window should lower it. Because
both scales already read this one score, no consumer needs to change.
