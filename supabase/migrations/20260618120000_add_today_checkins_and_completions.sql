-- Block 4 Today/Overview persistence: athlete-local Today check-ins (with the
-- server-evaluated recommendation co-located on the row) and per-session
-- completion records.
--
-- These back the executable contracts in api/contracts/ (training_day,
-- checkin_decision, recommendation, completion). The recommendation is computed
-- server-side by api.contracts.checkin_decision.evaluate_checkin() at check-in
-- time and stored denormalised on the check-in row — it is 1:1 with the
-- check-in, so the "source check-in id" is simply the row's own id. The saved
-- plan is never mutated; these tables only record what the athlete reported and
-- what the deterministic evaluator recommended.
--
-- Keying: rows are keyed by the athlete-local TRAINING DAY (04:00 rollover, see
-- api.contracts.training_day), not the raw UTC day. Storage stays UTC-backed
-- (timestamps), but the training_day date column is the contract key.
--
-- Write path: service role only (backend). Read path: athletes read their own
-- rows, admins read everything — matching daily_checkins/session_logs.

-- ---------------------------------------------------------------------------
-- today_checkins: one row per athlete per plan per training day. Categorical
-- inputs + red-flag safety toggles, plus the persisted recommendation.
-- ---------------------------------------------------------------------------
create table if not exists public.today_checkins (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid not null references public.plans(id) on delete cascade,
  training_day date not null,
  athlete_timezone text not null default '',
  sleep text not null check (sleep in ('poor', 'okay', 'good')),
  body text not null check (body in ('flat', 'normal', 'sharp')),
  pain text not null check (pain in ('none', 'manageable', 'high')),
  phase text not null check (phase in ('GPP', 'SPP', 'TAPER', 'REINTEGRATION')),
  active_injury text not null default 'none'
    check (active_injury in ('none', 'stable', 'worse')),
  previous_session text not null default 'none'
    check (previous_session in ('none', 'normal', 'very_hard')),
  sharp_pain boolean not null default false,
  instability boolean not null default false,
  swelling boolean not null default false,
  neurological_symptoms boolean not null default false,
  illness_symptoms boolean not null default false,
  cannot_warm_into_movement boolean not null default false,
  worse_next_day_pain boolean not null default false,
  recommendation_state text not null
    check (recommendation_state in ('train_as_planned', 'modify', 'pull_back')),
  recommendation_reason text not null default '',
  recommendation_triggers jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint today_checkins_athlete_plan_day_key unique (athlete_id, plan_id, training_day)
);

create index if not exists today_checkins_athlete_day_idx
  on public.today_checkins (athlete_id, training_day desc);

drop trigger if exists set_today_checkins_updated_at on public.today_checkins;
create trigger set_today_checkins_updated_at
  before update on public.today_checkins
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- session_completions: one row per athlete per session per training day.
-- session_id is the structured-plan/session identifier (text). started carries
-- started_at; done/modified carry completed_at; modified carries a reason.
-- ---------------------------------------------------------------------------
create table if not exists public.session_completions (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid not null references public.plans(id) on delete cascade,
  session_id text not null,
  training_day date not null,
  status text not null default 'not_started'
    check (status in ('not_started', 'started', 'done', 'modified', 'skipped')),
  session_rpe integer check (session_rpe is null or session_rpe between 1 and 10),
  pain_after integer check (pain_after is null or pain_after between 0 and 10),
  modification_reason text not null default '',
  notes text not null default '',
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint session_completions_athlete_session_day_key unique (athlete_id, session_id, training_day)
);

create index if not exists session_completions_athlete_day_idx
  on public.session_completions (athlete_id, training_day desc);

drop trigger if exists set_session_completions_updated_at on public.session_completions;
create trigger set_session_completions_updated_at
  before update on public.session_completions
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- RLS: athletes read their own rows, admins read all; writes are service-role
-- only (no insert/update/delete policies), matching daily_checkins/session_logs.
-- ---------------------------------------------------------------------------
alter table public.today_checkins enable row level security;
alter table public.session_completions enable row level security;

drop policy if exists "today_checkins_owner_select" on public.today_checkins;
create policy "today_checkins_owner_select" on public.today_checkins
for select using (athlete_id = auth.uid() or public.is_admin());

drop policy if exists "session_completions_owner_select" on public.session_completions;
create policy "session_completions_owner_select" on public.session_completions
for select using (athlete_id = auth.uid() or public.is_admin());

revoke all on public.today_checkins from anon;
revoke all on public.session_completions from anon;

revoke insert, update, delete on public.today_checkins from authenticated;
revoke insert, update, delete on public.session_completions from authenticated;

grant select on public.today_checkins to authenticated;
grant select on public.session_completions to authenticated;

grant all on public.today_checkins to service_role;
grant all on public.session_completions to service_role;
