# Prescribed completion provenance

Fixes F1 from unmerged audit PR #2920. Previously one Today submission copied
its RPE, pain, notes and outcome to every scheduled sibling. History/readiness
then counted those rows as independent workouts; later sibling submissions
could replace the original actuals.

## Representation

The existing `session_completions.id` remains the occurrence identity, with the
existing unique `(athlete_id, session_id, training_day)` key. One nullable,
server-owned column distinguishes its meaning:

| `completion_origin` | Meaning | Consumers |
| --- | --- | --- |
| `reported` | Athlete directly submitted this session's outcome | Existing completion/progress consumers; workload/contact only for done or modified |
| `day_credit` | Scheduled component credited by the existing one-day submission | Day/week progress and streak calculations; never independent workload, contact or rehab evidence |
| NULL | Historical row whose execution provenance was not recorded | Retained, visibly labelled legacy History/progress; no inferred independent workload/contact |

A submitted workout can contain scheduled support components. The report owns
its actuals; the components' credit is not another physical execution. Two
different prescribed sessions explicitly submitted on the same day retain two
row IDs and independent actuals. Repeating the same session/day corrects that
same occurrence, as before; this PR does not add multiple executions of the
same prescribed ID/day. Separately logged external training is unchanged.

## Persistence and safety

`today_service.upsert_session_completion` keeps the day-level credit loop, but
only the submitted row receives `reported` provenance and actuals. Credit rows
receive progress status/timestamps with empty RPE, pain and notes, and no
clinical snapshot, rehab outcome or response context. The database constraint
also forbids clinical/actual evidence on credit rows.

Already-reported and legacy sibling rows are left untouched. The store uses
insert-if-absent followed by an owner/plan/session/day/provenance-conditional
credit update. If an independent report arrives between those statements,
the conditional update cannot change it. A stale service read cannot authorize
an unconditional sibling overwrite. Retrying after partial fan-out fills the
missing progress credit without duplicating execution IDs.

Explicitly confirming a previous credit row retains its DB ID but treats its
execution state as new for timestamps, safety checks and rehab context
initialization. A progress timestamp or done flag cannot bypass accepted/frozen
prescription, injury or neurological safeguards. Existing clinical fields are
never repurposed as execution bookkeeping.

## Read models and progression

Training History excludes credit rows. Readiness and sparring history require
explicit reported provenance before counting a prescribed workout or deriving
completed-contact evidence from its prescription. A hard-sparring sibling
credited by an unrelated Conditioning submission cannot become confirmed
completed contact. Manual Hard remains qualitative effort, not head contact.

The five-day window, three-session cap, demanding thresholds, contact thresholds
and medical/rehab policies are unchanged. Week-progress, streak and XP owners
continue reading the original completion/progress table and status semantics;
there is no second ledger or reward implementation. Existing daily reward
limits/idempotency remain authoritative. If the athlete explicitly reports a
different sibling outcome, that independent outcome is preserved rather than
being rewritten by a later day-level submission.

## Legacy and rollout

Apply `20261018114339_add_completion_origin.sql` before deploying the API; the
runtime schema gate requires the column. It adds no table, index, function,
grant or RLS policy. There is no default or historical backfill. Old binaries
still produce unverified rows; roll API workers forward together before relying
on the new write semantics, since an old binary still has the old sibling writer.

Historical rows are not regrouped using dates, titles, matching RPEs or
timestamps. Their stored actuals and progress are preserved. Recent unverified
completed rows use the existing incomplete-history floor in Today (five dates)
and the existing unavailable-history contact-risk flag (seven dates). Generation
does not present their combined workload as verified. This can temporarily
make recommendations more conservative during rollout; it does not create a new
medical restriction or grant contact clearance.

Explicit re-submission confirms only the submitted occurrence. Legacy sibling
rows, including old in-progress records, are not automatically reclassified or
overwritten; they can require explicit confirmation. Legacy records remain
visible in History with an unverified label and are excluded from its verified
workout totals. There is no automatic historical repair in this PR.

## Verification

- `tests/test_prescribed_workload_provenance.py`: F1 regression reproductions
  converted to expected invariants, separate app/manual occurrences, modified
  and non-completed outcomes, optional components, contact, retries, unknown
  legacy data, current safety holds, local days and retro logging, route XP/streaks.
- `tests/test_store_completion_origin.py`: exact conditional persistence calls.
- Existing readiness/sparring fixtures now explicitly mark independently
  reported evidence; their decision assertions are unchanged.
- `tests/test_api_rehab_completion_flow.py`: credit cannot acquire the report's
  rehab response ownership; existing clinical journeys remain exercised.
- `tests/sql/completion_origin.test.mjs`: isolated PGlite Postgres executes the
  migration twice, checks NULL legacy retention, unique identity, interleaved
  credit/report statements, actual/clinical constraints and inherited access.
  Run with `PGLITE_ROOT` pointing to an isolated `@electric-sql/pglite` install;
  no application dependency or production database is needed.
- History component regression verifies legacy visibility and honest totals.

The audit report and unrelated audit characterizations are not carried over.
F2 (source-neutral Today refresh), the workload cap policy, explicit sparring
detail integration and future scheduling remain outside this fix.

Local results: workload/readiness/rehab selection **232 passed**; wider
completion/progress/XP/schema selection **299 passed**; clinical/frozen/intake
and custom-plan selection **243 passed**. After the final boundary adjustment,
the provenance plus Today-boundary run is **50 passed** (including all 21 new
provenance cases). The separate two store tests and isolated SQL script pass.
History/history-shortcut/habit frontend selection: **18 passed**. TypeScript,
changed-file ESLint/Ruff, generated API contract check and production build pass.
The build uses command-local `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`;
no environment file was changed. Counts overlap and are not a combined suite.

No final local test failures were observed. Existing Starlette/Sentry
deprecation warnings remain. Full remote CI, live database deployment and
multi-connection server-Postgres concurrency were not run; the SQL regression
executes the relevant race interleaving in isolated PGlite. No production data
was read or changed, and no migration was applied remotely.
