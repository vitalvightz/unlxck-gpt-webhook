# Measurable exercise coaching restoration

## Confirmed cause

Before #2876, the Stage 2 finaliser sent the model's first-pass plan directly into
review. RULE 6A already requested numerical next steps (repetitions, minutes,
carry distance, etc.). #2876 added authoritative whole-schedule reconciliation
before validation: replacement exercise lines kept the approved membership,
calendar and dose but discarded the model's exercise coaching. Validation did
not enforce the missing guidance. #2880 restored coaching fields using movement
profiles, but its Progress strings described execution quality at the same dose.
This restored field coverage without restoring measurable programming.

## Authority and safety

The restoration makes one deterministic lookup of selected future exposures.
Current prescriptions come from the same effective strength/assignment authority
as the renderer. A Progress instruction requires a comparable next exposure in
the same phase with exactly one authorised work variable increasing, unchanged
effort and no shorter rest. Extra numerical changes (including tempo and heart
rate targets) cannot be hidden inside that instruction. Known load increments
are limited to 5% of the starting load, or five percentage points of known 1RM.
Unknown loads, compound doses and ambiguous exposures abstain.

Taper, the final fortnight, injury restrictions, fatigue, cut pressure and
managed-stress/retention contexts suppress advancement. Unchanged next doses
become an exact maintenance target under Cue. No selected exercise, current
prescription or future prescription is changed.

Specific bank coaching, regressions and stop rules take precedence. A bank
numerical Progress survives when its step agrees with the approved future dose;
a conflicting step is replaced with the actual authorised step. Qualitative
execution instructions belong under Cue. Easier reduces one known work quantity
while retaining rest and the effort ceiling, and preserves existing movement
options. Athlete overrides remain authoritative. Same-day duplicates use their
own session identity; ambiguous legacy matches retain existing coaching.

The shared rules run in authoritative rendering, model conversion, deterministic
fallback and saved-plan recovery. React displays the same persisted/API fields.
No new AI call, schema change or production data write is involved.

## Production replay: same athlete programme

The anonymised fixtures replay plans `64a92843`, `4389543e`, `0e1f9aaf` and
`741aa47d` through saved-plan recovery, effective API resolution and expanded
React cards. They preserve exercise selection, current doses, existing
regressions and stop rules. The October 9 renewable plan has no dated role map;
its existing explicit block progression remains untouched. Historical model
numbers are not treated as future dose authority when the saved schedule does
not support them.

The latest programme (`741aa47d-23fb-43d9-964a-b8e06b93a48a`) has **no increasing
authorised future physical doses**. It would be incorrect to promise a numerical
increase on its current cards. Its 27 physical cards change as follows:

| Athlete-visible coverage | Before | After |
| --- | ---: | ---: |
| Coaching cues | 27 | 27 |
| Easier options | 27 | 27 |
| Stop rules | 27 | 27 |
| Explicit numerical Easier reductions | 0 | 27 |
| Exact next-exposure maintenance targets | 0 | 7 |
| Quality-only instructions mislabelled Progress | 18 | 0 |
| Authorised numerical advances | 0 | 0 |

Examples from that same programme (original coaching and lighter/depth options
are preserved):

| Exercise | Before Progress | After Cue / additional Easier |
| --- | --- | --- |
| D-44 Sled Pull Forward (Harness) | Aim for smoother unbroken rhythm at same load and distance | Next D-37: repeat 3 carries over 20 m, heavy but unbroken; rest 90s. / Reduce sets to 2 instead of 3. |
| D-44 Cossack Squat | Once reps are stable, improve control at same dose | Next D-37: repeat 2x6 @ RPE 6, keep reps crisp. / Reduce sets to 1 instead of 2. |
| D-33 Barbell Thruster | Once reps stay crisp, aim for consistent rep speed at same load | Next D-23: repeat 4x2 reps at max speed; full rest 120s. / Reduce sets to 3 instead of 4. |

Supported advancement is separately verified using controlled **approved future
dose** fixtures: 3x8 → 3x9 reps, 20 → 25 minutes, 20 → 30 m per carry,
one additional set/round, timed holds and known 50 → 52 kg. These are capability
tests, not claimed changes to the production athlete's programme. A typical
result is: “If all prescribed work is controlled and recovery is normal, at
D-28 use 3 x 9 reps; rest 120 sec; RPE 7 (increase reps per set only from 8 to 9).”

## Release checks and latency

The CI release gate compares all applicable coaching fields in the final expanded
React exercise cards, including model reconciliation/conversion, persistence,
API recovery and the fast deterministic fallback. Negative tests cover dropped
fields, conflicting numerical suggestions, unknown/unsafe load, extra variables,
injury/readiness/cut pressure, same-day duplicates and final-fortnight taper.
Tests also apply real athlete overrides after recovery.

Local benchmarks on the latest recorded programme: shared read recovery median
0.654 → 3.258 ms; deterministic fallback median 22.65 → 28.65 ms (about 6 ms
additional local work). The converter's existing maximum two-call/retry contract
is tested. These are local deterministic measurements, not a live provider
latency measurement.
