create or replace function public.claim_next_generation_job(
  worker_id text,
  stale_after_seconds integer,
  max_attempts integer default 3
)
returns setof public.generation_jobs
language plpgsql
security definer
set search_path = public
as $$
declare
  v_now timestamptz := timezone('utc', now());
  v_cutoff timestamptz := v_now - make_interval(secs => greatest(1, stale_after_seconds));
  v_row public.generation_jobs%rowtype;
  v_milestones jsonb;
  v_job_loaded jsonb := jsonb_build_object(
    'code', 'job_loaded',
    'label', 'Generation job loaded',
    'detail', 'Worker loaded the persisted generation job.',
    'meta', jsonb_build_object('worker_id', coalesce(worker_id, '')),
    'at', v_now
  );
  v_recovery jsonb := jsonb_build_object(
    'code', 'job_recovered_startup_stale',
    'label', 'Recovered startup-stale job',
    'detail', 'Worker reclaimed a stale startup job.',
    'meta', jsonb_build_object('worker_id', coalesce(worker_id, '')),
    'at', v_now
  );
begin
  with candidate as (
    select gj.id
    from public.generation_jobs gj
    where (
      gj.status = 'queued'
      or (
        gj.status = 'running'
        and gj.attempt_count < greatest(1, coalesce(max_attempts, 3))
        and gj.completed_at is null
        and gj.stage1_result is null
        and gj.final_result is null
        and (
          (coalesce(jsonb_array_length(gj.progress_milestones), 0) = 1 and coalesce(gj.progress_milestones->0->>'code', '') = 'job_loaded')
          or coalesce(jsonb_array_length(gj.progress_milestones), 0) = 0
        )
        and coalesce(gj.heartbeat_at, gj.started_at) is not null
        and coalesce(gj.heartbeat_at, gj.started_at) <= v_cutoff
      )
    )
    order by gj.created_at asc
    for update skip locked
    limit 1
  )
  update public.generation_jobs gj
  set status = 'running',
      started_at = coalesce(gj.started_at, v_now),
      heartbeat_at = v_now,
      attempt_count = coalesce(gj.attempt_count, 0) + 1,
      error = null,
      completed_at = null,
      progress_milestones = case
        when gj.status = 'queued' then jsonb_build_array(v_job_loaded)
        else coalesce(gj.progress_milestones, '[]'::jsonb) || jsonb_build_array(v_recovery, v_job_loaded)
      end
  from candidate
  where gj.id = candidate.id
  returning gj.* into v_row;

  if found then
    return next v_row;
  end if;
  return;
end;
$$;
