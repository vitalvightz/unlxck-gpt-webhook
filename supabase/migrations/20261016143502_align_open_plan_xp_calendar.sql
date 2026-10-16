-- Project only session identity/membership from the existing deterministic
-- Open Plan decisions. No workouts, doses or calendar placements are planned
-- here. Match the API's saved-card identity reconciliation without rewriting
-- historical plans. Both session and full-week XP consume this projection.
create or replace function public.xp_open_plan_session_weeks(p_plan_id uuid)
returns jsonb
language plpgsql
stable
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_saved jsonb;
  v_weeks jsonb := '[]';
  v_result jsonb := '[]';
  v_brief jsonb;
  v_spec jsonb;
  v_program jsonb;
  v_rotation jsonb;
  v_week jsonb;
  v_day jsonb;
  v_session jsonb;
  v_item jsonb;
  v_entry jsonb;
  v_names jsonb;
  v_old record;
  v_watch record;
  v_w record;
  v_d record;
  v_s record;
  v_p record;
  v_available integer[];
  v_taken text[];
  v_consumed text[];
  v_id text;
  v_base_id text;
  v_title text;
  v_slot text;
  v_candidate text;
  v_suffix integer;
  v_offset integer;
  v_position integer;
  v_day_index integer;
  v_expected_offset integer;
  v_weekdays text[] := array['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
begin
  select plan.structured_plan -> 'weeks', public.xp_try_jsonb(plan.planning_brief)
  into v_saved, v_brief
  from public.plans plan where plan.id = p_plan_id and plan.fight_date is null;
  if jsonb_typeof(v_saved) is distinct from 'array' then return null; end if;
  v_spec := v_brief -> 'open_plan_spec';
  select array_agg(offset_days order by offset_days) into v_available
  from (select distinct public.xp_weekday_offset(value) offset_days
        from jsonb_array_elements_text(coalesce(v_spec -> 'weekly_template' -> 'training_days','[]'))) days
  where offset_days is not null;
  if v_available is null then return null; end if;

  -- The same legacy id-less card ids as ensure_structured_session_ids().
  for v_w in select value, ordinality from jsonb_array_elements(v_saved) with ordinality loop
    v_week := v_w.value;
    for v_d in select value, ordinality from jsonb_array_elements(v_week -> 'days') with ordinality loop
      v_day := v_d.value;
      v_offset := public.xp_weekday_offset(v_day ->> 'weekday');
      v_expected_offset := case when jsonb_array_length(v_week -> 'days') = cardinality(v_available)
                               then v_available[v_d.ordinality]
                               when jsonb_array_length(v_week -> 'days') = 7 then v_d.ordinality - 1 end;
      if v_expected_offset is null or (v_offset is not null and v_offset <> v_expected_offset) then return null; end if;
      if v_offset is null then
        v_offset := v_expected_offset;
      end if;
      if v_offset is null then return null; end if;
      if not coalesce(v_brief ? 'custom_plan',false) and not (v_offset = any(v_available))
         and (jsonb_array_length(coalesce(v_day -> 'sessions','[]')) <> 0
              or nullif(btrim(v_day -> 'today_card' ->> 'coach_led_contact'),'') is not null
              or coalesce(v_day ->> 'day_type','') not in ('rest','recovery')) then return null; end if;
      v_day := jsonb_set(v_day, '{weekday}', to_jsonb(v_weekdays[v_offset + 1]));
      v_slot := left(coalesce(v_day ->> 'date',''),10);
      begin
        if v_slot !~ '^\d{4}-\d{2}-\d{2}$' then raise invalid_datetime_format; end if;
        perform v_slot::date;
      exception when invalid_datetime_format or datetime_field_overflow then
        v_slot := 'w' || v_w.ordinality || 'd' || v_d.ordinality;
      end;
      select coalesce(array_agg(btrim(value ->> 'session_id')),array[]::text[]) into v_taken
      from jsonb_array_elements(coalesce(v_day -> 'sessions','[]'));
      for v_s in select value, ordinality from jsonb_array_elements(coalesce(v_day -> 'sessions','[]')) with ordinality loop
        if nullif(btrim(v_s.value ->> 'session_id'),'') is not null then continue; end if;
        v_title := btrim(left(btrim(regexp_replace(lower(coalesce(v_s.value ->> 'title','')),
                                      '[^a-z0-9]+','-','g'),'-'),32),'-');
        if v_title = '' then
          v_title := btrim(left(btrim(regexp_replace(lower(coalesce(v_s.value ->> 'session_type','')),
                                        '[^a-z0-9]+','-','g'),'-'),32),'-');
        end if;
        v_base_id := 'ses-' || left(p_plan_id::text,8) || '-' || v_slot || '-' ||
                     coalesce(nullif(v_title,''),v_s.ordinality::text);
        v_candidate := v_base_id;
        v_suffix := 2;
        while v_candidate = any(v_taken) loop
          v_candidate := v_base_id || '-' || v_suffix;
          v_suffix := v_suffix + 1;
        end loop;
        v_taken := array_append(v_taken,v_candidate);
        v_day := jsonb_set(v_day,array['sessions',(v_s.ordinality - 1)::text,'session_id'],to_jsonb(v_candidate));
      end loop;
      v_week := jsonb_set(v_week,array['days',(v_d.ordinality - 1)::text],v_day);
    end loop;
    v_weeks := v_weeks || jsonb_build_array(v_week);
  end loop;

  v_program := v_spec -> 'weekly_session_plan';
  if coalesce(v_brief ? 'custom_plan',false)
     or v_spec ->> 'plan_type' is distinct from 'open_ongoing_system'
     or v_program ->> 'authority' is distinct from 'deterministic_open_development_block'
     or jsonb_typeof(v_program -> 'weeks') is distinct from 'array'
     or jsonb_array_length(v_program -> 'weeks') <> 4
     or jsonb_array_length(v_weeks) not in (1,4) then
    return v_weeks;
  end if;
  v_rotation := coalesce(v_spec -> 'tactical_watch' -> 'weekly_rotation','[]');
  for v_position in 1..4 loop
    v_week := v_weeks -> case when jsonb_array_length(v_weeks) = 1 then 0 else v_position - 1 end;
    if jsonb_array_length(v_weeks) = 1 then
      v_base_id := coalesce(nullif(btrim(v_week ->> 'week_id'),''),'open-template');
      v_week := v_week || jsonb_build_object('week_id',v_base_id || '-w' || v_position,'week_index',v_position);
    end if;
    v_consumed := array[]::text[];
    for v_d in select value, ordinality from jsonb_array_elements(v_week -> 'days') with ordinality loop
      v_week := jsonb_set(v_week,array['days',(v_d.ordinality - 1)::text,'sessions'],'[]');
    end loop;
    for v_p in select value, ordinality from jsonb_array_elements(v_program -> 'weeks' -> (v_position - 1) -> 'sessions') with ordinality loop
      v_item := v_p.value;
      v_offset := public.xp_weekday_offset(v_item ->> 'weekday');
      if v_offset is null or not (v_offset = any(v_available)) then return v_weeks; end if;
      if coalesce((v_item ->> 'coach_owned')::boolean,false) or v_item ->> 'category' = 'sparring' then continue; end if;
      select ordinality - 1 into v_day_index from jsonb_array_elements(v_week -> 'days') with ordinality
      where public.xp_weekday_offset(value ->> 'weekday') = v_offset;
      if v_day_index is null then return v_weeks; end if;
      select coalesce(jsonb_agg(value -> 'name'),'[]') into v_names
      from jsonb_array_elements(coalesce(v_item -> 'exercises','[]'));
      select d.ordinality::text || ':' || s.ordinality::text source_key, s.value item into v_old
      from jsonb_array_elements(v_weeks -> case when jsonb_array_length(v_weeks) = 1 then 0 else v_position - 1 end -> 'days') with ordinality d
      cross join lateral jsonb_array_elements(coalesce(d.value -> 'sessions','[]')) with ordinality s
      where public.xp_weekday_offset(d.value ->> 'weekday') = v_offset
        and not (d.ordinality::text || ':' || s.ordinality::text = any(v_consumed))
        and ((v_names <> '[]' and v_names = (select coalesce(jsonb_agg(b.value -> 'display_name'),'[]')
                                           from jsonb_array_elements(coalesce(s.value -> 'blocks','[]')) b))
             or s.value ->> 'title' = v_item ->> 'label')
      order by d.ordinality,s.ordinality limit 1;
      if v_old.source_key is not null then v_consumed := array_append(v_consumed,v_old.source_key); end if;
      v_id := coalesce(nullif(btrim(v_old.item ->> 'session_id'),''),
                       'deterministic-' || (112 - (v_position - 1) * 7 - v_offset) || '-' ||
                       (v_item ->> 'role_key') || '-' || (v_p.ordinality - 1));
      v_day := v_week -> 'days' -> v_day_index;
      v_day := v_day || jsonb_build_object('day_type',case when v_day ->> 'day_type' = 'rest' then 'moderate' else v_day ->> 'day_type' end,
                    'sessions',(v_day -> 'sessions') || jsonb_build_array(jsonb_build_object('session_id',v_id)));
      v_week := jsonb_set(v_week,array['days',v_day_index::text],v_day);
    end loop;
    -- The tactical cadence has its own saved rotation. Reuse its existing
    -- weekday and identity, just as the API does; never create a new placement.
    for v_entry in select value from jsonb_array_elements(v_rotation)
                   where (value ->> 'week')::integer = v_position loop
      select d.value ->> 'weekday' weekday, s.value item into v_watch
      from jsonb_array_elements(v_weeks) with ordinality w
      cross join lateral jsonb_array_elements(w.value -> 'days') with ordinality d
      cross join lateral jsonb_array_elements(coalesce(d.value -> 'sessions','[]')) with ordinality s
      where exists (select 1 from jsonb_array_elements(coalesce(s.value -> 'blocks','[]')) b
                    join jsonb_array_elements(v_rotation) r on b ->> 'display_name' = r ->> 'name')
      order by case when exists (select 1 from jsonb_array_elements(coalesce(s.value -> 'blocks','[]')) b
                                 where b ->> 'display_name' = v_entry ->> 'name') then 0 else 1 end,
               w.ordinality,d.ordinality,s.ordinality limit 1;
      if v_watch.item is null then continue; end if;
      select ordinality - 1 into v_day_index from jsonb_array_elements(v_week -> 'days') with ordinality
      where value ->> 'weekday' = v_watch.weekday;
      if v_day_index is null then return v_weeks; end if;
      v_day := v_week -> 'days' -> v_day_index;
      v_day := v_day || jsonb_build_object('day_type',case when v_day ->> 'day_type' = 'rest' then 'moderate' else v_day ->> 'day_type' end,
                    'sessions',(v_day -> 'sessions') || jsonb_build_array(jsonb_build_object('session_id',v_watch.item ->> 'session_id')));
      v_week := jsonb_set(v_week,array['days',v_day_index::text],v_day);
    end loop;
    v_result := v_result || jsonb_build_array(v_week);
  end loop;
  return v_result;
end;
$$;

revoke all on function public.xp_open_plan_session_weeks(uuid) from public, anon, authenticated;
grant execute on function public.xp_open_plan_session_weeks(uuid) to service_role;

-- Existing anchored week selection, now reading reconciled identities.
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
    public.xp_open_plan_session_weeks(plan.id)
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
    if p_week_id is not null and btrim(p_week_id) <> v_projected_id then
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
    or (p_week_id is not null and btrim(coalesce(v_week ->> 'week_id', '')) <> btrim(p_week_id)) then
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
      and session.item ->> 'optional' is distinct from 'true'
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

-- All existing source, ownership, active-plan and completion guards remain.
-- Only the open-plan membership lookup now uses the same projected week as
-- full-week bonuses, including the exact session date in repeated cycles.

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

    select
      completion.plan_id,
      completion.session_id,
      completion.training_day,
      completion.status
    into
      v_completion_plan_id,
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

    if v_plan_type = 'open_ongoing_system' then
      -- Null week id selects the anchor-authorized cycle week internally.
      -- Full-week awards still require an explicit, matching week id below.
      if not exists (
        select 1 from public.xp_full_week_planned_sessions(
          v_completion_plan_id, null,
          new.calendar_date - (extract(isodow from new.calendar_date)::integer - 1)
        ) planned
        where planned.session_id = v_completion_session_id
          and planned.training_day = new.calendar_date
      ) then
        raise exception 'session XP source is not scheduled in the active plan'
          using errcode = '23514';
      end if;
    elsif not exists (
      select 1
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
      from public.xp_full_week_planned_sessions(
        v_plan_id,
        v_week_id,
        new.calendar_date
      )
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
        and (
          injury.updated_at at time zone coalesce(v_timezone, 'UTC')
        )::date = new.calendar_date
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
            and new.idempotency_key =
              'first-plan-completed:' || new.athlete_id::text
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

revoke all on function public.enforce_xp_award_source_integrity()
  from public, anon, authenticated;
grant execute on function public.enforce_xp_award_source_integrity()
  to service_role;
