-- Post-sparring entries logged from the round timer (api/routes/today.py
-- POST /api/today/sparring-log). One row per logged block of rounds; an athlete
-- may spar more than once a day, so there is no per-day uniqueness.
--
-- head_contact and rocked are health data: the route requires health-data
-- consent, and only the backend (service role) writes. Athletes may read their
-- own rows; there is no client insert/update/delete grant.
create table if not exists public.sparring_logs (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid references public.plans(id) on delete set null,
  session_id text check (session_id is null or char_length(session_id) <= 200),
  -- The server's athlete-local training day, never a client-supplied date.
  training_day date not null,
  source text not null check (source in ('contact', 'session', 'free')),
  -- What the plan called for (null when the plan did not say).
  planned_intensity text
    check (planned_intensity is null or planned_intensity in ('hard', 'light', 'technical', 'contact')),
  -- What the athlete reports actually happened.
  intensity text not null check (intensity in ('light', 'medium', 'hard')),
  rounds_completed integer not null check (rounds_completed between 0 and 30),
  round_seconds integer check (round_seconds is null or round_seconds between 5 and 3600),
  head_contact text not null check (head_contact in ('none', 'light', 'heavy')),
  rocked boolean not null default false,
  notes text not null default '' check (char_length(notes) <= 1000),
  created_at timestamptz not null default now()
);

create index if not exists sparring_logs_athlete_day_idx
  on public.sparring_logs (athlete_id, training_day desc);

alter table public.sparring_logs enable row level security;

revoke insert, update, delete on public.sparring_logs from anon, authenticated;
revoke select on public.sparring_logs from anon;
grant select on public.sparring_logs to authenticated;

drop policy if exists sparring_logs_select_own on public.sparring_logs;
create policy sparring_logs_select_own on public.sparring_logs
  for select to authenticated using (athlete_id = auth.uid());

-- One transaction for a sparring entry and, when the athlete reports being
-- rocked or dropped, its pending admin review. A rocked report must never be
-- saved without a durable review: if either insert fails, neither is kept and
-- the API returns an error instead of acknowledging the report.
create or replace function public.record_sparring_log(
  p_athlete_id uuid,
  p_log jsonb,
  p_review_reason text
)
returns jsonb
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_log public.sparring_logs%rowtype;
  v_review public.admin_reviews%rowtype;
  v_rocked boolean := coalesce((p_log->>'rocked')::boolean, false);
begin
  if v_rocked and coalesce(btrim(p_review_reason), '') = '' then
    raise exception 'record_sparring_log: rocked report requires a review reason'
      using errcode = '22023';
  end if;

  insert into public.sparring_logs (
    athlete_id, plan_id, session_id, training_day, source, planned_intensity,
    intensity, rounds_completed, round_seconds, head_contact, rocked, notes
  ) values (
    p_athlete_id,
    nullif(p_log->>'plan_id', '')::uuid,
    nullif(p_log->>'session_id', ''),
    (p_log->>'training_day')::date,
    p_log->>'source',
    nullif(p_log->>'planned_intensity', ''),
    p_log->>'intensity',
    (p_log->>'rounds_completed')::integer,
    nullif(p_log->>'round_seconds', '')::integer,
    p_log->>'head_contact',
    v_rocked,
    coalesce(p_log->>'notes', '')
  )
  returning * into v_log;

  if v_rocked then
    insert into public.admin_reviews (athlete_id, reason, status)
    values (p_athlete_id, p_review_reason, 'pending')
    returning * into v_review;
  end if;

  return jsonb_build_object(
    'log', to_jsonb(v_log),
    'review', case when v_rocked then to_jsonb(v_review) else null end
  );
end;
$$;

revoke all on function public.record_sparring_log(uuid, jsonb, text) from public, anon, authenticated;
grant execute on function public.record_sparring_log(uuid, jsonb, text) to service_role;
