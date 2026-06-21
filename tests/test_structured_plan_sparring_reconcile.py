"""Tests for the deterministic coach-led / sparring card reconciliation.

The structured card derives a day's coach-led status from the LLM headline alone,
so a dropped or mislabelled sparring day silently renders as "Rest day.". These
tests prove the role-map schedule is used to stamp/insert those cards so a
declared sparring day always ships as a coach-led card.
"""
from __future__ import annotations

import re

from api.structured_plan_sparring_reconcile import reconcile_coach_led_sparring_days

# Mirror the web classifier (web/lib/structured-plan.ts) so the assertions prove a
# stamped/inserted headline would actually classify as coach-led there.
_TECHNICAL_RE = re.compile(
    r"\b(technical|skill|drill|pad\s?work|pads|mitts?|footwork|shadow)", re.I
)
_SPARRING_RE = re.compile(r"\bspar(?:r(?:ing|ed)|s)?\b", re.I)
_COACH_LED_RE = re.compile(r"\bcoach", re.I)


def _classifies_coach_led(headline: str) -> bool:
    return bool(
        _TECHNICAL_RE.search(headline)
        or _SPARRING_RE.search(headline)
        or _COACH_LED_RE.search(headline)
    )


def _planning_brief(hard_plan: list[dict], *, span_days: int = 7, end_d: int = 28) -> dict:
    """A single-week role map with a countdown spine (d_day, no calendar_date).

    Mirrors production: ``build_calendar_days`` ships weekday + d_day per day, so
    the deterministic schedule matches structured days by D-day.
    """
    calendar_days = []
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for offset in range(span_days):
        d_day = end_d + (span_days - 1 - offset)
        calendar_days.append({"weekday": weekdays[offset % 7], "d_day": d_day})
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "calendar_days": calendar_days,
                    "hard_sparring_plan": hard_plan,
                }
            ]
        }
    }


def _day(countdown: str, *, headline: str = "", sessions: list | None = None) -> dict:
    return {
        "date": "",
        "countdown_label": countdown,
        "day_type": "moderate",
        "today_card": {"headline": headline, "readiness_status": "train_as_planned"},
        "sessions": sessions if sessions is not None else [],
    }


def _structured_plan(days: list[dict]) -> dict:
    return {
        "weeks": [
            {
                "week_id": "wk-1",
                "week_index": 1,
                "phase_label": "SPP",
                "start_date": "",
                "end_date": "",
                "days": days,
            }
        ]
    }


def _hard_thursday() -> list[dict]:
    # Thursday in the synthetic week is the 4th day -> d_day 31 (end_d 28, span 7).
    return [
        {
            "day": "Thursday",
            "hard_day_class": "primary_hard",
            "effective_load": "hard",
            "status": "hard_as_planned",
        }
    ]


def test_stamps_coach_led_headline_on_mislabelled_rest_day():
    # The converter emitted Thursday (D-31) as a sessionless day headlined like a
    # rest day; reconciliation must restamp it so it classifies as coach-led.
    plan = _structured_plan([_day("D-31", headline="Recovery")])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    headline = plan["weeks"][0]["days"][0]["today_card"]["headline"]
    assert headline == "Coach-led sparring"
    assert _classifies_coach_led(headline)
    assert notes and "stamped" in notes[0]


def test_stamps_when_headline_is_blank():
    plan = _structured_plan([_day("D-31", headline="")])
    reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Coach-led sparring"


def test_inserts_dropped_sparring_day_into_covering_week():
    # The converter dropped Thursday entirely; the week still carries D-33 and
    # D-30, so D-31 must be inserted between them in chronological order.
    plan = _structured_plan([_day("D-33", headline="Strength"), _day("D-30", headline="Aerobic")])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    days = plan["weeks"][0]["days"]
    assert [d["countdown_label"] for d in days] == ["D-33", "D-31", "D-30"]
    inserted = days[1]
    assert inserted["today_card"]["headline"] == "Coach-led sparring"
    assert inserted["sessions"] == []
    assert inserted["phase_label"] == "SPP"
    assert any("inserted" in note for note in notes)


def test_never_overwrites_a_day_with_real_app_sessions():
    # A declared sparring day the converter gave actual S&C work already renders
    # as a session card — leave its headline and sessions untouched.
    real_session = [{"title": "Lower strength", "blocks": []}]
    plan = _structured_plan([_day("D-31", headline="Lower strength", sessions=real_session)])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))

    day = plan["weeks"][0]["days"][0]
    assert day["today_card"]["headline"] == "Lower strength"
    assert day["sessions"] == real_session
    assert notes == []


def test_leaves_already_coach_led_headline_alone():
    plan = _structured_plan([_day("D-31", headline="Coach-led boxing session")])
    notes = reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == "Coach-led boxing session"
    assert notes == []


def test_technical_and_reduced_loads_get_classifiable_headlines():
    hard_plan = [
        {"day": "Thursday", "effective_load": "technical", "status": "convert_to_technical_suggested",
         "hard_day_class": "technical"},
        {"day": "Friday", "effective_load": "reduced", "status": "deload_suggested",
         "hard_day_class": "managed_hard"},
    ]
    # Thu -> D-31, Fri -> D-30.
    plan = _structured_plan([_day("D-31", headline="Rest"), _day("D-30", headline="Rest")])
    reconcile_coach_led_sparring_days(plan, _planning_brief(hard_plan))

    technical = plan["weeks"][0]["days"][0]["today_card"]["headline"]
    reduced = plan["weeks"][0]["days"][1]["today_card"]["headline"]
    assert technical == "Coach-led boxing — technical only"
    assert reduced == "Coach-led sparring — reduced dose"
    assert _classifies_coach_led(technical)
    assert _classifies_coach_led(reduced)


def test_noop_when_no_contact_days_declared():
    plan = _structured_plan([_day("D-31", headline="Recovery")])
    brief = _planning_brief([])  # no hard sparring plan
    before = plan["weeks"][0]["days"][0]["today_card"]["headline"]
    notes = reconcile_coach_led_sparring_days(plan, brief)
    assert notes == []
    assert plan["weeks"][0]["days"][0]["today_card"]["headline"] == before


def test_noop_on_malformed_inputs():
    assert reconcile_coach_led_sparring_days(None, {}) == []
    assert reconcile_coach_led_sparring_days({}, None) == []
    assert reconcile_coach_led_sparring_days({"weeks": []}, _planning_brief(_hard_thursday())) == []


def test_does_not_double_insert_when_day_present_with_sessions():
    # Present (with sessions) means "do not insert" even though we won't stamp it.
    real_session = [{"title": "Lower strength", "blocks": []}]
    plan = _structured_plan([_day("D-31", headline="Lower strength", sessions=real_session)])
    reconcile_coach_led_sparring_days(plan, _planning_brief(_hard_thursday()))
    assert len(plan["weeks"][0]["days"]) == 1
