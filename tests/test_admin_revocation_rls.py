"""Regression coverage for the P0 admin-revocation gap.

Effective admin access requires BOTH ``profiles.role = 'admin'`` AND membership
in ``UNLXCK_ADMIN_EMAILS``. The env allowlist is the real kill-switch: dropping
an email must revoke cross-athlete access everywhere, including for a browser /
anon Supabase client that authenticates as the user (not service_role).

These tests prove that:

* browser-facing RLS is own-rows-only (``athlete_id = auth.uid()`` /
  ``auth.uid() = id``) — a normal athlete can only reach their own rows;
* a stale ``profiles.role = 'admin'`` no longer buys any client-side
  cross-athlete access, because ``public.is_admin()`` is absent from every
  browser-facing SELECT/UPDATE policy and mutation guard;
* the service-role admin path is preserved (service_role keeps ``grant all`` and
  bypasses RLS);
* users cannot escalate their own role (the guard is service-role-only and the
  profile UPDATE policy is self-only).
"""

from __future__ import annotations

import re
from pathlib import Path

from api.store import is_effective_admin_profile
from tests.support import FakeStore


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "supabase" / "schema.sql"
REVOCATION_MIGRATION_PATH = (
    REPO_ROOT
    / "supabase"
    / "migrations"
    / "20260710120000_revoke_client_admin_cross_athlete_rls.sql"
)


def _read_schema() -> str:
    return SCHEMA_PATH.read_text()


def _read_revocation_migration() -> str:
    return REVOCATION_MIGRATION_PATH.read_text()


# The complete set of browser-facing SELECT/UPDATE policies. None of them may
# grant cross-athlete access via public.is_admin(); each must be own-rows-only.
_OWN_ROW_SELECT_POLICIES = {
    "profiles_self_select": "auth.uid() = id",
    "intakes_self_select": "athlete_id = auth.uid()",
    "plans_self_select": "athlete_id = auth.uid()",
    "generation_jobs_self_select": "athlete_id = auth.uid()",
    "daily_checkins_owner_select": "athlete_id = auth.uid()",
    "session_logs_owner_select": "athlete_id = auth.uid()",
    "injury_flags_owner_select": "athlete_id = auth.uid()",
    "adaptation_notes_owner_select": "athlete_id = auth.uid()",
    "today_checkins_owner_select": "athlete_id = auth.uid()",
    "session_completions_owner_select": "athlete_id = auth.uid()",
}


def _policy_body(schema: str, policy_name: str) -> str:
    match = re.search(
        rf'create policy "{re.escape(policy_name)}"(.*?);',
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, f"policy {policy_name} missing from schema"
    return match.group(1)


def test_normal_athlete_select_policies_are_own_rows_only():
    schema = _read_schema()
    for policy_name, own_row_clause in _OWN_ROW_SELECT_POLICIES.items():
        body = _policy_body(schema, policy_name)
        assert own_row_clause in body, f"{policy_name} must scope to the caller's own rows"
        assert "is_admin" not in body, (
            f"{policy_name} must not grant cross-athlete access via is_admin()"
        )


def test_no_browser_facing_policy_uses_is_admin():
    """A stale DB role='admin' must not unlock any client-side cross-athlete read.

    Every ``using (... public.is_admin())`` / ``with check (... public.is_admin())``
    RLS clause is removed; the only surviving references are the function
    definition and explanatory comments.
    """
    schema = _read_schema()
    assert "or public.is_admin()" not in schema
    assert "using (public.is_admin())" not in schema
    # is_admin() may only appear in the retained function definition (for backend
    # introspection) and in comments — never inside a live policy/guard clause.
    for match in re.finditer(r"public\.is_admin\(\)", schema):
        line_start = schema.rfind("\n", 0, match.start()) + 1
        line = schema[line_start : schema.find("\n", match.start())]
        stripped = line.lstrip()
        assert stripped.startswith("--") or "create or replace function public.is_admin()" in line, (
            f"public.is_admin() used in a live clause: {line!r}"
        )


def test_profiles_update_policy_is_self_only():
    schema = _read_schema()
    body = _policy_body(schema, "profiles_self_update")
    assert "auth.uid() = id" in body
    assert "is_admin" not in body


def test_admin_only_tables_deny_all_browser_access():
    schema = _read_schema()
    for policy_name in ("admin_role_audit_no_client_select", "admin_reviews_no_client_select"):
        body = _policy_body(schema, policy_name)
        assert "using (false)" in body.lower().replace("  ", " ")
    # The authenticated SELECT grant is revoked, so the anon/browser client cannot
    # reach these tables at all.
    assert "revoke all on public.admin_role_audit from authenticated;" in schema
    assert "revoke all on public.admin_reviews from authenticated;" in schema
    assert "grant select on public.admin_role_audit to authenticated;" not in schema
    assert "grant select on public.admin_reviews to authenticated;" not in schema


def test_service_role_admin_path_is_preserved():
    """Cross-athlete admin work runs as service_role, which bypasses RLS. The
    admin-only tables keep their service_role grant so the backend endpoints
    continue to function after the browser access is removed."""
    schema = _read_schema()
    assert "grant all on public.admin_role_audit to service_role;" in schema
    assert "grant all on public.admin_reviews to service_role;" in schema


def test_revocation_migration_removes_client_admin_access():
    migration = _read_revocation_migration()
    # Own-rows-only SELECT policies are created without is_admin().
    for policy_name, own_row_clause in _OWN_ROW_SELECT_POLICIES.items():
        assert f'create policy "{policy_name}"' in migration
    assert "or public.is_admin()" not in migration
    # Admin-only tables are locked to false and the authenticated grant pulled.
    assert 'create policy "admin_role_audit_no_client_select"' in migration
    assert 'create policy "admin_reviews_no_client_select"' in migration
    assert "revoke select on public.admin_role_audit from authenticated;" in migration
    assert "revoke select on public.admin_reviews from authenticated;" in migration
    # Mutation guards drop the is_admin() bypass — no live clause references it
    # (the header comment explaining the history is allowed to mention it).
    assert "not public.is_admin()" not in migration
    assert "using (public.is_admin())" not in migration


def test_effective_admin_requires_env_allowlist_kill_switch():
    """The env allowlist is the real kill-switch: a stale DB role='admin' whose
    email is not in UNLXCK_ADMIN_EMAILS is NOT an effective admin, so the backend
    admin routes stay closed even though the DB role lingers."""
    store = FakeStore(admin_emails={"allowed@unlxck.com"})

    stale_admin = type(
        "P", (), {"role": "admin", "email": "removed@unlxck.com", "athlete_id": "a1"}
    )()
    live_admin = type(
        "P", (), {"role": "admin", "email": "allowed@unlxck.com", "athlete_id": "a2"}
    )()
    athlete = type(
        "P", (), {"role": "athlete", "email": "allowed@unlxck.com", "athlete_id": "a3"}
    )()

    # role=admin but no longer allowlisted -> not effective admin (kill-switch).
    assert is_effective_admin_profile(stale_admin, store) is False
    # role=admin AND allowlisted -> effective admin.
    assert is_effective_admin_profile(live_admin, store) is True
    # allowlisted email but role=athlete -> not admin (both are required).
    assert is_effective_admin_profile(athlete, store) is False
