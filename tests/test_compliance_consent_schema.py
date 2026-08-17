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
    # profiles_self_update lets a browser update its own row, so the trigger is
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
