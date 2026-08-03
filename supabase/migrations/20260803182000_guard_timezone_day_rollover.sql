-- The athlete timezone owns Today's server-side training date. Without a
-- durable change boundary, repeatedly hopping between far-ahead and far-behind
-- zones could expose adjacent-day check-ins or scheduled sessions early.

alter table public.profiles
  add column if not exists athlete_timezone_updated_at timestamptz;

create or replace function public.validate_profile_athlete_timezone()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, public
as $$
declare
  v_new_timezone text := btrim(coalesce(new.athlete_timezone, ''));
  v_old_timezone text := case
    when tg_op = 'UPDATE' then btrim(coalesce(old.athlete_timezone, ''))
    else ''
  end;
begin
  if v_new_timezone <> '' and not exists (
    select 1
    from pg_timezone_names
    where name = v_new_timezone
  ) then
    raise exception 'athlete_timezone must be a valid IANA timezone'
      using errcode = '22023';
  end if;

  new.athlete_timezone := v_new_timezone;

  if tg_op = 'INSERT' then
    if v_new_timezone <> '' then
      new.athlete_timezone_updated_at := clock_timestamp();
    end if;
    return new;
  end if;

  if v_new_timezone = v_old_timezone then
    return new;
  end if;

  if v_old_timezone <> '' and v_new_timezone = '' then
    raise exception 'athlete_timezone cannot be cleared after it is set'
      using errcode = '23514';
  end if;

  -- Initial setup from an empty timezone is allowed. Later changes are genuine
  -- travel/account events, but cannot be repeated fast enough to hop between
  -- adjacent server-owned training dates.
  if v_old_timezone <> ''
    and old.athlete_timezone_updated_at is not null
    and old.athlete_timezone_updated_at > clock_timestamp() - interval '24 hours' then
    raise exception 'athlete_timezone can only be changed once every 24 hours'
      using errcode = '23514';
  end if;

  new.athlete_timezone_updated_at := clock_timestamp();
  return new;
end;
$$;

drop trigger if exists profiles_validate_athlete_timezone_insert on public.profiles;
create trigger profiles_validate_athlete_timezone_insert
before insert on public.profiles
for each row execute function public.validate_profile_athlete_timezone();

drop trigger if exists profiles_validate_athlete_timezone_update on public.profiles;
create trigger profiles_validate_athlete_timezone_update
before update of athlete_timezone on public.profiles
for each row execute function public.validate_profile_athlete_timezone();

create index if not exists profiles_athlete_timezone_updated_at_idx
  on public.profiles (athlete_timezone_updated_at)
  where athlete_timezone_updated_at is not null;

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
    )
    or not exists (
      select 1 from pg_trigger
      where tgrelid = 'public.profiles'::regclass
        and tgname = 'profiles_validate_athlete_timezone_update'
        and not tgisinternal
    ) then
    raise exception 'XP abuse hardening is incomplete' using errcode = '55000';
  end if;

  return jsonb_build_object('ok', true, 'version', '20260803182000');
end;
$$;

revoke all on function public.validate_profile_athlete_timezone()
  from public, anon, authenticated;
grant execute on function public.validate_profile_athlete_timezone()
  to service_role;

revoke all on function public.validate_xp_abuse_hardening()
  from public, anon, authenticated;
grant execute on function public.validate_xp_abuse_hardening()
  to service_role;

revoke all on function public.validate_xp_abuse_hardening()
  from public, anon, authenticated;
grant execute on function public.validate_xp_abuse_hardening()
  to service_role;
