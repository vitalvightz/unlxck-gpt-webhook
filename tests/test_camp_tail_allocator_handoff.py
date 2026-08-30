from __future__ import annotations

from fightcamp import stage2_payload_late_fight as late_fight
from fightcamp.camp_week_fillers import _role_d_day, _splice_late_fight_tail


def _week(calendar_days, roles):
    return {
        "calendar_days": calendar_days,
        "session_roles": roles,
        "intentionally_unused_days": [],
        "phase": "TAPER",
    }


def _role(role_key: str, d_day: int, weekday: str):
    return {
        "role_key": role_key,
        "category": "strength",
        "countdown_offset": d_day,
        "countdown_label": f"D-{d_day}",
        "scheduled_countdown_label": f"D-{d_day}",
        "scheduled_day_hint": weekday,
    }


def test_d30_keeps_d14_normal_and_hands_d13_to_d1_to_existing_late_allocator(monkeypatch):
    weekly_role_map = {
        "weeks": [
            _week(
                [
                    {"weekday": "monday", "d_day": 15},
                    {"weekday": "tuesday", "d_day": 14},
                    {"weekday": "wednesday", "d_day": 13},
                    {"weekday": "thursday", "d_day": 12},
                ],
                [
                    _role("normal_d14", 14, "tuesday"),
                    _role("normal_d13", 13, "wednesday"),
                    _role("normal_d12", 12, "thursday"),
                ],
            ),
            _week(
                [
                    {"weekday": "monday", "d_day": 8},
                    {"weekday": "tuesday", "d_day": 7},
                    {"weekday": "wednesday", "d_day": 6},
                    {"weekday": "thursday", "d_day": 5},
                    {"weekday": "friday", "d_day": 4},
                ],
                [_role("normal_d7", 7, "tuesday")],
            ),
            _week(
                [
                    {"weekday": "monday", "d_day": 3},
                    {"weekday": "tuesday", "d_day": 2},
                    {"weekday": "wednesday", "d_day": 1},
                    {"weekday": "thursday", "d_day": 0},
                ],
                [
                    _role("normal_d1", 1, "wednesday"),
                    {
                        "role_key": "fight_day_protocol",
                        "category": "protocol",
                        "countdown_offset": 0,
                        "countdown_label": "D-0",
                        "scheduled_countdown_label": "D-0",
                        "scheduled_day_hint": "thursday",
                    },
                ],
            ),
        ]
    }
    athlete_model = {
        "days_until_fight": 30,
        "plan_creation_weekday": "monday",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
    }

    shifted_calls = []
    allocation_calls = []

    def fake_shift(days_until_fight, segment_start_day, model):
        shifted_calls.append((days_until_fight, segment_start_day))
        shifted = dict(model)
        shifted["days_until_fight"] = segment_start_day
        return shifted

    def fake_allocation(days_until_fight, model):
        allocation_calls.append(days_until_fight)
        assert model["days_until_fight"] == 13
        return {
            "session_roles": [
                _role("late_d13", 13, "wednesday"),
                _role("late_d7", 7, "tuesday"),
                _role("late_d1", 1, "wednesday"),
            ]
        }

    monkeypatch.setattr(late_fight, "_shifted_segment_athlete_model", fake_shift)
    monkeypatch.setattr(late_fight, "_late_fight_practical_allocation_plan", fake_allocation)

    assert _splice_late_fight_tail(weekly_role_map, athlete_model) is True
    assert shifted_calls == [(30, 13)]
    assert allocation_calls == [13]

    placed = {
        role["role_key"]: _role_d_day(week, role)
        for week in weekly_role_map["weeks"]
        for role in week["session_roles"]
        if isinstance(role, dict)
    }

    # D-14 remains exactly normal-camp owned.
    assert placed["normal_d14"] == 14

    # Normal-planner roles inside the tail are gone.
    assert "normal_d13" not in placed
    assert "normal_d12" not in placed
    assert "normal_d7" not in placed
    assert "normal_d1" not in placed

    # The existing late-fight allocator now owns the future tail.
    assert placed["late_d13"] == 13
    assert placed["late_d7"] == 7
    assert placed["late_d1"] == 1

    # Existing deterministic fight-day protocol remains intact.
    assert placed["fight_day_protocol"] == 0

    assert weekly_role_map["late_fight_tail_handoff"] == {
        "active": True,
        "normal_planner_through_d": 14,
        "late_fight_planner_from_d": 13,
        "source": "existing_late_fight_composite_allocator",
    }


def test_d13_generated_plan_is_not_spliced_again(monkeypatch):
    weekly_role_map = {"weeks": []}
    athlete_model = {"days_until_fight": 13}

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("direct D-13 plan must keep its existing late-fight route")

    monkeypatch.setattr(late_fight, "_late_fight_practical_allocation_plan", should_not_run)
    assert _splice_late_fight_tail(weekly_role_map, athlete_model) is False
    assert "late_fight_tail_handoff" not in weekly_role_map
