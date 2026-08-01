-- Preserve the original worker's oldest-first candidate ordering while keeping
-- the combined claimable-job query compact. Dummy JSON objects retain presence
-- semantics used by stale-job classification without returning planner blobs.

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
set search_path = public
as $$
  select
    j.id,
    j.status,
    j.created_at,
    j.started_at,
    j.heartbeat_at,
    j.completed_at,
    coalesce(j.progress_milestones, '[]'::jsonb) as progress_milestones,
    case when j.stage1_result is null then null else '{}'::jsonb end as stage1_result,
    case when j.final_result is null then null else '{}'::jsonb end as final_result
  from public.generation_jobs as j
  where
    j.status = 'queued'
    or (
      p_include_legacy_blank
      and coalesce(j.status, '') = ''
    )
    or (
      j.status = 'running'
      and (
        j.heartbeat_at <= p_stale_before
        or (j.heartbeat_at is null and j.started_at <= p_stale_before)
      )
    )
  order by j.created_at asc
  limit least(greatest(coalesce(p_limit, 1), 1), 100);
$$;

revoke all on function public.list_claimable_generation_jobs_v2(integer, timestamptz, boolean) from public, anon, authenticated;
grant execute on function public.list_claimable_generation_jobs_v2(integer, timestamptz, boolean) to service_role;
