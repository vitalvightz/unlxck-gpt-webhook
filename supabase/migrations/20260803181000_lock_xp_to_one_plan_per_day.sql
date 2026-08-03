-- Prevent sequential active-plan switching from becoming a session-XP farm and
-- independently verify every full-week source against persisted completions.

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

    if exists (
      select 1
      from public.xp_awards as previous_award
      join public.session_completions as previous_completion
        on previous_completion.athlete_id = previous_award.athlete_id
       and previous_completion.id::text = split_part(previous_award.idempotency_key, ':', 2)
      where previous_award.athlete_id = new.athlete_id
        and previous_award.calendar_date = new.calendar_date
        and previous_award.action in ('training_logged', 'planned_session_completed')
        and previous_completion.plan_id <> v_completion_plan_id
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
    where plan.id = v_plan_id
      and plan.athlete_id = new.athlete_id
      and week.item ->> 'week_id' = v_week_id
      and week.item ->> 'start_date' = new.calendar_date::text
      and lower(coalesce(day.item ->> 'day_type', '')) <> 'rest'
      and nullif(btrim(session.item ->> 'session_id'), '') is not null;

    if coalesce(v_planned_count, 0) = 0 then
      raise exception 'full-week XP source has no planned sessions'
        using errcode = '23514';
    end if;

    if exists (
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
      where plan.id = v_plan_id
        and plan.athlete_id = new.athlete_id
        and week.item ->> 'week_id' = v_week_id
        and week.item ->> 'start_date' = new.calendar_date::text
        and lower(coalesce(day.item ->> 'day_type', '')) <> 'rest'
        and nullif(btrim(session.item ->> 'session_id'), '') is not null
        and not exists (
          select 1
          from public.session_completions as completion
          where completion.athlete_id = new.athlete_id
            and completion.plan_id = v_plan_id
            and completion.session_id = session.item ->> 'session_id'
            and completion.training_day::text = day.item ->> 'date'
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

drop trigger if exists xp_awards_plan_lock_and_week_completion on public.xp_awards;
create trigger xp_awards_plan_lock_and_week_completion
before insert on public.xp_awards
for each row execute function public.enforce_xp_plan_lock_and_week_completion();

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
    ) then
    raise exception 'XP abuse hardening is incomplete' using errcode = '55000';
  end if;

  return jsonb_build_object('ok', true, 'version', '20260803181000');
end;
$$;

revoke all on function public.enforce_xp_plan_lock_and_week_completion()
  from public, anon, authenticated;
grant execute on function public.enforce_xp_plan_lock_and_week_completion()
  to service_role;

revoke all on function public.validate_xp_abuse_hardening()
  from public, anon, authenticated;
grant execute on function public.validate_xp_abuse_hardening()
  to service_role;
