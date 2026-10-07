# Today performance audit — 7 October 2026

## Finding

Today performs too much work for a small state change. The strongest evidence
is repeated large plan transfers and serial backend work, rather than a large
or consistently slow database. This is a contributor to latency, not a claim
that the reported five-second delay has been fully reproduced or resolved.

This audit starts from `Main` at `c40407f6`, including the merged timer handoff
and overlay fixes from #2771. Supabase project `unlxckpdf` was inspected through
the Supabase plugin using read-only SQL, aggregate logs and performance advisors.
No athlete records, production schema, RLS policies or environment files were changed.

## Measured evidence

| Measurement | Observation | Meaning |
| --- | --- | --- |
| Saved plan JSON | Mean 1,423,209 bytes; maximum 2,032,308 bytes across 62 plans | A full plan read is expensive even when only its ID is needed. |
| Largest plan fields | Mean planning brief 617,125 bytes; Stage-2 payload 458,413 bytes; structured plan 51,496 bytes | Planner/audit data dominates the operational calendar. |
| New training projection | Mean 738,065 bytes; maximum 1,096,516 bytes | Roughly 48% less JSON per execution read; deterministic fallback inputs remain present. |
| Ownership-only JSON | About 100 bytes | Logs and pending rehab responses need an ownership check, not the planner payload. |
| Full owner-scoped plan SQL | 25,365 cumulative calls; mean 40.70 ms; maximum 7,595.14 ms | Common full-row query with occasional severe spikes. These are cumulative statement statistics, not a per-day count. |
| Supabase plan GETs, preceding 24-hour log window | 1,721 requests; p50 101 ms; p95 348 ms; maximum 2,798 ms | Several sequential reads can add substantial latency before application computation. |
| Supabase profile GETs, same log window | 1,520 requests; p50 19 ms; p95 221 ms; maximum 10,871 ms | Individual outliers remain possible and need correlation with API request IDs. |
| Today table estimates | 43 check-ins, 39 completions, 15 exercise logs | Table size alone does not explain a routine five-second operation. |
| Warm SQL serialization sample | Full newest plan: 33.801 ms; identity-only: 0.266 ms | Trimming fields avoids JSON/TOAST work. These single samples exclude network and API time and are not an end-to-end benchmark. |
| Connection snapshot | Six idle PostgREST connections; no client waiting on a database lock | No saturation visible during inspection; this does not rule out historical incidents. |

Edge log durations above are Supabase origin timings. They exclude browser-to-API
latency, API-to-Supabase network transfer, Python JSON decoding, readiness and
clinical computation, and the subsequent frontend refresh. Missing content-length
headers were not treated as useful payload measurements; sizes came from SQL.

## Request paths inspected

**Today load:** authentication/profile dependency → active-plan pointer → owned
plan → intake injury synchronization → check-in/history → schedule/completions
→ injuries/episode observations/rehab evidence → command view. Diagnostic fixtures
before this change called 11 read methods for a healthy camp and 19 with one
intake injury. This is fixture evidence, not a measured production request count.
More injuries can add legitimate evidence reads.

**Client presentation:** `useTodayCommand` also fetched full Plan Detail after
every refresh. Plan Detail repeats plan and injury reads, reconciliation and
projection work. Overlapping refreshes could request the same presentation twice.
The live command already owns the current prescription and training gates.

**Exercise logs / pending rehab:** both fetched a full owned plan to establish
that it existed. The exercise-log write still needs the execution calendar and
fallback; the list and pending-response read need only ownership.

**Completion save:** the route persists the authoritative completion, then awaits
notification invalidation, training streak reconciliation, adherence reconciliation,
XP eligibility/awards, week progress and rehab response context handling before
responding. The streak and XP helpers independently resolve the active plan and
read completion history. Optional derived work extends the visible save time.
Rehab context persistence remains part of the authoritative completion flow.

**Retries:** backend transient store reads can take three attempts with a default
20-second read timeout. Frontend transient retries add 1.5- and 3-second waits.
Those budgets explain how a transient failure can become a long wait; this audit
did not attribute the user's particular five-second save to a retry trace.

**Project-wide traffic:** the log window also included roughly 12,852 exercise-media
updates, 7,826 notification-evaluation RPCs and over 5,000 calls to each worker
queue/recovery RPC. These are aggregate project counts, not Today requests. Worker
frequency and media verification deserve separate review; they were not changed.

## Changes implemented

1. Add owner-scoped identity and training projections to the store. Today builds,
   readiness/session writes and exercise-log writes use the training projection;
   exercise-log lists and pending rehab use identity only. Both predicates
   (`id`, `athlete_id`), existing error handling and retry behavior remain intact.
2. Share successful latest-intake and exact history-window reads within one Today
   build. Copies prevent one consumer changing another's rows. Failed reads are
   retried by the next safety consumer; writes invalidate the shared history.
   No live readiness result is reused across requests. Injury updates reuse the
   owned plan returned by active-plan resolution instead of reading it again.
3. Reuse presentation data for at most 60 seconds within the mounted Today hook.
   Plan, training-day, session-token and injury changes invalidate it. Overlapping
   refreshes share a pending plan read. A failed read keeps the last good same-plan
   presentation and can retry; an old response cannot replace the newly active plan.
   Every change still requests a fresh authoritative Today command.

Generation, injury policy, clinical evidence rules and deterministic calendar
fallbacks retain their existing behavior. Larger planner fields remain available
through the unchanged full-row store methods for generation and review.

## Recommended next work, in order

1. **Measure a real save through the deployed API.** Correlate existing `[http]`
   request IDs/durations with Supabase spans and split primary persistence,
   clinical validation, plan decoding, derived effects and reload time. Compare
   p50/p95 and payloads before promising a latency target. Supabase logs alone
   cannot identify which steps consumed a particular browser's five seconds.
2. **Share completion-side context.** Resolve the active execution plan and
   applicable completion history once for streak/XP consumers, with explicit
   invalidation around writes and unchanged ownership/eligibility checks.
   A durable outbox can move optional derived work off the response path while
   keeping retries and idempotency. Do not replace authoritative completion or
   rehab-context persistence with an unreliable background callback.
3. **Separate execution from planner/audit data.** The planning brief alone is
   still over 600 KB on average. Build a versioned operational read model from
   validated deterministic inputs, or a compact owner-scoped context RPC.
   Preserve legacy/calendar fallback, clinical evidence completeness, frozen
   prescription revisions, athlete-local rollover and active-plan ownership.
4. **Use a compact Today presentation response.** A day-specific block/media
   response can replace loading/reconciling an entire Plan Detail. Keep Plan
   Detail available for the Plan screen and verify that the two surfaces agree.
5. **Review worker traffic and retry budgets with traces.** Reduce repeated
   no-op media writes and idle evaluation work when measured unnecessary.
   Check actual API/Supabase placement and network latency; changing connection
   pooling alone does not remove PostgREST HTTP round trips. Preserve retries for
   authoritative writes and offer recoverable failures instead of stale green gates.
6. **Address database advisors for scale.** Five uncovered foreign keys and five
   RLS initialization warnings were reported. The Today API uses owner-scoped
   service-role reads, so RLS policy evaluation is not the direct cost of those
   queries. Review migrations separately, benchmark representative queries and
   retain authorization predicates. Tiny table sequential scans and “unused index”
   notices are not a reason to remove indexes blindly.

Advisor details and references:

- [Unindexed foreign keys](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys): exercise logs, injury episode events, rehab exposures, sparring logs and week lifecycle reconciliations.
- [RLS initialization plans](https://supabase.com/docs/guides/database/database-linter?lint=0003_auth_rls_initplan): exercise logs, plan milestones, week lifecycle reconciliations, rehab exposures and sparring logs.
- [Query optimization](https://supabase.com/docs/guides/database/query-optimization) and [EXPLAIN interpretation](https://supabase.com/docs/guides/troubleshooting/understanding-postgresql-explain-output-Un9dqX).

## Verification and limits

The projection SQL was executed successfully against the live schema using
aggregate-only results. Backend fixtures apply the actual training projection
so calendar, prescription, rehab and fallback checks exercise the reduced row.
Frontend tests cover overlap, plan changes, failed reads, invalidation and the
timer handoff. TypeScript, targeted lint, Python imports and the production
webpack build pass; the build used shell-only placeholder public configuration.

| Check | Result |
| --- | --- |
| Focused backend suite, including reduced-row fixtures | 284 passed |
| Today/timer/review frontend suite | 70 passed |
| TypeScript and production webpack build | Passed |
| Python import compilation and targeted Ruff | Passed |
| Full frontend lint | Zero errors; 50 warnings in unchanged files |
| Additional clinical-clearance suite | 87 passed; seven existing failures |

The full clinical suite produces the same seven failures and 87 passes with the
pulled `Main` service implementations. The failures are
`test_rehab_only_holds_normal_training_without_a_live_rehab_policy`, five
`test_no_contact_holds_all_clear_contact_representations` cases, and
`test_new_restrictive_report_holds_frozen_work_without_rewriting_it`. All expect
an “on hold” message and receive the current STOP message instead. These
pre-existing failures remain recorded; the clinical gates were preserved.

After deploying, use the browser network panel to repeat a check-in and a
completion save. Every refresh must fetch `/api/today`; ordinary same-plan saves
within 60 seconds should reuse presentation instead of requesting Plan Detail
again. A changed injury, active plan, training day or expired presentation must
fetch it again. Verify a failed timer batch can still retry and that review is
already populated after successful saving. Use API request IDs to measure the
remaining completion-side work separately.

The patch is proposed for review. No production writes or deployment were performed. Actual
iPhone Safari and authenticated end-to-end production save latency remain unverified.
