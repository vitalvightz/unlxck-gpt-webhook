-- Store a deterministic signature of the plan-generation payload for
-- client_request_id idempotency checks. Nullable preserves legacy rows.

alter table public.generation_jobs
  add column if not exists payload_hash text;

drop function if exists public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid);

create or replace function public.create_generation_job_with_daily_limit(
  p_athlete_id uuid,
  p_client_request_id text,
  p_source text,
  p_request_payload jsonb,
  p_daily_limit integer,
  p_day_start timestamptz,
  p_counted_sources text[],
  p_plan_id uuid default null,
  p_intake_id uuid default null,
  p_payload_hash text default null
)
returns table (job jsonb, limit_exceeded boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_source text := coalesce(nullif(trim(p_source), ''), 'self_serve');
  v_count integer;
  v_existing public.generation_jobs%rowtype;
  v_active public.generation_jobs%rowtype;
  v_inserted public.generation_jobs%rowtype;
begin
  perform pg_advisory_xact_lock(
    hashtext('generation_jobs_daily_cap'),
    hashtext(p_athlete_id::text)
  );

  select *
  into v_existing
  from public.generation_jobs
  where athlete_id = p_athlete_id
    and client_request_id = p_client_request_id
  order by created_at desc
  limit 1;

  if found then
    return query select to_jsonb(v_existing), false;
    return;
  end if;

  if p_daily_limit > 0 then
    select count(*)
    into v_count
    from public.generation_jobs
    where athlete_id = p_athlete_id
      and created_at >= p_day_start
      and (
        coalesce(array_length(p_counted_sources, 1), 0) = 0
        or source = any(p_counted_sources)
      );

    if v_count >= p_daily_limit then
      return query select null::jsonb, true;
      return;
    end if;
  end if;

  select *
  into v_active
  from public.generation_jobs
  where athlete_id = p_athlete_id
    and status in ('queued', 'running')
  order by created_at desc
  limit 1;

  if found then
    raise exception 'generation_job_in_flight';
  end if;

  insert into public.generation_jobs (
    athlete_id,
    client_request_id,
    source,
    request_payload,
    payload_hash,
    status,
    attempt_count,
    heartbeat_at,
    started_at,
    completed_at,
    error,
    intake_id,
    stage1_result,
    final_result,
    plan_id
  )
  values (
    p_athlete_id,
    p_client_request_id,
    v_source,
    coalesce(p_request_payload, '{}'::jsonb),
    nullif(trim(p_payload_hash), ''),
    'queued',
    0,
    null,
    null,
    null,
    null,
    p_intake_id,
    null,
    null,
    p_plan_id
  )
  returning * into v_inserted;

  return query select to_jsonb(v_inserted), false;
end;
$$;

revoke all on function public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid, text) from public;
revoke all on function public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid, text) from anon;
revoke all on function public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid, text) from authenticated;
grant execute on function public.create_generation_job_with_daily_limit(uuid, text, text, jsonb, integer, timestamptz, text[], uuid, uuid, text) to service_role;
