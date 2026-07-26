begin;

create schema if not exists private authorization postgres;
revoke all on schema private from public;
grant usage on schema private to anon, authenticated, service_role;

-- Move internal SECURITY DEFINER helpers out of the exposed public API schema.
alter function public.is_admin() set schema private;
alter function public.prevent_self_role_escalation() set schema private;
alter function public.prevent_username_policy_bypass() set schema private;

-- Lock function lookup paths to trusted system schemas.
alter function private.is_admin() set search_path = pg_catalog, pg_temp;
alter function private.prevent_self_role_escalation() set search_path = pg_catalog, pg_temp;
alter function private.prevent_username_policy_bypass() set search_path = pg_catalog, pg_temp;
alter function public.set_updated_at() set search_path = pg_catalog, pg_temp;
alter function public.try_parse_timestamptz(text) set search_path = pg_catalog, pg_temp;
alter function public.validate_generation_job_active_lock() set search_path = pg_catalog, pg_temp;

-- RLS policies require is_admin(), but it is no longer available as a public RPC.
revoke all on function private.is_admin() from public, anon, authenticated;
grant execute on function private.is_admin() to anon, authenticated, service_role;

-- Trigger helpers must only run through their bound triggers, never as client RPCs.
revoke all on function private.prevent_self_role_escalation() from public, anon, authenticated;
revoke all on function private.prevent_username_policy_bypass() from public, anon, authenticated;
revoke all on function public.set_updated_at() from public, anon, authenticated;

-- Backend-only helpers remain available to the service role only.
revoke all on function public.try_parse_timestamptz(text) from public, anon, authenticated;
grant execute on function public.try_parse_timestamptz(text) to service_role;
revoke all on function public.validate_generation_job_active_lock() from public, anon, authenticated;
grant execute on function public.validate_generation_job_active_lock() to service_role;

commit;
