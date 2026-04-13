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

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null unique,
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
  manual_injury_review_required boolean not null default false,
  approved_for_stage2 boolean not null default false,
  approved_for_stage2_by text,
  approved_for_stage2_at timestamptz,
  approval_reason text,
  liability_disclaimer_acknowledged boolean not null default false,
  stage2_override_source text,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.generation_jobs (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  client_request_id text not null,
  source text not null default 'self_service',
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

alter table public.plans add column if not exists draft_plan_text text not null default '';
alter table public.plans add column if not exists final_plan_text text not null default '';
alter table public.plans add column if not exists plan_name text not null default '';
alter table public.plans add column if not exists stage2_retry_text text not null default '';
alter table public.plans add column if not exists stage2_validator_report jsonb not null default '{}'::jsonb;
alter table public.plans add column if not exists stage2_status text not null default '';
alter table public.plans add column if not exists stage2_attempt_count integer not null default 0;
alter table public.plans add column if not exists parsing_metadata jsonb not null default '{}'::jsonb;
alter table public.plans add column if not exists manual_injury_review_required boolean not null default false;
alter table public.plans add column if not exists approved_for_stage2 boolean not null default false;
alter table public.plans add column if not exists approved_for_stage2_by text;
alter table public.plans add column if not exists approved_for_stage2_at timestamptz;
alter table public.plans add column if not exists approval_reason text;
alter table public.plans add column if not exists liability_disclaimer_acknowledged boolean not null default false;
alter table public.plans add column if not exists stage2_override_source text;
alter table public.generation_jobs add column if not exists source text not null default 'self_service';
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
alter table public.profiles add column if not exists appearance_mode text not null default 'dark';
alter table public.profiles add column if not exists avatar_url text;
alter table public.profiles add column if not exists nutrition_profile jsonb not null default '{}'::jsonb;
alter table public.athlete_intakes add column if not exists updated_at timestamptz not null default timezone('utc', now());

create index if not exists profiles_email_idx on public.profiles (email);
create index if not exists athlete_intakes_athlete_id_created_at_idx on public.athlete_intakes (athlete_id, created_at desc);
create index if not exists plans_athlete_id_created_at_idx on public.plans (athlete_id, created_at desc);
create index if not exists generation_jobs_athlete_id_created_at_idx on public.generation_jobs (athlete_id, created_at desc);
create index if not exists generation_jobs_status_heartbeat_at_idx on public.generation_jobs (status, heartbeat_at);
create unique index if not exists generation_jobs_athlete_client_request_uidx on public.generation_jobs (athlete_id, client_request_id);

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
before update on public.profiles
for each row
execute function public.set_updated_at();

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

drop policy if exists "plans_self_or_admin_select" on public.plans;
create policy "plans_self_or_admin_select" on public.plans
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "plans_self_or_admin_insert" on public.plans;
create policy "plans_self_or_admin_insert" on public.plans
for insert with check (athlete_id = auth.uid() or public.is_admin());

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

-- Grant admin role to designated admin accounts.
-- Runs on every apply; safe to re-run (idempotent).
update public.profiles
set role = 'admin'
where email in (
  'vitalvightz@gmail.com',
  'michaelokaforjr@gmail.com',
  'unlxckedmind@gmail.com',
  'frankribery@mailfence.com'
)
  and role != 'admin';
