"""The faithfulness gate judges each layer against its own authority.

Preparation for adaptive-only Stage 2 output: when Stage 2 stops emitting
deterministic sessions, the server assembles them and the gate must not read
their absence from model prose as an error. Model-authored content is still
checked against model prose exactly as before.
"""

from __future__ import annotations

import datetime

import pytest

from api.structured_plan_faithfulness import check_structured_faithfulness
from support import _build_request


@pytest.fixture(scope="module")
def camp_brief() -> dict:
    generate_plan_sync = pytest.importorskip("fightcamp.main").generate_plan_sync
    fight_date = (datetime.date.today() + datetime.timedelta(days=56)).isoformat()
    request = _build_request(
        {
            "fight_date": fight_date,
            "hard_sparring_days": ["Tuesday", "Thursday"],
            "support_work_days": ["Wednesday"],
            "training_availability": [
                "Monday", "Tuesday", "Wednesday", "Thursday", "Saturday",
            ],
            "weekly_training_frequency": 5,
        }
    ).to_payload()
    request["random_seed"] = 3
    return generate_plan_sync(request)["planning_brief"]


def _server_owned_days(planning_brief: dict) -> list[int]:
    from api.structured_plan_faithfulness import _server_owned_ddays

    return sorted(_server_owned_ddays(planning_brief), reverse=True)


def _day(countdown: int, sessions: list[dict]) -> dict:
    return {"countdown_label": f"D-{countdown}", "date": "", "sessions": sessions}


def _model_session(countdown: int, name: str) -> dict:
    return {
        "session_id": f"model-{countdown}",
        "session_type": "strength_power",
        "title": "Strength",
        "objective": "Build force",
        "blocks": [
            {
                "block_id": f"model-block-{countdown}",
                "block_type": "strength",
                "display_name": name,
                "duration": {"value": 30, "unit": "minutes"},
            }
        ],
    }


def _server_session(countdown: int, name: str) -> dict:
    return {
        "session_id": f"locked-{countdown}-tactical-watch",
        "session_type": "skill",
        "title": "Fight Tactical Watch",
        "objective": "Review the tactical plan.",
        "blocks": [
            {
                "block_id": f"locked-{countdown}-watch",
                "block_type": "mindset",
                "display_name": name,
                "duration": {"value": 10, "unit": "minutes"},
            }
        ],
    }


def test_server_owned_days_are_read_from_the_role_map(camp_brief):
    days = _server_owned_days(camp_brief)
    assert days, "fixture must carry deterministic server-owned roles"


def test_a_server_assembled_day_absent_from_stage2_text_is_not_a_violation(camp_brief):
    """The case that blocks adaptive-only output today."""
    server_day = _server_owned_days(camp_brief)[0]
    source = "### D-55\n\n- Back Squat: 3x5\n"  # Stage 2 never mentions the server day
    plan = {
        "weeks": [
            {
                "week_index": 1,
                "days": [
                    _day(55, [_model_session(55, "Back Squat")]),
                    _day(server_day, []),
                ],
            }
        ]
    }
    violations = check_structured_faithfulness(plan, source, camp_brief)
    assert not [issue for issue in violations if "absent from source text" in issue]


def test_a_day_the_server_does_not_own_still_must_come_from_stage2_text(camp_brief):
    """The gate is not weakened for model-owned content."""
    invented = 999
    assert invented not in _server_owned_days(camp_brief)
    source = "### D-55\n\n- Back Squat: 3x5\n"
    plan = {
        "weeks": [
            {
                "week_index": 1,
                "days": [
                    _day(55, [_model_session(55, "Back Squat")]),
                    _day(invented, [_model_session(invented, "Back Squat")]),
                ],
            }
        ]
    }
    violations = check_structured_faithfulness(plan, source, camp_brief)
    assert any("D-999" in issue and "absent from source text" in issue for issue in violations)


def test_server_assembled_sessions_are_exempt_from_the_introduced_check(camp_brief):
    """A Watch the server wrote is verified against the role, not the prose."""
    server_day = _server_owned_days(camp_brief)[0]
    source = f"### D-{server_day}\n\n- Back Squat: 3x5\n"
    plan = {
        "weeks": [
            {
                "week_index": 1,
                "days": [
                    _day(
                        server_day,
                        [
                            _model_session(server_day, "Back Squat"),
                            _server_session(server_day, "Pressure Route Scan"),
                        ],
                    )
                ],
            }
        ]
    }
    violations = check_structured_faithfulness(plan, source, camp_brief)
    # The exemption governs the faithfulness-to-prose checks. Locked-content
    # completeness is a separate check with its own authority (the role), and it
    # still applies to this deliberately hollow stub -- which is correct.
    assert not [
        issue
        for issue in violations
        if "Pressure Route Scan" in issue and "LOCKED_CONTENT" not in issue
    ]


def test_a_model_authored_exercise_absent_from_the_text_is_still_caught(camp_brief):
    server_day = _server_owned_days(camp_brief)[0]
    source = f"### D-{server_day}\n\n- Back Squat: 3x5\n"
    plan = {
        "weeks": [
            {
                "week_index": 1,
                "days": [
                    _day(
                        server_day,
                        [_model_session(server_day, "Barbell Snatch Complex")],
                    )
                ],
            }
        ]
    }
    violations = check_structured_faithfulness(plan, source, camp_brief)
    assert violations, "an invented model exercise must still be rejected"
