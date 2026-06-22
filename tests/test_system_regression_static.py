from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "supabase" / "schema.sql"
ENV_EXAMPLE = ROOT / ".env.example"


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_supabase_auth_redirects_use_configured_site_origin():
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    auth_form = _read("web/components/auth-form.tsx")
    forgot_password = _read("web/app/forgot-password/page.tsx")
    reset_password = _read("web/app/reset-password/page.tsx")

    assert "NEXT_PUBLIC_SITE_URL=http://localhost:3000" in env_example
    assert 'import { getSiteOrigin } from "@/lib/site-url";' in auth_form
    assert 'import { getSiteOrigin } from "@/lib/site-url";' in forgot_password
    assert "emailRedirectTo: siteOrigin ? `${siteOrigin}/login` : undefined" in auth_form
    assert "redirectTo: siteOrigin ? `${siteOrigin}/reset-password` : undefined" in forgot_password
    assert 'router.replace("/login")' in reset_password
    assert "client.auth.updateUser({ password })" in reset_password
    assert "client.auth.signOut()" in reset_password


def test_reset_password_expired_link_fallback_is_statically_present():
    reset_password = _read("web/app/reset-password/page.tsx")

    assert 'hashParams.get("error_description") || hashParams.get("error")' in reset_password
    assert "This reset link is expired or invalid. Please request a new one." in reset_password
    assert 'href="/forgot-password"' in reset_password
    assert "Request a new reset link" in reset_password


def test_settings_page_keeps_username_and_password_sections():
    settings = _read("web/app/settings/page.tsx")

    assert "settingsUsername" in settings
    assert "username_rate_limit" in settings
    assert "Update username" in settings
    assert "currentPassword" in settings
    assert "newPassword" in settings
    assert "Update password" in settings


def test_store_change_username_uses_shared_validator():
    store = _read("api/store.py")
    supabase_store = store.split("class SupabaseAppStore:", 1)[1]

    change_username = re.search(
        r"def change_username\(self, athlete_id: str, username: str\).*?def get_latest_intake",
        supabase_store,
        re.DOTALL,
    )
    assert change_username is not None
    assert "normalized = validate_username(username)" in change_username.group(0)
    assert '"change_profile_username"' in change_username.group(0)


def test_schema_contains_required_role_and_username_security_triggers():
    schema = SCHEMA.read_text(encoding="utf-8")

    assert "create or replace function public.prevent_self_role_escalation()" in schema
    assert re.search(
        r"create trigger profiles_prevent_self_role_escalation\s+before insert or update on public\.profiles",
        schema,
        re.IGNORECASE,
    )
    role_guard = re.search(
        r"create or replace function public\.prevent_self_role_escalation\(\).*?\$\$;",
        schema,
        re.IGNORECASE | re.DOTALL,
    )
    assert role_guard is not None
    role_guard_text = role_guard.group(0)
    assert "auth.role() <> 'service_role'" in role_guard_text
    assert "not public.is_admin()" in role_guard_text
    assert "Only admins can change profile roles." in role_guard_text

    assert "username text unique" in schema
    assert "username_change_history jsonb not null default '[]'::jsonb" in schema
    assert "active_plan_id uuid references public.plans(id) on delete set null" in schema
    assert "profiles_active_plan_id_idx" in schema
    assert "profiles_username_key" in schema
    assert "profiles_username_length" in schema
    assert "profiles_username_lowercase" in schema
    assert "profiles_username_format" in schema
    assert "create or replace function public.prevent_username_policy_bypass()" in schema
    assert "create trigger profiles_prevent_username_policy_bypass" in schema


def test_schema_blocks_direct_critical_table_mutation_rls_policies():
    schema = SCHEMA.read_text(encoding="utf-8")

    for policy in (
        "plans_self_or_admin_insert",
        "plans_self_or_admin_update",
        "plans_self_or_admin_delete",
        "intakes_self_or_admin_insert",
        "intakes_self_or_admin_update",
        "intakes_self_or_admin_delete",
        "generation_jobs_self_or_admin_insert",
        "generation_jobs_self_or_admin_update",
        "generation_jobs_self_or_admin_delete",
    ):
        assert f'drop policy if exists "{policy}"' in schema
        assert f'create policy "{policy}"' not in schema

    for policy in (
        "plans_self_or_admin_select",
        "intakes_self_or_admin_select",
        "generation_jobs_self_or_admin_select",
    ):
        assert f'create policy "{policy}"' in schema
