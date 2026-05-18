-- Adds username support with a rate-limited change history on profiles.
alter table public.profiles add column if not exists username text;
alter table public.profiles
  add column if not exists username_change_history jsonb not null default '[]'::jsonb;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_key'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles add constraint profiles_username_key unique (username);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_length'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_username_length
      check (username is null or char_length(username) between 3 and 24);
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_lowercase'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_username_lowercase
      check (username is null or username = lower(username));
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'profiles_username_format'
      and conrelid = 'public.profiles'::regclass
  ) then
    alter table public.profiles
      add constraint profiles_username_format
      check (username is null or username ~ '^[a-z0-9]([a-z0-9._-]*[a-z0-9])?$');
  end if;
end
$$;

create index if not exists profiles_username_idx on public.profiles (username);

create or replace function public.prevent_username_policy_bypass()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.role() <> 'service_role' and not public.is_admin() then
    if new.username is distinct from old.username
      or new.username_change_history is distinct from old.username_change_history then
      raise exception 'Use the username change endpoint.';
    end if;
  end if;

  return new;
end;
$$;

drop trigger if exists profiles_prevent_username_policy_bypass on public.profiles;
create trigger profiles_prevent_username_policy_bypass
before update on public.profiles
for each row
execute function public.prevent_username_policy_bypass();

create or replace view public.admin_athlete_rollups as
select
  p.id,
  p.email,
  p.username,
  p.role,
  p.full_name,
  p.technical_style,
  p.tactical_style,
  p.stance,
  p.professional_status,
  p.record_summary,
  p.athlete_timezone,
  p.athlete_locale,
  p.appearance_mode,
  p.onboarding_draft,
  p.nutrition_profile,
  p.created_at,
  p.updated_at,
  count(pl.id)::int as plan_count,
  max(pl.created_at) as latest_plan_created_at
from public.profiles p
left join public.plans pl on pl.athlete_id = p.id
group by
  p.id,
  p.email,
  p.username,
  p.role,
  p.full_name,
  p.technical_style,
  p.tactical_style,
  p.stance,
  p.professional_status,
  p.record_summary,
  p.athlete_timezone,
  p.athlete_locale,
  p.appearance_mode,
  p.onboarding_draft,
  p.nutrition_profile,
  p.created_at,
  p.updated_at;
