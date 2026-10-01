"""Real PostgreSQL connections: RPCs wait before taking an injury row lock.

REHAB_TEST_DATABASE_URL must point at a disposable localhost PostgreSQL cluster
with CREATE DATABASE/ROLE privileges. Each run creates and drops its own database.
CI supplies this through its PostgreSQL service; ordinary unit runs skip it.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import time
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260930173118_injury_episode_prescription_history.sql"
ATHLETE = "00000000-0000-4000-8000-000000000001"
INJURY = "00000000-0000-4000-8000-000000000002"
EPISODE = "00000000-0000-4000-8000-000000000003"


@pytest.fixture(scope="module")
def postgres_database():
    dsn = os.environ.get("REHAB_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("set REHAB_TEST_DATABASE_URL to run the real PostgreSQL lock tests")
    # Missing drivers must fail in CI when a database was explicitly configured.
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    config = conninfo_to_dict(dsn)
    assert config.get("host") in {"localhost", "127.0.0.1", "::1"}, "test cluster must be local"
    name = "unlxck_rehab_lock_test_" + uuid4().hex
    created_roles = []
    with psycopg.connect(dsn, autocommit=True) as admin:
        for role in ("anon", "authenticated", "service_role"):
            if not admin.execute("select 1 from pg_roles where rolname=%s", (role,)).fetchone():
                admin.execute(sql.SQL("create role {} {}").format(
                    sql.Identifier(role), sql.SQL("bypassrls" if role == "service_role" else "")))
                created_roles.append(role)
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    test_dsn = make_conninfo(dsn, dbname=name)
    try:
        schema = (ROOT / "supabase/schema.sql").read_text(encoding="utf-8")

        def table(table_name):
            return re.search(rf"create table if not exists public\.{table_name} \([\s\S]*?\n\);", schema)[0]

        validator = re.search(
            r"create or replace function public\.injury_flags_infection_signs_valid[\s\S]*?\$\$;", schema)[0]
        with psycopg.connect(test_dsn, autocommit=True) as setup:
            setup.execute(f"""
                create schema auth;
                grant usage on schema auth, public to authenticated, service_role;
                create function auth.uid() returns uuid language sql stable as $$
                  select nullif(current_setting('request.jwt.claim.sub', true),'')::uuid $$;
                create table public.profiles(id uuid primary key);
                create table public.plans(id uuid primary key);
                {validator} {table('injury_flags')}
                alter table injury_flags add column episode_id uuid not null default gen_random_uuid(),
                  add column body_region text, add column side text not null default 'unknown';
                create unique index injury_flags_episode_owner_idx on injury_flags(id,athlete_id,episode_id);
                {table('today_checkins')} {table('session_completions')} {table('rehab_exposures')}
            """)
            # Execute the actual migration, including its injury-update trigger.
            setup.execute((ROOT / "supabase/migrations/20260820170000_add_rehab_response_group_identity.sql").read_text(encoding="utf-8"))
            setup.execute(MIGRATION.read_text(encoding="utf-8"))
            setup.execute("insert into profiles values (%s)", (ATHLETE,))
            setup.execute("""insert into injury_flags(id,athlete_id,description,body_region,side,episode_id)
                values(%s,%s,'ankle sprain','ankle','left',%s)""", (INJURY, ATHLETE, EPISODE))
        yield test_dsn
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))
            for role in reversed(created_roles):
                admin.execute(sql.SQL("drop role {}").format(sql.Identifier(role)))


def event_for(rpc, episode):
    if rpc == "record_injury_episode_event":
        return {"id": str(uuid4()), "injury_id": INJURY, "injury_episode_id": episode,
                "event_type": "clinician_clearance_report",
                "payload": {"source": "athlete_reported", "externally_verified": False, "scopes": ["rehab"]}}
    return {"exposure_id": str(uuid4()), "response_group_id": str(uuid4()), "injury_id": INJURY, "injury_episode_id": episode,
            "drill_id": "ankle_sprain_heel_lowering", "body_region": "ankle", "side": "left",
            "demand": {"target_regions": ["ankle"], "load": "low", "impact": "none", "velocity": "low"},
            "dose_completed": {"completion_state": "performed_amount_unknown"},
            "response": {"during_response": "same", "next_day_response": "not_yet_known"},
            "occurred_at": "2026-09-30T12:00:00Z",
            "provenance": {"source": "athlete_logged_rehab", "recorded_at": "2026-09-30T12:30:00Z"}}


@pytest.mark.parametrize("rpc", ["record_injury_episode_event", "record_rehab_exposure"])
@pytest.mark.parametrize("reopen", [False, True], ids=["same-episode", "reopened-episode"])
def test_rpc_and_injury_update_serialize_without_deadlock(postgres_database, rpc, reopen):
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb

    # Only these two backend connections participate in the race. The writer
    # observes pg_locks itself; no observer connection or timing guess is needed.
    with psycopg.connect(postgres_database) as writer, psycopg.connect(postgres_database) as recorder:
        for connection in (writer, recorder):
            connection.execute("set statement_timeout = '8s'")
            connection.execute("set deadlock_timeout = '200ms'")
            connection.commit()
        episode = str(writer.execute("select episode_id from injury_flags where id=%s", (INJURY,)).fetchone()[0])
        writer.execute("select pg_advisory_xact_lock(hashtextextended('injury:' || %s, 0))", (ATHLETE,))
        event = event_for(rpc, episode)

        def record():
            try:
                recorder.execute(sql.SQL("select public.{}(%s,%s)").format(sql.Identifier(rpc)),
                                 (ATHLETE, Jsonb(event)))
                recorder.commit()
                return None
            except psycopg.Error as error:
                recorder.rollback()
                return error.sqlstate or "client_error"

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(record)
            try:
                deadline = time.monotonic() + 5
                while not writer.execute("""select 1 from pg_locks
                        where pid=%s and locktype='advisory' and not granted""",
                        (recorder.info.backend_pid,)).fetchone():
                    assert not pending.done(), "RPC finished before waiting for the athlete lock"
                    assert time.monotonic() < deadline, "RPC did not reach its advisory lock"
                    time.sleep(0.01)
                # Under the old order the RPC already owns FOR SHARE, so this
                # actual UPDATE and the waiting RPC form a deadlock cycle.
                if reopen:
                    writer.execute("update injury_flags set episode_id=%s, updated_at=now() where id=%s",
                                   (str(uuid4()), INJURY))
                else:
                    writer.execute("update injury_flags set description='updated ankle sprain', updated_at=now() where id=%s",
                                   (INJURY,))
                writer.commit()
                result = pending.result(timeout=10)
                # Reading after the advisory wait must see a reopened episode
                # and reject the stale report instead of accepting old evidence.
                assert result == ("23514" if reopen else None)
            finally:
                writer.rollback()  # release the blocker even if an assertion fails


def test_only_explicit_reports_refresh_recovery_evidence(postgres_database):
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb

    from api.contracts.injury_policy import resolve_injury_policy
    from api.contracts.rehab_schedule import schedule_rehab
    from api.services.injury_episode_service import apply_episode_observations
    from fightcamp.rehab_clinical import load_clinical_policies
    from fightcamp.rehab_protocols import get_rehab_bank

    identity, episode = str(uuid4()), str(uuid4())
    with psycopg.connect(postgres_database, autocommit=True, row_factory=dict_row) as connection:
        connection.execute("""insert into injury_flags(id,athlete_id,description,body_region,side,episode_id,
            status,severity,latest_reported_status) values(%s,%s,'ankle sprain','ankle','left',%s,
            'monitoring','mild','improving')""", (identity, ATHLETE, episode))
        event = event_for("record_rehab_exposure", episode)
        event["injury_id"] = identity
        event["response"]["next_day_response"] = "worse"
        connection.execute("select record_rehab_exposure(%s,%s)", (ATHLETE, Jsonb(event)))

        def decision():
            row = connection.execute("select * from injury_flags where id=%s", (identity,)).fetchone()
            row.update(id=str(row["id"]), athlete_id=str(row["athlete_id"]), episode_id=str(row["episode_id"]),
                       canonical_location="ankle", injury_type="sprain", rehab_stage="restore")
            observations = connection.execute("select * from injury_episode_events where injury_id=%s", (identity,)).fetchall()
            for observation in observations:
                for key in ("athlete_id", "injury_id", "injury_episode_id"):
                    observation[key] = str(observation[key])
            exposures = connection.execute("select * from rehab_exposures where injury_id=%s", (identity,)).fetchall()
            for exposure in exposures:
                exposure["athlete_id"] = str(exposure["athlete_id"])
            row = apply_episode_observations(row, observations)
            result = resolve_injury_policy(row, policies=load_clinical_policies(), bank=get_rehab_bank(), exposures=exposures)
            return row, result, exposures

        original_report = decision()[0]["latest_reported_at"]
        assert decision()[1]["stage"] == "calm"
        # A severity change emits audit history with the inherited improving
        # status; a description change also updates the generic row timestamp.
        connection.execute("update injury_flags set severity='moderate', updated_at=now() where id=%s", (identity,))
        connection.execute("update injury_flags set description='edited ankle sprain', updated_at=now() where id=%s", (identity,))
        row, result, _ = decision()
        assert row["latest_reported_at"] == original_report
        assert result["stage"] == "calm" and not result["prescription"]["is_loading"]
        # An explicit repeat must be recorded even though the value is unchanged.
        connection.execute("update injury_flags set latest_reported_status='improving', updated_at=now() where id=%s", (identity,))
        row, result, exposures = decision()
        assert row["latest_reported_at"] > original_report
        assert result["stage"] == "restore" and result["prescription"]["is_loading"]
        assert schedule_rehab(row, result, training_day="2026-10-08", exposures=exposures)["state"] == "due"


def test_historical_delayed_feedback_remains_owned_and_episode_scoped(postgres_database):
    import psycopg
    from psycopg.types.json import Jsonb

    identity, old_episode, new_episode = str(uuid4()), str(uuid4()), str(uuid4())
    with psycopg.connect(postgres_database, autocommit=True) as connection:
        connection.execute("""insert into injury_flags(id,athlete_id,description,body_region,side,episode_id)
            values(%s,%s,'ankle sprain','ankle','left',%s)""", (identity, ATHLETE, old_episode))
        exposure = event_for("record_rehab_exposure", old_episode)
        exposure["injury_id"] = identity
        connection.execute("select record_rehab_exposure(%s,%s)", (ATHLETE, Jsonb(exposure)))
        connection.execute("update injury_flags set episode_id=%s where id=%s", (new_episode, identity))
        pending = connection.execute("select id from pending_delayed_rehab(%s,'2026-10-08') where injury_id=%s", (ATHLETE, identity)).fetchall()
        assert [str(r[0]) for r in pending] == [exposure["exposure_id"]]
        report = dict(id=str(uuid4()), injury_id=identity, injury_episode_id=old_episode,
                      event_type="delayed_rehab_response", payload=dict(exposure_id=exposure["exposure_id"], response="worse"))
        connection.execute("select record_injury_episode_event(%s,%s)", (ATHLETE, Jsonb(report)))
        saved = connection.execute("select injury_episode_id from injury_episode_events where id=%s", (report["id"],)).fetchone()
        assert str(saved[0]) == old_episode
        assert not connection.execute("select id from pending_delayed_rehab(%s,'2026-10-08') where injury_id=%s", (ATHLETE, identity)).fetchall()
        with pytest.raises(psycopg.Error) as failure:
            connection.execute("select record_injury_episode_event(%s,%s)", (ATHLETE, Jsonb({**report, "id": str(uuid4()), "injury_episode_id": new_episode})))
        assert failure.value.sqlstate == "23514"
