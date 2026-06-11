create extension if not exists pgcrypto;

-- Role foundation for the single Unlxck app. `athlete` and `admin` are live in
-- private beta; `coach` and `gym_owner` are reserved for public beta (not yet
-- selectable at sign-up). On databases created before these values existed, the
-- 20260611130000 migration backfills `coach` and `gym_owner` into the enum.
do $$
begin
  create type public.app_role as enum ('athlete', 'coach', 'gym_owner', 'admin');
exception
  when duplicate_object then null;
end
$$;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create or replace function public.is_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists(
    select 1
    from public.profiles
    where id = auth.uid()
      and role = 'admin'
  );
$$;

create or replace function public.validate_generation_job_active_lock()
returns boolean
language sql
stable
as $$
select exists (
  select 1
  from pg_indexes
  where schemaname = 'public'
    and tablename = 'generation_jobs'
    and indexname = 'generation_jobs_one_active_job_per_athlete'
    and lower(indexdef) like 'create unique index%'
    and lower(indexdef) like '%(athlete_id)%'
    and lower(indexdef) like '%where%'
    and lower(indexdef) like '%queued%'
    and lower(indexdef) like '%running%'
);
$$;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
  username text unique
    constraint profiles_username_length
      check (username is null or char_length(username) between 3 and 24)
    constraint profiles_username_lowercase
      check (username is null or username = lower(username))
    constraint profiles_username_format
      check (username is null or username ~ '^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$'),
  username_change_history jsonb not null default '[]'::jsonb,
  role public.app_role not null default 'athlete',
  full_name text not null default '',
  technical_style text[] not null default '{}',
  tactical_style text[] not null default '{}',
  stance text not null default '',
  professional_status text not null default '',
  record_summary text not null default '',
  athlete_timezone text not null default '',
  athlete_locale text not null default '',
  appearance_mode text not null default 'dark',
  avatar_url text,
  onboarding_draft jsonb,
  nutrition_profile jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);


create or replace function public.prevent_self_role_escalation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.role() <> 'service_role' and not public.is_admin() then
    if (tg_op = 'INSERT' and new.role <> 'athlete')
      or (tg_op = 'UPDATE' and new.role is distinct from old.role) then
      raise exception 'Only admins can change profile roles.';
    end if;
  end if;

  return new;
end;
$$;

create or replace function public.prevent_username_policy_bypass()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.role() <> 'service_role' and not public.is_admin() then
    if new.username is distinct from old.username
      or new.username_change_history is distinct from old.username_change_history then
      raise exception 'Use the username change endpoint.';
    end if;
  end if;

  return new;
end;
$$;

create table if not exists public.athlete_intakes (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  fight_date date,
  technical_style text[] not null default '{}',
  intake jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.plans (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  intake_id uuid references public.athlete_intakes(id) on delete set null,
  fight_date date,
  technical_style text[] not null default '{}',
  full_name text not null default '',
  plan_name text not null default '',
  status text not null default 'generated',
  plan_text text not null default '',
  draft_plan_text text not null default '',
  final_plan_text text not null default '',
  coach_notes text not null default '',
  pdf_url text,
  why_log jsonb not null default '{}'::jsonb,
  planning_brief text,
  stage2_payload jsonb,
  stage2_handoff_text text not null default '',
  stage2_retry_text text not null default '',
  stage2_validator_report jsonb not null default '{}'::jsonb,
  stage2_status text not null default '',
  stage2_attempt_count integer not null default 0,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.generation_jobs (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  client_request_id text not null,
  source text not null default 'self_serve',
  request_payload jsonb not null default '{}'::jsonb,
  payload_hash text,
  status text not null default 'queued',
  error text,
  intake_id uuid references public.athlete_intakes(id) on delete set null,
  stage1_result jsonb,
  final_result jsonb,
  plan_id uuid references public.plans(id) on delete set null,
  attempt_count integer not null default 0,
  heartbeat_at timestamptz,
  started_at timestamptz,
  completed_at timestamptz,
  failed_at timestamptz,
  -- Worker ownership for the current running attempt (set by
  -- claim_generation_job; checked by the terminal RPCs). Lock expiry rides on
  -- heartbeat_at staleness, so there is no separate lock_expires_at.
  claimed_by text,
  claimed_at timestamptz,
  -- Stage 2 token/cost telemetry (nullable; populated best-effort after Stage 2
  -- finalization so cost can be audited per athlete/job from the database).
  stage2_model text,
  stage2_input_tokens integer,
  stage2_output_tokens integer,
  stage2_total_tokens integer,
  stage2_estimated_cost_usd numeric(14, 6),
  stage2_attempt_count integer,
  stage2_response_id text,
  stage2_cost_recorded_at timestamptz,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  constraint generation_jobs_athlete_client_request_key unique (athlete_id, client_request_id)
);

create table if not exists public.plan_generation_rate_limits (
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  created_at timestamptz not null default timezone('utc', now())
);

alter table public.plans add column if not exists draft_plan_text text not null default '';
alter table public.plans add column if not exists final_plan_text text not null default '';
alter table public.plans add column if not exists plan_name text not null default '';
alter table public.plans add column if not exists stage2_retry_text text not null default '';
alter table public.plans add column if not exists stage2_validator_report jsonb not null default '{}'::jsonb;
alter table public.plans add column if not exists stage2_status text not null default '';
alter table public.plans add column if not exists stage2_attempt_count integer not null default 0;
alter table public.plans add column if not exists parsing_metadata jsonb not null default '{}'::jsonb;
alter table public.generation_jobs add column if not exists source text not null default 'self_serve';
alter table public.generation_jobs add column if not exists request_payload jsonb not null default '{}'::jsonb;
alter table public.generation_jobs add column if not exists payload_hash text;
alter table public.generation_jobs add column if not exists status text not null default 'queued';
alter table public.generation_jobs add column if not exists error text;
alter table public.generation_jobs add column if not exists intake_id uuid references public.athlete_intakes(id) on delete set null;
alter table public.generation_jobs add column if not exists stage1_result jsonb;
alter table public.generation_jobs add column if not exists final_result jsonb;
alter table public.generation_jobs add column if not exists plan_id uuid references public.plans(id) on delete set null;
alter table public.generation_jobs add column if not exists attempt_count integer not null default 0;
alter table public.generation_jobs add column if not exists heartbeat_at timestamptz;
alter table public.generation_jobs add column if not exists started_at timestamptz;
alter table public.generation_jobs add column if not exists completed_at timestamptz;
alter table public.generation_jobs add column if not exists failed_at timestamptz;
alter table public.generation_jobs add column if not exists claimed_by text;
alter table public.generation_jobs add column if not exists claimed_at timestamptz;
alter table public.generation_jobs add column if not exists updated_at timestamptz not null default timezone('utc', now());
alter table public.generation_jobs add column if not exists progress_milestones jsonb not null default '[]'::jsonb;
alter table public.generation_jobs add column if not exists stage2_model text;
alter table public.generation_jobs add column if not exists stage2_input_tokens integer;
alter table public.generation_jobs add column if not exists stage2_output_tokens integer;
alter table public.generation_jobs add column if not exists stage2_total_tokens integer;
alter table public.generation_jobs add column if not exists stage2_estimated_cost_usd numeric(14, 6);
alter table public.generation_jobs add column if not exists stage2_attempt_count integer;
alter table public.generation_jobs add column if not exists stage2_response_id text;
alter table public.generation_jobs add column if not exists stage2_cost_recorded_at timestamptz;
alter table public.profiles add column if not exists appearance_mode text not null default 'dark';
alter table public.profiles add column if not exists avatar_url text;
alter table public.profiles add column if not exists nutrition_profile jsonb not null default '{}'::jsonb;
alter table public.profiles add column if not exists username text;
alter table public.profiles add column if not exists username_change_history jsonb not null default '[]'::jsonb;

do $$
begin
  update public.generation_jobs
  set status = case
    when status is null or btrim(status) = '' then 'queued'
    when lower(btrim(status)) in ('queued', 'running', 'completed', 'review_required', 'failed') then lower(btrim(status))
    when lower(btrim(status)) in ('held_for_review', 'needs_review', 'medical_hold', 'restricted_rehab_only') then 'review_required'
    when lower(btrim(status)) in ('generated', 'ready', 'publishable_with_flags', 'triage_blocked', 'archived') then 'completed'
    else 'review_required'
  end
  where status is null
     or status <> lower(btrim(status))
     or lower(btrim(status)) not in ('queued', 'running', 'completed', 'review_required', 'failed');

  update public.plans
  set status = case
    when status is null or btrim(status) = '' then 'generated'
    when lower(btrim(status)) in (
      'generated',
      'ready',
      'review_required',
      'held_for_review',
      'publishable_with_flags',
      'triage_blocked',
      'medical_hold',
      'restricted_rehab_only',
      'needs_review',
      'archived'
    ) then lower(btrim(status))
    else 'review_required'
  end
  where status is null
     or status <> lower(btrim(status))
     or lower(btrim(status)) not in (
      'generated',
      'ready',
      'review_required',
      'held_for_review',
      'publishable_with_flags',
      'triage_blocked',
      'medical_hold',
      'restricted_rehab_only',
      'needs_review',
      'archived'
     );

  if not exists (
    select 1
    from pg_constraint
    where conname = 'generation_jobs_status_check'
      and conrelid = 'public.generation_jobs'::regclass
  ) then
    alter table public.generation_jobs
      add constraint generation_jobs_status_check
      check (status in ('queued', 'running', 'completed', 'review_required', 'failed'));
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'plans_status_check'
      and conrelid = 'public.plans'::regclass
  ) then
    alter table public.plans
      add constraint plans_status_check
      check (
        status in (
          'generated',
          'ready',
          'review_required',
          'held_for_review',
          'publishable_with_flags',
          'triage_blocked',
          'medical_hold',
          'restricted_rehab_only',
          'needs_review',
          'archived'
        )
      )
      not valid;
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_key'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles add constraint profiles_username_key unique (username);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_length'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_username_length
      check (username is null or char_length(username) between 3 and 24);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_lowercase'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_username_lowercase
      check (username is null or username = lower(username));
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_format'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_username_format
      check (username is null or username ~ '^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$');
  end if;
end
$$;

alter table public.plans validate constraint plans_status_check;

alter table public.athlete_intakes add column if not exists updated_at timestamptz not null default timezone('utc', now());

create index if not exists profiles_email_idx on public.profiles (email);
create index if not exists profiles_username_idx on public.profiles (username);
create index if not exists athlete_intakes_athlete_id_created_at_idx on public.athlete_intakes (athlete_id, created_at desc);
create index if not exists plans_athlete_id_created_at_idx on public.plans (athlete_id, created_at desc);
create index if not exists generation_jobs_athlete_id_created_at_idx on public.generation_jobs (athlete_id, created_at desc);
create index if not exists generation_jobs_status_heartbeat_at_idx on public.generation_jobs (status, heartbeat_at);
create unique index if not exists generation_jobs_athlete_client_request_uidx on public.generation_jobs (athlete_id, client_request_id);
create unique index if not exists generation_jobs_one_active_job_per_athlete on public.generation_jobs (athlete_id) where status in ('queued', 'running');
-- Supports admin/dev "highest-cost jobs" lookups.
create index if not exists generation_jobs_stage2_estimated_cost_idx on public.generation_jobs (stage2_estimated_cost_usd desc nulls last);
create index if not exists plan_generation_rate_limits_athlete_created_idx on public.plan_generation_rate_limits (athlete_id, created_at);

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
before update on public.profiles
for each row
execute function public.set_updated_at();


drop trigger if exists profiles_prevent_self_role_escalation on public.profiles;
create trigger profiles_prevent_self_role_escalation
before insert or update on public.profiles
for each row
execute function public.prevent_self_role_escalation();

drop trigger if exists profiles_prevent_username_policy_bypass on public.profiles;
create trigger profiles_prevent_username_policy_bypass
before update on public.profiles
for each row
execute function public.prevent_username_policy_bypass();

create or replace function public.try_parse_timestamptz(p_value text)
returns timestamptz
language plpgsql
stable
as $$
begin
  return p_value::timestamptz;
exception when others then
  return null;
end;
$$;

create or replace function public.change_profile_username(
  p_profile_id uuid,
  p_username text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile public.profiles%rowtype;
  v_now timestamptz := now();
  v_cutoff timestamptz := v_now - interval '30 days';
  v_recent jsonb := '[]'::jsonb;
  v_next_available timestamptz;
begin
  select *
  into v_profile
  from public.profiles
  where id = p_profile_id
  for update;

  if not found then
    raise exception 'profile_not_found';
  end if;

  if v_profile.username is not null and v_profile.username = p_username then
    return;
  end if;

  select coalesce(jsonb_agg(to_jsonb(parsed_at)), '[]'::jsonb),
         min(parsed_at)
  into v_recent
       ,v_next_available
  from (
    select candidate.parsed_at
    from (
      select public.try_parse_timestamptz(value_text) as parsed_at
      from jsonb_array_elements_text(
        case
          when jsonb_typeof(v_profile.username_change_history) = 'array'
            then v_profile.username_change_history
          else '[]'::jsonb
        end
      ) as value_text
    ) candidate
    where candidate.parsed_at is not null and candidate.parsed_at >= v_cutoff
  ) filtered;

  if jsonb_array_length(v_recent) >= 4 then
    raise exception 'username_rate_limit_exceeded:%',
      coalesce((v_next_available + interval '30 days')::text, '');
  end if;

  update public.profiles
  set
    username = p_username,
    username_change_history = v_recent || to_jsonb(v_now),
    updated_at = v_now
  where id = p_profile_id;
end;
$$;

revoke execute on function public.change_profile_username(uuid, text) from public;
revoke execute on function public.change_profile_username(uuid, text) from anon;
revoke execute on function public.change_profile_username(uuid, text) from authenticated;
grant execute on function public.change_profile_username(uuid, text) to service_role;

create or replace function public.check_plan_generation_short_window_limit(
  p_athlete_id uuid,
  p_max_requests integer,
  p_window_seconds double precision
)
returns table (allowed boolean, retry_after_seconds integer)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_now timestamptz := timezone('utc', now());
  v_cutoff timestamptz;
  v_oldest timestamptz;
  v_count integer;
begin
  if p_max_requests <= 0 then
    return query select true, 0;
    return;
  end if;

  v_cutoff := v_now - make_interval(secs => p_window_seconds);

  perform pg_advisory_xact_lock(
    hashtext('plan_generation_rate_limits'),
    hashtext(p_athlete_id::text)
  );

  delete from public.plan_generation_rate_limits
  where athlete_id = p_athlete_id
    and created_at <= v_cutoff;

  select count(*), min(created_at)
  into v_count, v_oldest
  from public.plan_generation_rate_limits
  where athlete_id = p_athlete_id;

  if v_count >= p_max_requests then
    return query
    select
      false,
      greatest(1, ceil(extract(epoch from ((v_oldest + make_interval(secs => p_window_seconds)) - v_now)))::integer);
    return;
  end if;

  insert into public.plan_generation_rate_limits (athlete_id, created_at)
  values (p_athlete_id, v_now);

  return query select true, 0;
end;
$$;

revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from public;
revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from anon;
revoke all on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) from authenticated;
grant execute on function public.check_plan_generation_short_window_limit(uuid, integer, double precision) to service_role;

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

-- The terminal RPCs gained a worker-ownership argument; drop the pre-ownership
-- signatures so re-running this schema never leaves stale overloads behind.
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

-- Deploy-gate introspection helper. Returns ONLY catalog metadata (object
-- names + per-table RLS flags) for the public schema as a single jsonb object.
-- It never reads application/user row data. Consumed by
-- tools/check_supabase_runtime_schema.py to verify the live database matches the
-- schema the backend depends on before deploy. Restricted to service_role.
create or replace function public.runtime_schema_introspection()
returns jsonb
language sql
security definer
stable
set search_path = public
as $$
  select jsonb_build_object(
    'tables', (
      select coalesce(jsonb_agg(table_name order by table_name), '[]'::jsonb)
      from information_schema.tables
      where table_schema = 'public'
        and table_type = 'BASE TABLE'
    ),
    'columns', (
      select coalesce(jsonb_object_agg(table_name, cols), '{}'::jsonb)
      from (
        select table_name, jsonb_agg(column_name order by column_name) as cols
        from information_schema.columns
        where table_schema = 'public'
        group by table_name
      ) grouped
    ),
    'functions', (
      select coalesce(jsonb_agg(distinct p.proname order by p.proname), '[]'::jsonb)
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'public'
    ),
    'indexes', (
      select coalesce(jsonb_agg(indexname order by indexname), '[]'::jsonb)
      from pg_indexes
      where schemaname = 'public'
    ),
    'constraints', (
      select coalesce(jsonb_agg(c.conname order by c.conname), '[]'::jsonb)
      from pg_constraint c
      join pg_namespace n on n.oid = c.connamespace
      where n.nspname = 'public'
    ),
    'rls', (
      select coalesce(jsonb_object_agg(c.relname, c.relrowsecurity), '{}'::jsonb)
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'public'
        and c.relkind = 'r'
    )
  );
$$;

revoke all on function public.runtime_schema_introspection() from public;
revoke all on function public.runtime_schema_introspection() from anon;
revoke all on function public.runtime_schema_introspection() from authenticated;
grant execute on function public.runtime_schema_introspection() to service_role;

drop trigger if exists generation_jobs_set_updated_at on public.generation_jobs;
create trigger generation_jobs_set_updated_at
before update on public.generation_jobs
for each row
execute function public.set_updated_at();

drop trigger if exists athlete_intakes_set_updated_at on public.athlete_intakes;
create trigger athlete_intakes_set_updated_at
before update on public.athlete_intakes
for each row
execute function public.set_updated_at();

drop view if exists public.admin_athlete_rollups;
create or replace view public.admin_athlete_rollups
with (security_invoker = true) as
select
  p.id,
  p.email,
  p.username,
  p.role,
  p.full_name,
  p.technical_style,
  p.tactical_style,
  p.stance,
  p.professional_status,
  p.record_summary,
  p.athlete_timezone,
  p.athlete_locale,
  p.appearance_mode,
  p.onboarding_draft,
  p.nutrition_profile,
  p.created_at,
  p.updated_at,
  count(pl.id)::int as plan_count,
  max(pl.created_at) as latest_plan_created_at
from public.profiles p
left join public.plans pl on pl.athlete_id = p.id
group by
  p.id,
  p.email,
  p.username,
  p.role,
  p.full_name,
  p.technical_style,
  p.tactical_style,
  p.stance,
  p.professional_status,
  p.record_summary,
  p.athlete_timezone,
  p.athlete_locale,
  p.appearance_mode,
  p.onboarding_draft,
  p.nutrition_profile,
  p.created_at,
  p.updated_at;

-- The rollup view aggregates every athlete's profile. It is read only by the
-- service-role backend (api/store.py). security_invoker keeps it bound to the
-- caller's RLS context, and the explicit grants ensure browser-facing roles
-- cannot read it directly even if default privileges grant SELECT on new views.
revoke all on public.admin_athlete_rollups from anon;
revoke all on public.admin_athlete_rollups from authenticated;
grant select on public.admin_athlete_rollups to service_role;

alter table public.profiles enable row level security;
alter table public.athlete_intakes enable row level security;
alter table public.plans enable row level security;
alter table public.generation_jobs enable row level security;
alter table public.plan_generation_rate_limits enable row level security;

drop policy if exists "profiles_self_or_admin_select" on public.profiles;
create policy "profiles_self_or_admin_select" on public.profiles
for select using (auth.uid() = id or public.is_admin());

drop policy if exists "profiles_self_update" on public.profiles;
create policy "profiles_self_update" on public.profiles
for update using (auth.uid() = id or public.is_admin())
with check (auth.uid() = id or public.is_admin());

drop policy if exists "intakes_self_or_admin_select" on public.athlete_intakes;
create policy "intakes_self_or_admin_select" on public.athlete_intakes
for select using (athlete_id = auth.uid() or public.is_admin());

-- athlete_intakes: authenticated browser clients may read their own records,
-- but writes must go through FastAPI/service-role business logic.
drop policy if exists "intakes_self_or_admin_insert" on public.athlete_intakes;
drop policy if exists "intakes_self_or_admin_update" on public.athlete_intakes;
drop policy if exists "intakes_self_or_admin_delete" on public.athlete_intakes;
drop policy if exists "athlete_intakes_self_or_admin_insert" on public.athlete_intakes;
drop policy if exists "athlete_intakes_self_or_admin_update" on public.athlete_intakes;
drop policy if exists "athlete_intakes_self_or_admin_delete" on public.athlete_intakes;

drop policy if exists "plans_self_or_admin_select" on public.plans;
create policy "plans_self_or_admin_select" on public.plans
for select using (athlete_id = auth.uid() or public.is_admin());

-- plans: authenticated browser clients may read their own plans,
-- but writes must go through FastAPI/service-role business logic.
drop policy if exists "plans_self_or_admin_insert" on public.plans;
drop policy if exists "plans_self_or_admin_update" on public.plans;
drop policy if exists "plans_self_or_admin_delete" on public.plans;

drop policy if exists "generation_jobs_self_or_admin_select" on public.generation_jobs;
create policy "generation_jobs_self_or_admin_select" on public.generation_jobs
for select using (athlete_id = auth.uid() or public.is_admin());

-- generation_jobs: authenticated browser clients may read their own jobs,
-- but writes must go through FastAPI/service-role business logic.
drop policy if exists "generation_jobs_self_or_admin_insert" on public.generation_jobs;
drop policy if exists "generation_jobs_self_or_admin_update" on public.generation_jobs;
drop policy if exists "generation_jobs_self_or_admin_delete" on public.generation_jobs;

-- ---------------------------------------------------------------------------
-- Admin role change audit trail
-- (see migration 20260606010000_add_admin_role_audit.sql for rationale)
-- ---------------------------------------------------------------------------
create table if not exists public.admin_role_audit (
  id uuid primary key default gen_random_uuid(),
  target_athlete_id uuid references public.profiles(id) on delete set null,
  target_email text not null,
  previous_role public.app_role,
  new_role public.app_role not null,
  action text not null check (action in ('promote', 'revoke')),
  actor text not null,
  reason text,
  created_at timestamptz not null default now()
);

create index if not exists admin_role_audit_target_email_idx
  on public.admin_role_audit (target_email);
create index if not exists admin_role_audit_created_at_idx
  on public.admin_role_audit (created_at desc);

alter table public.admin_role_audit enable row level security;

drop policy if exists "admin_role_audit_admin_select" on public.admin_role_audit;
create policy "admin_role_audit_admin_select" on public.admin_role_audit
for select using (public.is_admin());

revoke all on public.admin_role_audit from anon;
revoke insert, update, delete on public.admin_role_audit from authenticated;
grant select on public.admin_role_audit to authenticated;
grant all on public.admin_role_audit to service_role;

-- Atomic admin role change + audit (see migration
-- 20260610150000_atomic_admin_role_change_audit.sql for rationale): the role
-- update and its audit row commit in one transaction, so a role change can
-- never land without its audit record. Policy checks (last-admin lockout,
-- no-op short-circuit) stay in api/store.py::set_profile_role.
create or replace function public.set_profile_role_with_audit(
  p_athlete_id uuid,
  p_new_role text,
  p_actor text,
  p_expected_previous_role text default null,
  p_reason text default null,
  p_target_email text default null
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_profile public.profiles%rowtype;
  v_new_role text := lower(btrim(p_new_role));
  v_actor text := nullif(btrim(p_actor), '');
  v_previous_role text;
  v_target_email text;
  v_action text;
begin
  if v_new_role is null or v_new_role not in ('admin', 'athlete') then
    raise exception 'unsupported_profile_role:%', p_new_role
      using errcode = 'P0001';
  end if;

  if v_actor is null then
    raise exception 'missing_role_change_actor:%', p_athlete_id
      using errcode = 'P0001';
  end if;

  select *
  into v_profile
  from public.profiles
  where id = p_athlete_id
  for update;

  if not found then
    raise exception 'profile_missing:%', p_athlete_id
      using errcode = 'P0002';
  end if;

  v_previous_role := coalesce(v_profile.role::text, 'athlete');

  -- CAS guard: the caller decided on the change after reading this role; a
  -- concurrent change means their decision (and audit previous_role) would be
  -- stale, so refuse instead of recording a misleading trail.
  if p_expected_previous_role is not null
    and v_previous_role <> lower(btrim(p_expected_previous_role)) then
    raise exception 'stale_profile_role:% expected %, got %',
      p_athlete_id, p_expected_previous_role, v_previous_role
      using errcode = 'P0001';
  end if;

  if v_previous_role = v_new_role then
    return jsonb_build_object(
      'athlete_id', v_profile.id,
      'email', lower(btrim(coalesce(v_profile.email, p_target_email, ''))),
      'previous_role', v_previous_role,
      'new_role', v_new_role,
      'changed', false
    );
  end if;

  v_target_email := coalesce(
    nullif(lower(btrim(v_profile.email)), ''),
    nullif(lower(btrim(p_target_email)), '')
  );
  if v_target_email is null then
    raise exception 'missing_role_change_target_email:%', p_athlete_id
      using errcode = 'P0001';
  end if;

  v_action := case when v_new_role = 'admin' then 'promote' else 'revoke' end;

  update public.profiles
  set role = v_new_role::public.app_role
  where id = p_athlete_id;

  -- Same transaction as the role update: if this insert fails, the role
  -- change rolls back with it.
  insert into public.admin_role_audit (
    target_athlete_id,
    target_email,
    previous_role,
    new_role,
    action,
    actor,
    reason
  )
  values (
    p_athlete_id,
    v_target_email,
    v_previous_role::public.app_role,
    v_new_role::public.app_role,
    v_action,
    v_actor,
    p_reason
  );

  return jsonb_build_object(
    'athlete_id', v_profile.id,
    'email', v_target_email,
    'previous_role', v_previous_role,
    'new_role', v_new_role,
    'action', v_action,
    'changed', true
  );
end;
$$;

revoke all on function public.set_profile_role_with_audit(uuid, text, text, text, text, text) from public;
revoke all on function public.set_profile_role_with_audit(uuid, text, text, text, text, text) from anon;
revoke all on function public.set_profile_role_with_audit(uuid, text, text, text, text, text) from authenticated;
grant execute on function public.set_profile_role_with_audit(uuid, text, text, text, text, text) to service_role;

-- ---------------------------------------------------------------------------
-- Live athlete daily tracking (see
-- supabase/migrations/20260611120000_add_live_athlete_daily_tracking.sql).
-- daily_checkins, session_logs, injury_flags, adaptation_notes record the
-- athlete's day-to-day state; admin_reviews is the ops attention queue.
-- Adaptation decisions are append-only history — plans are never silently
-- rewritten.
-- ---------------------------------------------------------------------------

create table if not exists public.daily_checkins (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  checkin_date date not null,
  readiness integer not null check (readiness between 1 and 5),
  fatigue integer not null check (fatigue between 1 and 5),
  soreness integer not null check (soreness between 1 and 5),
  sleep_quality integer not null check (sleep_quality between 1 and 5),
  sleep_hours numeric(4,1) check (sleep_hours is null or (sleep_hours >= 0 and sleep_hours <= 24)),
  injury_note text not null default '',
  notes text not null default '',
  readiness_state text not null default 'ready'
    check (readiness_state in ('ready', 'caution', 'high_fatigue', 'injury_flag')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint daily_checkins_athlete_date_key unique (athlete_id, checkin_date)
);

create index if not exists daily_checkins_athlete_date_idx
  on public.daily_checkins (athlete_id, checkin_date desc);

drop trigger if exists set_daily_checkins_updated_at on public.daily_checkins;
create trigger set_daily_checkins_updated_at
  before update on public.daily_checkins
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- session_logs: what the athlete actually did. plan_id is nullable so logs
-- survive plan deletion and ad-hoc sessions can be logged without a plan.
-- ---------------------------------------------------------------------------
create table if not exists public.session_logs (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid references public.plans(id) on delete set null,
  session_date date not null,
  session_type text not null default 'training',
  completed boolean not null default true,
  rpe integer check (rpe is null or rpe between 1 and 10),
  duration_minutes integer check (duration_minutes is null or (duration_minutes > 0 and duration_minutes <= 600)),
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists session_logs_athlete_date_idx
  on public.session_logs (athlete_id, session_date desc);

drop trigger if exists set_session_logs_updated_at on public.session_logs;
create trigger set_session_logs_updated_at
  before update on public.session_logs
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- injury_flags: open flags drive the 'injury_flag' readiness state and the
-- admin review queue. Flags are resolved (status transition), never deleted,
-- so the injury history stays auditable.
-- ---------------------------------------------------------------------------
create table if not exists public.injury_flags (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid references public.plans(id) on delete set null,
  source text not null default 'checkin'
    check (source in ('checkin', 'session_log', 'manual', 'admin')),
  body_area text not null default '',
  description text not null,
  severity text not null default 'moderate'
    check (severity in ('mild', 'moderate', 'severe')),
  status text not null default 'open'
    check (status in ('open', 'monitoring', 'resolved')),
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists injury_flags_athlete_status_idx
  on public.injury_flags (athlete_id, status);

drop trigger if exists set_injury_flags_updated_at on public.injury_flags;
create trigger set_injury_flags_updated_at
  before update on public.injury_flags
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- adaptation_notes: append-only record of every rule decision the system made
-- from logged data (reduce intensity, add recovery, flag for review, ...).
-- This is the "never silently change a plan" guarantee: any adjustment shown
-- to the athlete has a row here explaining which rule fired and why.
-- ---------------------------------------------------------------------------
create table if not exists public.adaptation_notes (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid references public.plans(id) on delete set null,
  checkin_id uuid references public.daily_checkins(id) on delete set null,
  session_log_id uuid references public.session_logs(id) on delete set null,
  rule_code text not null,
  decision text not null
    check (decision in ('keep_plan', 'reduce_intensity', 'swap_session', 'add_recovery', 'flag_admin_review')),
  summary text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists adaptation_notes_athlete_created_idx
  on public.adaptation_notes (athlete_id, created_at desc);

-- ---------------------------------------------------------------------------
-- admin_reviews: ops queue of athletes who need human attention (injury
-- reports, sustained high fatigue, repeated misses). Rows are resolved, not
-- deleted. resolved_by stores the admin's email for accountability.
-- ---------------------------------------------------------------------------
create table if not exists public.admin_reviews (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  adaptation_note_id uuid references public.adaptation_notes(id) on delete set null,
  injury_flag_id uuid references public.injury_flags(id) on delete set null,
  reason text not null,
  status text not null default 'pending'
    check (status in ('pending', 'acknowledged', 'resolved')),
  resolution_notes text not null default '',
  resolved_by text not null default '',
  resolved_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists admin_reviews_status_created_idx
  on public.admin_reviews (status, created_at desc);
create index if not exists admin_reviews_athlete_idx
  on public.admin_reviews (athlete_id);

drop trigger if exists set_admin_reviews_updated_at on public.admin_reviews;
create trigger set_admin_reviews_updated_at
  before update on public.admin_reviews
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- RLS: athletes read their own rows, admins read all; writes are service-role
-- only (no insert/update/delete policies), matching plans/athlete_intakes.
-- admin_reviews is admin-read-only, matching admin_role_audit.
-- ---------------------------------------------------------------------------
alter table public.daily_checkins enable row level security;
alter table public.session_logs enable row level security;
alter table public.injury_flags enable row level security;
alter table public.adaptation_notes enable row level security;
alter table public.admin_reviews enable row level security;

drop policy if exists "daily_checkins_owner_select" on public.daily_checkins;
create policy "daily_checkins_owner_select" on public.daily_checkins
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "session_logs_owner_select" on public.session_logs;
create policy "session_logs_owner_select" on public.session_logs
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "injury_flags_owner_select" on public.injury_flags;
create policy "injury_flags_owner_select" on public.injury_flags
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "adaptation_notes_owner_select" on public.adaptation_notes;
create policy "adaptation_notes_owner_select" on public.adaptation_notes
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "admin_reviews_admin_select" on public.admin_reviews;
create policy "admin_reviews_admin_select" on public.admin_reviews
for select using (public.is_admin());

revoke all on public.daily_checkins from anon;
revoke all on public.session_logs from anon;
revoke all on public.injury_flags from anon;
revoke all on public.adaptation_notes from anon;
revoke all on public.admin_reviews from anon;

revoke insert, update, delete on public.daily_checkins from authenticated;
revoke insert, update, delete on public.session_logs from authenticated;
revoke insert, update, delete on public.injury_flags from authenticated;
revoke insert, update, delete on public.adaptation_notes from authenticated;
revoke insert, update, delete on public.admin_reviews from authenticated;

grant select on public.daily_checkins to authenticated;
grant select on public.session_logs to authenticated;
grant select on public.injury_flags to authenticated;
grant select on public.adaptation_notes to authenticated;
grant select on public.admin_reviews to authenticated;

grant all on public.daily_checkins to service_role;
grant all on public.session_logs to service_role;
grant all on public.injury_flags to service_role;
grant select, insert on public.adaptation_notes to service_role;
grant all on public.admin_reviews to service_role;
