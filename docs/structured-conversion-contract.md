# Structured conversion: ownership and reliability

Audited against Supabase and `Main` on 23 October 2026.

The converter extracts an approved programme. It does not select exercises,
author coaching or prescribe a second workout. The executable instruction lives
in `api/structured_plan_generation.py::_STRUCTURED_PLAN_RULES`; keep that one
contract short instead of accumulating competing prompt patches.

| Owner | Responsibility |
| --- | --- |
| Deterministic planner | Membership, calendar, weekly development, dose bounds, locked drills and safety constraints |
| Finalizer | Exact working dose inside those bounds; missing rest/effort; How, Cue, Easier and Stop |
| Converter | JSON shape and faithful extraction; no additional coaching or exercise Progress lines |
| Source projection | Recover missing dose, rest, How, Cue and Stop from a provable day/session/exercise occurrence; preserve source Easier |
| Validation | Schema, membership, changed doses, coverage and safety gates remain active |
| Effective-plan reader | Apply the same source recovery to saved cards without rewriting database rows or athlete overrides |
| Renderer | Show How and rest, including during logging without a demo; omit exercise Progress while retaining legacy stop criteria and explicit deload instructions |

The conversion prompt contains the approved text once. Open-plan context carries
only plan type, training weekdays and week count, rather than another full copy
of the programme, tactical library and finalizer render rules. Optional context
is budgeted as complete JSON fields. Missing unsupported data stays missing.

Source recovery requires an exact exercise within its own day and session. A
renamed session may match a unique exercise on that day. Repeated ambiguous
exercises never borrow another session's rest or coaching. Dated camps use
countdowns; renewable plans use week, weekday and session identity. Existing
measured values are not overwritten to hide validation failures. Numeric rest
ranges remain readable as `rest_note` rather than disappearing.

Historical `progression_rule` remains schema-compatible so existing records and
stop instructions stored in that field still load. It is no longer a required
faithfulness field or a visible exercise Progress line. Weekly development and
rehab stage progression retain their existing owners.

## Audit evidence

Read-only Supabase queries found 9 conversion fallbacks among 56 October plan
rows. The latest failed conversion named missing exercise progression fields;
other successful conversions reported missing source rest. Generation jobs also
show separate finalizer timeouts and stalled runs; those are not all conversion
failures.

Recorded average Stage 2 input grew from 40,223 tokens in the week starting
21 September to 61,303 in the week starting 12 October. These are recorded job
totals, not isolated conversion usage; failed jobs frequently lack token data.

A saved-plan replay reduced its conversion prompt from 65,698 to 24,413
characters (63%). Source recovery restored five missing rest fields while
retaining all 58 blocks. This is an input-size and deterministic-recovery
measurement, not a measured reduction in live API cost or a success-rate claim.

Regression tests cover technical blocks, repeated same-day exercises, renamed
sessions, week-specific open-plan rest, safety instructions, athlete edits,
source-only extraction and prompt budgets. Validate provider latency and actual
token usage after release using existing `stage2_model_calls` telemetry; do not
repair historical prescriptions or rerun paid generations automatically.

## Verification

- 394 focused Python tests and 121 focused frontend tests passed.
- Production build, TypeScript, Python import checks and lint passed. Frontend
  lint reports existing warnings.
- Playwright exercised the real exercise sheet in a temporary local fixture
  at 390px and 1280px: open, inspect prescription, close, start session, reopen.
  How, rest and safety criteria remained available; Progress stayed absent;
  no browser errors or sheet overflow were observed. The fixture was removed
  before the production build. Browser plugin was unavailable.
- The broader run passed 2,252 Python tests before expectation updates. A
  separate unchanged-Main checkout reproduced 17 existing backend failures,
  including one already-stale stop-rule prompt assertion replaced here. The
  full frontend run exposed three existing compact-summary assertion failures,
  also reproduced on unchanged Main. Remaining planner failures are outside
  the conversion changes; this is not a claim that the entire suite is green.
- No live model call, deployment or Supabase write was performed.
