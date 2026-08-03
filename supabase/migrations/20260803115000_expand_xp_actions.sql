-- Expand server-owned XP rewards beyond daily login/session completion.
-- Existing historical daily-login awards remain readable, but future claims
-- return without awarding XP.

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
    'first_plan_completed'
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
  );

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

  -- Daily login is retired. Preserve the endpoint contract without writing a
  -- new ledger row or increasing total XP.
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

create or replace function public.reconcile_feedback_xp(
  p_athlete_id uuid,
  p_feedback_id uuid,
  p_target_amount integer
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_key text := 'feedback:' || p_feedback_id::text;
  v_existing public.xp_awards%rowtype;
  v_previous_total bigint;
  v_total bigint;
  v_delta integer := 0;
  v_award public.xp_awards%rowtype;
  v_recent_awards jsonb;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'reconcile_feedback_xp is restricted to the backend service role'
      using errcode = '42501';
  end if;

  if p_athlete_id is null or not exists (
    select 1 from public.profiles where id = p_athlete_id
  ) then
    raise exception 'xp athlete profile not found' using errcode = '23503';
  end if;

  if p_feedback_id is null or not exists (
    select 1
    from public.beta_feedback
    where id = p_feedback_id
      and submitted_by_profile_id = p_athlete_id
  ) then
    raise exception 'feedback not found for athlete' using errcode = '23503';
  end if;

  if p_target_amount not in (1, 3) then
    raise exception 'invalid feedback XP target' using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 0));

  insert into public.xp_accounts (athlete_id)
  values (p_athlete_id)
  on conflict (athlete_id) do nothing;

  select total_xp
    into v_previous_total
  from public.xp_accounts
  where athlete_id = p_athlete_id
  for update;

  select *
    into v_existing
  from public.xp_awards
  where athlete_id = p_athlete_id
    and idempotency_key = v_key
  for update;

  if v_existing.id is null then
    insert into public.xp_awards (
      athlete_id,
      action,
      amount,
      idempotency_key,
      calendar_date
    ) values (
      p_athlete_id,
      case when p_target_amount = 3 then 'feedback_with_comment' else 'feedback_submitted' end,
      p_target_amount,
      v_key,
      null
    )
    returning * into v_award;
    v_delta := p_target_amount;
  elsif v_existing.amount < p_target_amount then
    update public.xp_awards
    set
      action = 'feedback_with_comment',
      amount = 3
    where id = v_existing.id
    returning * into v_award;
    v_delta := 3 - v_existing.amount;
  else
    v_award := v_existing;
  end if;

  if v_delta > 0 then
    update public.xp_accounts
    set
      total_xp = total_xp + v_delta,
      updated_at = clock_timestamp()
    where athlete_id = p_athlete_id
    returning total_xp into v_total;
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
      'recent_awards', v_recent_awards
    ),
    'previous_total_xp', v_previous_total,
    'awarded', v_delta > 0,
    'xp_delta', v_delta,
    'award', jsonb_strip_nulls(jsonb_build_object(
      'id', v_award.id,
      'action', v_award.action,
      'amount', v_award.amount,
      'awarded_at', v_award.awarded_at
    ))
  );
end;
$$;
