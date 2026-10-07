-- Report private-schema function names from public.runtime_schema_introspection()
-- so the deploy gate (tools/check_supabase_runtime_schema.py) can verify the
-- helpers moved to `private` by
-- 20260726162809_harden_internal_functions_and_search_paths.sql
-- (is_admin, prevent_self_role_escalation, prevent_username_policy_bypass).
--
-- Additive: every existing key is unchanged; `private_functions` is new, so an
-- older checker that ignores it keeps working. Still catalog metadata only.
create or replace function public.runtime_schema_introspection()
returns jsonb
language sql
security definer
stable
set search_path = public
as $$
  select jsonb_build_object(
    'tables', (
      select coalesce(jsonb_agg(table_name order by table_name), '[]'::jsonb)
      from information_schema.tables
      where table_schema = 'public'
        and table_type = 'BASE TABLE'
    ),
    'columns', (
      select coalesce(jsonb_object_agg(table_name, cols), '{}'::jsonb)
      from (
        select table_name, jsonb_agg(column_name order by column_name) as cols
        from information_schema.columns
        where table_schema = 'public'
        group by table_name
      ) grouped
    ),
    'functions', (
      select coalesce(jsonb_agg(distinct p.proname order by p.proname), '[]'::jsonb)
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'public'
    ),
    'private_functions', (
      select coalesce(jsonb_agg(distinct p.proname order by p.proname), '[]'::jsonb)
      from pg_proc p
      join pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'private'
    ),
    'indexes', (
      select coalesce(jsonb_agg(indexname order by indexname), '[]'::jsonb)
      from pg_indexes
      where schemaname = 'public'
    ),
    'constraints', (
      select coalesce(jsonb_agg(c.conname order by c.conname), '[]'::jsonb)
      from pg_constraint c
      join pg_namespace n on n.oid = c.connamespace
      where n.nspname = 'public'
    ),
    'rls', (
      select coalesce(jsonb_object_agg(c.relname, c.relrowsecurity), '{}'::jsonb)
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
      where n.nspname = 'public'
        and c.relkind = 'r'
    )
  );
$$;

revoke all on function public.runtime_schema_introspection() from public;
revoke all on function public.runtime_schema_introspection() from anon;
revoke all on function public.runtime_schema_introspection() from authenticated;
grant execute on function public.runtime_schema_introspection() to service_role;
