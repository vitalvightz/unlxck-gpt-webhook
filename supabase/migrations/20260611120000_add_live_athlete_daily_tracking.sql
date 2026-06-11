-- Live athlete daily tracking: check-ins, session logs, injury flags,
-- adaptation notes, and the admin review queue.
--
-- This is the persistence layer that turns UNLXCK from a one-shot plan
-- generator into a daily operating system. Training weeks/sessions remain
-- derived from the persisted plan (plans.planning_brief weekly schedule);
-- the tables below record what actually happened each day and why the
-- system recommended an adjustment. Adaptation decisions are append-only
-- history: the plan itself is never silently rewritten.
--
-- Write path: service role only (backend), matching plans/athlete_intakes.
-- Read path: athletes see their own rows; admins see everything except
-- admin_reviews, which is admin-only (it is an ops queue, not athlete data).

-- ---------------------------------------------------------------------------
-- daily_checkins: one row per athlete per UTC day.
-- readiness/fatigue/soreness/sleep_quality are 1-5 self-reported scales.
-- readiness_state is the server-computed status snapshot at submission time
-- ('ready' | 'caution' | 'high_fatigue' | 'injury_flag') kept for history.
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
