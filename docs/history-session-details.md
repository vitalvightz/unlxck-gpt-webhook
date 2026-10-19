# History session details: data audit

## Confirmed relationships

- `session_completions.id` identifies the occurrence. Ownership is `athlete_id`;
  the existing unique key is `(athlete_id, session_id, training_day)`.
- `prescription_snapshot.session.blocks` is the frozen ordered prescription.
  Its plan and session identity must agree with the completion. No current or
  regenerated plan is used to reconstruct historical exercises.
- `exercise_logs` has no completion foreign key. Its unique key is
  `(athlete_id, plan_id, training_day, block_id)`. Logs also carry `session_id`.
  A frozen block may carry `source_session_id` when Today consolidates sessions.
  Match all those fields, including block identity; never match names or dates alone.
- Without a valid snapshot, logs with the exact non-null plan/session/day identity
  can show their own frozen `prescribed` and explicit `actual` values. Original
  prescription order and unlogged exercises are unavailable.
- `actual={}` is unknown unless that exercise has explicit `as_prescribed` status.
  Session completion alone never confirms individual exercises.
- Rehab bypasses exercise logging. `rehab_performance=done_as_shown`, a completed
  session and its frozen prescription allow the existing `completed_dose_from_session`
  contract to confirm only the dose actually specified. Changed/stopped remains
  unquantified. Skipped is not a completed dose.
- Saved `rehab_response_contexts` bind completion ID, athlete, plan, session, day,
  injury episode, response group and expected exposure IDs. Only matching stored
  exposure events for the exact `block:<block_id>` occurrence supply responses.
  No live injury resolution, bank lookup or evidence writes are needed.
- Manual sessions are separate `external_training_sessions` rows. Sparring links
  through `sparring_logs.external_session_id`, never a date/name match.

## Limitations and boundaries

- Schema inspected read-only in connected Supabase; no migration required.
- Connected production constraints confirm that deleting a plan **cascades its
  session completions** and sets exercise-log `plan_id` to null. A deleted
  completion therefore returns 404; this feature cannot recover it. We do not
  guess which deleted plan an orphan exercise log belonged to. If a legacy
  completion survives with a null plan ID, its valid frozen prescription can
  still be displayed, with uncertain actuals and response contexts withheld.
- Legacy snapshots without block IDs show prescriptions but cannot acquire logs
  by name. Missing/malformed snapshots never trigger plan reconstruction.
- Missing legacy rehab contexts mean responses cannot be attributed safely.
  Guidance-only blocks remain guidance, not quantified exercises.
- No prescribed duration is presented as recorded session duration; completion
  timestamps are not assumed to measure training time.
- Current health consent gates rehab, pain and free text. Response payloads use
  allowlists and exclude injury metadata, demand, clinical decisions and markers.
- The history list remains summary-only. Details load on opening a card and are
  cached in memory for the History visit, with manual edits invalidating the cache.
- Exercises drill-down, charts and detailed manual exercise logging remain PR 2 work.
- Preserving completions across future plan deletion would require a separate,
  reviewed retention/foreign-key change. It is outside this read-only PR.
