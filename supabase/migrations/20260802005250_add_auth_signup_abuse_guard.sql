-- Protect Supabase Auth from direct automated signup floods.
-- This guard runs inside Postgres, so it still applies when callers bypass
-- unlxck.com and call /auth/v1/signup directly.

create table if not exists private.auth_signup_guard_settings (
  singleton boolean primary key default true check (singleton),
  enabled boolean not null default true,
  max_per_10_minutes integer not null default 8 check (max_per_10_minutes between 1 and 1000),
  max_per_hour integer not null default 25 check (max_per_hour between 1 and 10000),
  stale_unconfirmed_hours integer not null default 48 check (stale_unconfirmed_hours between 1 and 720),
  updated_at timestamptz not null default now()
);

insert into private.auth_signup_guard_settings (singleton)
values (true)
on conflict (singleton) do nothing;

revoke all on table private.auth_signup_guard_settings from public, anon, authenticated;
grant select on table private.auth_signup_guard_settings to service_role;

create or replace function private.enforce_auth_signup_rate_limit()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  guard_enabled boolean;
  ten_minute_limit integer;
  hourly_limit integer;
  signups_last_10_minutes integer;
  signups_last_hour integer;
begin
  select enabled, max_per_10_minutes, max_per_hour
    into guard_enabled, ten_minute_limit, hourly_limit
  from private.auth_signup_guard_settings
  where singleton = true;

  if coalesce(guard_enabled, false) is false then
    return new;
  end if;

  -- Serialize account creation briefly so simultaneous requests cannot all
  -- pass the count check before any of them commits.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('unlxck-auth-signup-guard', 0)
  );

  select count(*)::integer
    into signups_last_10_minutes
  from auth.users
  where created_at >= pg_catalog.now() - interval '10 minutes';

  if signups_last_10_minutes >= ten_minute_limit then
    raise exception using
      errcode = 'P0001',
      message = 'signup_rate_limit_exceeded',
      detail = 'Too many new accounts were created in the last 10 minutes.';
  end if;

  select count(*)::integer
    into signups_last_hour
  from auth.users
  where created_at >= pg_catalog.now() - interval '1 hour';

  if signups_last_hour >= hourly_limit then
    raise exception using
      errcode = 'P0001',
      message = 'signup_rate_limit_exceeded',
      detail = 'Too many new accounts were created in the last hour.';
  end if;

  return new;
end;
$$;

revoke all on function private.enforce_auth_signup_rate_limit() from public, anon, authenticated;

drop trigger if exists enforce_auth_signup_rate_limit on auth.users;
create trigger enforce_auth_signup_rate_limit
before insert on auth.users
for each row
execute function private.enforce_auth_signup_rate_limit();

create or replace function private.cleanup_stale_unconfirmed_auth_users(
  p_older_than_hours integer default 48
)
returns integer
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  deleted_count integer;
begin
  if p_older_than_hours < 1 or p_older_than_hours > 720 then
    raise exception 'p_older_than_hours must be between 1 and 720';
  end if;

  delete from auth.users
  where email_confirmed_at is null
    and phone_confirmed_at is null
    and last_sign_in_at is null
    and created_at < pg_catalog.now() - pg_catalog.make_interval(hours => p_older_than_hours);

  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke all on function private.cleanup_stale_unconfirmed_auth_users(integer)
  from public, anon, authenticated;
grant execute on function private.cleanup_stale_unconfirmed_auth_users(integer)
  to service_role;

create extension if not exists pg_cron with schema pg_catalog;
grant usage on schema cron to postgres;
grant all privileges on all tables in schema cron to postgres;

do $$
declare
  existing_job record;
begin
  for existing_job in
    select jobid
    from cron.job
    where jobname = 'cleanup-stale-unconfirmed-auth-users'
  loop
    perform cron.unschedule(existing_job.jobid);
  end loop;

  perform cron.schedule(
    'cleanup-stale-unconfirmed-auth-users',
    '17 * * * *',
    'select private.cleanup_stale_unconfirmed_auth_users(48);'
  );
end
$$;
