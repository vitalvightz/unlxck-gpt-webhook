-- Final rollout gate. The backend still expects version 20260803182000, while
-- these additional flags prove the legacy-compatible projection and stable
-- open-plan scope layers also landed.

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
      select 1
      from information_schema.columns
      where table_schema = 'public'
        and table_name = 'xp_awards'
        and column_name = 'source_plan_id'
    )
    or not exists (
      select 1
      from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_source_integrity'
        and not tgisinternal
    )
    or not exists (
      select 1
      from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_plan_lock_and_week_completion'
        and not tgisinternal
    )
    or not exists (
      select 1
      from pg_trigger
      where tgrelid = 'public.xp_awards'::regclass
        and tgname = 'xp_awards_source_plan_immutable'
        and not tgisinternal
    )
    or not exists (
      select 1
      from pg_trigger
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

revoke all on function public.validate_xp_abuse_hardening()
  from public, anon, authenticated;
grant execute on function public.validate_xp_abuse_hardening()
  to service_role;
