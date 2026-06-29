# Generation reliability checklist

Before merging generation-related changes, verify all of these are green:

- Run backend quality checks: `ruff check api fightcamp tests tools`.
- Run focused generation/runtime regressions: `pytest -q tests/test_api_generation_flows.py tests/test_generation_runtime.py`.
- Run backend suite: `pytest tests/ -q` (or the repository’s configured full backend equivalent).
- Run frontend checks from `web/`: `npm run typecheck` and `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run build`.
- If JSON bank validation is in scope, run: `python tools/validate_banks.py`.
- Confirm active generation states never route to `/generate`; they only reconnect and refresh status.
- Confirm `review_required` routes with `?review_required=1` when a plan id exists.
- Confirm stale running jobs cannot remain running forever and are recovered/failed safely.
- Confirm retry cannot create duplicate active jobs for the same athlete.
- Confirm localStorage pending state cannot override backend active-job truth.

## Stale-recovery ownership (read/write separation)

Generation stale recovery lives **only on explicit write/control paths**. Read
methods are pure: they never requeue, fail, or otherwise mutate job state, so
polling and status checks cannot change the backend.

### Pure read methods (never mutate)

- `SupabaseAppStore.get_generation_job(...)` — plain lookup, used by
  `GET /api/generation-jobs/{job_id}`.
- `SupabaseAppStore.get_visible_active_generation_job_for_athlete(...)` — latest
  queued/running job for polling, used by `GET /api/generation-jobs/active`.
- `SupabaseAppStore.get_latest_generation_job_for_athlete(...)`.

### Explicit recovery / reconciliation methods (mutate by design)

- `SupabaseAppStore.recover_generation_job_if_stale(job)` — single-job recovery.
  Requeues `job_loaded_stalled` and fails/recovers `stage1_planner_stalled`
  running jobs, returning the refreshed row. No-op for non-running jobs.
- `SupabaseAppStore.reconcile_active_generation_job_for_athlete(athlete_id, ...)`
  — per-athlete reconciliation. Resets `startup_stale` to `queued`, requeues or
  fails `job_loaded_stalled` (attempt-gated), and fails/recovers
  `stage1_planner_stalled` / `mid_pipeline_stale` running jobs.
- `SupabaseAppStore.claim_generation_job_start(...)` /
  `claim_generation_job(...)` — worker claim loop recovery at startup/claim.

### Where reconciliation runs

- **Job creation:** `create_or_get_generation_job(...)` and
  `create_or_get_generation_job_with_daily_limit(...)` call
  `reconcile_active_generation_job_for_athlete(...)` before deciding whether a
  request is in flight, so a crashed worker's stale `running` row cannot block
  new generation forever.
- **Retry generation:** the retry service routes through the same
  `create_or_get_generation_job*` write paths.
- **Worker startup / claim loop:** `claim_generation_job_start` /
  `claim_generation_job` recover startup-stale rows as they are claimed.

### Invariants to keep green

- `GET /api/generation-jobs/{job_id}` and `GET /api/generation-jobs/active` are
  side-effect free, even for stale running jobs (proved by
  `test_get_active_endpoint_does_not_mutate_stale_running_job` and
  `test_get_job_by_id_endpoint_does_not_mutate_stale_running_job`).
- Stale running jobs are still recovered through the explicit paths above and
  cannot remain active forever
  (`test_reconcile_active_generation_job_mutates_stale_running_job`).
- Retry must not create duplicate active jobs for the same athlete.
