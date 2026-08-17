"""Schema parity for the age and consent columns.

The canonical `schema.sql` and the migration that gets a live database there
have to agree — a trigger that exists in only one of them is a deploy-time
surprise, not a test-time one.
"""

from pathlib import Path

from api.schema_requirements import REQUIRED_PROFILES_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (ROOT / "supabase" / "schema.sql").read_text(encoding="utf-8")
MIGRATION = (
    ROOT / "supabase" / "migrations" / "20260817120000_add_compliance_age_and_consent.sql"
).read_text(encoding="utf-8")
BOOLEAN_MIGRATION = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260817130000_add_health_data_consent_boolean.sql"
).read_text(encoding="utf-8")

CONSENT_COLUMNS = (
    "date_of_birth",
    "terms_version",
    "terms_accepted_at",
    "health_consent_version",
    "health_consent_at",
    "health_consent_withdrawn_at",
)


def test_every_consent_column_exists_in_both():
    for column in CONSENT_COLUMNS:
        assert column in SCHEMA, column
        assert f"add column if not exists {column}" in MIGRATION, column


def test_the_runtime_schema_check_requires_the_consent_columns():
    # Without this the gate would silently read a missing column as "not
    # consented" for every athlete, locking the whole userbase out instead of
    # failing the deploy.
    for column in CONSENT_COLUMNS:
        assert column in REQUIRED_PROFILES_COLUMNS, column


def test_current_health_consent_choice_is_stored_with_the_timestamps():
    assert "health_data_consent boolean not null default false" in SCHEMA
    assert "add column if not exists health_data_consent boolean not null default false" in BOOLEAN_MIGRATION
    assert "health_data_consent" in REQUIRED_PROFILES_COLUMNS
    assert "new.health_data_consent is distinct from old.health_data_consent" in SCHEMA
    assert "new.health_data_consent is distinct from old.health_data_consent" in BOOLEAN_MIGRATION


def test_the_migration_is_additive():
    lowered = MIGRATION.lower()
    assert "drop column" not in lowered
    assert "drop table" not in lowered
    # Nullable and default-free: every existing profile stays valid and simply
    # reads as "has not consented yet". Scoped to the ALTER TABLE block, since
    # the trigger bodies below it legitimately test columns with `is not null`.
    alter_block = lowered.split("alter table public.profiles", 1)[1].split(";", 1)[0]
    assert "not null" not in alter_block
    assert "default" not in alter_block


def test_clients_cannot_write_their_own_consent_evidence():
    # The live UPDATE policy (profiles_self_or_admin_update) lets a browser
    # write its own row and a DB-role admin write anyone's, so the trigger is
    # what stops an athlete stamping their own terms_accepted_at or editing a
    # date of birth out of the under-18 band.
    for sql in (SCHEMA, MIGRATION):
        assert "prevent_client_compliance_writes" in sql
        assert "auth.role() <> 'service_role'" in sql
    assert "profiles_prevent_client_compliance_writes" in SCHEMA
    assert "profiles_prevent_client_compliance_writes" in MIGRATION


def test_the_minimum_age_floor_is_enforced_in_the_database():
    for sql in (SCHEMA, MIGRATION):
        assert "enforce_profile_minimum_age" in sql
        assert "current_date - interval '13 years'" in sql
    assert "profiles_enforce_minimum_age" in SCHEMA
    assert "profiles_enforce_minimum_age" in MIGRATION


def test_guard_helpers_follow_the_internal_hardening_convention():
    # 20260726162809_harden_internal_functions_and_search_paths moved guard
    # helpers into `private` with a pinned search_path so they cannot be reached
    # as client RPCs or hijacked through search-path injection. A new guard in
    # `public` with an unpinned path would quietly reverse that.
    for helper in ("prevent_client_compliance_writes", "enforce_profile_minimum_age"):
        for sql in (SCHEMA, MIGRATION):
            assert f"create or replace function private.{helper}()" in sql, helper
            assert f"public.{helper}" not in sql, helper
            assert f"execute function private.{helper}()" in sql, helper
        body = MIGRATION.split(f"create or replace function private.{helper}()", 1)[1]
        assert "set search_path = pg_catalog, pg_temp" in body.split("as $$", 1)[0], helper
        assert (
            f"revoke all on function private.{helper}() from public, anon, authenticated"
            in MIGRATION
        ), helper


def test_the_auth_signup_guard_matches_its_sibling_shape():
    # private.enforce_auth_signup_rate_limit is SECURITY DEFINER with
    # search_path = pg_catalog because it runs during signup under the auth
    # admin role. The age guard sits on the same table and matches it.
    header = MIGRATION.split(
        "create or replace function private.enforce_auth_signup_minimum_age()", 1
    )[1].split("as $$", 1)[0]
    assert "security definer" in header
    assert "set search_path = pg_catalog" in header
    assert (
        "revoke all on function private.enforce_auth_signup_minimum_age() "
        "from public, anon, authenticated" in MIGRATION
    )


def test_the_migration_is_transactional():
    # Matches the hardening migrations: a partially applied consent guard would
    # leave the columns present but unprotected.
    statements = "\n".join(
        line for line in MIGRATION.splitlines() if not line.strip().startswith("--")
    ).strip()
    assert statements.startswith("begin;")
    assert statements.endswith("commit;")


def test_under_13_signup_is_refused_at_the_auth_layer():
    # Applies even when a caller bypasses unlxck.com and posts straight to
    # /auth/v1/signup, mirroring the existing signup rate-limit guard.
    assert "private.enforce_auth_signup_minimum_age" in MIGRATION
    assert "before insert on auth.users" in MIGRATION
    assert "under_minimum_age" in MIGRATION


def test_private_trial_acknowledgement_is_left_alone():
    # The requirement is explicit: private_trial_ack_at must not be repurposed
    # as Terms or health-data consent evidence. The migration may mention it in
    # prose (it says exactly that) but must never read or write it.
    statements = "\n".join(
        line for line in MIGRATION.splitlines() if not line.strip().startswith("--")
    )
    assert "private_trial_ack_at" not in statements
    assert "private_trial_ack_at timestamptz" in SCHEMA
