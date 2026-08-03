-- Final XP hardening rollout layer.
--
-- This migration has two responsibilities:
-- 1. Keep the currently deployed pre-hardening backend compatible while the
--    database is migrated first. Legacy calls omit p_calendar_date, so derive it
--    from the persisted source rather than opening an unverified client path.
-- 2. Validate full-week XP for renewable open plans against the same concrete
--    calendar projection used by the backend.

create or replace function public.xp_try_jsonb(p_value text)
returns jsonb
language plpgsql
immutable
security invoker
set search_path = pg_catalog, public
as $$
begin
  if p_value is null or btrim(p_value) = '' then
    return '{}'::jsonb;
  end if;
  return p_value::jsonb;
exception when others then
  return '{}'::jsonb;
end;
$$;

create or replace function public.xp_weekday_offset(p_weekday text)
returns integer
language sql
immutable
security invoker
set search_path = pg_catalog, public
as $$
  select case lower(left(btrim(coalesce(p_weekday, '')), 3))
    when 'mon' then 0
    when 'tue' then 1
    when 'wed' then 2
    when 'thu' then 3
    when 'fri' then 4
    when 'sat' then 5
    when 'sun' then 6
    else null
  end
$$;

create or replace function public.xp_open_plan_anchor_date(p_plan_id uuid)
returns date
language plpgsql
stable
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_created date;
  v_brief jsonb;
  v_snapshot jsonb;
  v_basis text;
  v_weekday text;
  v_expected_isodow integer;
  v_created_isodow integer;
  v_shifted date;
begin
  select
    (plan.created_at at time zone 'UTC')::date,
    public.xp_try_jsonb(plan.planning_brief)
  into v_created, v_brief
  from public.plans as plan
  where plan.id = p_plan_id;

  if v_created is null then
    return null;
  end if;

  v_snapshot := case
    when jsonb_typeof(v_brief -> 'athlete_snapshot') = 'object'
      then v_brief -> 'athlete_snapshot'
    when jsonb_typeof(v_brief -> 'athlete_model') = 'object'
      then v_brief -> 'athlete_model'
    else '{}'::jsonb
  end;
  v_basis := lower(btrim(coalesce(v_snapshot ->> 'plan_creation_weekday_basis', '')));
  v_weekday := lower(left(btrim(coalesce(v_snapshot ->> 'plan_creation_weekday', '')), 3));
  v_expected_isodow := case v_weekday
    when 'mon' then 1
    when 'tue' then 2
    when 'wed' then 3
    when 'thu' then 4
    when 'fri' then 5
    when 'sat' then 6
    when 'sun' then 7
    else null
  end;

  if v_basis = 'athlete_local_weekday' and v_expected_isodow is not null then
    v_created_isodow := extract(isodow from v_created)::integer;
    if v_expected_isodow = case when v_created_isodow = 1 then 7 else v_created_isodow - 1 end then
      v_created := v_created - 1;
    elsif v_expected_isodow = case when v_created_isodow = 7 then 1 else v_created_isodow + 1 end then
      v_created := v_created + 1;
    end if;
  end if;

  -- Match open_plan_anchor_date(): shift three days, then take that week's Monday.
  v_shifted := v_created + 3;
  return v_shifted - (extract(isodow from v_shifted)::integer - 1);
end;
$$;

create or replace function public.xp_open_plan_week_item(
  p_plan_id uuid,
  p_week_start date,
  p_week_id text
)
returns jsonb
language plpgsql
stable
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_plan_type text;
  v_weeks jsonb;
  v_anchor date;
  v_week_count integer;
  v_week_position integer;
  v_week jsonb;
  v_base_id text;
  v_projected_id text;
begin
  select
    lower(btrim(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', ''))),
    case
      when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
        then plan.structured_plan -> 'weeks'
      else '[]'::jsonb
    end
  into v_plan_type, v_weeks
  from public.plans as plan
  where plan.id = p_plan_id;

  if v_plan_type <> 'open_ongoing_system'
    or p_week_start is null
    or extract(isodow from p_week_start)::integer <> 1 then
    return null;
  end if;

  v_anchor := public.xp_open_plan_anchor_date(p_plan_id);
  if v_anchor is null or p_week_start < v_anchor or (p_week_start - v_anchor) % 7 <> 0 then
    return null;
  end if;

  v_week_position := (((p_week_start - v_anchor) / 7) % 4) + 1;
  v_week_count := jsonb_array_length(v_weeks);

  if v_week_count = 1 then
    v_week := v_weeks -> 0;
    v_base_id := coalesce(nullif(btrim(v_week ->> 'week_id'), ''), 'open-template');
    v_projected_id := v_base_id || '-w' || v_week_position::text;
    if btrim(coalesce(p_week_id, '')) <> v_projected_id then
      return null;
    end if;
    v_week := jsonb_set(v_week, '{week_id}', to_jsonb(v_projected_id), true);
    v_week := jsonb_set(v_week, '{week_index}', to_jsonb(v_week_position), true);
    return v_week;
  end if;

  if v_week_count <> 4 then
    return null;
  end if;

  select candidate.item
  into v_week
  from jsonb_array_elements(v_weeks) with ordinality as candidate(item, ordinal)
  where case
    when coalesce(candidate.item ->> 'week_index', '') ~ '^\d+$'
      then (candidate.item ->> 'week_index')::integer
    else candidate.ordinal::integer
  end = v_week_position
  limit 1;

  if v_week is null or btrim(coalesce(v_week ->> 'week_id', '')) <> btrim(coalesce(p_week_id, '')) then
    return null;
  end if;
  return v_week;
end;
$$;

create or replace function public.xp_full_week_planned_sessions(
  p_plan_id uuid,
  p_week_id text,
  p_week_start date
)
returns table(session_id text, training_day date)
language plpgsql
stable
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_plan_type text;
  v_week jsonb;
begin
  select lower(btrim(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', '')))
  into v_plan_type
  from public.plans as plan
  where plan.id = p_plan_id;

  if v_plan_type = 'open_ongoing_system' then
    v_week := public.xp_open_plan_week_item(p_plan_id, p_week_start, p_week_id);
    if v_week is null then
      return;
    end if;

    return query
    select
      session.item ->> 'session_id',
      p_week_start + weekday.offset_days
    from jsonb_array_elements(
      case when jsonb_typeof(v_week -> 'days') = 'array'
        then v_week -> 'days' else '[]'::jsonb end
    ) as day(item)
    cross join lateral (
      select public.xp_weekday_offset(day.item ->> 'weekday') as offset_days
    ) as weekday
    cross join lateral jsonb_array_elements(
      case when jsonb_typeof(day.item -> 'sessions') = 'array'
        then day.item -> 'sessions' else '[]'::jsonb end
    ) as session(item)
    where lower(coalesce(day.item ->> 'day_type', '')) <> 'rest'
      and weekday.offset_days is not null
      and nullif(btrim(session.item ->> 'session_id'), '') is not null;
    return;
  end if;

  return query
  select
    session.item ->> 'session_id',
    (day.item ->> 'date')::date
  from public.plans as plan
  cross join lateral jsonb_array_elements(
    case when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
      then plan.structured_plan -> 'weeks' else '[]'::jsonb end
  ) as week(item)
  cross join lateral jsonb_array_elements(
    case when jsonb_typeof(week.item -> 'days') = 'array'
      then week.item -> 'days' else '[]'::jsonb end
  ) as day(item)
  cross join lateral jsonb_array_elements(
    case when jsonb_typeof(day.item -> 'sessions') = 'array'
      then day.item -> 'sessions' else '[]'::jsonb end
  ) as session(item)
  where plan.id = p_plan_id
    and week.item ->> 'week_id' = p_week_id
    and week.item ->> 'start_date' = p_week_start::text
    and lower(coalesce(day.item ->> 'day_type', '')) <> 'rest'
    and coalesce(day.item ->> 'date', '') ~ '^\d{4}-\d{2}-\d{2}$'
    and nullif(btrim(session.item ->> 'session_id'), '') is not null;
end;
$$;

create or replace function public.xp_legacy_calendar_date(
  p_athlete_id uuid,
  p_action text,
  p_idempotency_key text
)
returns date
language plpgsql
stable
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_action text := btrim(coalesce(p_action, ''));
  v_key text := btrim(coalesce(p_idempotency_key, ''));
  v_suffix text;
  v_completion_id uuid;
  v_plan_id uuid;
  v_week_id text;
  v_date date;
begin
  if v_action in ('training_logged', 'planned_session_completed') then
    begin
      v_completion_id := split_part(v_key, ':', 2)::uuid;
    exception when invalid_text_representation then
      return null;
    end;
    select completion.training_day
    into v_date
    from public.session_completions as completion
    where completion.id = v_completion_id
      and completion.athlete_id = p_athlete_id;
    return v_date;
  end if;

  if v_action = 'full_training_week_completed' then
    begin
      v_plan_id := split_part(v_key, ':', 2)::uuid;
    exception when invalid_text_representation then
      return null;
    end;
    v_week_id := btrim(split_part(v_key, ':', 3));
    select (week.item ->> 'start_date')::date
    into v_date
    from public.plans as plan
    cross join lateral jsonb_array_elements(
      case when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
        then plan.structured_plan -> 'weeks' else '[]'::jsonb end
    ) as week(item)
    where plan.id = v_plan_id
      and plan.athlete_id = p_athlete_id
      and week.item ->> 'week_id' = v_week_id
      and coalesce(week.item ->> 'start_date', '') ~ '^\d{4}-\d{2}-\d{2}$'
    limit 1;
    return v_date;
  end if;

  v_suffix := substring(v_key from '(\d{4}-\d{2}-\d{2})$');
  if v_suffix is null then
    return null;
  end if;
  begin
    return v_suffix::date;
  exception when invalid_datetime_format or datetime_field_overflow then
    return null;
  end;
end;
$$;

create or replace function public.enforce_xp_award_source_integrity()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_completion_id uuid;
  v_completion_plan_id uuid;
  v_completion_session_id text;
  v_completion_day date;
  v_completion_status text;
  v_plan_id uuid;
  v_week_id text;
  v_plan_type text;
  v_active_plan_id uuid;
  v_timezone text;
begin
  if new.action in ('recommended_fighter_content_watched', 'stop_decision_followed') then
    raise exception 'XP action has no live authoritative earning hook'
      using errcode = '23514';
  end if;

  if new.action in ('training_logged', 'planned_session_completed') then
    if split_part(new.idempotency_key, ':', 1) <> new.action then
      raise exception 'invalid session XP source key' using errcode = '22023';
    end if;
    begin
      v_completion_id := split_part(new.idempotency_key, ':', 2)::uuid;
    exception when invalid_text_representation then
      raise exception 'invalid session completion source id' using errcode = '22023';
    end;

    select completion.plan_id,
           completion.session_id,
           completion.training_day,
           completion.status
      into v_completion_plan_id,
           v_completion_session_id,
           v_completion_day,
           v_completion_status
    from public.session_completions as completion
    where completion.id = v_completion_id
      and completion.athlete_id = new.athlete_id;

    if v_completion_plan_id is null
      or v_completion_day is distinct from new.calendar_date
      or v_completion_status not in ('done', 'modified') then
      raise exception 'session XP source is not a terminal athlete completion'
        using errcode = '23514';
    end if;

    v_active_plan_id := public.xp_resolved_active_plan_id(
      new.athlete_id,
      new.calendar_date
    );
    if v_active_plan_id is null or v_completion_plan_id <> v_active_plan_id then
      raise exception 'inactive plan cannot earn session XP'
        using errcode = '23514';
    end if;

    select lower(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', ''))
      into v_plan_type
    from public.plans as plan
    where plan.id = v_completion_plan_id
      and plan.athlete_id = new.athlete_id;

    if not exists (
      select 1
      from public.plans as plan
      cross join lateral jsonb_array_elements(
        case when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
          then plan.structured_plan -> 'weeks' else '[]'::jsonb end
      ) as week(item)
      cross join lateral jsonb_array_elements(
        case when jsonb_typeof(week.item -> 'days') = 'array'
          then week.item -> 'days' else '[]'::jsonb end
      ) as day(item)
      cross join lateral jsonb_array_elements(
        case when jsonb_typeof(day.item -> 'sessions') = 'array'
          then day.item -> 'sessions' else '[]'::jsonb end
      ) as session(item)
      where plan.id = v_completion_plan_id
        and plan.athlete_id = new.athlete_id
        and lower(coalesce(day.item ->> 'day_type', '')) <> 'rest'
        and session.item ->> 'session_id' = v_completion_session_id
        and (
          day.item ->> 'date' = new.calendar_date::text
          or (
            v_plan_type = 'open_ongoing_system'
            and day.item ->> 'weekday' = to_char(new.calendar_date, 'Dy')
          )
        )
    ) then
      raise exception 'session XP source is not scheduled in the active plan'
        using errcode = '23514';
    end if;
  end if;

  if new.action = 'full_training_week_completed' then
    if split_part(new.idempotency_key, ':', 1) <> 'full-week' then
      raise exception 'invalid full-week XP source key' using errcode = '22023';
    end if;
    begin
      v_plan_id := split_part(new.idempotency_key, ':', 2)::uuid;
    exception when invalid_text_representation then
      raise exception 'invalid full-week plan source id' using errcode = '22023';
    end;
    v_week_id := btrim(split_part(new.idempotency_key, ':', 3));
    if v_week_id = '' then
      raise exception 'full-week source is missing the week id' using errcode = '22023';
    end if;

    v_active_plan_id := public.xp_resolved_active_plan_id(
      new.athlete_id,
      new.calendar_date
    );
    if v_active_plan_id is null or v_plan_id <> v_active_plan_id then
      raise exception 'inactive plan cannot earn full-week XP'
        using errcode = '23514';
    end if;

    if not exists (
      select 1
      from public.xp_full_week_planned_sessions(v_plan_id, v_week_id, new.calendar_date)
    ) then
      raise exception 'full-week source is not part of the active structured plan'
        using errcode = '23514';
    end if;
  end if;

  if new.action = 'injury_update_completed' then
    select coalesce(nullif(profile.athlete_timezone, ''), 'UTC')
      into v_timezone
    from public.profiles as profile
    where profile.id = new.athlete_id;

    if not exists (
      select 1
      from public.injury_flags as injury
      where injury.athlete_id = new.athlete_id
        and (injury.updated_at at time zone coalesce(v_timezone, 'UTC'))::date = new.calendar_date
    ) then
      raise exception 'injury XP requires an injury record updated on the training day'
        using errcode = '23514';
    end if;
  end if;

  if new.action in ('phase_completed', 'first_plan_completed', 'camp_completed')
    and not exists (
      select 1
      from public.plan_milestones as milestone
      join public.plans as plan on plan.id = milestone.plan_id
      where milestone.athlete_id = new.athlete_id
        and (
          (
            new.action = 'phase_completed'
            and milestone.milestone_type = 'phase_completed'
            and new.idempotency_key =
              'phase-completed:' || new.athlete_id::text || ':' ||
              public.xp_plan_reward_scope(milestone.plan_id) || ':' ||
              lower(milestone.phase_label)
          )
          or (
            new.action = 'first_plan_completed'
            and milestone.milestone_type = 'plan_completed'
            and new.idempotency_key = 'first-plan-completed:' || new.athlete_id::text
          )
          or (
            new.action = 'camp_completed'
            and milestone.milestone_type = 'camp_completed'
            and lower(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', '')) = 'fight_camp'
            and plan.fight_date is not null
            and new.idempotency_key =
              'camp-completed:' || new.athlete_id::text || ':' ||
              public.xp_plan_reward_scope(milestone.plan_id)
          )
        )
    ) then
      raise exception 'lifecycle XP requires a matching persisted plan milestone'
        using errcode = '23514';
  end if;

  return new;
end;
$$;

create or replace function public.enforce_xp_plan_lock_and_week_completion()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_completion_plan_id uuid;
  v_plan_id uuid;
  v_week_id text;
  v_planned_count integer;
begin
  if new.action in ('training_logged', 'planned_session_completed') then
    select completion.plan_id
      into v_completion_plan_id
    from public.session_completions as completion
    where completion.athlete_id = new.athlete_id
      and completion.id::text = split_part(new.idempotency_key, ':', 2);

    if v_completion_plan_id is null then
      raise exception 'session XP plan source is unavailable' using errcode = '23514';
    end if;

    new.source_plan_id := v_completion_plan_id;

    if exists (
      select 1
      from public.xp_awards as previous_award
      where previous_award.athlete_id = new.athlete_id
        and previous_award.calendar_date = new.calendar_date
        and previous_award.action in ('training_logged', 'planned_session_completed')
        and previous_award.source_plan_id is distinct from v_completion_plan_id
    ) then
      raise exception 'session XP is already locked to another plan for this training day'
        using errcode = '23514';
    end if;
  end if;

  if new.action = 'full_training_week_completed' then
    begin
      v_plan_id := split_part(new.idempotency_key, ':', 2)::uuid;
    exception when invalid_text_representation then
      raise exception 'invalid full-week plan source id' using errcode = '22023';
    end;
    v_week_id := btrim(split_part(new.idempotency_key, ':', 3));

    select count(*)
    into v_planned_count
    from public.xp_full_week_planned_sessions(v_plan_id, v_week_id, new.calendar_date);

    if coalesce(v_planned_count, 0) = 0 then
      raise exception 'full-week XP source has no planned sessions'
        using errcode = '23514';
    end if;

    if exists (
      select 1
      from public.xp_full_week_planned_sessions(v_plan_id, v_week_id, new.calendar_date) as planned
      where not exists (
        select 1
        from public.session_completions as completion
        where completion.athlete_id = new.athlete_id
          and completion.plan_id = v_plan_id
          and completion.session_id = planned.session_id
          and completion.training_day = planned.training_day
          and completion.status in ('done', 'modified')
      )
    ) then
      raise exception 'full-week XP requires every planned session to be completed or modified'
        using errcode = '23514';
    end if;
  end if;

  return new;
end;
$$;

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
    select 1 from public.profiles
    where id = p_athlete_id and role::text = 'athlete'
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
    raise exception 'feedback XP must use reconcile_feedback_xp' using errcode = '22023';
  end if;

  v_calendar_scoped := v_action in (
    'daily_login', 'training_logged', 'planned_session_completed',
    'full_training_week_completed', 'readiness_checkin_completed',
    'injury_update_completed', 'stop_decision_followed'
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
  if v_action <> 'daily_login' and v_calendar_scoped and v_calendar_date is null then
    raise exception 'invalid calendar scope for XP action' using errcode = '22023';
  end if;
  if not v_calendar_scoped and v_calendar_date is not null then
    raise exception 'invalid calendar scope for XP action' using errcode = '22023';
  end if;

  if v_action = 'profile_completed' and not exists (
    select 1 from public.profiles p
    where p.id = p_athlete_id
      and char_length(btrim(coalesce(p.full_name, ''))) > 0
      and exists (
        select 1 from unnest(coalesce(p.technical_style, array[]::text[])) sport(value)
        where lower(btrim(sport.value)) in ('boxing', 'kickboxing', 'mma')
      )
  ) then
    raise exception 'profile activation milestone is not complete' using errcode = '23514';
  end if;
  if v_action = 'first_intake_completed' and not exists (
    select 1 from public.athlete_intakes where athlete_id = p_athlete_id
  ) then
    raise exception 'intake activation milestone is not complete' using errcode = '23514';
  end if;
  if v_action = 'first_plan_ready' and not exists (
    select 1 from public.plans
    where athlete_id = p_athlete_id and status in ('ready', 'publishable_with_flags')
  ) then
    raise exception 'plan activation milestone is not complete' using errcode = '23514';
  end if;
  if v_action = 'first_checkin_completed' and not exists (
    select 1 from public.today_checkins where athlete_id = p_athlete_id
  ) then
    raise exception 'first check-in milestone is not complete' using errcode = '23514';
  end if;
  if v_action = 'readiness_checkin_completed' and not exists (
    select 1 from public.today_checkins
    where athlete_id = p_athlete_id and training_day = v_calendar_date
  ) then
    raise exception 'daily check-in milestone is not complete' using errcode = '23514';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(p_athlete_id::text, 0));
  insert into public.xp_accounts (athlete_id)
  values (p_athlete_id) on conflict (athlete_id) do nothing;
  select total_xp, last_daily_login_date into v_previous, v_last_login
  from public.xp_accounts where athlete_id = p_athlete_id for update;

  if v_action <> 'daily_login' then
    insert into public.xp_awards (
      athlete_id, action, amount, idempotency_key, calendar_date
    ) values (
      p_athlete_id, v_action, v_amount, v_key, v_calendar_date
    ) on conflict do nothing returning * into v_award;
    v_awarded := v_award.id is not null;
  end if;

  if v_awarded then
    update public.xp_accounts
    set total_xp = total_xp + v_amount, updated_at = clock_timestamp()
    where athlete_id = p_athlete_id
    returning total_xp, last_daily_login_date into v_total, v_last_login;
  else
    v_total := v_previous;
  end if;

  select coalesce(jsonb_agg(item order by awarded_at desc, id desc), '[]'::jsonb)
  into v_recent
  from (
    select award.id, award.awarded_at,
      jsonb_strip_nulls(jsonb_build_object(
        'id', award.id, 'action', award.action, 'amount', award.amount,
        'awarded_at', award.awarded_at, 'calendar_date', award.calendar_date
      )) item
    from public.xp_awards award
    where award.athlete_id = p_athlete_id
    order by award.awarded_at desc, award.id desc limit 20
  ) recent;

  return jsonb_build_object(
    'state', jsonb_build_object(
      'total_xp', v_total,
      'last_daily_login_date', v_last_login,
      'recent_awards', v_recent
    ),
    'previous_total_xp', v_previous,
    'awarded', v_awarded,
    'award', case when v_awarded then jsonb_strip_nulls(jsonb_build_object(
      'id', v_award.id, 'action', v_award.action, 'amount', v_award.amount,
      'awarded_at', v_award.awarded_at, 'calendar_date', v_award.calendar_date
    )) else 'null'::jsonb end
  );
end;
$$;

create or replace function public.validate_xp_abuse_hardening()
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
begin
  if coalesce(auth.role(), '') <> 'service_role' then
    raise exception 'validate_xp_abuse_hardening is restricted to the backend service role'
      using errcode = '42501';
  end if;

  if to_regclass('public.xp_awards_one_time_action_per_athlete') is null
    or to_regclass('public.xp_awards_one_daily_action_per_athlete') is null
    or to_regprocedure('public.xp_legacy_calendar_date(uuid,text,text)') is null
    or to_regprocedure('public.xp_full_week_planned_sessions(uuid,text,date)') is null
    or to_regprocedure('public.xp_open_plan_week_item(uuid,date,text)') is null
    or not exists (
      select 1 from information_schema.columns
      where table_schema = 'public'
        and table_name = 'xp_awards'
        and column_name = 'source_plan_id'
    )
    or not exists (
      select 1 from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_source_integrity'
        and not tgisinternal
    )
    or not exists (
      select 1 from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_plan_lock_and_week_completion'
        and not tgisinternal
    )
    or not exists (
      select 1 from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_source_plan_immutable'
        and not tgisinternal
    )
    or not exists (
      select 1 from pg_trigger
      where tgrelid = 'public.profiles'::regclass
        and tgname = 'profiles_validate_athlete_timezone_update'
        and not tgisinternal
    ) then
    raise exception 'XP abuse hardening is incomplete' using errcode = '55000';
  end if;

  return jsonb_build_object(
    'ok', true,
    'version', '20260803182000',
    'rollout_ready', true
  );
end;
$$;

revoke all on function public.xp_try_jsonb(text)
  from public, anon, authenticated;
grant execute on function public.xp_try_jsonb(text)
  to service_role;

revoke all on function public.xp_weekday_offset(text)
  from public, anon, authenticated;
grant execute on function public.xp_weekday_offset(text)
  to service_role;

revoke all on function public.xp_open_plan_anchor_date(uuid)
  from public, anon, authenticated;
grant execute on function public.xp_open_plan_anchor_date(uuid)
  to service_role;

revoke all on function public.xp_open_plan_week_item(uuid, date, text)
  from public, anon, authenticated;
grant execute on function public.xp_open_plan_week_item(uuid, date, text)
  to service_role;

revoke all on function public.xp_full_week_planned_sessions(uuid, text, date)
  from public, anon, authenticated;
grant execute on function public.xp_full_week_planned_sessions(uuid, text, date)
  to service_role;

revoke all on function public.xp_legacy_calendar_date(uuid, text, text)
  from public, anon, authenticated;
grant execute on function public.xp_legacy_calendar_date(uuid, text, text)
  to service_role;

revoke all on function public.enforce_xp_award_source_integrity()
  from public, anon, authenticated;
grant execute on function public.enforce_xp_award_source_integrity()
  to service_role;

revoke all on function public.enforce_xp_plan_lock_and_week_completion()
  from public, anon, authenticated;
grant execute on function public.enforce_xp_plan_lock_and_week_completion()
  to service_role;

revoke all on function public.award_athlete_xp(uuid, text, text, date)
  from public, anon, authenticated;
grant execute on function public.award_athlete_xp(uuid, text, text, date)
  to service_role;

revoke all on function public.validate_xp_abuse_hardening()
  from public, anon, authenticated;
grant execute on function public.validate_xp_abuse_hardening()
  to service_role;
