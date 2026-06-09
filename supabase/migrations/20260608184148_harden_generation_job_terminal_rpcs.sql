-- Harden terminal generation job lifecycle transitions.
--
-- Completion/failure must be atomic: lock the job row, verify the worker is
-- still acting on the expected running attempt, then write the terminal fields.
-- The current schema has no worker/lock-owner column, so ownership is enforced
-- through the claimed attempt number and row lock.

alter table public.generation_jobs
  add column if not exists failed_at timestamptz;

create or replace function public.complete_generation_job(
  p_job_id uuid,
  p_expected_status text,
  p_expected_attempt_count integer,
  p_final_status text,
  p_final_result jsonb default null,
  p_plan_id uuid default null,
  p_error text default null,
  p_completed_at timestamptz default now(),
  p_heartbeat_at timestamptz default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job public.generation_jobs%rowtype;
  v_expected_status text := coalesce(nullif(lower(btrim(p_expected_status)), ''), 'running');
  v_final_status text := lower(btrim(p_final_status));
  v_completed_at timestamptz := coalesce(p_completed_at, now());
  v_heartbeat_at timestamptz := coalesce(p_heartbeat_at, v_completed_at);
begin
  if v_final_status not in ('completed', 'review_required') then
    raise exception 'invalid_terminal_status:%', p_final_status
      using errcode = 'P0001';
  end if;

  select *
  into v_job
  from public.generation_jobs
  where id = p_job_id
  for update;

  if not found then
    raise exception 'generation_job_missing:%', p_job_id
      using errcode = 'P0002';
  end if;

  if coalesce(v_job.status, '') <> v_expected_status then
    raise exception 'wrong_generation_job_status:% expected %, got %',
      p_job_id, v_expected_status, coalesce(v_job.status, '<null>')
      using errcode = 'P0001';
  end if;

  if coalesce(v_job.attempt_count, 0) <> p_expected_attempt_count then
    raise exception 'stale_generation_job_attempt:% expected %, got %',
      p_job_id, p_expected_attempt_count, coalesce(v_job.attempt_count, 0)
      using errcode = 'P0001';
  end if;

  update public.generation_jobs
  set
    status = v_final_status,
    final_result = coalesce(p_final_result, final_result),
    plan_id = coalesce(p_plan_id, plan_id),
    error = p_error,
    completed_at = v_completed_at,
    failed_at = null,
    heartbeat_at = v_heartbeat_at,
    updated_at = now()
  where id = p_job_id
  returning * into v_job;

  return to_jsonb(v_job);
end;
$$;

create or replace function public.fail_generation_job(
  p_job_id uuid,
  p_expected_status text,
  p_expected_attempt_count integer,
  p_error text,
  p_final_result jsonb default null,
  p_plan_id uuid default null,
  p_progress_milestones jsonb default null,
  p_failed_at timestamptz default now(),
  p_heartbeat_at timestamptz default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job public.generation_jobs%rowtype;
  v_expected_status text := coalesce(nullif(lower(btrim(p_expected_status)), ''), 'running');
  v_failed_at timestamptz := coalesce(p_failed_at, now());
  v_heartbeat_at timestamptz := coalesce(p_heartbeat_at, v_failed_at);
begin
  select *
  into v_job
  from public.generation_jobs
  where id = p_job_id
  for update;

  if not found then
    raise exception 'generation_job_missing:%', p_job_id
      using errcode = 'P0002';
  end if;

  if coalesce(v_job.status, '') <> v_expected_status then
    raise exception 'wrong_generation_job_status:% expected %, got %',
      p_job_id, v_expected_status, coalesce(v_job.status, '<null>')
      using errcode = 'P0001';
  end if;

  if coalesce(v_job.attempt_count, 0) <> p_expected_attempt_count then
    raise exception 'stale_generation_job_attempt:% expected %, got %',
      p_job_id, p_expected_attempt_count, coalesce(v_job.attempt_count, 0)
      using errcode = 'P0001';
  end if;

  update public.generation_jobs
  set
    status = 'failed',
    error = coalesce(nullif(p_error, ''), 'Generation job failed.'),
    final_result = coalesce(p_final_result, final_result),
    plan_id = coalesce(p_plan_id, plan_id),
    progress_milestones = coalesce(p_progress_milestones, progress_milestones),
    completed_at = v_failed_at,
    failed_at = v_failed_at,
    heartbeat_at = v_heartbeat_at,
    updated_at = now()
  where id = p_job_id
  returning * into v_job;

  return to_jsonb(v_job);
end;
$$;

revoke all on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz) from public;
revoke all on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz) from anon;
revoke all on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz) from authenticated;
grant execute on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz) to service_role;

revoke all on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz) from public;
revoke all on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz) from anon;
revoke all on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz) from authenticated;
grant execute on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz) to service_role;
