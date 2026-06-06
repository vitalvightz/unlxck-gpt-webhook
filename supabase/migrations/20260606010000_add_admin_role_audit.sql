-- Admin role change audit trail.
--
-- UNLXCK_ADMIN_EMAILS only seeds profiles.role at first profile creation; after
-- that, role changes happen through the service-role backend
-- (api/store.py::set_profile_role, driven by tools/manage_admin.py). Without an
-- audit trail there is no record of who granted or revoked admin access or why.
-- This table captures every change. Rows are written by the service role only;
-- target_athlete_id is nullable + ON DELETE SET NULL so the audit history
-- survives profile deletion (target_email preserves the identity either way).

create table if not exists public.admin_role_audit (
  id uuid primary key default gen_random_uuid(),
  target_athlete_id uuid references public.profiles(id) on delete set null,
  target_email text not null,
  previous_role public.app_role,
  new_role public.app_role not null,
  action text not null check (action in ('promote', 'revoke')),
  actor text not null,
  reason text,
  created_at timestamptz not null default now()
);

create index if not exists admin_role_audit_target_email_idx
  on public.admin_role_audit (target_email);
create index if not exists admin_role_audit_created_at_idx
  on public.admin_role_audit (created_at desc);

-- Writes go through the service role (which bypasses RLS). Browser clients get
-- no access by default; admins may read the trail for accountability. There is
-- deliberately no insert/update/delete policy, so even an admin browser session
-- cannot forge or tamper with audit rows.
alter table public.admin_role_audit enable row level security;

drop policy if exists "admin_role_audit_admin_select" on public.admin_role_audit;
create policy "admin_role_audit_admin_select" on public.admin_role_audit
for select using (public.is_admin());

revoke all on public.admin_role_audit from anon;
revoke insert, update, delete on public.admin_role_audit from authenticated;
grant select on public.admin_role_audit to authenticated;
grant all on public.admin_role_audit to service_role;
