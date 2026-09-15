import pytest

import api.structured_plan_deterministic_fallback as fallback_module


def _brief(d_day: int, contact_fields: dict) -> dict:
    """One locked Tactical Watch sharing a day with deterministic contact."""
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "phase": "SPP",
                    "hard_sparring_plan": [],
                    "session_roles": [
                        {
                            "role_key": "hard_sparring_day",
                            "scheduled_countdown_label": f"D-{d_day}",
                            "countdown_label": f"D-{d_day}",
                            "countdown_offset": d_day,
                            **contact_fields,
                        },
                        {
                            "role_key": "tactical_watch",
                            "scheduled_countdown_label": f"D-{d_day}",
                            "countdown_label": f"D-{d_day}",
                            "governance": {
                                "selected_drill_locked": True,
                                "selected_drill_name": "Pocket Exchange Map",
                            },
                            "tactical_watch": {
                                "name": "Pocket Exchange Map",
                                "duration_min": 10,
                                "why": "Keep pocket exchanges planned rather than chaotic.",
                                "instructions": ["Map the opponent's likely response."],
                                "mindset": {
                                    "intent": "Win the second decision.",
                                    "focus": "Read the response after the first punches.",
                                    "reset": "Smother or leave if the exchange loses shape.",
                                },
                                "progress": "Rehearse the chosen ending.",
                            },
                        },
                    ],
                }
            ]
        }
    }


def _spine(d_day: int) -> dict:
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase_label": "SPP",
                "days": [
                    {
                        "countdown_label": f"D-{d_day}",
                        "day_type": "rest",
                        "today_card": {"headline": ""},
                        "sessions": [],
                    }
                ],
            }
        ]
    }


@pytest.mark.parametrize(
    ("d_day", "contact_fields", "expected_contact", "expected_day_type"),
    [
        (
            11,
            {
                "downgraded": True,
                "downgraded_to_role_key": "technical_touch_day",
                "placement_source": "declared_hard_day_downgrade_context",
            },
            "Controlled fight-speed technical rounds",
            "rest",
        ),
        (
            20,
            {
                "downgraded": False,
                "placement_source": "declared_hard_day_lock",
            },
            "Hard sparring",
            "high",
        ),
        (
            25,
            {
                "hard_sparring_status": "deload_suggested",
                "hard_sparring_class": "managed_hard",
                "hard_sparring_reason_codes": ["consecutive_hard_days"],
            },
            "Hard sparring — reduced dose",
            "rest",
        ),
    ],
)
def test_locked_tactical_focus_survives_contact_reconcile(
    monkeypatch,
    d_day,
    contact_fields,
    expected_contact,
    expected_day_type,
):
    """Locked Tactical Focus and deterministic contact must both survive fallback."""
    brief = _brief(d_day, contact_fields)
    monkeypatch.setattr(
        fallback_module,
        "reconcile_calendar_spine",
        lambda _plan, _brief: _spine(d_day),
    )

    plan = fallback_module.build_deterministic_structured_plan(brief)

    assert plan is not None
    day = plan["weeks"][0]["days"][0]
    assert [session["title"] for session in day["sessions"]] == ["Tactical Focus"]
    assert day["today_card"]["coach_led_contact"] == expected_contact
    assert day["day_type"] == expected_day_type
