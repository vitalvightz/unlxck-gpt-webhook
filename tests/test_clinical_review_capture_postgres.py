"""Real local PostgreSQL role boundaries and two-connection capture races."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

import pytest

from api.services.clinical_review_capture_service import build_review_context, record_clinical_review
from tests.clinical_capture_fixtures import ADMIN, capture_bundle
from tests import test_rehab_lock_concurrency as lock_tests

postgres_database = lock_tests.postgres_database

MIGRATION = Path(__file__).resolve().parents[1] / "supabase/migrations/20261007133906_clinical_progression_review_capture.sql"


@pytest.fixture(scope="module")
def capture_postgres(postgres_database):
    import psycopg
    with psycopg.connect(postgres_database, autocommit=True) as connection:
        connection.execute("""alter table profiles add column role text default 'athlete',
            add column access_status text default 'approved', add column date_of_birth date,
            add column terms_version text, add column terms_accepted_at timestamptz,
            add column health_data_consent boolean default false, add column health_consent_version text,
            add column health_consent_at timestamptz, add column health_consent_withdrawn_at timestamptz""")
        connection.execute(MIGRATION.read_text(encoding="utf-8"))
        connection.execute(MIGRATION.read_text(encoding="utf-8"))
        connection.execute("insert into profiles(id,role) values(%s,'admin')", (ADMIN,))
        connection.execute("grant select on injury_flags,today_checkins,rehab_exposures,session_completions to service_role")
    return postgres_database


class PostgresCaptureStore:
    def __init__(self, dsn, athlete, injury, episode):
        self.dsn, self.scope = dsn, (athlete, injury, episode)
        self.saved_events = []

    def is_admin_email(self, email):
        return email == "operator@example.test"

    def get_clinical_review_capture_context(self, athlete_id, injury_id, episode_id):
        import psycopg
        with psycopg.connect(self.dsn) as connection:
            connection.execute("set local role service_role")
            return connection.execute("select clinical_review_capture_context(%s,%s,%s)",
                                      (athlete_id,injury_id,episode_id)).fetchone()[0]

    def record_clinical_review_event(self, athlete_id, recorder_id, context, event, supersession):
        import psycopg
        from psycopg.types.json import Jsonb
        self.saved_events.append((deepcopy(context),deepcopy(event),deepcopy(supersession)))
        with psycopg.connect(self.dsn) as connection:
            connection.execute("set local role service_role")
            return connection.execute("select to_jsonb(record_clinical_review_event(%s,%s,%s,%s,%s))",
                (athlete_id,recorder_id,Jsonb(context),Jsonb(event),Jsonb(supersession) if supersession else None)).fetchone()[0]


def postgres_bundle(dsn):
    import psycopg
    from psycopg import sql
    now = datetime.now(timezone.utc)
    fake, recorder, request, kwargs = capture_bundle(as_of=now)
    athlete, injury, episode = map(str, (uuid4(),uuid4(),uuid4()))
    profile = dict(fake.snapshot["profile"], id=athlete)
    with psycopg.connect(dsn) as connection:
        connection.execute(sql.SQL("insert into profiles({}) values({})").format(
            sql.SQL(',').join(map(sql.Identifier,profile)), sql.SQL(',').join(sql.Placeholder() for _ in profile)), tuple(profile.values()))
        connection.execute("""insert into injury_flags(id,athlete_id,episode_id,description,body_area,body_region,side,
            status,severity,latest_reported_status,created_at,updated_at)
            values(%s,%s,%s,'Left ankle sprain','Left ankle','ankle','left','monitoring','mild','improving',
            now()-interval '30 days',now()-interval '1 day')""", (injury,athlete,episode))
    store = PostgresCaptureStore(dsn,athlete,injury,episode)
    snapshot = store.get_clinical_review_capture_context(*store.scope)
    context = build_review_context(snapshot, definition=kwargs["registry"].current(request.criterion_id),
        policy=kwargs["policies"][0],bank=kwargs["bank"],as_of=datetime.now(timezone.utc))
    confirmed = datetime.now(timezone.utc)
    raw = request.model_dump(mode="json")
    raw.update(athlete_id=athlete,injury_id=injury,injury_episode_id=episode)
    raw["statement"].update(reviewed_at=confirmed.isoformat(),confirmed_at=confirmed.isoformat(),
        reviewed_packet_revision=context.current_packet.packet_revision)
    from api.contracts.clinical_review_capture import ClinicalReviewCaptureRequest
    kwargs.pop("as_of")
    return store,recorder,ClinicalReviewCaptureRequest.model_validate(raw),kwargs


def call_writer(connection, store, captured):
    from psycopg.types.json import Jsonb
    context,event,supersession = captured
    return connection.execute("select to_jsonb(record_clinical_review_event(%s,%s,%s,%s,%s))",
        (store.scope[0],ADMIN,Jsonb(context),Jsonb(event),Jsonb(supersession) if supersession else None)).fetchone()[0]


def test_real_service_channel_privileges_private_owner_stream_and_immutability(capture_postgres):
    import psycopg
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    result = record_clinical_review(store,recorder=recorder,request=request,**kwargs)
    assert record_clinical_review(store,recorder=recorder,request=request,**kwargs) == result
    captured = store.saved_events[0]
    with psycopg.connect(capture_postgres) as connection:
        for role in ("anon","authenticated"):
            for fn in ("clinical_review_capture_context(uuid,uuid,uuid)","record_clinical_review_event(uuid,uuid,jsonb,jsonb,jsonb)"):
                assert not connection.execute("select has_function_privilege(%s,%s,'EXECUTE')",(role,fn)).fetchone()[0]
            with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
                connection.execute(f"set local role {role}")
                call_writer(connection,store,captured)
        for subject in (store.scope[0],str(uuid4()),ADMIN):
            with connection.transaction():
                connection.execute("set local role authenticated")
                connection.execute("select set_config('request.jwt.claim.sub',%s,true)",(subject,))
                assert connection.execute("select count(*) from injury_episode_events where id=%s",(result.event_id,)).fetchone()[0] == 0
                with pytest.raises(psycopg.errors.InsufficientPrivilege), connection.transaction():
                    connection.execute("insert into injury_episode_events select * from injury_episode_events limit 1")
        connection.execute("reset role")
        assert connection.execute("select count(*) from injury_episode_events where id=%s",(result.event_id,)).fetchone()[0] == 1
        with pytest.raises(psycopg.Error,match="immutable"),connection.transaction():
            connection.execute("update injury_episode_events set payload=payload where id=%s",(result.event_id,))
        with pytest.raises(psycopg.Error,match="unknown episode event"),connection.transaction():
            from psycopg.types.json import Jsonb
            connection.execute("select record_injury_episode_event(%s,%s)",(store.scope[0],Jsonb(captured[1])))


def test_concurrent_exact_duplicates_return_one_original_result(capture_postgres):
    import psycopg
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    captured = candidate_event(store,recorder,request,kwargs)
    identity = captured[1]["id"]
    def duplicate():
        with psycopg.connect(capture_postgres) as connection:
            connection.execute("set local role service_role")
            return call_writer(connection,store,captured)["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _:duplicate(), range(2))) == [identity]*2
    with psycopg.connect(capture_postgres) as connection:
        assert connection.execute("select count(*) from injury_episode_events where id=%s",(identity,)).fetchone()[0] == 1
        changed = deepcopy(captured)
        changed[1]["clinical_capture"]["request_hash"] = "0"*64
        with pytest.raises(psycopg.Error,match="request_conflict"),connection.transaction():
            call_writer(connection,store,changed)


@pytest.mark.parametrize("mutation", ["setback","closure","episode","assessment","withdrawal","admin_revocation"])
def test_in_flight_capture_waits_then_rejects_changed_locked_context(capture_postgres, mutation):
    import psycopg
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    # Build/validate without writing, then race the real writer against a mutation.
    original = store.record_clinical_review_event
    captured = []
    def intercept(athlete_id,recorder_id,context,event,supersession):
        captured.append((context,event,supersession))
        return event
    store.record_clinical_review_event = intercept
    record_clinical_review(store,recorder=recorder,request=request,**kwargs)
    store.record_clinical_review_event = original
    with psycopg.connect(capture_postgres) as blocker, psycopg.connect(capture_postgres) as writer:
        blocker.execute("select pg_advisory_xact_lock(hashtextextended('injury:' || %s,0))",(store.scope[0],))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(call_writer,writer,store,captured[0])
            deadline = time.monotonic()+5
            while time.monotonic() < deadline:
                if blocker.execute("select wait_event from pg_stat_activity where pid=%s",(writer.info.backend_pid,)).fetchone()[0] == 'advisory':
                    break
                time.sleep(.02)
            else:
                pytest.fail("writer did not wait for the existing athlete lock")
            if mutation == "setback":
                blocker.execute("update injury_flags set latest_reported_status='worse',updated_at=clock_timestamp() where id=%s",(store.scope[1],))
            elif mutation == "closure":
                blocker.execute("update injury_flags set status='resolved' where id=%s",(store.scope[1],))
            elif mutation == "episode":
                blocker.execute("update injury_flags set episode_id=%s where id=%s",(uuid4(),store.scope[1]))
            elif mutation == "assessment":
                blocker.execute("""insert into injury_episode_events(id,athlete_id,injury_id,injury_episode_id,event_type,payload)
                    values(%s,%s,%s,%s,'rehab_progression_assessment','{}')""",(uuid4(),*store.scope))
            elif mutation == "withdrawal":
                blocker.execute("update profiles set health_data_consent=false where id=%s",(store.scope[0],))
            else:
                blocker.execute("update profiles set role='athlete' where id=%s",(ADMIN,))
            blocker.commit()
            with pytest.raises(psycopg.Error):
                future.result(timeout=5)
        if mutation == "admin_revocation":
            with psycopg.connect(capture_postgres) as restore:
                restore.execute("update profiles set role='admin' where id=%s",(ADMIN,))
    with psycopg.connect(capture_postgres) as connection:
        assert not connection.execute("select 1 from injury_episode_events where id=%s",(captured[0][1]["id"],)).fetchone()


def test_atomic_supersession_fork_prevention_revocation_and_replay(capture_postgres):
    import psycopg
    from api.contracts.clinical_review_capture import ClinicalReviewLifecycleRequest
    from api.services.clinical_review_capture_service import record_review_lifecycle
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    first = record_clinical_review(store,recorder=recorder,request=request,**kwargs)
    replacement = request.model_copy(update={"request_id":uuid4(),"supersedes_review_id":first.review_id})
    second = record_clinical_review(store,recorder=recorder,request=replacement,**kwargs)
    assert first.review_id != second.review_id
    with psycopg.connect(capture_postgres) as connection:
        assert connection.execute("select count(*) from injury_episode_events where athlete_id=%s and event_type like 'clinical%%'",
                                  (store.scope[0],)).fetchone()[0] == 3
    action = ClinicalReviewLifecycleRequest(request_id=uuid4(), athlete_id=request.athlete_id,injury_id=request.injury_id,
        injury_episode_id=request.injury_episode_id,review_id=second.review_id,action="revoke",
        effective_at=datetime.now(timezone.utc),confirmation_reference="verified-withdrawal",reason="withdrawn")
    revoked = record_review_lifecycle(store,recorder=recorder,request=action)
    assert record_review_lifecycle(store,recorder=recorder,request=action) == revoked
    from tests.test_clinical_review_capture import replay
    store.snapshot = store.get_clinical_review_capture_context(*store.scope)
    assert replay(store,request,dict(kwargs,as_of=datetime.now(timezone.utc)))[1].validity == "invalid"


def candidate_event(store, recorder, request, kwargs, *, lifecycle=False):
    from api.services.clinical_review_capture_service import record_review_lifecycle
    original = store.record_clinical_review_event
    captured = []
    def intercept(athlete_id,recorder_id,context,event,supersession):
        captured.append((context,event,supersession))
        return event
    store.record_clinical_review_event = intercept
    try:
        if lifecycle:
            record_review_lifecycle(store,recorder=recorder,request=request)
        else:
            record_clinical_review(store,recorder=recorder,request=request,**kwargs)
    finally:
        store.record_clinical_review_event = original
    return captured[0]


def wait_for_athlete_lock(observer, future, pid):
    deadline = time.monotonic()+5
    while not observer.execute("select 1 from pg_locks where pid=%s and locktype='advisory' and not granted",(pid,)).fetchone():
        assert not future.done() and time.monotonic()<deadline, "write did not wait for existing athlete lock"
        time.sleep(.01)


@pytest.mark.parametrize("competitor", ["supersession","revocation"])
def test_competing_supersession_and_revoke_write_races(capture_postgres, competitor):
    import psycopg
    from api.contracts.clinical_review_capture import ClinicalReviewLifecycleRequest
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    first = record_clinical_review(store,recorder=recorder,request=request,**kwargs)
    replacement = request.model_copy(update={"request_id":uuid4(),"supersedes_review_id":first.review_id})
    pending = candidate_event(store,recorder,replacement,kwargs)
    if competitor == "supersession":
        competing = candidate_event(store,recorder,replacement.model_copy(update={"request_id":uuid4()}),kwargs)
    else:
        action = ClinicalReviewLifecycleRequest(request_id=uuid4(),athlete_id=request.athlete_id,injury_id=request.injury_id,
            injury_episode_id=request.injury_episode_id,review_id=first.review_id,action="revoke",
            effective_at=datetime.now(timezone.utc),confirmation_reference="confirmed-withdrawal",reason="withdrawn")
        competing = candidate_event(store,recorder,action,kwargs,lifecycle=True)
    with psycopg.connect(capture_postgres) as blocker, psycopg.connect(capture_postgres) as writer:
        call_writer(blocker,store,competing)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(call_writer,writer,store,pending)
            wait_for_athlete_lock(blocker,future,writer.info.backend_pid)
            blocker.commit()
            with pytest.raises(psycopg.Error,match="context_changed"):
                future.result(timeout=5)
    with psycopg.connect(capture_postgres) as connection:
        assert not connection.execute("select 1 from injury_episode_events where id=%s",(pending[1]["id"],)).fetchone()
        count = connection.execute("select count(*) from injury_episode_events where athlete_id=%s and event_type='clinical_progression_review'",
                                   (store.scope[0],)).fetchone()[0]
        assert count == (2 if competitor == "supersession" else 1)


def accepted_snapshot(connection,store,review):
    from api.contracts.clinical_review_validity import FrozenClinicalReviewPin
    athlete,injury,episode = store.scope
    plan,occurrence = str(uuid4()),str(uuid4())
    day = datetime.now(timezone.utc).date().isoformat()
    connection.execute("insert into plans values(%s)",(plan,))
    readiness = connection.execute("""insert into today_checkins(athlete_id,plan_id,training_day,sleep,body,pain,phase,recommendation_state)
        values(%s,%s,%s,'good','normal','none','GPP','train_as_planned') returning id,updated_at""",(athlete,plan,day)).fetchone()
    injuries = connection.execute("select id,episode_id,updated_at from injury_flags where athlete_id=%s and status in ('open','monitoring')",
                                  (athlete,)).fetchall()
    event = connection.execute("select id::text from injury_episode_events where athlete_id=%s order by created_at desc,id desc limit 1",
                               (athlete,)).fetchone()
    selected = review["selected_prescription"]
    pin = FrozenClinicalReviewPin(review_id=review["review_id"],criterion_id=review["criterion_id"],criterion_version=review["criterion_version"],
        **{k:selected[k] for k in ("option_id","option_version","selection_version","materialised_prescription_hash")})
    snapshot = dict(plan_id=plan,training_day=day,revision="a"*64,allocation_limit=2,
        session=dict(session_id=occurrence,blocks=[dict(block_type="rehab",injury_id=injury,injury_episode_id=episode,
            clinical_review_pin=pin.model_dump(mode="json"))]),
        evidence_context=dict(event_id=event[0],exposure_id=None),
        readiness_context=dict(id=str(readiness[0]),updated_at=readiness[1].isoformat()),
        injury_context=[dict(id=str(i[0]),episode_id=str(i[1]),updated_at=i[2].isoformat()) for i in injuries])
    return snapshot


def accept(connection,store,snapshot):
    from psycopg.types.json import Jsonb
    return connection.execute("""insert into session_completions(athlete_id,plan_id,session_id,training_day,status,prescription_snapshot)
        values(%s,%s,%s,%s,'started',%s) returning id""",(store.scope[0],snapshot["plan_id"],snapshot["session"]["session_id"],
                                                     snapshot["training_day"],Jsonb(snapshot))).fetchone()[0]


def test_revoke_acceptance_race_old_pin_cannot_be_refreshed(capture_postgres):
    import psycopg
    from api.contracts.clinical_review_capture import ClinicalReviewLifecycleRequest
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    first = record_clinical_review(store,recorder=recorder,request=request,**kwargs)
    review = store.saved_events[0][1]["payload"]
    with psycopg.connect(capture_postgres) as setup:
        snapshot = accepted_snapshot(setup,store,review)
        with setup.transaction(force_rollback=True):
            accept(setup,store,snapshot)  # Initially usable.
    action = ClinicalReviewLifecycleRequest(request_id=uuid4(),athlete_id=request.athlete_id,injury_id=request.injury_id,
        injury_episode_id=request.injury_episode_id,review_id=first.review_id,action="revoke",
        effective_at=datetime.now(timezone.utc),confirmation_reference="withdrawal",reason="withdrawn")
    revoke = candidate_event(store,recorder,action,kwargs,lifecycle=True)
    with psycopg.connect(capture_postgres) as blocker,psycopg.connect(capture_postgres) as accepter:
        call_writer(blocker,store,revoke)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(accept,accepter,store,snapshot)
            wait_for_athlete_lock(blocker,future,accepter.info.backend_pid)
            blocker.commit()
            with pytest.raises(psycopg.Error,match="prescription_revision_conflict|pin_invalidated_hold"):
                future.result(timeout=5)
    snapshot["evidence_context"]["event_id"] = revoke[1]["id"]
    with psycopg.connect(capture_postgres) as connection:
        with pytest.raises(psycopg.Error,match="pin_invalidated_hold"), connection.transaction():
            accept(connection,store,snapshot)


def test_started_and_completed_prescriptions_keep_history_after_revocation(capture_postgres):
    import psycopg
    from psycopg.types.json import Jsonb
    from api.contracts.clinical_review_capture import ClinicalReviewLifecycleRequest
    from api.services.clinical_review_capture_service import record_review_lifecycle
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    first = record_clinical_review(store,recorder=recorder,request=request,**kwargs)
    with psycopg.connect(capture_postgres) as connection:
        snapshot = accepted_snapshot(connection,store,store.saved_events[0][1]["payload"])
        occurrence = accept(connection,store,snapshot)
    action = ClinicalReviewLifecycleRequest(request_id=uuid4(),athlete_id=request.athlete_id,injury_id=request.injury_id,
        injury_episode_id=request.injury_episode_id,review_id=first.review_id,action="revoke",
        effective_at=datetime.now(timezone.utc),confirmation_reference="withdrawal",reason="withdrawn")
    record_review_lifecycle(store,recorder=recorder,request=action)
    with psycopg.connect(capture_postgres) as connection:
        with pytest.raises(psycopg.Error,match="pin_invalidated_hold"), connection.transaction():
            connection.execute("update session_completions set status='done' where id=%s",(occurrence,))
        connection.execute("update session_completions set status='modified',rehab_performance='stopped' where id=%s",(occurrence,))
        assert connection.execute("select prescription_snapshot from session_completions where id=%s",(occurrence,)).fetchone()[0] == snapshot
        connection.execute("update session_completions set notes='completed history' where id=%s",(occurrence,))
        assert connection.execute("select prescription_snapshot from session_completions where id=%s",(occurrence,)).fetchone()[0] == snapshot
        with pytest.raises(psycopg.Error,match="rehab_exposure_cannot_be_reset"), connection.transaction():
            connection.execute("update session_completions set status='not_started' where id=%s",(occurrence,))
        altered = deepcopy(snapshot)
        altered["session"]["blocks"][0]["clinical_review_pin"]["review_id"] = str(uuid4())
        with pytest.raises(psycopg.Error,match="prescription_revision_conflict"), connection.transaction():
            connection.execute("update session_completions set prescription_snapshot=%s where id=%s",(Jsonb(altered),occurrence))


@pytest.mark.parametrize("mutation", ["athlete","injury","episode","side","author","recorder","verifier","source","qualification","schema","missing_decision"])
def test_sql_rechecks_generic_scope_and_server_owned_envelope(capture_postgres,mutation):
    import psycopg
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    captured = candidate_event(store,recorder,request,kwargs)
    envelope = captured[1]["payload"]
    if mutation in {"athlete","injury","episode"}:
        captured[1][{"athlete":"athlete_id","injury":"injury_id","episode":"injury_episode_id"}[mutation]] = str(uuid4())
    elif mutation == "side":
        envelope["side"] = "right"
    elif mutation == "author":
        envelope["clinical_author"]["author_id"] = ADMIN.upper()
    elif mutation in {"recorder","verifier"}:
        envelope["provenance"][mutation]["actor_id"] = str(uuid4())
    elif mutation == "source":
        envelope["provenance"]["source"] = "athlete_reported"
    elif mutation == "qualification":
        envelope["clinical_author"]["qualification_reference"] = ""
    elif mutation == "schema":
        envelope["schema_version"] = True
    else:
        del envelope["decision"]
    with psycopg.connect(capture_postgres) as connection:
        connection.execute("set local role service_role")
        with pytest.raises(psycopg.Error), connection.transaction():
            call_writer(connection,store,captured)


def test_lifecycle_requires_exact_existing_target_and_correct_replacement(capture_postgres):
    import psycopg
    from api.contracts.clinical_review_capture import ClinicalReviewLifecycleRequest
    from api.services.clinical_review_capture_service import record_review_lifecycle
    store,recorder,request,kwargs = postgres_bundle(capture_postgres)
    first = record_clinical_review(store,recorder=recorder,request=request,**kwargs)
    action = ClinicalReviewLifecycleRequest(request_id=uuid4(),athlete_id=request.athlete_id,injury_id=request.injury_id,
        injury_episode_id=request.injury_episode_id,review_id=first.review_id,action="supersede",replacement_review_id=uuid4(),
        effective_at=datetime.now(timezone.utc),confirmation_reference="confirmed-replacement",reason="replacement")
    with pytest.raises(psycopg.Error,match="replacement_invalid"):
        record_review_lifecycle(store,recorder=recorder,request=action)


def test_same_request_cannot_be_rebound_to_another_valid_owned_episode(capture_postgres):
    import psycopg
    first_store,recorder,first,kwargs = postgres_bundle(capture_postgres)
    record_clinical_review(first_store,recorder=recorder,request=first,**kwargs)
    second_store,second_recorder,second,second_kwargs = postgres_bundle(capture_postgres)
    second = second.model_copy(update={"request_id":first.request_id})
    with pytest.raises(psycopg.Error,match="request_conflict"):
        record_clinical_review(second_store,recorder=second_recorder,request=second,**second_kwargs)
