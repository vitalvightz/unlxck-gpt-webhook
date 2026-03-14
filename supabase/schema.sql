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
  onboarding_draft jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.athlete_intakes (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  fight_date date,
  technical_style text[] not null default '{}',
  intake jsonb not null,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.plans (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  intake_id uuid references public.athlete_intakes(id) on delete set null,
  fight_date date,
  technical_style text[] not null default '{}',
  full_name text not null default '',
  status text not null default 'generated',
  plan_text text not null default '',
  coach_notes text not null default '',
  pdf_url text,
  why_log jsonb not null default '{}'::jsonb,
  planning_brief text,
  stage2_payload jsonb,
  stage2_handoff_text text not null default '',
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists profiles_email_idx on public.profiles (email);
create index if not exists athlete_intakes_athlete_id_created_at_idx on public.athlete_intakes (athlete_id, created_at desc);
create index if not exists plans_athlete_id_created_at_idx on public.plans (athlete_id, created_at desc);

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
before update on public.profiles
for each row
execute function public.set_updated_at();

alter table public.profiles enable row level security;
alter table public.athlete_intakes enable row level security;
alter table public.plans enable row level security;

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

drop policy if exists "plans_self_or_admin_select" on public.plans;
create policy "plans_self_or_admin_select" on public.plans
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "plans_self_or_admin_insert" on public.plans;
create policy "plans_self_or_admin_insert" on public.plans
for insert with check (athlete_id = auth.uid() or public.is_admin());