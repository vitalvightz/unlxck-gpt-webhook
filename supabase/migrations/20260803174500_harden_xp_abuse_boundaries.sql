-- Harden XP against repeated activation, plan regeneration and action spam.
-- This migration changes no existing totals. It adds independent database
-- boundaries beneath the backend-owned award hooks.

create unique index if not exists xp_awards_one_time_action_per_athlete
  on public.xp_awards (athlete_id, action)
  where action in (
    'profile_completed',
    'first_intake_completed',
    'first_plan_ready',
    'first_checkin_completed',
    'first_plan_completed'
  );

create unique index if not exists xp_awards_one_daily_action_per_athlete
  on public.xp_awards (athlete_id, action, calendar_date)
  where action in (
    'full_training_week_completed',
    'readiness_checkin_completed',
    'injury_update_completed',
    'stop_decision_followed'
  ) and calendar_date is not null;

alter table public.xp_awards
  drop constraint if exists xp_awards_calendar_scope_check;

alter table public.xp_awards
  add constraint xp_awards_calendar_scope_check check (
    (
      action in (
        'daily_login',
        'training_logged',
        'planned_session_completed',
        'full_training_week_completed',
        'readiness_checkin_completed',
        'injury_update_completed',
        'stop_decision_followed',
        'feedback_submitted',
        'feedback_with_comment'
      )
      and calendar_date is not null
    )
    or
    (
      action not in (
        'daily_login',
        'training_logged',
        'planned_session_completed',
        'full_training_week_completed',
        'readiness_checkin_completed',
        'injury_update_completed',
        'stop_decision_followed',
        'feedback_submitted',
        'feedback_with_comment'
      )
      and calendar_date is null
    )
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
  v_completion_id uuid;
  v_plan_id uuid;
  v_daily_count integer := 0;
  v_calendar_scoped boolean;
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
    else null
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

  if v_calendar_scoped and p_calendar_date is null then
    raise exception 'calendar date is required for this XP action'
      using errcode = '22023';
  end if;
  if not v_calendar_scoped and p_calendar_date is not null then
    raise exception 'calendar date is not valid for this XP action'
      using errcode = '22023';
  end if;

  -- One-time activation awards must be supported by persisted state. This is
  -- independent of the idempotency-key format used by application code.
  if v_action = 'profile_completed' and not exists (
    select 1
    from public.profiles p
    where p.id = p_athlete_id
      and char_length(btrim(coalesce(p.full_name, ''))) > 0
      and exists (
        select 1
        from unnest(coalesce(p.technical_style, array[]::text[])) as sport(value)
        where lower(btrim(sport.value)) in ('boxing', 'kickboxing', 'mma')
      )
  ) then
    raise exception 'profile activation milestone is not complete'
      using errcode = '23514';
  end if;

  if v_action = 'first_intake_completed' and not exists (
    select 1 from public.athlete_intakes where athlete_id = p_athlete_id
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
    select 1 from public.today_checkins where athlete_id = p_athlete_id
  ) then
    raise exception 'first check-in milestone is not complete'
      using errcode = '23514';
  end if;

  if v_action = 'readiness_checkin_completed' and not exists (
    select 1
    from public.today_checkins
    where athlete_id = p_athlete_id
      and training_day = p_calendar_date
  ) then
    raise exception 'daily check-in milestone is not complete'
      using errcode = '23514';
  end if;

  -- Session awards must point at a real terminal completion belonging to the
  -- athlete on the same training day. Two sessions per day is the maximum
  -- currently emitted by the production plan schema; the cap blocks switching
  -- through generated plans to create an unbounded XP loop.
  if v_action in ('training_logged', 'planned_session_completed') then
    if split_part(v_key, ':', 1) <> v_action then
      raise exception 'invalid session XP key' using errcode = '22023';
    end if;
    begin
      v_completion_id := split_part(v_key, ':', 2)::uuid;
    exception when invalid_text_representation then
      raise exception 'invalid session completion id' using errcode = '22023';
    end;
    if not exists (
      select 1
      from public.session_completions
      where id = v_completion_id
        and athlete_id = p_athlete_id
        and training_day = p_calendar_date
        and status in ('done', 'modified')
    ) then
      raise exception 'session completion is not eligible for XP'
        using errcode = '23514';
    end if;
  end if;

  if v_action = 'full_training_week_completed' then
    if split_part(v_key, ':', 1) <> 'full-week' then
      raise exception 'invalid full-week XP key' using errcode = '22023';
    end if;
    begin
      v_plan_id := split_part(v_key, ':', 2)::uuid;
    exception when invalid_text_representation then
      raise exception 'invalid full-week plan id' using errcode = '22023';
    end;
    if not exists (
      select 1
      from public.plans
      where id = v_plan_id
        and athlete_id = p_athlete_id
        and status in ('ready', 'publishable_with_flags')
    ) then
      raise exception 'full-week plan is not eligible for XP'
        using errcode = '23514';
    end if;
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
    if v_action in ('training_logged', 'planned_session_completed') then
      select count(*)
        into v_daily_count
      from public.xp_awards
      where athlete_id = p_athlete_id
        and action = v_action
        and calendar_date = p_calendar_date;
    end if;

    if v_daily_count < 2 then
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
        p_calendar_date
      )
      on conflict do nothing
      returning * into v_award;

      v_awarded := v_award.id is not null;
    end if;
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
  v_feedback_created_at timestamptz;
  v_calendar_date date;
  v_daily_count integer := 0;
  v_cap_reached boolean := false;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'reconcile_feedback_xp is restricted to the backend service role'
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

  select created_at
    into v_feedback_created_at
  from public.beta_feedback
  where id = p_feedback_id
    and submitted_by_profile_id = p_athlete_id;

  if v_feedback_created_at is null then
    raise exception 'feedback not found for athlete' using errcode = '23503';
  end if;

  if p_target_amount not in (1, 3) then
    raise exception 'invalid feedback XP target' using errcode = '22023';
  end if;

  -- UTC makes the cap deterministic and immune to client timezone changes.
  v_calendar_date := (v_feedback_created_at at time zone 'UTC')::date;

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
    select count(*)
      into v_daily_count
    from public.xp_awards
    where athlete_id = p_athlete_id
      and action in ('feedback_submitted', 'feedback_with_comment')
      and calendar_date = v_calendar_date;

    if v_daily_count >= 3 then
      v_cap_reached := true;
    else
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
        v_calendar_date
      )
      returning * into v_award;
      v_delta := p_target_amount;
    end if;
  elsif v_existing.amount < p_target_amount then
    -- A useful comment may upgrade an existing 1 XP record even after the daily
    -- new-record cap is reached. It cannot create a fourth feedback award.
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
    'cap_reached', v_cap_reached,
    'award', case
      when v_award.id is not null then jsonb_strip_nulls(jsonb_build_object(
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
  v_plan_status text;
  v_plan_type text;
  v_fight_date date;
  v_structured_plan jsonb;
  v_milestone public.plan_milestones%rowtype;
  v_inserted boolean := false;
  v_award_result jsonb;
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'record_plan_milestone is restricted to the backend service role'
      using errcode = '42501';
  end if;

  select status, fight_date, structured_plan
    into v_plan_status, v_fight_date, v_structured_plan
  from public.plans
  where id = p_plan_id
    and athlete_id = p_athlete_id;

  if v_plan_status is null then
    raise exception 'plan not found for athlete' using errcode = '23503';
  end if;
  if v_plan_status not in ('ready', 'publishable_with_flags') then
    raise exception 'plan is not eligible for progress XP' using errcode = '23514';
  end if;

  v_plan_type := lower(btrim(coalesce(
    v_structured_plan -> 'plan_metadata' ->> 'plan_type',
    ''
  )));

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

  if v_type in ('plan_completed', 'camp_completed') and (
    v_plan_type = '' or v_plan_type = 'open_ongoing_system'
  ) then
    raise exception 'open or untyped plans cannot complete lifecycle XP'
      using errcode = '23514';
  end if;

  if v_type = 'camp_completed' and (
    v_plan_type <> 'fight_camp' or v_fight_date is null
  ) then
    raise exception 'camp milestone requires a dated fight camp'
      using errcode = '23514';
  end if;

  v_action := case v_type
    when 'phase_completed' then 'phase_completed'
    when 'plan_completed' then 'first_plan_completed'
    when 'camp_completed' then 'camp_completed'
  end;

  -- Regenerating a plan for the same fight must not create another phase/camp
  -- reward. Milestone history remains per plan, but XP scope follows the fight.
  v_xp_key := case
    when v_type = 'phase_completed'
      and v_plan_type = 'fight_camp'
      and v_fight_date is not null
      then 'phase-completed:' || p_athlete_id::text || ':' || v_fight_date::text || ':' || lower(v_phase)
    when v_type = 'phase_completed'
      then 'phase-completed:' || p_plan_id::text || ':' || v_key
    when v_type = 'plan_completed'
      then 'first-plan-completed:' || p_athlete_id::text
    when v_type = 'camp_completed'
      then 'camp-completed:' || p_athlete_id::text || ':' || v_fight_date::text
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

revoke all on function public.award_athlete_xp(uuid, text, text, date)
  from public, anon, authenticated;
grant execute on function public.award_athlete_xp(uuid, text, text, date)
  to service_role;

revoke all on function public.reconcile_feedback_xp(uuid, uuid, integer)
  from public, anon, authenticated;
grant execute on function public.reconcile_feedback_xp(uuid, uuid, integer)
  to service_role;

revoke all on function public.record_plan_milestone(uuid, uuid, text, text, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.record_plan_milestone(uuid, uuid, text, text, text, jsonb)
  to service_role;
