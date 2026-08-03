-- Defense in depth for XP source integrity.
-- The application already checks these conditions before requesting an award;
-- this migration makes the ledger independently reject forged or stale sources.

create or replace function public.xp_resolved_active_plan_id(
  p_athlete_id uuid,
  p_training_day date
)
returns uuid
language sql
stable
security invoker
set search_path = pg_catalog, public
as $$
  select candidate.id
  from public.plans as candidate
  join public.profiles as profile on profile.id = p_athlete_id
  where candidate.athlete_id = p_athlete_id
    and candidate.status in ('ready', 'publishable_with_flags')
    and (candidate.fight_date is null or candidate.fight_date >= p_training_day)
  order by
    case
      when candidate.id = profile.active_plan_id then 0
      when candidate.fight_date is not null then 1
      else 2
    end,
    candidate.fight_date asc nulls last,
    candidate.created_at desc,
    candidate.id desc
  limit 1
$$;

create or replace function public.xp_plan_reward_scope(p_plan_id uuid)
returns text
language sql
stable
security invoker
set search_path = pg_catalog, public
as $$
  select case
    when plan.fight_date is not null then 'fight:' || plan.fight_date::text
    when first_week.start_date is not null then
      'start:' || first_week.start_date || ':' || lower(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', 'plan'))
    else 'plan:' || plan.id::text
  end
  from public.plans as plan
  left join lateral (
    select min(week.item ->> 'start_date') as start_date
    from jsonb_array_elements(
      case
        when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
          then plan.structured_plan -> 'weeks'
        else '[]'::jsonb
      end
    ) as week(item)
    where coalesce(week.item ->> 'start_date', '') ~ '^\d{4}-\d{2}-\d{2}$'
  ) as first_week on true
  where plan.id = p_plan_id
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
      from public.plans as plan
      cross join lateral jsonb_array_elements(
        case
          when jsonb_typeof(plan.structured_plan -> 'weeks') = 'array'
            then plan.structured_plan -> 'weeks'
          else '[]'::jsonb
        end
      ) as week(item)
      where plan.id = v_plan_id
        and plan.athlete_id = new.athlete_id
        and week.item ->> 'week_id' = v_week_id
        and week.item ->> 'start_date' = new.calendar_date::text
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

drop trigger if exists xp_awards_source_integrity on public.xp_awards;
create trigger xp_awards_source_integrity
before insert on public.xp_awards
for each row execute function public.enforce_xp_award_source_integrity();

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
  v_scope text;
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

  select *
    into v_milestone
  from public.plan_milestones
  where athlete_id = p_athlete_id
    and plan_id = p_plan_id
    and milestone_type = v_type
    and milestone_key = v_key;

  -- A previously persisted milestone may repair its missing XP after archival.
  -- A new milestone can only be created while the plan is athlete-visible.
  if v_milestone.id is null
    and v_plan_status not in ('ready', 'publishable_with_flags') then
    raise exception 'plan is not eligible for new progress milestones'
      using errcode = '23514';
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

  if v_milestone.id is null then
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
  end if;

  v_scope := public.xp_plan_reward_scope(p_plan_id);
  if v_scope is null then
    raise exception 'plan reward scope is unavailable' using errcode = '23514';
  end if;

  v_action := case v_type
    when 'phase_completed' then 'phase_completed'
    when 'plan_completed' then 'first_plan_completed'
    when 'camp_completed' then 'camp_completed'
  end;
  v_xp_key := case
    when v_type = 'phase_completed'
      then 'phase-completed:' || p_athlete_id::text || ':' || v_scope || ':' || lower(v_phase)
    when v_type = 'plan_completed'
      then 'first-plan-completed:' || p_athlete_id::text
    when v_type = 'camp_completed'
      then 'camp-completed:' || p_athlete_id::text || ':' || v_scope
  end;

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
    or not exists (
      select 1
      from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_source_integrity'
        and not tgisinternal
    ) then
    raise exception 'XP abuse hardening is incomplete'
      using errcode = '55000';
  end if;

  return jsonb_build_object('ok', true, 'version', '20260803175500');
end;
$$;

revoke all on function public.xp_resolved_active_plan_id(uuid, date)
  from public, anon, authenticated;
grant execute on function public.xp_resolved_active_plan_id(uuid, date)
  to service_role;

revoke all on function public.xp_plan_reward_scope(uuid)
  from public, anon, authenticated;
grant execute on function public.xp_plan_reward_scope(uuid)
  to service_role;

revoke all on function public.enforce_xp_award_source_integrity()
  from public, anon, authenticated;
grant execute on function public.enforce_xp_award_source_integrity()
  to service_role;

revoke all on function public.record_plan_milestone(uuid, uuid, text, text, text, jsonb)
  from public, anon, authenticated;
grant execute on function public.record_plan_milestone(uuid, uuid, text, text, text, jsonb)
  to service_role;

revoke all on function public.validate_xp_abuse_hardening()
  from public, anon, authenticated;
grant execute on function public.validate_xp_abuse_hardening()
  to service_role;
