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
IDENTITY_MIGRATION = MIGRATIONS / "20261008001000_intake_injury_identity_across_plans.sql"


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
    connection.execute(IDENTITY_MIGRATION.read_text(encoding="utf-8"))


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


def _sync_injury(connection, athlete, plan, key, area, description, *, severity="moderate", identity=None):
    return connection.execute(
        """select adopt_or_create_intake_injury_flag_with_wound_fields(
             %s, %s, %s, %s, %s, %s, 'open', null, null, null, '[]'::jsonb, null, null, %s)""",
        (athlete, plan, key, area, description, severity, identity),
    ).fetchone()[0]


def _live_flags(connection, athlete):
    return connection.execute(
        "select id::text, plan_id::text, description, status, severity from injury_flags"
        " where athlete_id = %s and status in ('open', 'monitoring') order by created_at",
        (athlete,),
    ).fetchall()


def _new_athlete(connection, plans):
    athlete = str(uuid4())
    connection.execute("insert into profiles(id) values (%s)", (athlete,))
    ids = [str(uuid4()) for _ in range(plans)]
    for plan in ids:
        connection.execute("insert into plans(id) values (%s)", (plan,))
    return athlete, ids


def test_a_training_impact_change_carries_the_same_injury_onto_the_new_plan(postgres_database):
    import psycopg

    with psycopg.connect(postgres_database, autocommit=True) as connection:
        _setup(connection)
        athlete, (old_plan, new_plan) = _new_athlete(connection, 2)

        old = _sync_injury(connection, athlete, old_plan, f"intake:{old_plan}:a", "Chest",
                           "Chest: strain. [training_impact:limiting]", identity="guided:chest:strain")
        connection.execute("update injury_flags set status = 'monitoring' where id = %s", (old["id"],))
        carried = _sync_injury(connection, athlete, new_plan, f"intake:{new_plan}:b", "Chest",
                               "Chest: strain. [training_impact:not_limiting]", severity="mild",
                               identity="guided:chest:strain")

        assert carried["id"] == old["id"]
        assert _live_flags(connection, athlete) == [
            (old["id"], new_plan, "Chest: strain. [training_impact:not_limiting]", "monitoring", "mild"),
        ]
        # A repeat read under the carried key is not a write.
        again = _sync_injury(connection, athlete, new_plan, f"intake:{new_plan}:b", "Chest",
                             "Chest: strain. [training_impact:not_limiting]", severity="mild",
                             identity="guided:chest:strain")
        assert again["updated_at"] == carried["updated_at"]


def test_a_row_from_before_identity_is_carried_on_area_and_untagged_description(postgres_database):
    import psycopg

    with psycopg.connect(postgres_database, autocommit=True) as connection:
        _setup(connection)
        athlete, (old_plan, new_plan) = _new_athlete(connection, 2)
        old = _sync_injury(connection, athlete, old_plan, f"intake:{old_plan}:a", "Chest",
                           "Chest: strain. [training_impact:limiting]")
        assert old["intake_identity"] is None

        carried = _sync_injury(connection, athlete, new_plan, f"intake:{new_plan}:b", "Chest",
                               "Chest: strain. [training_impact:not_limiting]", identity="guided:chest:strain")
        assert carried["id"] == old["id"]
        assert carried["intake_identity"] == "guided:chest:strain"


def test_distinct_injuries_in_one_area_are_never_merged_and_resolved_is_never_carried(postgres_database):
    import psycopg

    with psycopg.connect(postgres_database, autocommit=True) as connection:
        _setup(connection)
        athlete, (old_plan, new_plan, third_plan) = _new_athlete(connection, 3)
        sprain = _sync_injury(connection, athlete, old_plan, f"intake:{old_plan}:a", "Left ankle",
                              "Left ankle: sprain", identity="guided:l_ankle:sprain")
        blister = _sync_injury(connection, athlete, new_plan, f"intake:{new_plan}:x", "Left ankle",
                               "Left ankle: blister", identity="guided:l_ankle:surface_injury")
        assert blister["id"] != sprain["id"]
        assert [row[:3] for row in _live_flags(connection, athlete)] == [
            (sprain["id"], old_plan, "Left ankle: sprain"),
            (blister["id"], new_plan, "Left ankle: blister"),
        ]

        connection.execute("update injury_flags set status = 'resolved', resolved_at = now() where id = %s",
                           (sprain["id"],))
        reopened = _sync_injury(connection, athlete, third_plan, f"intake:{third_plan}:a", "Left ankle",
                                "Left ankle: sprain", identity="guided:l_ankle:sprain")
        assert reopened["id"] != sprain["id"]
        assert reopened["status"] == "open"


def test_the_migration_merges_existing_duplicates_like_the_reported_chest_strain(postgres_database):
    """Replays production: the same chest strain open on two plans, differing
    only in the training-impact tag, beside unrelated rows that must stay."""
    import psycopg

    with psycopg.connect(postgres_database, autocommit=True) as connection:
        _setup(connection)
        athlete, (old_plan, new_plan) = _new_athlete(connection, 2)

        def insert(plan, key, area, description, status, severity, age):
            return connection.execute(
                """insert into injury_flags(athlete_id, plan_id, source, source_key, body_area, description,
                     severity, status, created_at)
                   values (%s, %s, 'intake', %s, %s, %s, %s, %s, now() - %s::interval)
                   returning id::text""",
                (athlete, plan, key, area, description, severity, status, age),
            ).fetchone()[0]

        kept = insert(old_plan, f"intake:{old_plan}:a", "Chest", "Chest: strain. [training_impact:limiting]",
                      "monitoring", "moderate", "2 hours")
        duplicate = insert(new_plan, f"intake:{new_plan}:b", "Chest", "Chest: strain. [training_impact:not_limiting]",
                           "open", "mild", "10 minutes")
        # A different injury in the same area, open across two plans: never merged.
        old_blister = insert(old_plan, f"intake:{old_plan}:c", "Left ankle", "Left ankle: blister", "open", "mild", "2 hours")
        new_sprain = insert(new_plan, f"intake:{new_plan}:d", "Left ankle", "Left ankle: sprain", "open", "mild", "10 minutes")

        connection.execute(IDENTITY_MIGRATION.read_text(encoding="utf-8"))

        live = {row[0]: row for row in _live_flags(connection, athlete)}
        assert set(live) == {kept, old_blister, new_sprain}
        assert live[kept][1:] == (new_plan, "Chest: strain. [training_impact:not_limiting]", "monitoring", "mild")
        assert live[old_blister][1:3] == (old_plan, "Left ankle: blister")
        retired = connection.execute("select status, source_key from injury_flags where id = %s", (duplicate,)).fetchone()
        assert retired[0] == "resolved" and ":merged-duplicate:" in retired[1]

        # The next Today read for the new plan finds the kept row by its key.
        synced = _sync_injury(connection, athlete, new_plan, f"intake:{new_plan}:b", "Chest",
                              "Chest: strain. [training_impact:not_limiting]", identity="guided:chest:strain")
        assert synced["id"] == kept
