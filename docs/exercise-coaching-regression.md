# Exercise coaching regression: 14 October 2026

The direct regression is **#2876**, not #2875. Commit `6358dc3e` added
`reconcile_authoritative_programme` before Stage 2 validation. It replaces the
entire weekly schedule with the deterministic schedule to enforce exact dates,
membership and effective doses. The replacement's closed-membership renderer
only wrote dose, bank notes as Cue, and Purpose. It never wrote Progress or
Easier, and left bank stop criteria embedded inside cues. Correcting the
programme therefore deleted its exercise coaching.

## Evidence and trace

Read-only Supabase inspection confirmed the reported historical totals:
`0e1f9aaf-d789-4733-b513-8bdd23fa43ac` has 37 blocks with Progress and 34 with
Easier; `f01e0d74-8215-451f-9658-a2a43d4b64d5` has no Easier and no Progress
on selected physical exercises. The latest reconciliation corrected 61
programme findings and the structured conversion was marked valid.

The existing anonymised recorded model response in
`tests/fixtures/programme_fidelity/production_render.txt` independently proves
the loss. Replaying its recorded authority with the pre-fix renderer takes
**26 Progress / 26 Easier / 26 Stop labels to 8 / 0 / 0**. Those remaining
Progress labels belong to deterministic non-S&C support. The current fix
retains 29 / 26 / 26 on that historical programme, including its support labels.
This is a replay of recorded text, not a new model evaluation.

The latest job does not persist its original provider response. Its saved
final text is already reconciled; we cannot measure that particular initial
response's guidance coverage. The source diff and the separate recorded-response
replay establish the destructive step without assuming what it contained.

The downstream trace:

1. The Stage 2 handoff asks for exercise-level coaching and progression,
   regression and stop guidance. #2875's finalizer still passed the model text
   directly to validation; it did not add wholesale programme replacement.
2. #2876 reconciled schedule text before conversion. Progress/Easier vanished
   there, so a faithful converter had nothing to retain.
3. Conversion normalization already routes labelled guidance into
   `coaching_cues`, `progression_rule`, `regression_options`, and `stop_rules`.
   Faithfulness previously checked dose changes and advisory cue omissions,
   but did not block loss of these coaching fields.
4. Fallback parsed these fields when present in source text. With no matching
   source line, it only lifted the exact planner dose and omitted bank coaching.
   #2878 avoided futile repeat conversions; that exposed an existing lossy
   fallback more often rather than causing the initial source loss.
5. Persistence retained the converted fields. A valid saved card was preferred
   unchanged by the effective-plan resolver, so missing guidance persisted.
6. React already renders all four fields. The sled's dose-embedded stop rule
   survives source recovery, explaining why it shows a stop cue while the
   adjacent thruster and lateral bound show only execution cues.

## Repair and measured coverage

Authoritative rendering and no-text fallback now share conservative,
movement-specific coaching profiles and preserve authored bank cues/stops.
Progress names a conditional improvement in execution at the existing dose;
it never authorises extra load, reps, duration or shorter rest. Taper, the
final fortnight, high fatigue, active injury/restrictions, significant cut
risk, support-only assignments and microdoses get no new Progress instruction.
Unknown movements and rehabilitation do not get invented progression.
Easier changes movement execution or reduces load/force; a stop criterion
still means end the work.

The shared effective-plan resolver also fills missing coaching fields on
already saved generated cards, matched to the selected exercise on its D-day.
It preserves existing coaching, dose fields, calendar, identity and the
stored object. Custom plans are excluded. No production rows were changed.

Authored coaching is authoritative field by field. Structured bank cues,
Easier, Progress and Stop fields survive selection and take precedence over
movement profiles; labelled bank notes are routed to those same fields.
Profiles only fill missing fields. Bank cues are not truncated to two
sentences, and existing saved coach instructions are never overwritten.
The context guards still prevent adding Progress in maintenance/taper.

Same-day duplicate exercise recovery uses the full deterministic session
identity, a unique exact session title, or a unique role key in the session
ID. There is no last-write-wins day/name map. Ambiguous legacy duplicates
keep their existing coaching without borrowing from another appointment.
Source-text fallback and validation scope repeated names to the session.
React's day/name source overrides fail closed on duplicate names, retaining
each card's own structured prescription and stop guidance.

For the **same latest saved athlete and exact selected programme**, counting
all 27 selected S&C exercises (three are labelled `skill` by the converter):

| Final physical exercise cards | Saved before | Read recovery / fixed fallback |
| --- | ---: | ---: |
| Coaching cues | 27 | 27 |
| Progress | 0 | 18 |
| Easier | 0 | 27 |
| Stop rules | 4 | 27 |

The fixed fallback with and without source text has the same coaching coverage.
Taper Progress is zero. Comparing the old-source and fixed-source fallback
shows **zero changes** to sets, reps, rounds, duration, work, rest, distance,
effort or load. The actual saved payload recovered through the API resolver
was also rendered through React: 27 cues, 18 Progress, 27 Easier, 27 stops.

## Release gate

`tests/test_exercise_coaching_release.py` runs the recorded model response
through the real finalizer/reconciliation, conversion, pre-release retry
decision, fake persistence, effective API resolver and expanded React
`ExerciseRow` rendering. It compares every applicable coaching instruction
and every dose field on the final physical exercise rows.

It covers successful conversion, rejected conversion with #2878's fast
fallback (exactly two provider calls, no repeat/repair), and no inline conversion.
Separate mutations remove each of the four coaching fields and must be
rejected. No-text fallback checks include the affected boxer, novice,
high-frequency athlete, fatigue/injury, short camp and fight week.
Saved-card recovery verifies dose identity and read-only behaviour.

`tests/test_exercise_coaching_context.py` additionally checks authored bank
fields/notes, selection metadata, existing coach precedence, same-role-key
duplicates with different session indices, reversed role/session order,
converter session titles, name-only cards, ambiguous duplicates, distinct
source doses and stop guidance, and expanded React rows that must not contain
the other session's cues. Web guardrail tests cover duplicated source overrides.

The `coaching-release` job in Web Build installs both runtimes and executes
this gate for PRs and Main. Backend-only pytest runs skip only the three
React subprocess cases when frontend dependencies are absent; the dedicated
job requires those dependencies and runs them.

Final local verification: **563 Python tests passed** across release,
effective-plan, production programme, authority, representative replay,
source-dose, faithfulness, fallback, Stage 2 pipeline/validator/conversion and
persistence suites; **105 React tests passed**. TypeScript typecheck, Ruff and
diff checks passed. No live model calls, deployment or production writes were
performed.

Follow-up verification for authored precedence and same-day duplicates:
578 broader Python tests passed, then all 16 focused coaching-context cases
passed after adding the unknown-movement taper guard; 121 React tests passed.
Typecheck, targeted ESLint, Ruff and diff checks passed.
