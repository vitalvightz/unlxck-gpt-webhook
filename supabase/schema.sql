create extension if not exists pgcrypto;

do $$
begin
  create type public.app_role as enum ('athlete', 'admin');
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
alter table public.generation_jobs add column if not exists updated_at timestamptz not null default timezone('utc', now());
alter table public.generation_jobs add column if not exists progress_milestones jsonb not null default '[]'::jsonb;
alter table public.profiles add column if not exists appearance_mode text not null default 'dark';
alter table public.profiles add column if not exists avatar_url text;
alter table public.profiles add column if not exists nutrition_profile jsonb not null default '{}'::jsonb;
alter table public.profiles add column if not exists username text;
alter table public.profiles add column if not exists username_change_history jsonb not null default '[]'::jsonb;

do $$
begin
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
alter table public.athlete_intakes add column if not exists updated_at timestamptz not null default timezone('utc', now());

create index if not exists profiles_email_idx on public.profiles (email);
create index if not exists profiles_username_idx on public.profiles (username);
create index if not exists athlete_intakes_athlete_id_created_at_idx on public.athlete_intakes (athlete_id, created_at desc);
create index if not exists plans_athlete_id_created_at_idx on public.plans (athlete_id, created_at desc);
create index if not exists generation_jobs_athlete_id_created_at_idx on public.generation_jobs (athlete_id, created_at desc);
create index if not exists generation_jobs_status_heartbeat_at_idx on public.generation_jobs (status, heartbeat_at);
create unique index if not exists generation_jobs_athlete_client_request_uidx on public.generation_jobs (athlete_id, client_request_id);
create unique index if not exists generation_jobs_one_active_job_per_athlete on public.generation_jobs (athlete_id) where status in ('queued', 'running');
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

create or replace view public.admin_athlete_rollups as
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

drop policy if exists "intakes_self_or_admin_insert" on public.athlete_intakes;
create policy "intakes_self_or_admin_insert" on public.athlete_intakes
for insert with check (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "intakes_self_or_admin_update" on public.athlete_intakes;
create policy "intakes_self_or_admin_update" on public.athlete_intakes
for update using (athlete_id = auth.uid() or public.is_admin())
with check (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "intakes_self_or_admin_delete" on public.athlete_intakes;
create policy "intakes_self_or_admin_delete" on public.athlete_intakes
for delete using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "plans_self_or_admin_select" on public.plans;
create policy "plans_self_or_admin_select" on public.plans
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "plans_self_or_admin_insert" on public.plans;
create policy "plans_self_or_admin_insert" on public.plans
for insert with check (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "plans_self_or_admin_update" on public.plans;
create policy "plans_self_or_admin_update" on public.plans
for update using (athlete_id = auth.uid() or public.is_admin())
with check (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "plans_self_or_admin_delete" on public.plans;
create policy "plans_self_or_admin_delete" on public.plans
for delete using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "generation_jobs_self_or_admin_select" on public.generation_jobs;
create policy "generation_jobs_self_or_admin_select" on public.generation_jobs
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "generation_jobs_self_or_admin_insert" on public.generation_jobs;
create policy "generation_jobs_self_or_admin_insert" on public.generation_jobs
for insert with check (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "generation_jobs_self_or_admin_update" on public.generation_jobs;
create policy "generation_jobs_self_or_admin_update" on public.generation_jobs
for update using (athlete_id = auth.uid() or public.is_admin())
with check (athlete_id = auth.uid() or public.is_admin());


drop policy if exists "generation_jobs_self_or_admin_delete" on public.generation_jobs;
create policy "generation_jobs_self_or_admin_delete" on public.generation_jobs
for delete using (athlete_id = auth.uid() or public.is_admin());
