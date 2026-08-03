-- Persist authoritative plan lifecycle milestones and award their XP atomically.

alter table public.xp_awards
  drop constraint if exists xp_awards_action_check;

alter table public.xp_awards
  add constraint xp_awards_action_check check (action in (
    'daily_login',
    'training_logged',
    'planned_session_completed',
    'recommended_fighter_content_watched',
    'full_training_week_completed',
    'profile_completed',
    'first_intake_completed',
    'first_plan_ready',
    'first_checkin_completed',
    'readiness_checkin_completed',
    'injury_update_completed',
    'stop_decision_followed',
    'feedback_submitted',
    'feedback_with_comment',
    'first_plan_completed',
    'phase_completed',
    'camp_completed'
  ));

alter table public.xp_awards
  drop constraint if exists xp_awards_amount_check;

alter table public.xp_awards
  add constraint xp_awards_amount_check check (
    (action = 'daily_login' and amount = 10)
    or (action = 'training_logged' and amount = 25)
    or (action = 'planned_session_completed' and amount = 50)
    or (action = 'recommended_fighter_content_watched' and amount = 10)
    or (action = 'full_training_week_completed' and amount = 100)
    or (action = 'profile_completed' and amount = 25)
    or (action = 'first_intake_completed' and amount = 50)
    or (action = 'first_plan_ready' and amount = 100)
    or (action = 'first_checkin_completed' and amount = 25)
    or (action = 'readiness_checkin_completed' and amount = 10)
    or (action = 'injury_update_completed' and amount = 10)
    or (action = 'stop_decision_followed' and amount = 15)
    or (action = 'feedback_submitted' and amount = 1)
    or (action = 'feedback_with_comment' and amount = 3)
    or (action = 'first_plan_completed' and amount = 250)
    or (action = 'phase_completed' and amount = 200)
    or (action = 'camp_completed' and amount = 500)
  );

create table if not exists public.plan_milestones (
  id uuid primary key default gen_random_uuid(),
  athlete_id uuid not null references public.profiles(id) on delete cascade,
  plan_id uuid not null references public.plans(id) on delete cascade,
  milestone_type text not null check (
    milestone_type in ('phase_completed', 'plan_completed', 'camp_completed')
  ),
  milestone_key text not null check (
    char_length(btrim(milestone_key)) between 1 and 160
  ),
  phase_label text check (
    phase_label is null or char_length(btrim(phase_label)) between 1 and 32
  ),
  metadata jsonb not null default '{}'::jsonb check (
    jsonb_typeof(metadata) = 'object' and pg_column_size(metadata) <= 16384
  ),
  completed_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique (athlete_id, plan_id, milestone_type, milestone_key),
  check (
    (milestone_type = 'phase_completed' and phase_label is not null)
    or (milestone_type <> 'phase_completed' and phase_label is null)
  )
);

create index if not exists plan_milestones_athlete_completed_idx
  on public.plan_milestones (athlete_id, completed_at desc);

create index if not exists plan_milestones_plan_completed_idx
  on public.plan_milestones (plan_id, completed_at desc);

alter table public.plan_milestones enable row level security;

revoke all on table public.plan_milestones from anon, authenticated;
grant select on table public.plan_milestones to authenticated;
grant all on table public.plan_milestones to service_role;

drop policy if exists plan_milestones_select_own on public.plan_milestones;
create policy plan_milestones_select_own
  on public.plan_milestones
  for select
  to authenticated
  using (athlete_id = auth.uid());

create or replace function public.award_athlete_xp(
  p_athlete_id uuid,
  p_action text,
  p_idempotency_key text,
  p_calendar_date date default null
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_action text := btrim(coalesce(p_action, ''));
  v_key text := btrim(coalesce(p_idempotency_key, ''));
  v_amount integer;
  v_previous_total bigint;
  v_total bigint;
  v_last_daily_login_date date;
  v_award public.xp_awards%rowtype;
  v_awarded boolean := false;
  v_recent_awards jsonb;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'award_athlete_xp is restricted to the backend service role'
      using errcode = '42501';
  end if;

  if p_athlete_id is null or not exists (
    select 1 from public.profiles where id = p_athlete_id
  ) then
    raise exception 'xp athlete profile not found' using errcode = '23503';
  end if;

  if char_length(v_key) not between 1 and 200 then
    raise exception 'invalid XP idempotency key' using errcode = '22023';
  end if;

  v_amount := case v_action
    when 'daily_login' then 0
    when 'training_logged' then 25
    when 'planned_session_completed' then 50
    when 'recommended_fighter_content_watched' then 10
    when 'full_training_week_completed' then 100
    when 'profile_completed' then 25
    when 'first_intake_completed' then 50
    when 'first_plan_ready' then 100
    when 'first_checkin_completed' then 25
    when 'readiness_checkin_completed' then 10
    when 'injury_update_completed' then 10
    when 'stop_decision_followed' then 15
    when 'feedback_submitted' then 1
    when 'feedback_with_comment' then 3
    when 'first_plan_completed' then 250
    when 'phase_completed' then 200
    when 'camp_completed' then 500
    else null
  end;

  if v_amount is null then
    raise exception 'unknown XP action' using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 0));

  insert into public.xp_accounts (athlete_id)
  values (p_athlete_id)
  on conflict (athlete_id) do nothing;

  select total_xp, last_daily_login_date
    into v_previous_total, v_last_daily_login_date
  from public.xp_accounts
  where athlete_id = p_athlete_id
  for update;

  if v_action <> 'daily_login' then
    insert into public.xp_awards (
      athlete_id,
      action,
      amount,
      idempotency_key,
      calendar_date
    )
    values (
      p_athlete_id,
      v_action,
      v_amount,
      v_key,
      null
    )
    on conflict do nothing
    returning * into v_award;

    v_awarded := v_award.id is not null;
  end if;

  if v_awarded then
    update public.xp_accounts
    set
      total_xp = total_xp + v_amount,
      updated_at = clock_timestamp()
    where athlete_id = p_athlete_id
    returning total_xp, last_daily_login_date
      into v_total, v_last_daily_login_date;
  else
    v_total := v_previous_total;
  end if;

  select coalesce(
    jsonb_agg(recent.item order by recent.awarded_at desc, recent.id desc),
    '[]'::jsonb
  )
  into v_recent_awards
  from (
    select
      award.id,
      award.awarded_at,
      jsonb_strip_nulls(jsonb_build_object(
        'id', award.id,
        'action', award.action,
        'amount', award.amount,
        'awarded_at', award.awarded_at,
        'calendar_date', award.calendar_date
      )) as item
    from public.xp_awards as award
    where award.athlete_id = p_athlete_id
    order by award.awarded_at desc, award.id desc
    limit 20
  ) as recent;

  return jsonb_build_object(
    'state', jsonb_build_object(
      'total_xp', v_total,
      'last_daily_login_date', v_last_daily_login_date,
      'recent_awards', v_recent_awards
    ),
    'previous_total_xp', v_previous_total,
    'awarded', v_awarded,
    'award', case
      when v_awarded then jsonb_strip_nulls(jsonb_build_object(
        'id', v_award.id,
        'action', v_award.action,
        'amount', v_award.amount,
        'awarded_at', v_award.awarded_at,
        'calendar_date', v_award.calendar_date
      ))
      else 'null'::jsonb
    end
  );
end;
$$;

create or replace function public.record_plan_milestone(
  p_athlete_id uuid,
  p_plan_id uuid,
  p_milestone_type text,
  p_milestone_key text,
  p_phase_label text default null,
  p_metadata jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_type text := btrim(coalesce(p_milestone_type, ''));
  v_key text := btrim(coalesce(p_milestone_key, ''));
  v_phase text := nullif(btrim(coalesce(p_phase_label, '')), '');
  v_action text;
  v_xp_key text;
  v_milestone public.plan_milestones%rowtype;
  v_inserted boolean := false;
  v_award_result jsonb;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'record_plan_milestone is restricted to the backend service role'
      using errcode = '42501';
  end if;

  if p_athlete_id is null or p_plan_id is null or not exists (
    select 1
    from public.plans
    where id = p_plan_id
      and athlete_id = p_athlete_id
  ) then
    raise exception 'plan not found for athlete' using errcode = '23503';
  end if;

  if v_type not in ('phase_completed', 'plan_completed', 'camp_completed') then
    raise exception 'invalid plan milestone type' using errcode = '22023';
  end if;

  if char_length(v_key) not between 1 and 160 then
    raise exception 'invalid plan milestone key' using errcode = '22023';
  end if;

  if v_type = 'phase_completed' and (
    v_phase is null or char_length(v_phase) > 32
  ) then
    raise exception 'phase milestone requires a valid phase label' using errcode = '22023';
  end if;

  if v_type <> 'phase_completed' and v_phase is not null then
    raise exception 'non-phase milestone cannot carry a phase label' using errcode = '22023';
  end if;

  if jsonb_typeof(coalesce(p_metadata, '{}'::jsonb)) <> 'object'
    or pg_column_size(coalesce(p_metadata, '{}'::jsonb)) > 16384 then
    raise exception 'invalid plan milestone metadata' using errcode = '22023';
  end if;

  v_action := case v_type
    when 'phase_completed' then 'phase_completed'
    when 'plan_completed' then 'first_plan_completed'
    when 'camp_completed' then 'camp_completed'
  end;

  v_xp_key := case v_type
    when 'phase_completed' then 'phase-completed:' || p_plan_id::text || ':' || v_key
    when 'plan_completed' then 'first-plan-completed:' || p_athlete_id::text
    when 'camp_completed' then 'camp-completed:' || p_plan_id::text
  end;

  insert into public.plan_milestones (
    athlete_id,
    plan_id,
    milestone_type,
    milestone_key,
    phase_label,
    metadata
  ) values (
    p_athlete_id,
    p_plan_id,
    v_type,
    v_key,
    v_phase,
    coalesce(p_metadata, '{}'::jsonb)
  )
  on conflict (athlete_id, plan_id, milestone_type, milestone_key) do nothing
  returning * into v_milestone;

  v_inserted := v_milestone.id is not null;

  if not v_inserted then
    select *
      into v_milestone
    from public.plan_milestones
    where athlete_id = p_athlete_id
      and plan_id = p_plan_id
      and milestone_type = v_type
      and milestone_key = v_key;
  end if;

  -- The award is idempotent and occurs in the same transaction as milestone
  -- persistence. Retrying repairs a manually inserted milestone without
  -- creating duplicate XP.
  v_award_result := public.award_athlete_xp(
    p_athlete_id,
    v_action,
    v_xp_key,
    null
  );

  return jsonb_build_object(
    'milestone_inserted', v_inserted,
    'milestone', jsonb_strip_nulls(jsonb_build_object(
      'id', v_milestone.id,
      'plan_id', v_milestone.plan_id,
      'milestone_type', v_milestone.milestone_type,
      'milestone_key', v_milestone.milestone_key,
      'phase_label', v_milestone.phase_label,
      'metadata', v_milestone.metadata,
      'completed_at', v_milestone.completed_at
    )),
    'award_result', v_award_result
  );
end;
$$;

revoke all on function public.record_plan_milestone(
  uuid, uuid, text, text, text, jsonb
) from public, anon, authenticated;
grant execute on function public.record_plan_milestone(
  uuid, uuid, text, text, text, jsonb
) to service_role;
