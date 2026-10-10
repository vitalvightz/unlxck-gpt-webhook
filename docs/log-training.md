# Log Training

Implements the first delivery from investigation PR #2816. Plan offers a single Log Training action row opening a modal
form: activity, whole minutes (1–600, matching the existing session-duration
boundary), and reported Easy / Moderate / Hard effort. Saving requires neither
an active plan nor a prescribed session. The existing History page shows completed Unlxck sessions and manual entries,
with edits/deletion only for manual work. Plan shows a brief save confirmation,
with no session feed. Manual edit/delete controls are a small pencil and adjacent
Delete action. Those idempotent API operations retry transient gateway/network
failures using the existing bounded retry helper; permanent errors retain the
entry and leave the form/action available for retry.
An optional training-date disclosure allows logging yesterday or earlier work;
the default form still shows only the three required fields.
The existing History session tab reads the same service, retaining prescribed
RPE, pain, notes, reasons and skipped records; skipped work is never adaptive load.

## Storage and history

Apply `20261010184612_add_external_training_sessions.sql` before releasing the API
and frontend. It adds one table with an athlete FK, owner SELECT policy, validated
fields, and an athlete-scoped unique request key. Authenticated browser clients
cannot write directly; the API's existing profile/consent gates authorize writes,
and service-role queries explicitly scope every read/update/delete to the actor.
Reading prior history and deleting entries remain available after consent withdrawal.
The runtime schema checker includes the table, RLS and indexes.

When no date is supplied, the server assigns the athlete-local training day using
the existing 03:00 rollover, including DST handling. An explicit ISO date may
select that day or earlier; future training days are rejected against the same
local boundary. Edits cannot change its recorded date or owner. Atomic
conflict-ignore insertion plus an immutable original-request fingerprint makes
retries safe across date changes and subsequent edits. Deleted rows retain a
tombstone, so a late retry cannot recreate them. There is no plan FK: deleting or
regenerating a plan does not delete manual history. Account deletion still cascades.
Omitting the date retains the original three-field request fingerprint, preserving
retries from earlier clients. Explicit dates are part of the retry identity.
Backdating uses the existing date column and requires no additional migration.

`training_history` merges terminal `session_completions` with live
manual entries. Exercise logs and sparring detail logs are detail records, never
additional session-level workload. Planned, started and skipped work are excluded.
The History tab explicitly requests skipped records for display only.
Manual names/date matches are distinct occurrences; no guessed deduplication
across separately reported workouts. The API returns the most recent 30 rows
(up to 200 when requested). Existing prescribed-completion contracts are unchanged.

## Both adaptive paths

- **Today:** the existing readiness context reads the shared history; its existing
  repeated-hard-work rules accept validated qualitative Hard as demanding work.
  The original prescribed RPE/pain rules remain unchanged. Today re-evaluates the
  current check-in while recent manual work exists (including deletion tombstones),
  without rewriting it, so an earlier stored decision
  cannot hide work logged later or survive deletion of that work. Mutations invalidate
  the existing Today cache; failed history reads use its established fail-safe.
- **Generation:** the existing authenticated generation annotation loads the same
  shared history. The conditioning step calls the same pure Today decision engine.
  With repeated hard work plus poor readiness recorded for the current training
  day, it uses the existing moderate-fatigue conditioning selection penalties in
  the first active phase. It never lowers an existing higher fatigue setting.
  Later phases, phase lengths, strength, saved plans and coach sessions are unchanged.

Both paths retain actual total minutes, Hard minutes, effort and activity for the
existing recent-session window (most recent three completed sessions, five local
days). Hard never becomes RPE 8 or a head-contact measurement. This release does
not invent a duration-weighted fatigue score: the existing rule uses demanding
session counts, and durations remain explicit evidence. One 60-minute Hard
Sparring session with good readiness is considered without automatically cancelling
training. Generation does not infer current readiness from a stale check-in.

Manual logging is historical evidence only. It cannot award prescribed-session
XP, create rehab exposure evidence, progress stages, grant injury clearance or
change the existing contact-permission logic. Underlying conditioning injury and
restriction filters still apply.

## Verification

`tests/test_external_training.py` covers no-plan/rest-day/multiple-session logging,
retries, edits/deletion, local dates/DST, invalid fields, ownership/consent, plan
independence, cache invalidation, both adaptive inputs and decisions, stale readiness,
failed history, planned-work exclusion, and unchanged rehab/XP evidence. Store
query tests verify privileged-client scoping. Existing prescribed completion,
Today/readiness, generation, rehab and XP tests provide regression coverage.
Backdated 60-minute Hard Sparring reaches both adaptive paths on its reported day;
future/invalid dates, local rollover, retry conflicts and legacy fingerprints are tested.

`web/e2e/log-training.spec.ts` exercises the actual Plan UI and API adapter at
390px and 1280px, with isolated API responses: log, navigation to History, reload, edit, delete, retry
identity, field count, accessibility and overflow. It uses no live athlete data.
The optional-date mobile flow verifies logging yesterday, reloading and editing
without moving the recorded training day.

The migration also runs on isolated PostgreSQL via PGlite:

```powershell
# Install only in a temporary QA directory, not in application dependencies.
npm install --prefix <temporary-directory> @electric-sql/pglite@0.5.8
$env:PGLITE_ROOT = '<temporary-directory>'
node tests/sql/external_training_sessions.test.mjs
```

This verifies actual SQL constraints, RLS, forbidden browser writes, concurrent
request keys, plan independence and edit/delete retry safety. Production migration
application is complete on `unlxckpdf`, with live catalog verification of constraints,
RLS, grants and migration history. Live API/PostgREST verification remains a
deployment follow-up. There are no recurring sessions, custom plans or library changes.
