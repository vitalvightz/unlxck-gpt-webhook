-- Stage 2 token/cost telemetry on generation_jobs.
--
-- PR #1700 removed the default Stage 2 output-token cap (to stop GPT-5
-- reasoning-budget truncation) and PR #1704 added job_id/athlete_id attribution
-- to the Stage 2 cost *logs*. Logs alone are not enough for admin/business
-- visibility, so this migration persists the same token/cost metadata on the
-- generation job, making cost auditable per athlete/job with a plain SQL query.
--
-- All columns are additive and nullable:
--   * A generation_jobs row created before this migration simply has NULLs.
--   * A Stage 2 call whose OpenAI response omitted a usage field falls back to
--     char-based estimates; anything genuinely unknown (e.g. output tokens on a
--     request that failed before any response) stays NULL.
-- The backend write (api/store.py::record_stage2_cost) is best-effort and never
-- blocks generation, so applying this migration cannot break in-flight jobs.

alter table public.generation_jobs add column if not exists stage2_model text;
alter table public.generation_jobs add column if not exists stage2_input_tokens integer;
alter table public.generation_jobs add column if not exists stage2_output_tokens integer;
alter table public.generation_jobs add column if not exists stage2_total_tokens integer;
alter table public.generation_jobs add column if not exists stage2_estimated_cost_usd numeric(14, 6);
alter table public.generation_jobs add column if not exists stage2_attempt_count integer;
alter table public.generation_jobs add column if not exists stage2_response_id text;
alter table public.generation_jobs add column if not exists stage2_cost_recorded_at timestamptz;

-- Supports admin/dev "highest-cost jobs" lookups (ORDER BY cost DESC).
create index if not exists generation_jobs_stage2_estimated_cost_idx
  on public.generation_jobs (stage2_estimated_cost_usd desc nulls last);
