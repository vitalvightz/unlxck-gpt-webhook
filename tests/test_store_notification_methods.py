"""SupabaseAppStore's notification ledger methods issue the queries production runs.

These reads and RPCs used to be raw-client branches inside
notification_foundation, next to an in-memory fallback that every test store
used, so the production queries were not exercised. They are store methods now;
these tests pin the shapes the service depends on.
"""

from datetime import datetime, timedelta, timezone

from api.services.notification_foundation import (
    NotificationCandidate,
    attempt_notification_delivery_claim,
    record_notification_evaluation,
    simulate_notification_delivery_decision,
)
from test_store_xp_methods import RecordingClient, _store

NOW = datetime(2026, 8, 2, 7, 30, tzinfo=timezone.utc)


def _candidate(**overrides) -> NotificationCandidate:
    fields = dict(
        profile_id="p1",
        notification_type="checkin",
        intent="morning_checkin",
        category="checkin_reminders",
        priority=10,
        title="Check in",
        body="Two minutes.",
        url="/today",
        tag="checkin",
        dedupe_key="d1",
        expires_at=NOW + timedelta(hours=4),
        timezone_name="Europe/London",
    )
    fields.update(overrides)
    return NotificationCandidate(**fields)


def test_claim_sends_every_candidate_field_as_an_rpc_parameter():
    client = RecordingClient(
        rpcs={
            "claim_notification_delivery_v2": {
                "decision": "claimed",
                "delivery": {"id": "dl", "claim_token": "ct", "attempt_count": 1},
            }
        }
    )

    attempt = attempt_notification_delivery_claim(_store(client), _candidate(), now_utc=NOW)

    assert attempt.decision == "claimed"
    assert attempt.claim.delivery_id == "dl"
    ((_, (params,)),) = client.calls("claim_notification_delivery_v2")
    assert params == {
        "p_profile_id": "p1",
        "p_notification_type": "checkin",
        "p_intent": "morning_checkin",
        "p_category": "checkin_reminders",
        "p_priority": 10,
        "p_title": "Check in",
        "p_body": "Two minutes.",
        "p_url": "/today",
        "p_tag": "checkin",
        "p_dedupe_key": "d1",
        "p_expires_at": (NOW + timedelta(hours=4)).isoformat(),
        "p_training_day": "2026-08-02",
        "p_scheduled_for": None,
        "p_timing_source": "",
        "p_timing_confidence": "",
        "p_variant_id": "",
        "p_source_event_metadata": {},
        "p_action_key": "",
        "p_notification_class": "routine",
        "p_respect_quiet_hours": True,
        "p_merged_intents": [],
        "p_daily_cap": 6,
        "p_min_spacing_minutes": 45,
    }


def test_claim_sends_optional_candidate_fields_when_present():
    client = RecordingClient(rpcs={"claim_notification_delivery_v2": {"decision": "daily_cap"}})

    attempt = attempt_notification_delivery_claim(
        _store(client),
        _candidate(
            scheduled_for=NOW,
            timing_source="saved_session_time",
            timing_confidence="high",
            variant_id="v2",
            action_key="checkin:2026-08-02",
            source_event_metadata={"plan_id": "plan-1"},
        ),
        now_utc=NOW,
    )

    assert attempt.claim is None and attempt.decision == "daily_cap"
    ((_, (params,)),) = client.calls("claim_notification_delivery_v2")
    assert params["p_scheduled_for"] == NOW.isoformat()
    assert params["p_timing_source"] == "saved_session_time"
    assert params["p_timing_confidence"] == "high"
    assert params["p_variant_id"] == "v2"
    assert params["p_action_key"] == "checkin:2026-08-02"
    assert params["p_source_event_metadata"] == {"plan_id": "plan-1"}


def test_evaluation_rpc_blanks_optional_text_and_sends_the_interval():
    client = RecordingClient(rpcs={"record_notification_evaluation": [{"id": "ev"}]})

    row = record_notification_evaluation(
        _store(client),
        profile_id="p1",
        training_day="2026-08-02",
        intent="morning_checkin",
        now_utc=NOW,
        decision="suppressed",
        rejection_reasons=("quiet_hours",),
        min_persist_interval=timedelta(minutes=30),
    )

    assert row == {"id": "ev"}
    ((_, (params,)),) = client.calls("record_notification_evaluation")
    evaluation_key = params.pop("p_evaluation_key")
    assert len(evaluation_key) == 64  # sha256 of the decision's diagnostic identity
    assert params == {
        "p_profile_id": "p1",
        "p_training_day": "2026-08-02",
        "p_intent": "morning_checkin",
        "p_notification_type": "",
        "p_category": "",
        "p_evaluated_at": NOW.isoformat(),
        "p_scheduled_for": None,
        "p_timing_source": "",
        "p_timing_confidence": "",
        "p_eligible": False,
        "p_decision": "suppressed",
        "p_rejection_reasons": ["quiet_hours"],
        "p_priority": None,
        "p_dedupe_key": "",
        "p_variant_id": "",
        "p_source_event_metadata": {},
        "p_resulting_delivery_id": None,
        "p_min_interval_seconds": 1800,
    }


def test_evaluation_rpc_carries_the_candidate_and_its_snapshot():
    client = RecordingClient(rpcs={"record_notification_evaluation": [{"id": "ev"}]})
    candidate = _candidate(variant_id="v1", scheduled_for=NOW, timing_source="default")

    record_notification_evaluation(
        _store(client),
        profile_id="p1",
        training_day="2026-08-02",
        intent="morning_checkin",
        now_utc=NOW,
        decision="selected",
        eligible=True,
        candidate=candidate,
        resulting_delivery_id="dl",
    )

    ((_, (params,)),) = client.calls("record_notification_evaluation")
    assert params["p_notification_type"] == "checkin"
    assert params["p_category"] == "checkin_reminders"
    assert params["p_dedupe_key"] == "d1"
    assert params["p_variant_id"] == "v1"
    assert params["p_priority"] == 10
    assert params["p_scheduled_for"] == NOW.isoformat()
    assert params["p_eligible"] is True
    assert params["p_resulting_delivery_id"] == "dl"
    assert params["p_min_interval_seconds"] == 0
    assert params["p_source_event_metadata"]["_candidate_snapshot"]["daily_cap"] == 6


def test_simulation_reads_skip_action_states_without_action_keys():
    client = RecordingClient()

    simulate_notification_delivery_decision(_store(client), [_candidate()], now_utc=NOW)

    assert client.calls("notification_action_states") == []
    delivery_reads = [args for name, args in client.calls("notification_deliveries") if name == "select"]
    evaluation_reads = [args for name, args in client.calls("notification_evaluations") if name == "select"]
    assert len(delivery_reads) == 2
    assert len(evaluation_reads) == 2


def test_simulation_reads_action_states_for_candidate_action_keys():
    client = RecordingClient()

    simulate_notification_delivery_decision(
        _store(client), [_candidate(action_key="checkin:2026-08-02")], now_utc=NOW
    )

    assert ("in_", ("action_key", ["checkin:2026-08-02"])) in client.calls(
        "notification_action_states"
    )
