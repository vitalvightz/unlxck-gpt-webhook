-- Renewable open plans have no persisted week start dates. Use the same stable
-- calendar anchor as their runtime projection so regenerating a plan does not
-- gain a fresh phase-XP scope merely because the plan UUID changed.

create or replace function public.xp_plan_reward_scope(p_plan_id uuid)
returns text
language sql
stable
security invoker
set search_path = pg_catalog, public
as $$
  select case
    when plan.fight_date is not null then
      'fight:' || plan.fight_date::text
    when lower(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', '')) = 'open_ongoing_system'
      and public.xp_open_plan_anchor_date(plan.id) is not null then
      'open-anchor:' || public.xp_open_plan_anchor_date(plan.id)::text
    when first_week.start_date is not null then
      'start:' || first_week.start_date || ':' ||
      lower(coalesce(plan.structured_plan -> 'plan_metadata' ->> 'plan_type', 'plan'))
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
    or to_regprocedure('public.xp_plan_reward_scope(uuid)') is null
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
    'rollout_ready', true,
    'open_plan_scope_ready', true
  );
end;
$$;

revoke all on function public.xp_plan_reward_scope(uuid)
  from public, anon, authenticated;
grant execute on function public.xp_plan_reward_scope(uuid)
  to service_role;

revoke all on function public.validate_xp_abuse_hardening()
  from public, anon, authenticated;
grant execute on function public.validate_xp_abuse_hardening()
  to service_role;
