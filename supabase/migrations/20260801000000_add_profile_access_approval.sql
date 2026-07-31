-- Require an explicit admin approval before newly-created profiles can use the app.
-- Existing profiles are grandfathered to avoid locking out the current beta cohort.

alter table public.profiles
  add column if not exists access_status text not null default 'pending';

update public.profiles
set access_status = 'approved'
where access_status = 'pending';

alter table public.profiles
  drop constraint if exists profiles_access_status_check;
alter table public.profiles
  add constraint profiles_access_status_check
  check (access_status in ('pending', 'approved'));

create or replace function private.prevent_client_access_status_change()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, pg_temp
as $$
begin
  if current_user <> 'service_role'
    and new.access_status is distinct from old.access_status then
    raise exception 'Only the backend service role can approve profile access.';
  end if;
  return new;
end;
$$;

revoke all on function private.prevent_client_access_status_change() from public, anon, authenticated;
grant execute on function private.prevent_client_access_status_change() to service_role;

drop trigger if exists profiles_prevent_client_access_status_change on public.profiles;
create trigger profiles_prevent_client_access_status_change
before update of access_status on public.profiles
for each row
execute function private.prevent_client_access_status_change();

create or replace view public.admin_athlete_rollups
with (security_invoker = true) as
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
  max(pl.created_at) as latest_plan_created_at,
  p.access_status
from public.profiles p
left join public.plans pl on pl.athlete_id = p.id
group by p.id;

revoke all on public.admin_athlete_rollups from anon, authenticated;
grant select on public.admin_athlete_rollups to service_role;
