from datetime import datetime, timedelta, timezone
from copy import deepcopy

import pytest

from api.plan_mappers import (
    _derive_structured_card_state,
    _map_plan_detail,
)
from api.structured_plan_models import SCHEMA_VERSION, validate_structured_plan
from test_structured_plan_models import _valid_plan


NOW = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


def _row(*, debug: dict | None = None, marker: datetime | str | None = None) -> dict:
    report: dict = {}
    if debug is not None:
        report["structured_plan"] = debug
    if marker is not None:
        report["structured_card_attempt_started_at"] = (
            marker.isoformat() if isinstance(marker, datetime) else marker
        )
    return {
        "id": "plan-state-1",
        "athlete_id": "athlete-state-1",
        "full_name": "State Test",
        "status": "generated",
        "plan_text": "# Text fallback",
        "stage2_validator_report": report,
    }


def _derive(
    row: dict,
    *,
    structured_plan=None,
    schema_version: str | None = None,
):
    return _derive_structured_card_state(
        row,
        structured_plan=structured_plan,
        structured_schema_version=schema_version,
        now=NOW,
    )


@pytest.mark.parametrize("status", ["valid", "repair_attempted_valid"])
def test_clean_saved_card_is_live_and_wins_over_an_old_marker(status: str):
    parsed_plan = validate_structured_plan(_valid_plan())
    marker = NOW - timedelta(hours=1)

    state = _derive(
        _row(
            debug={"status": status, "schema_version": SCHEMA_VERSION},
            marker=marker,
        ),
        structured_plan=parsed_plan,
        schema_version=SCHEMA_VERSION,
    )

    assert state.state == "live"
    assert state.schema_version == SCHEMA_VERSION
    assert state.attempt_started_at == marker.isoformat()


def test_recent_attempt_marker_is_building_even_with_previous_failure_debug():
    marker = NOW - timedelta(minutes=24, seconds=59)

    state = _derive(
        _row(
            debug={
                "status": "invalid_fallback_used",
                "errors": ["previous attempt failed"],
            },
            marker=marker,
        )
    )

    assert state.state == "building"
    assert state.reasons == []
    assert state.attempt_started_at == marker.isoformat()


@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("invalid_fallback_used", "schema validation failed"),
        ("blocked_by_safety_audit", "unsafe conflict detected"),
    ],
)
def test_terminal_failure_debug_is_failed_with_errors_and_warnings(
    status: str,
    error: str,
):
    state = _derive(
        _row(
            debug={
                "status": status,
                "errors": [error],
                "warnings": ["review source plan"],
            }
        )
    )

    assert state.state == "failed"
    assert state.reasons == [error, "review source plan"]


def test_not_attempted_without_errors_retains_recorded_reason():
    state = _derive(
        _row(
            debug={
                "status": "not_attempted",
                "errors": [],
                "warnings": ["converter disabled"],
                "reason": "feature unavailable",
            }
        )
    )

    assert state.state == "not_attempted"
    assert state.reasons == ["converter disabled", "feature unavailable"]


def test_not_attempted_with_errors_is_failed():
    state = _derive(
        _row(
            debug={
                "status": "not_attempted",
                "errors": ["structured generation error"],
            }
        )
    )

    assert state.state == "failed"
    assert state.reasons == ["structured generation error"]


def test_legacy_row_without_debug_marker_or_card_is_none():
    state = _derive(_row())

    assert state.state == "none"
    assert state.reasons == []
    assert state.attempt_started_at is None


def test_marker_at_25_minute_cutoff_is_failed_and_preserves_prior_reasons():
    marker = NOW - timedelta(minutes=25)

    state = _derive(
        _row(
            debug={
                "status": "invalid_fallback_used",
                "errors": ["schema validation failed"],
                "warnings": ["repair exhausted"],
            },
            marker=marker,
        )
    )

    assert state.state == "failed"
    assert state.reasons == [
        "Enhanced card build did not complete.",
        "schema validation failed",
        "repair exhausted",
    ]
    assert state.attempt_started_at == marker.isoformat()


def test_claimed_clean_but_malformed_saved_card_maps_to_failed_plan_detail():
    row = _row(debug={"status": "valid", "schema_version": SCHEMA_VERSION})
    row["structured_plan"] = {"plan_metadata": "not-an-object"}

    detail = _map_plan_detail(row, include_admin=True)

    assert detail.outputs.structured_plan is None
    assert detail.structured_card_state.state == "failed"
    assert detail.structured_card_state.reasons == [
        "Saved enhanced card is unavailable."
    ]


def test_plan_detail_serializes_server_authoritative_state():
    row = _row(debug={"status": "not_attempted", "warnings": ["not queued"]})

    payload = _map_plan_detail(row, include_admin=False).model_dump(mode="json")

    assert payload["structured_card_state"] == {
        "state": "not_attempted",
        "reasons": ["not queued"],
        "schema_version": None,
        "attempt_started_at": None,
    }


@pytest.mark.parametrize(
    ("d_day", "contact_fields", "expected_contact"),
    [
        (
            11,
            {
                "downgraded": True,
                "downgraded_to_role_key": "technical_touch_day",
                "placement_source": "declared_hard_day_downgrade_context",
            },
            "Controlled fight-speed technical rounds",
        ),
        (
            20,
            {"downgraded": False, "placement_source": "declared_hard_day_lock"},
            "Hard sparring",
        ),
        (
            25,
            {
                "hard_sparring_status": "deload_suggested",
                "hard_sparring_class": "managed_hard",
                "hard_sparring_reason_codes": ["consecutive_hard_days"],
            },
            "Hard sparring — reduced dose",
        ),
    ],
)
def test_plan_detail_carries_planner_contact_after_locked_tactical_merge(
    d_day: int,
    contact_fields: dict,
    expected_contact: str,
):
    plan = _valid_plan()
    day = plan["weeks"][0]["days"][0]
    day["countdown_label"] = f"D-{d_day}"
    day["today_card"]["headline"] = "Rest day"
    day["sessions"] = []

    row = _row(debug={"status": "valid", "schema_version": SCHEMA_VERSION})
    row["structured_plan"] = plan
    row["planning_brief"] = {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "session_roles": [
                        {
                            "role_key": "hard_sparring_day",
                            "countdown_offset": d_day,
                            "scheduled_countdown_label": f"D-{d_day}",
                            **contact_fields,
                        },
                        {
                            "role_key": "tactical_watch",
                            "countdown_offset": d_day,
                            "scheduled_countdown_label": f"D-{d_day}",
                            "governance": {
                                "selected_drill_locked": True,
                                "selected_drill_name": "Pocket Exchange Map",
                            },
                            "tactical_watch": {
                                "name": "Pocket Exchange Map",
                                "duration_min": 10,
                                "why": "Keep the exchange planned.",
                                "instructions": ["Read the first response."],
                                "mindset": {},
                                "progress": "Rehearse the chosen ending.",
                            },
                        },
                    ],
                }
            ]
        }
    }

    detail = _map_plan_detail(row, include_admin=False)
    mapped_day = detail.outputs.structured_plan.weeks[0].days[0]

    assert [session.title for session in mapped_day.sessions] == ["Tactical Focus"]
    assert mapped_day.today_card.coach_led_contact == expected_contact
@pytest.mark.parametrize("legacy_role", [False, True])
def test_saved_light_technical_day_is_projected_as_declared_contact_without_mutating_row(legacy_role):
    saved = _valid_plan()
    saved["schema_version"] = "1.0"
    day = saved["weeks"][0]["days"][0]
    day["today_card"]["headline"] = "Technical Shadow Rhythm"
    day["sessions"] = [{
        "session_id": "shadow", "session_type": "skill", "title": "Technical Shadow Rhythm",
        "objective": "Light rhythm", "mindset_anchor": {"intent": "", "focus_cue": "", "reset_cue": ""}, "blocks": [{
            "block_id": "shadow-block", "block_type": "skill", "display_name": "Technical Shadow Rhythm",
        }],
    }]
    brief = {"weekly_role_map": {"weeks": [{
        "phase": "SPP",
        "calendar_days": [{"weekday": "Fri", "d_day": 15, "calendar_date": "2026-05-29"}],
        "session_roles": [] if legacy_role else [{"role_key": "light_combat_day", "scheduled_day_hint": "Friday", "coach_owned": True}],
        "declared_support_work_days": ["Friday"],
    }]}}
    row = _row(debug={"status": "valid", "schema_version": "1.0"})
    row["structured_plan"] = saved
    row["planning_brief"] = brief
    original = deepcopy(saved)

    detail = _map_plan_detail(row, include_admin=False)
    displayed = detail.outputs.structured_plan
    assert displayed is not None
    projected = displayed.model_dump(mode="json")
    shown_day = projected["weeks"][0]["days"][0]
    assert shown_day["today_card"]["headline"] == "Light Combat / Technical"
    assert shown_day["sessions"] == []
    assert row["structured_plan"] == original
