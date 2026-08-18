-- Repository snapshot of the live, server-authoritative streak tables.
create table if not exists public.athlete_streaks (
  athlete_id uuid primary key references public.profiles(id) on delete cascade,
  login_current integer not null default 0 check (login_current >= 0),
  login_best integer not null default 0 check (login_best >= login_current),
  login_last_active_date date,
  adherence_current integer not null default 0 check (adherence_current >= 0),
  adherence_best integer not null default 0 check (adherence_best >= adherence_current),
  adherence_last_qualifying_day date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.athlete_daily_activity (
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  activity_date date not null,
  first_seen_at timestamptz not null default now(),
  primary key (athlete_id, activity_date)
);

alter table public.athlete_streaks enable row level security;
alter table public.athlete_daily_activity enable row level security;

revoke insert, update, delete on public.athlete_streaks from authenticated;
revoke insert, update, delete on public.athlete_daily_activity from authenticated;
grant select on public.athlete_streaks to authenticated;
grant select on public.athlete_daily_activity to authenticated;

drop policy if exists athlete_streaks_select_own on public.athlete_streaks;
create policy athlete_streaks_select_own on public.athlete_streaks
  for select to authenticated using (athlete_id = auth.uid());

drop policy if exists athlete_daily_activity_select_own on public.athlete_daily_activity;
create policy athlete_daily_activity_select_own on public.athlete_daily_activity
  for select to authenticated using (athlete_id = auth.uid());
