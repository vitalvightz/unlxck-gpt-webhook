"""The athlete path, end to end: session done → injury asked → evidence stored.

The contract tests in ``test_rehab_completion_capture.py`` prove the gate makes
the right decisions. These prove the decisions actually reach an athlete and
actually land in the store — that the prompt appears on a rehab session and only
a rehab session, that answering it writes a canonical exposure, and that the
attribution in that exposure came from the server rather than the request.
"""

from datetime import date, timedelta

import pytest

from api.contracts.rehab_completion import build_exposure_id
from tests.support import _build_client, withdraw_health_consent

ATHLETE = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"
SESSION_ID = "s-rehab"

# A real bank drill, so the id resolves through the shipped rehab bank exactly as
# it would in production. Its demand is unreviewed, which is the point: unknown
# demand is a recordable observation and must not block the athlete path.
ANKLE_DRILL = "ankle_sprain_single_leg_balance_on_foam_pad"
KNEE_DRILL = "knee_pain_terminal_knee_extensions_tkes"


def _structured_plan(training_day: str, *, blocks: list[dict]) -> dict:
    return {
        "weeks": [
            {
                "week_index": 1,
                "days": [
                    {
                        "date": training_day,
                        "sessions": [{"session_id": SESSION_ID, "blocks": blocks}],
                    }
                ],
            }
        ]
    }


def _rehab_block(drill_id: str, *, name: str = "Rehab drill", **extra) -> dict:
    return {
        "block_id": f"b-{drill_id}",
        "block_type": "rehab",
        "display_name": name,
        "rehab_drill_id": drill_id,
        **extra,
    }


def _seed_plan(store, *, blocks: list[dict], training_day: str) -> None:
    store.plans[PLAN_ID] = {
        "id": PLAN_ID,
        "athlete_id": "athlete-1",
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
        "structured_plan": _structured_plan(training_day, blocks=blocks),
    }
    store.set_active_plan_id("athlete-1", PLAN_ID)


def _seed_injury(store, *, region: str = "ankle", side: str = "left", **extra) -> dict:
    return store.create_injury_flag(
        "athlete-1",
        {
            "body_area": f"{side} {region}",
            "description": f"{side} {region} sprain",
            "severity": "moderate",
            "status": "open",
            "body_region": region,
            "side": side,
            "injury_type": "sprain",
            **extra,
        },
    )


def _today(client) -> str:
    """The server's own training day, read back rather than assumed."""
    resp = client.post(
        "/api/today/session-completion",
        headers=ATHLETE,
        json={"plan_id": PLAN_ID, "session_id": "s-probe", "status": "started"},
    )
    return resp.json()["completion"]["training_day"]


def _complete(client, *, status: str = "done", **overrides):
    body = {"plan_id": PLAN_ID, "session_id": SESSION_ID, "status": status, **overrides}
    return client.post("/api/today/session-completion", headers=ATHLETE, json=body)


@pytest.fixture()
def rehab_day():
    """A client whose active plan schedules one attributable ankle rehab block."""
    client, store, _ = _build_client()
    # Seed against a placeholder day first so the server can tell us its own.
    _seed_plan(store, blocks=[], training_day="1970-01-01")
    training_day = _today(client)
    _seed_plan(
        store,
        blocks=[_rehab_block(ANKLE_DRILL, name="Single-Leg Balance on Foam Pad", sets=3, reps=10)],
        training_day=training_day,
    )
    injury = _seed_injury(store)
    return client, store, training_day, injury


class TestPromptIsRaisedOnlyForAttributableRehab:
    def test_completed_rehab_session_asks_about_the_injury_by_name(self, rehab_day):
        client, _store, _day, injury = rehab_day

        prompts = _complete(client).json()["rehab_response_prompts"]

        assert [prompt["injury_id"] for prompt in prompts] == [injury["id"]]
        assert prompts[0]["injury_label"] == "LEFT ANKLE"
        assert prompts[0]["drill_ids"] == [ANKLE_DRILL]
        # The server ships the vocabulary with the question, so the client never
        # invents an answer the contract does not accept.
        assert prompts[0]["during_options"] == ["better", "same", "worse", "not_sure"]
        assert prompts[0]["limit_options"] == ["no", "reduced", "stopped"]

    def test_normal_training_session_asks_nothing(self):
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        training_day = _today(client)
        _seed_plan(
            store,
            blocks=[
                {
                    "block_id": "b1",
                    "block_type": "strength",
                    "display_name": "Back Squat",
                    "sets": 5,
                    "reps": 5,
                }
            ],
            training_day=training_day,
        )
        _seed_injury(store)

        assert _complete(client).json()["rehab_response_prompts"] == []

    def test_unstamped_rehab_block_asks_nothing(self):
        """No canonical id means no identifiable drill, so nothing is claimed."""
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        training_day = _today(client)
        _seed_plan(
            store,
            blocks=[
                {
                    "block_id": "b1",
                    "block_type": "rehab",
                    "display_name": "Single-Leg Balance on Foam Pad",
                }
            ],
            training_day=training_day,
        )
        _seed_injury(store)

        assert _complete(client).json()["rehab_response_prompts"] == []

    def test_started_session_asks_nothing(self, rehab_day):
        client, _store, _day, _injury = rehab_day
        assert _complete(client, status="started").json()["rehab_response_prompts"] == []

    def test_skipped_session_asks_nothing(self, rehab_day):
        client, _store, _day, _injury = rehab_day
        body = _complete(client, status="skipped", modification_reason="travel").json()
        assert body["rehab_response_prompts"] == []

    def test_modified_session_still_asks(self, rehab_day):
        client, _store, _day, injury = rehab_day
        body = _complete(client, status="modified", modification_reason="cut it short").json()
        assert [prompt["injury_id"] for prompt in body["rehab_response_prompts"]] == [injury["id"]]

    def test_rehab_for_no_open_injury_asks_nothing(self):
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        training_day = _today(client)
        _seed_plan(store, blocks=[_rehab_block(ANKLE_DRILL)], training_day=training_day)
        # A knee injury cannot claim ankle rehab.
        _seed_injury(store, region="knee", side="right")

        assert _complete(client).json()["rehab_response_prompts"] == []

    def test_withdrawn_health_consent_is_never_asked(self, rehab_day):
        client, store, _day, _injury = rehab_day
        withdraw_health_consent(store)
        assert _complete(client).json()["rehab_response_prompts"] == []


class TestAnsweringStoresEvidence:
    def _answer(self, client, *, injury_id: str, during: str, limit: str, **overrides):
        body = {
            "plan_id": PLAN_ID,
            "session_id": SESSION_ID,
            "answers": [
                {
                    "injury_id": injury_id,
                    "during_response": during,
                    "limit_response": limit,
                }
            ],
            **overrides,
        }
        return client.post("/api/today/rehab-responses", headers=ATHLETE, json=body)

    def test_the_full_path_stores_one_canonical_exposure(self, rehab_day):
        client, store, training_day, injury = rehab_day
        _complete(client)

        resp = self._answer(client, injury_id=injury["id"], during="worse", limit="reduced")

        assert resp.status_code == 201
        assert resp.json()["recorded_injury_ids"] == [injury["id"]]
        assert len(store.rehab_exposures) == 1
        event = next(iter(store.rehab_exposures.values()))["event_json"]
        assert event["injury_id"] == injury["id"]
        assert event["injury_episode_id"] == injury["episode_id"]
        assert event["drill_id"] == ANKLE_DRILL
        assert event["body_region"] == "ankle"
        assert event["side"] == "left"
        assert event["provenance"]["source"] == "athlete_logged_rehab"
        assert event["occurred_at"].startswith(training_day)

    def test_the_answer_is_recorded_as_given(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        self._answer(client, injury_id=injury["id"], during="worse", limit="stopped")

        response = next(iter(store.rehab_exposures.values()))["event_json"]["response"]
        assert response["during_response"] == "worse"
        assert response["stopped_due_to_symptoms"] is True
        # "Worse during this exposure" is not promoted to an injury-level
        # setback, and no pain score is manufactured from a categorical answer.
        assert response.get("worsening_reported") is None
        assert response["pain_during"] is None
        assert response["pain_immediate_after"] is None

    def test_unknown_demand_is_stored_rather_than_blocking(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        self._answer(client, injury_id=injury["id"], during="same", limit="no")

        demand = next(iter(store.rehab_exposures.values()))["event_json"]["demand"]
        assert demand["load"] == "unknown"
        assert demand["impact"] == "unknown"
        assert demand["velocity"] == "unknown"
        assert demand["target_regions"] == ["ankle"]

    def test_prescribed_dose_is_not_echoed_as_completed(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        self._answer(client, injury_id=injury["id"], during="better", limit="no")

        event = next(iter(store.rehab_exposures.values()))["event_json"]
        assert event["prescribed_dose"]["sets"] == 3
        assert event["prescribed_dose"]["reps"] == 10
        # The athlete marked the session done; they never confirmed every rep.
        assert event["dose_completed"]["sets"] is None
        assert event["dose_completed"]["reps"] is None
        assert event["dose_completed"]["completed_fraction"] == 1.0

    def test_reduced_answer_drops_the_full_completion_claim(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        self._answer(client, injury_id=injury["id"], during="same", limit="reduced")

        dose = next(iter(store.rehab_exposures.values()))["event_json"]["dose_completed"]
        assert dose["stopped_early"] is True
        assert dose["completed_fraction"] is None

    def test_resubmitting_cannot_duplicate_the_evidence(self, rehab_day):
        client, store, training_day, injury = rehab_day
        _complete(client)

        first = self._answer(client, injury_id=injury["id"], during="same", limit="no")
        second = self._answer(client, injury_id=injury["id"], during="same", limit="no")

        assert first.json() == second.json()
        assert len(store.rehab_exposures) == 1
        assert first.json()["recorded_exposure_ids"] == [
            str(
                build_exposure_id(
                    athlete_id="athlete-1",
                    injury_episode_id=injury["episode_id"],
                    drill_id=ANKLE_DRILL,
                    session_id=SESSION_ID,
                    training_day=training_day,
                )
            )
        ]


class TestTheClientCannotAssertAttribution:
    def test_an_injury_the_session_did_not_target_is_ignored(self, rehab_day):
        client, store, _day, _injury = rehab_day
        unrelated = _seed_injury(store, region="shoulder", side="right")
        _complete(client)

        resp = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": unrelated["id"],
                        "during_response": "better",
                        "limit_response": "no",
                    }
                ],
            },
        )

        assert resp.status_code == 201
        assert resp.json()["recorded_injury_ids"] == []
        assert store.rehab_exposures == {}

    def test_attribution_fields_cannot_be_sent_at_all(self, rehab_day):
        client, _store, _day, injury = rehab_day
        _complete(client)

        resp = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": injury["id"],
                        "during_response": "better",
                        "limit_response": "no",
                    }
                ],
                "drill_id": KNEE_DRILL,
                "side": "right",
            },
        )

        assert resp.status_code == 422

    def test_an_answer_outside_the_offered_vocabulary_is_rejected(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        resp = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": injury["id"],
                        "during_response": "agony",
                        "limit_response": "no",
                    }
                ],
            },
        )

        assert resp.status_code == 422
        assert store.rehab_exposures == {}

    def test_answering_without_a_completion_records_nothing(self, rehab_day):
        client, store, _day, injury = rehab_day
        # No session-completion posted for SESSION_ID at all.

        resp = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": injury["id"],
                        "during_response": "better",
                        "limit_response": "no",
                    }
                ],
            },
        )

        assert resp.status_code == 404
        assert store.rehab_exposures == {}

    def test_another_athletes_plan_is_refused(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)
        other_plan = "22222222-2222-2222-2222-222222222222"
        store.plans[other_plan] = {
            "id": other_plan,
            "athlete_id": "someone-else",
            "status": "ready",
            "plan_name": "Other",
            "created_at": "2026-06-01T00:00:00+00:00",
        }

        resp = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": other_plan,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": injury["id"],
                        "during_response": "better",
                        "limit_response": "no",
                    }
                ],
            },
        )

        assert resp.status_code == 404
        assert store.rehab_exposures == {}

    def test_a_malformed_plan_id_is_rejected_before_the_database(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        resp = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": "not-a-uuid",
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": injury["id"],
                        "during_response": "better",
                        "limit_response": "no",
                    }
                ],
            },
        )

        assert resp.status_code == 422
        assert store.rehab_exposures == {}

    def test_the_same_injury_cannot_be_answered_twice_in_one_request(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        answer = {
            "injury_id": injury["id"],
            "during_response": "better",
            "limit_response": "no",
        }
        resp = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={"plan_id": PLAN_ID, "session_id": SESSION_ID, "answers": [answer, answer]},
        )

        assert resp.status_code == 422
        assert store.rehab_exposures == {}

    def test_the_endpoint_requires_authentication(self):
        client, _store, _ = _build_client()
        resp = client.post(
            "/api/today/rehab-responses",
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": "x",
                        "during_response": "better",
                        "limit_response": "no",
                    }
                ],
            },
        )
        assert resp.status_code in (401, 403)


class TestConcurrentInjuriesStayIsolated:
    def test_each_injury_gets_its_own_prompt_and_its_own_exposure(self):
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        training_day = _today(client)
        _seed_plan(
            store,
            blocks=[_rehab_block(ANKLE_DRILL), _rehab_block(KNEE_DRILL)],
            training_day=training_day,
        )
        ankle = _seed_injury(store, region="ankle", side="left")
        knee = _seed_injury(store, region="knee", side="right", injury_type="pain")

        prompts = _complete(client).json()["rehab_response_prompts"]
        assert {prompt["injury_id"] for prompt in prompts} == {ankle["id"], knee["id"]}

        # Answer for the ankle only. The knee said nothing, so nothing is stored
        # for the knee — silence is not an observation.
        client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": ankle["id"],
                        "during_response": "worse",
                        "limit_response": "stopped",
                    }
                ],
            },
        )

        stored = [row["event_json"] for row in store.rehab_exposures.values()]
        assert [event["injury_id"] for event in stored] == [ankle["id"]]
        assert stored[0]["body_region"] == "ankle"

    def test_two_open_injuries_in_one_region_are_never_guessed_between(self):
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        training_day = _today(client)
        _seed_plan(store, blocks=[_rehab_block(ANKLE_DRILL)], training_day=training_day)
        _seed_injury(store, region="ankle", side="left")
        _seed_injury(store, region="ankle", side="right")

        assert _complete(client).json()["rehab_response_prompts"] == []


class TestRetroLoggedSessions:
    def test_a_back_filled_session_records_against_the_day_it_happened(self):
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        today = _today(client)
        yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
        _seed_plan(
            store,
            blocks=[_rehab_block(ANKLE_DRILL)],
            training_day=yesterday,
        )
        injury = _seed_injury(store)

        completion = client.post(
            "/api/today/session-completion",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "status": "done",
                "training_day": yesterday,
            },
        ).json()
        assert [p["injury_id"] for p in completion["rehab_response_prompts"]] == [injury["id"]]

        client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "training_day": yesterday,
                "answers": [
                    {
                        "injury_id": injury["id"],
                        "during_response": "same",
                        "limit_response": "no",
                    }
                ],
            },
        )

        event = next(iter(store.rehab_exposures.values()))["event_json"]
        assert event["occurred_at"].startswith(yesterday)
