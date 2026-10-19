# Training XP and notification opt-in

The first successful new manual log or done/modified prescribed session offers
**UNLXCK your next move.** on push-capable devices with default permission.
The native dialog blurs the background, traps focus and restores scroll/focus.
Its red CTA has two light sweeps; reduced motion disables them. Permission is
requested only on the Enable click using preloaded subscription prerequisites.
Session takeaway and sparring/safety dialogs finish first. Unsupported, blocked,
already subscribed, server-disabled and account-paused devices are excluded.
The offer is shown once per athlete/browser device; Settings remains available.

## Rewards

| Action | XP | Scope |
| --- | ---: | --- |
| Manual training recorded | 25 | Once per training day; shares recording credit with prescribed training |
| First session recorded | 50 | Once per athlete, either source |
| First exercise result recorded | 25 | Once; positive saved measurements, including confirmed numeric prescriptions |
| 10 / 25 / 50 / 100 training days | 100 / 150 / 250 / 500 | Each once; distinct days, either source |
| Approved YouTube exercise contribution | 100 | Original creator; once per contribution and per video |
| First manual plan published | 100 | Existing `first_plan_ready`; shared with generated plans |

Prescribed `training_logged` and `planned_session_completed` earning paths and
historical awards remain. `manual_training_logged` is a separate source action
because `training_logged` already requires a prescribed completion in the
database. The manual daily credit is suppressed if prescribed recording XP was
already earned that day; prescribed recording credit is suppressed if the
manual reward landed first. The separate prescribed completion award remains.

Milestones count owned live manual occurrences and directly reported done or
modified prescribed occurrences. Future work, skipped sessions, sibling day
credit and unverified legacy completions do not count. The athlete's existing
03:00 training-day rollover is used. Multiple sessions on a day count as one
milestone day. Existing eligible history can establish a one-time milestone on
the next qualifying save; there is no daily-history backfill. Banked XP is never
removed by later edits/deletion, and idempotency prevents retry/delete farming.
Name-only exercises, rest-only measurements and zero-work entries do not earn.
Exercise recording still creates no workload, rehab exposure or contact clearance.

Community rewards require a currently published, consenting contribution with
verified and confirmed available YouTube media. SQL derives the creator, exercise
and canonical video identity. Private demos, pending/rejected/withdrawn entries
cannot earn. Reapproval/revisions cannot earn again for the same contribution;
duplicate videos (including alternate clips/accounts) cannot earn again.

New milestone/approval results produce one combined progress notification,
including any level-up from the same reconciliation. Copy uses **UNLXCKED**.
Existing account preferences, quiet hours, event caps, spacing and delivery
deduplication apply. Routine daily logs have no new milestone push. XP and push
failures never turn a successful product save or approval into a failed action.
Later qualifying saves/retries reconcile missing training awards. Approval XP
can be retried by calling its backend-only reconciliation RPC with the revision
ID; no notification is emitted again for already awarded XP.

## Rollout and verification

1. Verify existing migrations through `20261019170000_add_manual_exercise_entries.sql`
   are applied in the target database.
2. Review/apply `20261019200000_add_tracking_and_contribution_xp.sql` before backend
   rollout. Runtime schema requirements include both reconciliation RPCs and the
   new source guard. Only `service_role` can execute them. No new browser grants,
   RLS assumptions or environment variables are introduced.
3. Deploy backend and frontend. Verify push server settings/VAPID already work;
   this change reuses them and does not provision delivery credentials.
4. Log a first manual session: 25 + 50 XP; add measured exercise actuals: 25 XP.
   Retry and log another same-day session: no additional manual daily reward.
   Publish a manual plan: the existing first-plan milestone pays once.
5. Approve a verified public YouTube contribution: its creator earns 100 XP.
   Reapproval and duplicate-video submissions must award zero.

The migration is prepared and tested locally, **not applied to a hosted database**.
Use a disposable localhost PostgreSQL cluster for `tests/test_tracking_xp_postgres.py`;
never point the test DSN at a hosted database. Tests cover migration replay,
ownership, daily sharing, 03:00 eligibility, source provenance, measurement
requirements, thresholds, browser-role denial and concurrent retries.
Frontend checks cover mobile/desktop blur, focus, dismissal, subscription saving,
no overflow, accessibility and reduced motion. Real iPhone/PWA permission and
live push delivery still need a deployed-device check.
