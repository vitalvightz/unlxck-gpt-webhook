-- Plan-free daily readiness check-ins (api/routes/today.py POST /api/today/checkin).
--
-- An athlete who trains without an UNLXCK programme gets the same deterministic
-- check-in. Their row has no plan and no camp phase: neither is fabricated.
-- The check constraint keeps the two in step, so a planned row always carries
-- a real phase and a plan-free row can never claim one.
--
-- Uniqueness: planned rows keep today_checkins_athlete_plan_day_key. A unique
-- constraint treats NULL plan_ids as distinct, so it cannot deduplicate
-- plan-free rows; a partial unique index gives exactly one plan-free row per
-- athlete-local training day. PostgREST cannot target a partial index, so
-- plan-free writes go through upsert_plan_free_today_checkin.
--
-- Existing rows all have a plan and a phase and are left untouched. Plan-scoped
-- triggers and XP checks match on plan_id, which a plan-free row never
-- satisfies. Repeatable: every step is guarded.

alter table public.today_checkins alter column plan_id drop not null;
alter table public.today_checkins alter column phase drop not null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'today_checkins_phase_matches_plan'
      and conrelid = 'public.today_checkins'::regclass) then
    alter table public.today_checkins
      add constraint today_checkins_phase_matches_plan check ((plan_id is null) = (phase is null));
  end if;
end
$$;

create unique index if not exists today_checkins_athlete_plan_free_day_key
  on public.today_checkins (athlete_id, training_day) where plan_id is null;

create or replace function public.upsert_plan_free_today_checkin(
  p_athlete_id uuid,
  p_fields jsonb
)
returns public.today_checkins
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_row public.today_checkins%rowtype;
begin
  insert into public.today_checkins (
    athlete_id, plan_id, phase, training_day, athlete_timezone,
    sleep, body, pain, active_injury, previous_session,
    sharp_pain, instability, swelling, neurological_symptoms, illness_symptoms,
    cannot_warm_into_movement, worse_next_day_pain,
    recommendation_state, recommendation_reason, recommendation_triggers
  ) values (
    p_athlete_id, null, null,
    (p_fields->>'training_day')::date,
    coalesce(p_fields->>'athlete_timezone', ''),
    p_fields->>'sleep', p_fields->>'body', p_fields->>'pain',
    coalesce(p_fields->>'active_injury', 'none'),
    coalesce(p_fields->>'previous_session', 'none'),
    coalesce((p_fields->>'sharp_pain')::boolean, false),
    coalesce((p_fields->>'instability')::boolean, false),
    coalesce((p_fields->>'swelling')::boolean, false),
    coalesce((p_fields->>'neurological_symptoms')::boolean, false),
    coalesce((p_fields->>'illness_symptoms')::boolean, false),
    coalesce((p_fields->>'cannot_warm_into_movement')::boolean, false),
    coalesce((p_fields->>'worse_next_day_pain')::boolean, false),
    p_fields->>'recommendation_state',
    coalesce(p_fields->>'recommendation_reason', ''),
    coalesce(p_fields->'recommendation_triggers', '[]'::jsonb)
  )
  on conflict (athlete_id, training_day) where plan_id is null do update set
    athlete_timezone = excluded.athlete_timezone,
    sleep = excluded.sleep,
    body = excluded.body,
    pain = excluded.pain,
    active_injury = excluded.active_injury,
    previous_session = excluded.previous_session,
    sharp_pain = excluded.sharp_pain,
    instability = excluded.instability,
    swelling = excluded.swelling,
    neurological_symptoms = excluded.neurological_symptoms,
    illness_symptoms = excluded.illness_symptoms,
    cannot_warm_into_movement = excluded.cannot_warm_into_movement,
    worse_next_day_pain = excluded.worse_next_day_pain,
    recommendation_state = excluded.recommendation_state,
    recommendation_reason = excluded.recommendation_reason,
    recommendation_triggers = excluded.recommendation_triggers
  returning * into v_row;
  return v_row;
end;
$$;

revoke all on function public.upsert_plan_free_today_checkin(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.upsert_plan_free_today_checkin(uuid, jsonb) to service_role;
