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
CARRY_MIGRATION = MIGRATIONS / "20261007210000_carry_intake_injury_across_plans.sql"


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
    connection.execute(CARRY_MIGRATION.read_text(encoding="utf-8"))


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


def _sync_key(connection, athlete, plan, key, area, description):
    return connection.execute(
        """select adopt_or_create_intake_injury_flag_with_wound_fields(
             %s, %s, %s, %s, %s, 'moderate', 'open', null, null, null, '[]'::jsonb, null, null)""",
        (athlete, plan, key, area, description),
    ).fetchone()[0]


def _live_flags(connection, athlete):
    return connection.execute(
        "select id::text, plan_id::text, description from injury_flags"
        " where athlete_id = %s and status in ('open', 'monitoring') order by created_at",
        (athlete,),
    ).fetchall()


def test_a_new_plan_carries_the_live_injury_and_never_carries_a_resolved_one(postgres_database):
    import psycopg

    athlete, old_plan, new_plan, third_plan = (str(uuid4()) for _ in range(4))
    with psycopg.connect(postgres_database, autocommit=True) as connection:
        _setup(connection)
        connection.execute("insert into profiles(id) values (%s)", (athlete,))
        for plan in (old_plan, new_plan, third_plan):
            connection.execute("insert into plans(id) values (%s)", (plan,))

        old = _sync_key(connection, athlete, old_plan, f"intake:{old_plan}:a", "Left ankle", "Ankle sprain")
        carried = _sync_key(connection, athlete, new_plan, f"intake:{new_plan}:b", "left-ankle", "Ankle strain")
        assert carried["id"] == old["id"]
        assert _live_flags(connection, athlete) == [(old["id"], new_plan, "Ankle strain")]

        # A repeat read under the carried key is not a write.
        again = _sync_key(connection, athlete, new_plan, f"intake:{new_plan}:b", "left-ankle", "Ankle strain")
        assert again["updated_at"] == carried["updated_at"]

        # Resolved is never carried: listing it again opens a new injury.
        connection.execute("update injury_flags set status = 'resolved', resolved_at = now() where id = %s", (old["id"],))
        reopened = _sync_key(connection, athlete, third_plan, f"intake:{third_plan}:c", "Left ankle", "Ankle sprain")
        assert reopened["id"] != old["id"]
        assert [row[0] for row in _live_flags(connection, athlete)] == [reopened["id"]]


def test_the_migration_merges_existing_cross_plan_duplicates(postgres_database):
    import psycopg

    athlete, old_plan, new_plan = (str(uuid4()) for _ in range(3))
    with psycopg.connect(postgres_database, autocommit=True) as connection:
        _setup(connection)
        connection.execute("insert into profiles(id) values (%s)", (athlete,))
        for plan in (old_plan, new_plan):
            connection.execute("insert into plans(id) values (%s)", (plan,))

        def insert(plan, key, area, description, age):
            return connection.execute(
                """insert into injury_flags(athlete_id, plan_id, source, source_key, body_area, description,
                     severity, status, created_at)
                   values (%s, %s, 'intake', %s, %s, %s, 'moderate', 'open', now() - %s::interval)
                   returning id::text""",
                (athlete, plan, key, area, description, age),
            ).fetchone()[0]

        kept = insert(old_plan, f"intake:{old_plan}:a", "Left ankle", "Ankle sprain", "10 days")
        duplicate = insert(new_plan, f"intake:{new_plan}:a", "Left ankle", "Ankle sprain", "1 day")
        # Two injuries the athlete listed in the same area of one plan stay separate.
        knee_a = insert(new_plan, f"intake:{new_plan}:k1", "Right knee", "Knee sprain", "1 day")
        knee_b = insert(new_plan, f"intake:{new_plan}:k2", "Right knee", "Knee bruise", "1 day")

        connection.execute(CARRY_MIGRATION.read_text(encoding="utf-8"))

        live = {row[0]: row[1] for row in _live_flags(connection, athlete)}
        assert set(live) == {kept, knee_a, knee_b}
        assert live[kept] == new_plan
        retired = connection.execute(
            "select status, source_key from injury_flags where id = %s", (duplicate,)
        ).fetchone()
        assert retired[0] == "resolved"
        assert ":merged-duplicate:" in retired[1]
        # The kept row now answers the new plan's key, so the next sync adopts it.
        synced = _sync_key(connection, athlete, new_plan, f"intake:{new_plan}:a", "Left ankle", "Ankle sprain")
        assert synced["id"] == kept
