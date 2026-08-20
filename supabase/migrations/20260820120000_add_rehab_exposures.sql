-- Injury-specific rehab observations. These rows do not assert tolerance or
-- stage eligibility; interpretation belongs to later condition-specific logic.
alter table public.injury_flags
  add column if not exists episode_id uuid not null default gen_random_uuid();

create unique index if not exists injury_flags_id_athlete_episode_idx
  on public.injury_flags (id, athlete_id, episode_id);

create table if not exists public.rehab_exposures (
  id uuid primary key,
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  injury_id uuid not null,
  injury_episode_id uuid not null,
  drill_id text not null check (drill_id ~ '^[a-z0-9]+(_[a-z0-9]+)*$'),
  body_region text not null,
  side text not null check (side in ('left', 'right', 'bilateral', 'unknown')),
  demand jsonb not null check (jsonb_typeof(demand) = 'object'),
  prescribed_dose jsonb check (prescribed_dose is null or jsonb_typeof(prescribed_dose) = 'object'),
  completed_dose jsonb not null check (jsonb_typeof(completed_dose) = 'object'),
  response jsonb not null default '{}'::jsonb check (jsonb_typeof(response) = 'object'),
  evidence_source text not null check (evidence_source in (
    'athlete_logged_rehab', 'clinician_logged_rehab', 'coach_logged_rehab'
  )),
  occurred_at timestamptz not null,
  recorded_at timestamptz not null,
  created_at timestamptz not null default now(),
  foreign key (injury_id, athlete_id, injury_episode_id)
    references public.injury_flags (id, athlete_id, episode_id) on delete cascade
);

create index if not exists rehab_exposures_injury_episode_occurred_idx
  on public.rehab_exposures (injury_id, injury_episode_id, occurred_at desc);

alter table public.rehab_exposures enable row level security;

drop policy if exists "rehab_exposures_owner_select" on public.rehab_exposures;
create policy "rehab_exposures_owner_select" on public.rehab_exposures
  for select using (athlete_id = auth.uid());
drop policy if exists "rehab_exposures_owner_insert" on public.rehab_exposures;
create policy "rehab_exposures_owner_insert" on public.rehab_exposures
  for insert with check (athlete_id = auth.uid());
drop policy if exists "rehab_exposures_owner_update" on public.rehab_exposures;
create policy "rehab_exposures_owner_update" on public.rehab_exposures
  for update using (athlete_id = auth.uid()) with check (athlete_id = auth.uid());
drop policy if exists "rehab_exposures_owner_delete" on public.rehab_exposures;
create policy "rehab_exposures_owner_delete" on public.rehab_exposures
  for delete using (athlete_id = auth.uid());

revoke all on table public.rehab_exposures from anon;
grant select, insert, update, delete on table public.rehab_exposures to authenticated;
