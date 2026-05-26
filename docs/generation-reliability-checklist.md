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

## Current stale-recovery ownership (transitional)

Generation stale recovery is currently **intentional self-healing on read paths** in addition to worker/claim flows.
This is a known transition state and must be treated as part of the backend state machine until explicit reconciler-only ownership lands.

### Read methods that currently mutate

- `SupabaseAppStore.get_generation_job(...)`
  - May requeue `job_loaded_stalled` running jobs.
  - May fail `stage1_planner_stalled` running jobs.
- `SupabaseAppStore.get_active_generation_job_for_athlete(...)`
  - May reset/requeue `startup_stale` running jobs to `queued`.
  - May requeue or fail `job_loaded_stalled` running jobs (attempt-gated).
  - May fail `stage1_planner_stalled` running jobs.
  - May fail `mid_pipeline_stale` running jobs.

### API implications

- `GET /api/generation-jobs/{job_id}` and `GET /api/generation-jobs/active` can currently trigger stale-job repair side effects via store reads.
- This is kept intentionally for reliability safety right now (to avoid endless-running stale jobs), but it means polling can mutate state.

### Guardrails for future refactor

When refactoring to strict read/write separation:
- Keep stale safety behaviour unchanged.
- Move stale mutation to explicit recovery/reconciler paths.
- Keep tests that prove both stale safety and endpoint behaviour.
