-- Replace the source-integrity trigger so renewable open-plan full-week awards
-- are validated against deterministic projected calendar dates.

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
