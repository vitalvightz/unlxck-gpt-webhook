-- What an athlete actually did for one prescribed block on one training day.
--
-- The plan is never edited by a log. `prescribed` is a frozen copy of the block
-- as the athlete was shown it, and `actual` is what they report doing, in the
-- same shape (sets, reps, load, duration, distance, rounds, work, rest, effort),
-- so the two compare field by field for every load type and a log still reads
-- correctly after the plan is regenerated or deleted.
--
-- Identity:
--   block_id      which prescription this is. Server-owned and present on every
--                 loggable block (api/structured_block_identity.py), unique
--                 within its day. An open plan repeats its weekly template, so
--                 one logged occurrence is (plan_id, training_day, block_id).
--   exercise_key  which movement it is (SessionBlock.exercise_key). Best effort:
--                 NULL when the planner could not identify the block. A NULL key
--                 never blocks a log; `prescribed` keeps the name so the row can
--                 be keyed later.
--
-- Table only: no endpoint writes it yet. When one does, a `pain` reason is
-- health data and that route must require health-data consent. Only the backend
-- (service role) writes. Athletes may read their own rows; there is no client
-- insert/update/delete grant.
create table if not exists public.exercise_logs (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  -- Training history outlives the plan it was logged against.
  plan_id uuid references public.plans(id) on delete set null,
  session_id text check (session_id is null or char_length(session_id) between 1 and 200),
  block_id text not null check (char_length(block_id) between 1 and 200),
  exercise_key text
    check (
      exercise_key is null
      or (char_length(exercise_key) between 1 and 120 and exercise_key ~ '^[a-z0-9]+(-[a-z0-9]+)*$')
    ),
  -- The server's athlete-local training day, never a client-supplied date.
  training_day date not null,
  status text not null check (status in ('as_prescribed', 'modified', 'skipped')),
  -- Optional one-tap reason for a deviation.
  reason text check (reason is null or reason in ('equipment', 'fatigue', 'pain', 'felt_strong')),
  prescribed jsonb not null
    check (jsonb_typeof(prescribed) = 'object' and octet_length(prescribed::text) <= 16384),
  actual jsonb not null default '{}'::jsonb
    check (jsonb_typeof(actual) = 'object' and octet_length(actual::text) <= 8192),
  notes text not null default '' check (char_length(notes) <= 500),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  -- One log per prescribed block per training day; a correction updates it.
  constraint exercise_logs_occurrence_key unique (athlete_id, plan_id, training_day, block_id),
  -- "Modified" means something different was done, so it must say what.
  constraint exercise_logs_modified_has_actual check (status <> 'modified' or actual <> '{}'::jsonb),
  -- A reason explains a deviation; work done as prescribed has none.
  constraint exercise_logs_reason_needs_deviation check (status <> 'as_prescribed' or reason is null)
);

create index if not exists exercise_logs_athlete_day_idx
  on public.exercise_logs (athlete_id, training_day desc);

drop trigger if exists set_exercise_logs_updated_at on public.exercise_logs;
create trigger set_exercise_logs_updated_at
  before update on public.exercise_logs
  for each row execute function public.set_updated_at();

alter table public.exercise_logs enable row level security;

revoke all on public.exercise_logs from anon, authenticated;
grant select on public.exercise_logs to authenticated;
grant all on public.exercise_logs to service_role;

drop policy if exists exercise_logs_select_own on public.exercise_logs;
create policy exercise_logs_select_own on public.exercise_logs
  for select to authenticated using (athlete_id = auth.uid());
