-- Close the admin revocation gap (P0).
--
-- Effective admin access in the backend requires BOTH profiles.role = 'admin'
-- AND membership in UNLXCK_ADMIN_EMAILS (see api/store.py::is_effective_admin_profile).
-- The env allowlist is meant to be the real admin kill-switch: dropping an email
-- from UNLXCK_ADMIN_EMAILS must fully revoke cross-athlete access.
--
-- Before this migration, Supabase RLS still trusted profiles.role = 'admin'
-- alone through public.is_admin(). A stale DB-role admin whose email had been
-- removed from the allowlist could therefore still read every athlete's rows
-- directly through the browser/anon Supabase client (which authenticates as the
-- user, not service_role), bypassing the backend allowlist entirely. The env
-- kill-switch was not a real kill-switch for direct client access.
--
-- Fix: user-facing authenticated Supabase access is limited to the caller's OWN
-- rows. Cross-athlete admin reads/writes go exclusively through the FastAPI
-- service-role endpoints, which enforce is_effective_admin_profile. The admin
-- web UI already talks to /api/admin/* (service role), never to Supabase
-- cross-athlete queries, so this does not remove any legitimate client access.
--
-- public.is_admin() is intentionally left defined (some backend introspection
-- and historical migrations reference it) but is no longer used by any
-- browser-facing RLS policy or mutation guard.

-- ---------------------------------------------------------------------------
-- 1. Own-rows-only SELECT for the core athlete tables.
--    Old "*_self_or_admin_select" names are replaced with own-only policies.
-- ---------------------------------------------------------------------------
drop policy if exists "profiles_self_or_admin_select" on public.profiles;
drop policy if exists "profiles_self_select" on public.profiles;
create policy "profiles_self_select" on public.profiles
for select using (auth.uid() = id);

-- profiles UPDATE stays self-only. Role/username column changes are additionally
-- blocked for every non-service-role writer by the trigger guards below.
drop policy if exists "profiles_self_update" on public.profiles;
create policy "profiles_self_update" on public.profiles
for update using (auth.uid() = id)
with check (auth.uid() = id);

drop policy if exists "intakes_self_or_admin_select" on public.athlete_intakes;
drop policy if exists "intakes_self_select" on public.athlete_intakes;
create policy "intakes_self_select" on public.athlete_intakes
for select using (athlete_id = auth.uid());

drop policy if exists "plans_self_or_admin_select" on public.plans;
drop policy if exists "plans_self_select" on public.plans;
create policy "plans_self_select" on public.plans
for select using (athlete_id = auth.uid());

drop policy if exists "generation_jobs_self_or_admin_select" on public.generation_jobs;
drop policy if exists "generation_jobs_self_select" on public.generation_jobs;
create policy "generation_jobs_self_select" on public.generation_jobs
for select using (athlete_id = auth.uid());

-- ---------------------------------------------------------------------------
-- 2. Own-rows-only SELECT for the daily-tracking + Today tables.
--    These already used the "*_owner_select" name; keep it, drop is_admin().
-- ---------------------------------------------------------------------------
drop policy if exists "daily_checkins_owner_select" on public.daily_checkins;
create policy "daily_checkins_owner_select" on public.daily_checkins
for select using (athlete_id = auth.uid());

drop policy if exists "session_logs_owner_select" on public.session_logs;
create policy "session_logs_owner_select" on public.session_logs
for select using (athlete_id = auth.uid());

drop policy if exists "injury_flags_owner_select" on public.injury_flags;
create policy "injury_flags_owner_select" on public.injury_flags
for select using (athlete_id = auth.uid());

drop policy if exists "adaptation_notes_owner_select" on public.adaptation_notes;
create policy "adaptation_notes_owner_select" on public.adaptation_notes
for select using (athlete_id = auth.uid());

drop policy if exists "today_checkins_owner_select" on public.today_checkins;
create policy "today_checkins_owner_select" on public.today_checkins
for select using (athlete_id = auth.uid());

drop policy if exists "session_completions_owner_select" on public.session_completions;
create policy "session_completions_owner_select" on public.session_completions
for select using (athlete_id = auth.uid());

-- ---------------------------------------------------------------------------
-- 3. Admin-only tables: no browser access at all. Backend reads these through
--    service_role, which bypasses RLS, so a permanently-false policy keeps every
--    authenticated browser client (even a stale DB-role admin) out while the
--    service-role admin endpoints keep working. Also drop the authenticated
--    SELECT grant so the table is unreachable from the anon client.
-- ---------------------------------------------------------------------------
drop policy if exists "admin_role_audit_admin_select" on public.admin_role_audit;
create policy "admin_role_audit_no_client_select" on public.admin_role_audit
for select using (false);
revoke select on public.admin_role_audit from authenticated;

drop policy if exists "admin_reviews_admin_select" on public.admin_reviews;
create policy "admin_reviews_no_client_select" on public.admin_reviews
for select using (false);
revoke select on public.admin_reviews from authenticated;

-- ---------------------------------------------------------------------------
-- 4. Mutation guards: role and username changes must flow through the
--    service-role backend (which records the audit trail / enforces the
--    username-change policy). Dropping the is_admin() bypass means a stale
--    DB-role admin can no longer self-escalate or bypass the username policy
--    directly from the browser — closing the same revocation gap on writes.
-- ---------------------------------------------------------------------------
create or replace function public.prevent_self_role_escalation()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.role() <> 'service_role' then
    if (tg_op = 'INSERT' and new.role <> 'athlete')
      or (tg_op = 'UPDATE' and new.role is distinct from old.role) then
      raise exception 'Only the backend service role can change profile roles.';
    end if;
  end if;

  return new;
end;
$$;

create or replace function public.prevent_username_policy_bypass()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if auth.role() <> 'service_role' then
    if new.username is distinct from old.username
      or new.username_change_history is distinct from old.username_change_history then
      raise exception 'Use the username change endpoint.';
    end if;
  end if;

  return new;
end;
$$;
