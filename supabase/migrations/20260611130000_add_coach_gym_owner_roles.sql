-- Role foundation: extend public.app_role with the future public-beta roles.
--
-- `athlete` and `admin` remain the only roles that are live in private beta.
-- `coach` and `gym_owner` are reserved so the account/role system can reference
-- them ahead of public beta; they are NOT yet selectable at sign-up and are not
-- assigned to any account. We use `gym_owner` (not `gym`) because a gym is an
-- organisation while the user account is the person managing it.
--
-- ALTER TYPE ... ADD VALUE IF NOT EXISTS is idempotent and, on PostgreSQL 12+
-- (Supabase runs 15), is safe to run in a migration as long as the new values
-- are not used in the same transaction (they are not here). Existing
-- prevent_self_role_escalation() behaviour is intentionally unchanged: normal
-- users may only self-assign 'athlete', so coach/gym_owner accounts cannot be
-- created until that policy is loosened in a future migration.
alter type public.app_role add value if not exists 'coach';
alter type public.app_role add value if not exists 'gym_owner';
