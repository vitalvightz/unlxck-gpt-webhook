# Active-plan beta account reconciliation

`profiles.active_plan_id` is the sole runtime authority. Normal application
reads must never repair it or select a saved plan. Reconciliation is an audited
support operation, followed by the existing `set_active_plan(...)` write path.

## Evidence order

For an account with a null pointer, inspect evidence in this order:

1. An explicit activation record retained in backend or support audit history.
2. The one plan that legacy Today or Overview demonstrably served to the athlete.
3. The plan on the newest valid `done` or `modified` session completions.
4. The plan on recent Today check-ins.
5. A sole eligible saved plan, only when every available signal agrees and no
   other eligible plan makes the choice ambiguous.

At each step, require one plan to win unambiguously. Confirm that it belongs to
the athlete and is still eligible under `get_plan_activation_state(...)`. Stop
without changing data if evidence conflicts, is missing, or points to an
archived, ended, unavailable, or foreign plan.

## Safe repair procedure

1. Record the athlete id, candidate plan id, evidence source, operator and time
   in the support case.
2. Preview the candidate and verify ownership and activation state.
3. Use `set_active_plan(...)`; do not update `profiles` directly. This preserves
   validation and the existing overlap pause/replace decision.
4. Re-read `/api/plans/active`, Today and Progress. Weekly progress and adherence
   then reconcile from completion history for that exact plan.
5. Leave ambiguous accounts with no active plan. Ask the athlete to activate a
   saved plan, or escalate for manual review.

This process never deletes completion rows and never treats recency alone as
proof of activation.
## Adherence streak repair

`session_completions` is the authoritative training history. The persisted
`athlete_streaks.adherence_*` columns are a derived view. A terminal completion
(`done`, `modified`, or `skipped`) now triggers `reconcile_adherence_streak`
independently of XP eligibility. Activating a plan also runs the same
reconciliation, so re-activating the existing active plan is the supported,
deterministic repair path for stale rows after deployment. It replays the active
plan's prescribed days against completion history; it does not edit counters or
award XP directly.

For a deployment-wide repair, invoke that same service reconciliation once for
each athlete with an active plan (for example from an authenticated maintenance
job). Do not update `athlete_streaks` counters in SQL: doing so bypasses required
multi-session, skipped-day, current-day-neutral, and active-plan rules.
