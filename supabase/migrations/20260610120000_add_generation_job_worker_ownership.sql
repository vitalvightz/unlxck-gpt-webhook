-- Worker ownership for generation jobs.
--
-- Claiming a job now happens through an atomic RPC that records which worker
-- owns the running attempt (claimed_by/claimed_at), and the terminal RPCs
-- refuse completion/failure from a worker that no longer owns the job. Lock
-- expiry stays on the existing heartbeat_at staleness model, so no
-- lock_expires_at column is introduced.
--
-- Rollback notes:
--   drop function if exists public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz);
--   recreate complete_generation_job/fail_generation_job from
--   20260608184148_harden_generation_job_terminal_rpcs.sql (the worker guard
--   only fires when p_expected_worker_id is provided, so leaving the new
--   functions in place is also safe). The added columns are nullable and can
--   stay.

alter table public.generation_jobs
  add column if not exists claimed_by text,
  add column if not exists claimed_at timestamptz;

-- Atomic claim: flip an eligible job to running, bump attempt_count, and
-- record worker ownership in one guarded update. Concurrent claimers
-- serialize on the row lock; the loser re-evaluates the status/attempt guards
-- against the winner's row, matches nothing, and receives null (a lost claim
-- race is normal, not an error). Eligibility policy (startup-staleness,
-- retry caps) stays in the application; this function only guarantees the
-- transition itself is atomic and owned.
create or replace function public.claim_generation_job(
  p_job_id uuid,
  p_worker_id text,
  p_expected_status text,
  p_expected_attempt_count integer,
  p_progress_milestones jsonb default null,
  p_claimed_at timestamptz default now()
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_job public.generation_jobs%rowtype;
  v_expected_status text := coalesce(nullif(lower(btrim(p_expected_status)), ''), 'queued');
  v_worker_id text := nullif(btrim(p_worker_id), '');
  v_claimed_at timestamptz := coalesce(p_claimed_at, now());
begin
  if v_worker_id is null then
    raise exception 'missing_generation_job_worker_id:%', p_job_id
      using errcode = 'P0001';
  end if;

  if v_expected_status not in ('queued', 'running') then
    return null;
  end if;

  update public.generation_jobs
  set
    status = 'running',
    attempt_count = coalesce(attempt_count, 0) + 1,
    claimed_by = v_worker_id,
    claimed_at = v_claimed_at,
    heartbeat_at = v_claimed_at,
    started_at = case
      when v_expected_status = 'queued' then v_claimed_at
      else coalesce(started_at, v_claimed_at)
    end,
    error = null,
    completed_at = null,
    failed_at = null,
    progress_milestones = coalesce(p_progress_milestones, '[]'::jsonb),
    updated_at = now()
  where id = p_job_id
    and coalesce(nullif(lower(btrim(status)), ''), 'queued') = v_expected_status
    and coalesce(attempt_count, 0) = p_expected_attempt_count
  returning * into v_job;

  if not found then
    return null;
  end if;

  return to_jsonb(v_job);
end;
$$;

-- Recreate the terminal RPCs with a worker-ownership guard. The argument list
-- changes, so the old signatures must be dropped first (create or replace
-- would otherwise leave both overloads behind).
drop function if exists public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz);
drop function if exists public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz);

create or replace function public.complete_generation_job(
  p_job_id uuid,
  p_expected_status text,
  p_expected_attempt_count integer,
  p_final_status text,
  p_final_result jsonb default null,
  p_plan_id uuid default null,
  p_error text default null,
  p_completed_at timestamptz default now(),
  p_heartbeat_at timestamptz default null,
  p_expected_worker_id text default null
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

  -- Ownership guard: a caller that claims to be a specific worker may only
  -- finish a job that worker still owns. claimed_by stays null only for rows
  -- claimed before the worker-ownership migration, so the null case is let
  -- through and the status/attempt guards above carry the protection there.
  if p_expected_worker_id is not null
    and v_job.claimed_by is not null
    and v_job.claimed_by <> p_expected_worker_id then
    raise exception 'stale_generation_job_worker:% expected %, got %',
      p_job_id, p_expected_worker_id, v_job.claimed_by
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
  p_heartbeat_at timestamptz default null,
  p_expected_worker_id text default null
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

  -- Ownership guard: see complete_generation_job for the null-claimed_by
  -- rationale.
  if p_expected_worker_id is not null
    and v_job.claimed_by is not null
    and v_job.claimed_by <> p_expected_worker_id then
    raise exception 'stale_generation_job_worker:% expected %, got %',
      p_job_id, p_expected_worker_id, v_job.claimed_by
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

revoke all on function public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz) from public;
revoke all on function public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz) from anon;
revoke all on function public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz) from authenticated;
grant execute on function public.claim_generation_job(uuid, text, text, integer, jsonb, timestamptz) to service_role;

revoke all on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz, text) from public;
revoke all on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz, text) from anon;
revoke all on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz, text) from authenticated;
grant execute on function public.complete_generation_job(uuid, text, integer, text, jsonb, uuid, text, timestamptz, timestamptz, text) to service_role;

revoke all on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz, text) from public;
revoke all on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz, text) from anon;
revoke all on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz, text) from authenticated;
grant execute on function public.fail_generation_job(uuid, text, integer, text, jsonb, uuid, jsonb, timestamptz, timestamptz, text) to service_role;
