# Sparring follow-up across training sources

Every sparring session gets the same short post-sparring follow-up
(`SparringLogPrompt`), whether it was run on the round timer, prescribed by a
plan, or logged manually, with or without a plan. It asks for actual
intensity, rounds, head contact, whether the athlete was rocked or dropped, and
optional notes.

## Manual sparring

Saving a new **Sparring** session through `LogTraining` (Today, Plans, plan
detail, History → Repeat) offers the follow-up straight away. Editing an
existing session does not.

- The manual effort pre-selects intensity (Easy → Light, Moderate → Medium,
  Hard → Hard). Rounds start unset and must be chosen. Head contact is never
  inferred.
- **Skip** keeps the basic training log. The follow-up is optional.
- The report is sent with `source: "free"`, no plan fields, and
  `external_session_id` set to the manual session.

## Data integrity

`external_training_sessions` stays the record of the training occurrence and
its workload. The linked `sparring_logs` row only adds contact and safety
evidence. Workload, history and readiness do not read `sparring_logs`, so the
link cannot double-count load.

Migration `20261019014437_link_sparring_detail_to_manual_sessions.sql`:

- `sparring_logs.external_session_id`: a composite foreign key with
  `athlete_id`, so the link cannot cross athletes. It is unique, so one manual
  session has at most one detail row. A hard delete of the session unlinks the
  detail but keeps it.
- `sparring_log_requests`: the append-only history of every accepted
  `(athlete_id, client_request_id)`. It has row-level security on and is
  backend-only. A retry of any accepted request is answered from it and never
  writes again, even after later corrections. Keeping only the latest request
  id would let a delayed retry of report A overwrite correction B.
- A transaction-scoped advisory lock on the athlete and request id queues
  simultaneous copies of one request, so exactly one writes.
- `sparring_logs.detail_revision`: rises with each new set of answers from one
  report. A correction applies only when its revision is newer, so an older
  request that first arrives late cannot overwrite a newer one. A late
  "rocked" still counts, because safety evidence is never dropped for arriving
  out of order.
- `sparring_logs.admin_review_id`: the review opened by a rocked report, so a
  retry can return it without opening another.
- `record_sparring_log` checks, in the same transaction, that the linked
  session is the athlete's own, live, and `sparring`. It takes the training day
  from that session. `rocked` can never go from true back to false, and a
  review is opened only on the change to rocked.

Separate manual sparring sessions on the same day stay separate rows. The
client generates a new request id and revision whenever an answer changes, so a
corrected "Yes, rocked" is never swallowed by an earlier request that landed
without its response.

## Head-impact safety

A rocked/dropped report still shows the immediate no-contact message and
always opens an admin review. The notice is also authoritative on Today's
session card. For the rest of the day it locks the contact-rounds timer,
contact leading the day, and starting or finishing a contact-only session, and
it removes sparring rounds from a mixed session's timer. Non-contact blocks and
sessions stay available. Today now also reads that day's sparring reports.
A rocked report sets `primary_safety_notice` to `head_impact_no_contact` for
the rest of that athlete-local day, with or without a plan. That notice
outranks skin notices and replaces a green or not-checked-in lead, so no
positive message stays in the lead. A modify/pull-back/stop decision still
leads, because it is already restrictive.

The readiness recommendation, decision tier and prescribed-session algorithms
are unchanged. If the sparring read fails, Today renders exactly as it did
before this change; the failure never adds clearance.

## Rollout

Apply the migration **before deploying the backend**. The runtime schema gate
requires the new columns, the request-history table and its keys, so the live
schema-check job fails until the migration is applied. The migration is
repeatable and does not change existing rows. No environment changes are
needed.

## Verification

- Schema: `PGLITE_ROOT=<isolated pglite install> node tests/sql/sparring_detail_link.test.mjs`.
- Races on real PostgreSQL (also in the `rehab-lock-concurrency` CI job):
  `REHAB_TEST_DATABASE_URL=<local disposable cluster> python -m pytest tests/test_sparring_log_postgres.py -q`.
- API: `python -m pytest tests/test_api_sparring_log.py -q`.
- Web: `npm run typecheck`, `npm run lint`, `npm run test:unit`, `npm run build`,
  then `npx playwright test e2e/starting-path.spec.ts e2e/log-training.spec.ts`.

## Known limitations

- A sparring block run on the round timer and also logged manually produces
  two reports. The timer does not create a training record, so there is
  nothing to link it to.
- Changing a manual session's activity away from Sparring keeps its existing
  detail, which is safety evidence.
- The head-impact notice covers the athlete-local day of the report only.
  Next-day guidance is PR 3's readiness work.
