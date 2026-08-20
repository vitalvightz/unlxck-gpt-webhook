"""The athlete path, end to end: session done → injury asked → evidence stored.

The contract tests in ``test_rehab_completion_capture.py`` prove the gate makes
the right decisions. These prove the decisions actually reach an athlete and
actually land in the store — that the prompt appears on a rehab session and only
a rehab session, that answering it writes a canonical exposure, and that the
attribution in that exposure came from the server rather than the request.
"""

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from api.contracts.rehab_completion import build_exposure_id
from api.contracts.rehab_exposure import RehabExposureEvent
from tests.support import _build_client, withdraw_health_consent

ATHLETE = {"Authorization": "Bearer athlete-token"}
PLAN_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PLAN_ID = "22222222-2222-2222-2222-222222222222"
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


def _seed_plan(
    store,
    *,
    blocks: list[dict],
    training_day: str,
    plan_id: str = PLAN_ID,
    activate: bool = True,
) -> None:
    store.plans[plan_id] = {
        "id": plan_id,
        "athlete_id": "athlete-1",
        "status": "ready",
        "plan_name": "Camp A",
        "created_at": "2026-06-01T00:00:00+00:00",
        "structured_plan": _structured_plan(training_day, blocks=blocks),
    }
    if activate:
        store.set_active_plan_id("athlete-1", plan_id)


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


def _complete(client, *, status: str = "done", plan_id: str = PLAN_ID, **overrides):
    body = {"plan_id": plan_id, "session_id": SESSION_ID, "status": status, **overrides}
    return client.post("/api/today/session-completion", headers=ATHLETE, json=body)


def _pending(client, *, plan_id: str = PLAN_ID):
    return client.get(
        "/api/today/rehab-responses/pending",
        headers=ATHLETE,
        params={"plan_id": plan_id},
    )


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
        assert prompts[0]["injury_episode_id"] == injury["episode_id"]
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


class TestPendingPromptRehydration:
    @staticmethod
    def _answer(client, prompt: dict, *, plan_id: str = PLAN_ID, **answers):
        return client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": plan_id,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": prompt["injury_id"],
                        "injury_episode_id": prompt["injury_episode_id"],
                        "during_response": answers.get("during", "same"),
                        "limit_response": answers.get("limit", "no"),
                    }
                ],
            },
        )

    def test_completion_persists_identity_and_rehydrates_the_same_prompt(self, rehab_day):
        client, store, training_day, injury = rehab_day
        completion = _complete(client).json()

        row = store.get_session_completion("athlete-1", SESSION_ID, training_day)
        assert row is not None
        [context] = row["rehab_response_contexts"]
        assert context["athlete_id"] == "athlete-1"
        assert context["plan_id"] == PLAN_ID
        assert context["session_id"] == SESSION_ID
        assert context["training_day"] == training_day
        assert context["session_completion_id"] == row["id"]
        assert context["injury_id"] == injury["id"]
        assert context["injury_episode_id"] == injury["episode_id"]
        assert context["response_context_id"] == context["response_group_id"]
        assert len(context["expected_exposures"]) == 1
        serialized = str(context)
        for forbidden in ("demand", "body_region", "side", "load", "impact", "velocity"):
            assert forbidden not in serialized

        response = _pending(client)
        assert response.status_code == 200
        assert response.json()["history_truncated"] is False
        [pending] = response.json()["response_sets"]
        assert pending["completion_id"] == row["id"]
        assert pending["plan_id"] == PLAN_ID
        assert pending["session_id"] == SESSION_ID
        assert pending["training_day"] == training_day
        assert pending["rehab_response_prompts"] == completion["rehab_response_prompts"]

    def test_bounded_plan_history_reports_truncation_without_mutating_contexts(
        self, rehab_day
    ):
        client, store, training_day, _injury = rehab_day
        completion = _complete(client).json()["completion"]
        bucket = store.session_completions["athlete-1"]
        for index in range(500):
            bucket.append(
                {
                    **completion,
                    "id": f"00000000-0000-0000-0000-{index:012d}",
                    "session_id": f"historical-{index}",
                    "rehab_response_contexts": [],
                }
            )

        before = store.get_session_completion("athlete-1", SESSION_ID, training_day)
        response = _pending(client)
        after = store.get_session_completion("athlete-1", SESSION_ID, training_day)

        assert response.status_code == 200
        assert response.json()["history_truncated"] is True
        assert before["rehab_response_contexts"] == after["rehab_response_contexts"]

    def test_successful_answer_removes_prompt_using_canonical_exposures(self, rehab_day):
        client, _store, training_day, _injury = rehab_day
        prompt = _complete(client).json()["rehab_response_prompts"][0]

        assert self._answer(client, prompt).status_code == 201
        assert _pending(client).json()["response_sets"] == []

    def test_partial_write_keeps_one_injury_prompt_recoverable(self):
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        training_day = _today(client)
        _seed_plan(
            store,
            blocks=[
                _rehab_block(ANKLE_DRILL, block_id="rehab-1"),
                _rehab_block(ANKLE_DRILL, block_id="rehab-2"),
            ],
            training_day=training_day,
        )
        _seed_injury(store)
        prompt = _complete(client).json()["rehab_response_prompts"][0]
        original = store.create_rehab_exposure
        calls = 0

        def fail_second(athlete_id, payload):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise HTTPException(status_code=503, detail="simulated partial write")
            return original(athlete_id, payload)

        store.create_rehab_exposure = fail_second
        failed = self._answer(client, prompt)
        store.create_rehab_exposure = original

        assert failed.status_code == 503
        assert len(store.rehab_exposures) == 1
        [pending] = _pending(client).json()["response_sets"]
        assert [item["injury_id"] for item in pending["rehab_response_prompts"]] == [
            prompt["injury_id"]
        ]

        retry = self._answer(client, prompt)
        assert retry.status_code == 201
        assert len(store.rehab_exposures) == 2
        assert _pending(client).json()["response_sets"] == []

    def test_context_failure_does_not_rollback_completion_or_return_volatile_prompt(
        self, rehab_day
    ):
        client, store, training_day, _injury = rehab_day

        def fail_context(*_args, **_kwargs):
            raise RuntimeError("context store unavailable")

        store.initialize_session_completion_rehab_contexts = fail_context
        response = _complete(client)

        assert response.status_code == 201
        assert response.json()["completion_status"] == "done"
        assert response.json()["rehab_response_prompts"] == []
        row = store.get_session_completion("athlete-1", SESSION_ID, training_day)
        assert row is not None and row["status"] == "done"
        assert row.get("rehab_response_contexts") is None

    def test_answering_one_injury_rehydrates_only_the_other(self):
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
        ankle_prompt = next(item for item in prompts if item["injury_id"] == ankle["id"])

        assert self._answer(client, ankle_prompt).status_code == 201
        [pending] = _pending(client).json()["response_sets"]
        assert [item["injury_id"] for item in pending["rehab_response_prompts"]] == [knee["id"]]


class TestAnsweringStoresEvidence:
    def _answer(
        self,
        client,
        *,
        injury_id: str,
        injury_episode_id: str,
        during: str,
        limit: str,
        **overrides,
    ):
        body = {
            "plan_id": PLAN_ID,
            "session_id": SESSION_ID,
            "answers": [
                {
                    "injury_id": injury_id,
                    "injury_episode_id": injury_episode_id,
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

        resp = self._answer(
            client,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
            during="worse",
            limit="reduced",
        )

        assert resp.status_code == 201
        assert resp.json()["recorded_injury_ids"] == [injury["id"]]
        assert len(store.rehab_exposures) == 1
        event = next(iter(store.rehab_exposures.values()))["event_json"]
        assert event["injury_id"] == injury["id"]
        assert event["injury_episode_id"] == injury["episode_id"]
        assert event["response_group_id"]
        assert event["drill_id"] == ANKLE_DRILL
        assert event["body_region"] == "ankle"
        assert event["side"] == "left"
        assert event["provenance"]["source"] == "athlete_logged_rehab"
        assert event["occurred_at"].startswith(training_day)

    def test_the_answer_is_recorded_as_given(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        self._answer(
            client,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
            during="worse",
            limit="stopped",
        )

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

        self._answer(
            client,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
            during="same",
            limit="no",
        )

        demand = next(iter(store.rehab_exposures.values()))["event_json"]["demand"]
        assert demand["load"] == "unknown"
        assert demand["impact"] == "unknown"
        assert demand["velocity"] == "unknown"
        assert demand["target_regions"] == ["ankle"]

    def test_prescribed_dose_is_not_echoed_as_completed(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        self._answer(
            client,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
            during="better",
            limit="no",
        )

        event = next(iter(store.rehab_exposures.values()))["event_json"]
        assert event["prescribed_dose"]["sets"] == 3
        assert event["prescribed_dose"]["reps"] == 10
        # The athlete marked the session done; they never confirmed every rep.
        assert event["dose_completed"]["sets"] is None
        assert event["dose_completed"]["reps"] is None
        assert event["dose_completed"]["completed_fraction"] is None
        assert event["dose_completed"]["completion_state"] == "performed_amount_unknown"

    def test_reduced_answer_drops_the_full_completion_claim(self, rehab_day):
        client, store, _day, injury = rehab_day
        _complete(client)

        self._answer(
            client,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
            during="same",
            limit="reduced",
        )

        dose = next(iter(store.rehab_exposures.values()))["event_json"]["dose_completed"]
        assert dose["stopped_early"] is True
        assert dose["completed_fraction"] is None
        assert dose["completion_state"] == "partial_amount_unknown"

    def test_resubmitting_cannot_duplicate_the_evidence(self, rehab_day):
        client, store, training_day, injury = rehab_day
        _complete(client)

        first = self._answer(
            client,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
            during="same",
            limit="no",
        )
        second = self._answer(
            client,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
            during="same",
            limit="no",
        )

        assert first.json() == second.json()
        assert len(store.rehab_exposures) == 1
        assert first.json()["recorded_exposure_ids"] == [
            str(
                build_exposure_id(
                    athlete_id="athlete-1",
                    plan_id=PLAN_ID,
                    injury_episode_id=injury["episode_id"],
                    drill_id=ANKLE_DRILL,
                    session_id=SESSION_ID,
                    training_day=training_day,
                    rehab_occurrence_key=f"block:b-{ANKLE_DRILL}",
                )
            )
        ]


class TestPlanAndOccurrenceBinding:
    @staticmethod
    def _answer(client, *, plan_id: str, injury_id: str, injury_episode_id: str):
        return client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": plan_id,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": injury_id,
                        "injury_episode_id": injury_episode_id,
                        "during_response": "same",
                        "limit_response": "no",
                    }
                ],
            },
        )

    def test_completion_from_plan_a_cannot_authorize_plan_b(self, rehab_day):
        client, store, training_day, injury = rehab_day
        _complete(client, plan_id=PLAN_ID)
        _seed_plan(
            store,
            plan_id=OTHER_PLAN_ID,
            blocks=[_rehab_block(ANKLE_DRILL, block_id="other-plan-rehab")],
            training_day=training_day,
            activate=False,
        )

        response = self._answer(
            client,
            plan_id=OTHER_PLAN_ID,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
        )

        assert response.status_code == 409
        assert store.rehab_exposures == {}

    def test_completion_identity_cannot_be_rebound_to_another_plan(self, rehab_day):
        client, store, training_day, injury = rehab_day
        original = _complete(client, plan_id=PLAN_ID)
        original_prompt = original.json()["rehab_response_prompts"][0]
        _seed_plan(
            store,
            plan_id=OTHER_PLAN_ID,
            blocks=[_rehab_block(ANKLE_DRILL, block_id="other-plan-rehab")],
            training_day=training_day,
            activate=False,
        )
        rebound = _complete(client, plan_id=OTHER_PLAN_ID)

        refused = self._answer(
            client,
            plan_id=OTHER_PLAN_ID,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
        )

        assert rebound.status_code == 409
        assert rebound.json()["detail"] == "session_completion_plan_mismatch"
        assert refused.status_code == 409
        completion = store.get_session_completion("athlete-1", SESSION_ID, training_day)
        assert completion["plan_id"] == PLAN_ID
        assert completion["rehab_response_contexts"][0]["injury_episode_id"] == (
            original_prompt["injury_episode_id"]
        )
        assert store.rehab_exposures == {}

    def test_same_drill_in_two_blocks_creates_two_idempotent_exposures(self):
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        training_day = _today(client)
        blocks = [
            _rehab_block(ANKLE_DRILL, block_id="rehab-1"),
            _rehab_block(ANKLE_DRILL, block_id="rehab-2"),
        ]
        _seed_plan(store, blocks=blocks, training_day=training_day)
        injury = _seed_injury(store)
        _complete(client)

        first = self._answer(
            client,
            plan_id=PLAN_ID,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
        )
        first_ids = set(first.json()["recorded_exposure_ids"])
        retry = self._answer(
            client,
            plan_id=PLAN_ID,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
        )

        assert first.status_code == 201
        assert len(first_ids) == 2
        assert len(
            {
                row["event_json"]["response_group_id"]
                for row in store.rehab_exposures.values()
            }
        ) == 1
        assert set(retry.json()["recorded_exposure_ids"]) == first_ids
        assert len(store.rehab_exposures) == 2

        _seed_plan(store, blocks=list(reversed(blocks)), training_day=training_day)
        reordered = self._answer(
            client,
            plan_id=PLAN_ID,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
        )
        assert set(reordered.json()["recorded_exposure_ids"]) == first_ids
        assert len(store.rehab_exposures) == 2

    def test_same_completion_occurrence_cannot_be_reused_on_two_plans(self):
        client, store, _ = _build_client()
        _seed_plan(store, blocks=[], training_day="1970-01-01")
        training_day = _today(client)
        block = _rehab_block(ANKLE_DRILL, block_id="rehab-1")
        _seed_plan(store, blocks=[block], training_day=training_day)
        injury = _seed_injury(store)
        _complete(client, plan_id=PLAN_ID)
        first = self._answer(
            client,
            plan_id=PLAN_ID,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
        )

        _seed_plan(
            store,
            plan_id=OTHER_PLAN_ID,
            blocks=[block],
            training_day=training_day,
            activate=False,
        )
        rebound = _complete(client, plan_id=OTHER_PLAN_ID)
        second = self._answer(
            client,
            plan_id=OTHER_PLAN_ID,
            injury_id=injury["id"],
            injury_episode_id=injury["episode_id"],
        )

        assert first.status_code == 201
        assert rebound.status_code == 409
        assert second.status_code == 409
        assert len(store.rehab_exposures) == 1


class TestPromptEpisodeBinding:
    def test_old_prompt_is_rejected_after_the_injury_reopens(self, rehab_day):
        client, store, training_day, injury = rehab_day
        prompt = _complete(client).json()["rehab_response_prompts"][0]
        episode_a = prompt["injury_episode_id"]

        store.update_injury_flag(injury["id"], {"status": "resolved"})
        reopened = store.update_injury_flag(injury["id"], {"status": "open"})
        assert reopened["episode_id"] != episode_a

        _seed_plan(
            store,
            plan_id=OTHER_PLAN_ID,
            blocks=[_rehab_block(ANKLE_DRILL)],
            training_day=training_day,
            activate=False,
        )
        rebound = _complete(client, plan_id=OTHER_PLAN_ID)
        assert rebound.status_code == 409
        assert rebound.json()["detail"] == "session_completion_plan_mismatch"

        # Reload suppresses the stale opportunity rather than rebinding it to
        # the newly opened episode. The immutable saved identity remains A.
        assert _pending(client).json()["response_sets"] == []
        completion = store.get_session_completion("athlete-1", SESSION_ID, training_day)
        assert completion["rehab_response_contexts"][0]["injury_episode_id"] == episode_a

        response = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": prompt["injury_id"],
                        "injury_episode_id": episode_a,
                        "during_response": "same",
                        "limit_response": "no",
                    }
                ],
            },
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "stale_rehab_response"
        assert store.rehab_exposures == {}


class TestTheClientCannotAssertAttribution:
    def test_an_injury_the_saved_context_did_not_target_is_rejected(self, rehab_day):
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
                        "injury_episode_id": unrelated["episode_id"],
                        "during_response": "better",
                        "limit_response": "no",
                    }
                ],
            },
        )

        assert resp.status_code == 409
        assert resp.json()["detail"] == "rehab_response_not_pending"
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
                        "injury_episode_id": injury["episode_id"],
                        "during_response": "better",
                        "limit_response": "no",
                    }
                ],
                "drill_id": KNEE_DRILL,
                "side": "right",
                "episode_id": "33333333-3333-3333-3333-333333333333",
                "demand": {"load": "low", "impact": "none", "velocity": "low"},
                "response_group_id": "44444444-4444-4444-4444-444444444444",
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
                        "injury_episode_id": injury["episode_id"],
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
                        "injury_episode_id": injury["episode_id"],
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
                        "injury_episode_id": injury["episode_id"],
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
                        "injury_episode_id": injury["episode_id"],
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
            "injury_episode_id": injury["episode_id"],
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

    def test_an_event_that_does_not_match_its_injury_never_reaches_the_store(
        self, rehab_day, monkeypatch
    ):
        """The same identity check `POST /api/rehab-exposures` applies.

        Both write paths run `RehabExposureEvent.is_attributable_to` against the
        injury row the event claims. Forcing it to disagree stands in for any
        future drift between the resolution and the record: the write must be
        refused, not stored and reconciled later.
        """
        client, store, _day, injury = rehab_day
        _complete(client)
        monkeypatch.setattr(
            RehabExposureEvent, "is_attributable_to", lambda self, injury: False
        )

        resp = client.post(
            "/api/today/rehab-responses",
            headers=ATHLETE,
            json={
                "plan_id": PLAN_ID,
                "session_id": SESSION_ID,
                "answers": [
                    {
                        "injury_id": injury["id"],
                        "injury_episode_id": injury["episode_id"],
                        "during_response": "same",
                        "limit_response": "no",
                    }
                ],
            },
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
                        "injury_episode_id": "11111111-1111-1111-1111-111111111111",
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
                        "injury_episode_id": ankle["episode_id"],
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
                        "injury_episode_id": injury["episode_id"],
                        "during_response": "same",
                        "limit_response": "no",
                    }
                ],
            },
        )

        event = next(iter(store.rehab_exposures.values()))["event_json"]
        assert event["occurred_at"].startswith(yesterday)
