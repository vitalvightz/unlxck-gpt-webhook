-- Reuse the projected-session helper for independent full-week proof while
-- preserving the one-plan-per-training-day session-XP lock.

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
      raise exception 'session XP plan source is unavailable'
        using errcode = '23514';
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
    from public.xp_full_week_planned_sessions(
      v_plan_id,
      v_week_id,
      new.calendar_date
    );

    if coalesce(v_planned_count, 0) = 0 then
      raise exception 'full-week XP source has no planned sessions'
        using errcode = '23514';
    end if;

    if exists (
      select 1
      from public.xp_full_week_planned_sessions(
        v_plan_id,
        v_week_id,
        new.calendar_date
      ) as planned
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

revoke all on function public.enforce_xp_plan_lock_and_week_completion()
  from public, anon, authenticated;
grant execute on function public.enforce_xp_plan_lock_and_week_completion()
  to service_role;
