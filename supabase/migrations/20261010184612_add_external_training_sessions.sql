-- Completed manual work only. No plan FK: regeneration/deletion cannot erase it.
create table if not exists public.external_training_sessions (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  client_request_id uuid not null,
  request_fingerprint text not null check (request_fingerprint ~ '^[a-f0-9]{64}$'),
  training_day date not null,
  activity text not null check (activity in ('sparring', 'boxing', 'roadwork', 'strength', 'conditioning', 'other')),
  duration_minutes integer not null check (duration_minutes between 1 and 600),
  effort text not null check (effort in ('easy', 'moderate', 'hard')),
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint external_training_sessions_request_key unique (athlete_id, client_request_id)
);
create index if not exists external_training_sessions_athlete_day_idx
  on public.external_training_sessions (athlete_id, training_day desc, created_at desc)
  where deleted_at is null;
drop trigger if exists set_external_training_sessions_updated_at on public.external_training_sessions;
create trigger set_external_training_sessions_updated_at
  before update on public.external_training_sessions
  for each row execute function public.set_updated_at();
alter table public.external_training_sessions enable row level security;
revoke all on public.external_training_sessions from anon, authenticated;
grant select on public.external_training_sessions to authenticated;
grant all on public.external_training_sessions to service_role;
drop policy if exists external_training_sessions_select_own on public.external_training_sessions;
create policy external_training_sessions_select_own on public.external_training_sessions
  for select to authenticated using (athlete_id = (select auth.uid()) and deleted_at is null);
