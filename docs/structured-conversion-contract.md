# Structured conversion: ownership and reliability

Audited against Supabase and `Main` on 23 October 2026.

The converter structures an approved programme and may complete missing rest,
effort and one execution cue for an existing physical exercise. It cannot select
exercises or change explicit prescriptions. The executable instruction lives
in `api/structured_plan_generation.py::_STRUCTURED_PLAN_RULES`; keep that one
contract short instead of accumulating competing prompt patches.

| Owner | Responsibility |
| --- | --- |
| Deterministic planner | Membership, calendar, weekly development, dose bounds, locked drills and safety constraints |
| Finalizer | Exact working dose inside those bounds; missing rest/effort; How, Cue, Easier, authorised Progress and Stop |
| Converter | JSON shape and faithful extraction; complete only missing rest, effort and one execution cue using athlete/session context; preserve authored Progress |
| Source projection | Recover missing dose, rest, How, Cue and Stop from a provable day/session/exercise occurrence; preserve source Easier and Progress |
| Validation | Schema, membership, changed doses, coverage and safety gates remain active |
| Effective-plan reader | Apply the same source recovery to saved cards without rewriting database rows or athlete overrides |
| Renderer | Show How and rest, including during logging without a demo; retain exercise Progress, stop criteria and explicit deload instructions |

The conversion prompt contains the approved text once. Open-plan context carries
only plan type, training weekdays and week count, rather than another full copy
of the programme, tactical library and finalizer render rules. Optional context
is budgeted as complete JSON fields. The three permitted gap-filling fields use
conservative athlete/session context within all injury, fatigue, taper and dose
constraints. Supplied rest, effort and cues must be preserved. Contact/sparring
prescriptions and locked mental drills are excluded from gap-filling; unsupported
adjustments, volume, load, dates and exercises cannot be invented.

Source recovery requires an exact exercise within its own day and session. A
renamed session may match a unique exercise on that day. Repeated ambiguous
exercises never borrow another session's rest or coaching. Dated camps use
countdowns; renewable plans use week, weekday and session identity. Existing
measured values are not overwritten to hide validation failures. Numeric rest
ranges remain readable as `rest_note` rather than disappearing.

`progression_rule` remains active in authoring, conversion, faithfulness checks
and display. Source projection restores a dropped Progress instruction instead
of removing the feature to avoid conversion failures. Existing progression
validation, taper restrictions and deload display behaviour remain unchanged;
stop instructions stored in that field still surface as safety criteria.

## Audit evidence

Read-only Supabase queries found 9 conversion fallbacks among 56 October plan
rows. The latest failed conversion named missing exercise progression fields;
other successful conversions reported missing source rest. Generation jobs also
show separate finalizer timeouts and stalled runs; those are not all conversion
failures.

Recorded average Stage 2 input grew from 40,223 tokens in the week starting
21 September to 61,303 in the week starting 12 October. These are recorded job
totals, not isolated conversion usage; failed jobs frequently lack token data.

A saved-plan replay reduced its conversion prompt from 65,698 to 25,272
characters (61.5%) while retaining gap-filling and exercise Progress. Source recovery restored five missing rest fields while
retaining all 58 blocks. This is an input-size and deterministic-recovery
measurement, not a measured reduction in live API cost or a success-rate claim.

Regression tests cover technical blocks, repeated same-day exercises, renamed
sessions, week-specific open-plan rest, safety instructions, athlete edits,
gap-filling, authored Progress and prompt budgets. Offline model-boundary tests
cover Box Jump and Goblet Squat: missing rest, intent/RPE and cues survive
conversion while explicit sets/rest/effort cannot be changed. Validate provider latency and actual
token usage after release using existing `stage2_model_calls` telemetry; do not
repair historical prescriptions or rerun paid generations automatically.

## Verification

- 497 focused Python tests passed, followed by all 17 source-projection and
  completion tests after adding separate Box Jump and Goblet Squat cases.
  All 121 focused frontend tests passed with Progress support restored.
- Production build, TypeScript, Python import checks and lint passed. Frontend
  lint reports existing warnings.
- Playwright exercised the real exercise sheet in a temporary local fixture
  at 390px and 1280px: open, inspect prescription, close, start session, reopen.
  How, rest and safety criteria remained available; Progress appeared in preview
  and kept its existing logging behaviour;
  no browser errors or sheet overflow were observed. The fixture was removed
  before the production build. Browser plugin was unavailable.
- The broader run passed 2,252 Python tests before expectation updates. A
  separate unchanged-Main checkout reproduced 17 existing backend failures,
  including one already-stale stop-rule prompt assertion replaced here. The
  full frontend run exposed three existing compact-summary assertion failures,
  also reproduced on unchanged Main. Remaining planner failures are outside
  the conversion changes; this is not a claim that the entire suite is green.
- No live model call, deployment or Supabase write was performed.
