-- Shared helpers for staged XP hardening and renewable open-plan week proof.

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
    if v_expected_isodow = (
      case when v_created_isodow = 1 then 7 else v_created_isodow - 1 end
    ) then
      v_created := v_created - 1;
    elsif v_expected_isodow = (
      case when v_created_isodow = 7 then 1 else v_created_isodow + 1 end
    ) then
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
  if v_anchor is null
    or p_week_start < v_anchor
    or (p_week_start - v_anchor) % 7 <> 0 then
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

  if v_week is null
    or btrim(coalesce(v_week ->> 'week_id', '')) <> btrim(coalesce(p_week_id, '')) then
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
      case
        when jsonb_typeof(v_week -> 'days') = 'array'
          then v_week -> 'days'
        else '[]'::jsonb
      end
    ) as day(item)
    cross join lateral (
      select public.xp_weekday_offset(day.item ->> 'weekday') as offset_days
    ) as weekday
    cross join lateral jsonb_array_elements(
      case
        when jsonb_typeof(day.item -> 'sessions') = 'array'
          then day.item -> 'sessions'
        else '[]'::jsonb
      end
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
    case
      when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
        then plan.structured_plan -> 'weeks'
      else '[]'::jsonb
    end
  ) as week(item)
  cross join lateral jsonb_array_elements(
    case
      when jsonb_typeof(week.item -> 'days') = 'array'
        then week.item -> 'days'
      else '[]'::jsonb
    end
  ) as day(item)
  cross join lateral jsonb_array_elements(
    case
      when jsonb_typeof(day.item -> 'sessions') = 'array'
        then day.item -> 'sessions'
      else '[]'::jsonb
    end
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
      case
        when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
          then plan.structured_plan -> 'weeks'
        else '[]'::jsonb
      end
    ) as week(item)
    where plan.id = v_plan_id
      and plan.athlete_id = p_athlete_id
      and week.item ->> 'week_id' = v_week_id
      and coalesce(week.item ->> 'start_date', '') ~ '^\d{4}-\d{2}-\d{2}$'
    limit 1;
    return v_date;
  end if;

  v_suffix := substring(v_key from '([0-9]{4}-[0-9]{2}-[0-9]{2})$');
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
