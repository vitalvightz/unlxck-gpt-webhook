"""Real PostgreSQL: syncing intake injuries on a Today read never writes.

Every Today build calls adopt_or_create_intake_injury_flag_with_wound_fields.
When that RPC updated the row unconditionally, the updated_at trigger moved the
injury's updated_at on every read; the live prescription revision includes it,
so starting a session was always refused as "prescription changed".
"""
from pathlib import Path
from uuid import uuid4

from tests import test_rehab_lock_concurrency as lock_tests

postgres_database = lock_tests.postgres_database

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase/migrations"


def _setup(connection):
    # Supabase ships pgcrypto; the source-key migration's backfill uses digest().
    connection.execute("create extension if not exists pgcrypto")
    schema = (ROOT / "supabase/schema.sql").read_text(encoding="utf-8")
    start = schema.index("create or replace function public.set_updated_at()")
    connection.execute(schema[start:schema.index("$$;", start) + 3])
    connection.execute("""drop trigger if exists set_injury_flags_updated_at on public.injury_flags;
        create trigger set_injury_flags_updated_at before update on public.injury_flags
        for each row execute function public.set_updated_at()""")
    connection.execute((MIGRATIONS / "20260804090000_add_intake_injury_source_key.sql").read_text(encoding="utf-8"))
    connection.execute((MIGRATIONS / "20260804093000_preserve_intake_wound_fields.sql").read_text(encoding="utf-8"))
    connection.execute((MIGRATIONS / "20261007193500_skip_noop_intake_wound_field_update.sql").read_text(encoding="utf-8"))


def _sync(connection, athlete, plan, **wound):
    params = {"skin_integrity": None, "bleeding_status": None, "infection_signs": "[]",
              "coverable": None, "drainage": None, **wound}
    return connection.execute(
        """select adopt_or_create_intake_injury_flag_with_wound_fields(
             %s, %s, 'intake:test:chest', 'Chest', 'Chest strain', 'moderate', 'open', null,
             %s, %s, %s::jsonb, %s, %s)""",
        (athlete, plan, params["skin_integrity"], params["bleeding_status"], params["infection_signs"],
         params["coverable"], params["drainage"]),
    ).fetchone()[0]


def test_repeated_sync_leaves_the_injury_untouched_until_a_wound_field_is_new(postgres_database):
    import psycopg

    athlete, plan = str(uuid4()), str(uuid4())
    with psycopg.connect(postgres_database, autocommit=True) as connection:
        _setup(connection)
        connection.execute("insert into profiles(id) values (%s)", (athlete,))
        connection.execute("insert into plans(id) values (%s)", (plan,))

        created = _sync(connection, athlete, plan, skin_integrity="intact")
        # Each autocommit call is its own transaction, so a write would stamp a new now().
        again = _sync(connection, athlete, plan, skin_integrity="intact")
        third = _sync(connection, athlete, plan)
        assert again["id"] == third["id"] == created["id"]
        assert again["updated_at"] == third["updated_at"] == created["updated_at"]

        # A wound field the row lacks is still filled in (and only then is it a write).
        filled = _sync(connection, athlete, plan, drainage="none")
        assert filled["drainage"] == "none"
        assert filled["skin_integrity"] == "intact"
        assert filled["updated_at"] != created["updated_at"]
