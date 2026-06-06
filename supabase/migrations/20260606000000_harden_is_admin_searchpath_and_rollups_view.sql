-- Hardening: pin search_path on the is_admin() SECURITY DEFINER function and
-- bind the admin_athlete_rollups view to the caller's RLS context.
--
-- 1. is_admin() backs every admin Row Level Security policy. As a SECURITY
--    DEFINER function without a fixed search_path, a caller able to influence
--    the session search_path could shadow `public.profiles` and subvert the
--    admin check. Pinning search_path closes that vector. All other SECURITY
--    DEFINER functions in this schema already set search_path = public.
--
-- 2. admin_athlete_rollups aggregates every athlete's profile (email, role,
--    nutrition_profile, ...). Views default to security_invoker = false, so
--    they run with the view owner's privileges and ignore the underlying
--    profiles RLS. The view is read only by the service-role backend
--    (api/store.py), so security_invoker = true plus explicit grants make it
--    safe: the service role still reads it (it bypasses RLS), while anon and
--    authenticated browser clients cannot read other athletes' rows even if
--    project default privileges grant SELECT on new views.

create or replace function public.is_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists(
    select 1
    from public.profiles
    where id = auth.uid()
      and role = 'admin'
  );
$$;

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

revoke all on public.admin_athlete_rollups from anon;
revoke all on public.admin_athlete_rollups from authenticated;
grant select on public.admin_athlete_rollups to service_role;
