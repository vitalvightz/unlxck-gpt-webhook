-- The database is deployed before the new backend. The currently running
-- backend sends p_calendar_date = null for calendar-scoped XP. Derive that date
-- only from persisted authoritative sources so the old backend keeps working
-- under the new integrity triggers without reopening a client-controlled path.

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
  v_previous bigint;
  v_total bigint;
  v_last_login date;
  v_award public.xp_awards%rowtype;
  v_awarded boolean := false;
  v_recent jsonb;
  v_calendar_scoped boolean;
  v_calendar_date date := p_calendar_date;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'award_athlete_xp is restricted to the backend service role'
      using errcode = '42501';
  end if;
  if p_athlete_id is null or not exists (
    select 1
    from public.profiles
    where id = p_athlete_id
      and role::text = 'athlete'
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
  end;
  if v_amount is null then
    raise exception 'unknown XP action' using errcode = '22023';
  end if;
  if v_action in ('feedback_submitted', 'feedback_with_comment') then
    raise exception 'feedback XP must use reconcile_feedback_xp'
      using errcode = '22023';
  end if;

  v_calendar_scoped := v_action in (
    'daily_login',
    'training_logged',
    'planned_session_completed',
    'full_training_week_completed',
    'readiness_checkin_completed',
    'injury_update_completed',
    'stop_decision_followed'
  );

  if v_calendar_scoped and v_calendar_date is null then
    v_calendar_date := public.xp_legacy_calendar_date(
      p_athlete_id,
      v_action,
      v_key
    );
  end if;

  -- Daily login is retired and writes no row, so an old caller with no date may
  -- still receive the zero-XP compatibility response.
  if v_action <> 'daily_login'
    and v_calendar_scoped
    and v_calendar_date is null then
    raise exception 'invalid calendar scope for XP action' using errcode = '22023';
  end if;
  if not v_calendar_scoped and v_calendar_date is not null then
    raise exception 'invalid calendar scope for XP action' using errcode = '22023';
  end if;

  if v_action = 'profile_completed' and not exists (
    select 1
    from public.profiles p
    where p.id = p_athlete_id
      and char_length(btrim(coalesce(p.full_name, ''))) > 0
      and exists (
        select 1
        from unnest(coalesce(p.technical_style, array[]::text[])) sport(value)
        where lower(btrim(sport.value)) in ('boxing', 'kickboxing', 'mma')
      )
  ) then
    raise exception 'profile activation milestone is not complete'
      using errcode = '23514';
  end if;

  if v_action = 'first_intake_completed' and not exists (
    select 1
    from public.athlete_intakes
    where athlete_id = p_athlete_id
  ) then
    raise exception 'intake activation milestone is not complete'
      using errcode = '23514';
  end if;

  if v_action = 'first_plan_ready' and not exists (
    select 1
    from public.plans
    where athlete_id = p_athlete_id
      and status in ('ready', 'publishable_with_flags')
  ) then
    raise exception 'plan activation milestone is not complete'
      using errcode = '23514';
  end if;

  if v_action = 'first_checkin_completed' and not exists (
    select 1
    from public.today_checkins
    where athlete_id = p_athlete_id
  ) then
    raise exception 'first check-in milestone is not complete'
      using errcode = '23514';
  end if;

  if v_action = 'readiness_checkin_completed' and not exists (
    select 1
    from public.today_checkins
    where athlete_id = p_athlete_id
      and training_day = v_calendar_date
  ) then
    raise exception 'daily check-in milestone is not complete'
      using errcode = '23514';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 0));

  insert into public.xp_accounts (athlete_id)
  values (p_athlete_id)
  on conflict (athlete_id) do nothing;

  select total_xp, last_daily_login_date
  into v_previous, v_last_login
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
    ) values (
      p_athlete_id,
      v_action,
      v_amount,
      v_key,
      v_calendar_date
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
    into v_total, v_last_login;
  else
    v_total := v_previous;
  end if;

  select coalesce(
    jsonb_agg(item order by awarded_at desc, id desc),
    '[]'::jsonb
  )
  into v_recent
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
      )) item
    from public.xp_awards award
    where award.athlete_id = p_athlete_id
    order by award.awarded_at desc, award.id desc
    limit 20
  ) recent;

  return jsonb_build_object(
    'state', jsonb_build_object(
      'total_xp', v_total,
      'last_daily_login_date', v_last_login,
      'recent_awards', v_recent
    ),
    'previous_total_xp', v_previous,
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

revoke all on function public.award_athlete_xp(uuid, text, text, date)
  from public, anon, authenticated;
grant execute on function public.award_athlete_xp(uuid, text, text, date)
  to service_role;
