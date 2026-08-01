-- Keep claim/start and recovery as separate worker contracts.
-- Only queued and completely pre-start stale rows can enter claim_generation_job_start().
-- All other running rows are inspected by the explicit worker recovery sweep.

drop function if exists public.list_claimable_generation_jobs_v2(integer, timestamptz, boolean);
create function public.list_claimable_generation_jobs_v2(
  p_limit integer,
  p_stale_before timestamptz,
  p_include_legacy_blank boolean default false
)
returns table (
  id uuid,
  status text,
  created_at timestamptz,
  started_at timestamptz,
  heartbeat_at timestamptz,
  completed_at timestamptz,
  progress_milestones jsonb,
  stage1_result jsonb,
  final_result jsonb
)
language sql
stable
security invoker
set search_path = pg_catalog, public
as $$
  select
    job.id,
    job.status,
    job.created_at,
    job.started_at,
    job.heartbeat_at,
    job.completed_at,
    coalesce(job.progress_milestones, '[]'::jsonb),
    case when job.stage1_result is null then null else '{}'::jsonb end,
    case when job.final_result is null then null else '{}'::jsonb end
  from public.generation_jobs as job
  where job.status = 'queued'
    or (p_include_legacy_blank and coalesce(job.status, '') = '')
    or (
      job.status = 'running'
      and job.completed_at is null
      and job.stage1_result is null
      and job.final_result is null
      and coalesce(job.progress_milestones, '[]'::jsonb) = '[]'::jsonb
      and coalesce(job.heartbeat_at, job.started_at) <= p_stale_before
    )
  order by job.created_at asc
  limit least(greatest(coalesce(p_limit, 1), 1), 100);
$$;

revoke all on function public.list_claimable_generation_jobs_v2(integer, timestamptz, boolean)
  from public, anon, authenticated;
grant execute on function public.list_claimable_generation_jobs_v2(integer, timestamptz, boolean)
  to service_role;

create or replace function public.list_active_generation_jobs_for_recovery_v1(
  p_limit integer default 100
)
returns table (
  id uuid,
  status text,
  created_at timestamptz
)
language sql
stable
security invoker
set search_path = pg_catalog, public
as $$
  select job.id, job.status, job.created_at
  from public.generation_jobs as job
  where job.status = 'running'
  order by job.created_at asc
  limit least(greatest(coalesce(p_limit, 1), 1), 100);
$$;

revoke all on function public.list_active_generation_jobs_for_recovery_v1(integer)
  from public, anon, authenticated;
grant execute on function public.list_active_generation_jobs_for_recovery_v1(integer)
  to service_role;
