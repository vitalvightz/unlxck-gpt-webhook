from __future__ import annotations

from fightcamp import camp_week_fillers as fillers
from fightcamp import stage2_payload_late_fight as late_fight


def _role(role_key: str, d_day: int, weekday: str) -> dict:
    return {
        "role_key": role_key,
        "category": "strength",
        "countdown_offset": d_day,
        "countdown_label": f"D-{d_day}",
        "scheduled_countdown_label": f"D-{d_day}",
        "scheduled_day_hint": weekday,
    }


def test_mixed_d14_d13_week_keeps_normal_d14_filler_path(monkeypatch):
    weekly_role_map = {
        "weeks": [
            {
                "phase": "SPP",
                "calendar_days": [
                    {"weekday": "monday", "d_day": 15},
                    {"weekday": "tuesday", "d_day": 14},
                    {"weekday": "wednesday", "d_day": 13},
                    {"weekday": "thursday", "d_day": 12},
                ],
                "declared_training_days": ["tuesday", "wednesday", "thursday"],
                "session_roles": [
                    _role("normal_d14", 14, "tuesday"),
                    _role("normal_d13", 13, "wednesday"),
                    _role("normal_d12", 12, "thursday"),
                ],
                "intentionally_unused_days": [],
            }
        ]
    }
    athlete_model = {
        "days_until_fight": 30,
        "plan_creation_weekday": "monday",
        "training_days": ["tuesday", "wednesday", "thursday"],
    }

    monkeypatch.setattr(
        late_fight,
        "_shifted_segment_athlete_model",
        lambda _days, _start, model: {**model, "days_until_fight": 13},
    )
    monkeypatch.setattr(
        late_fight,
        "_late_fight_practical_allocation_plan",
        lambda _days, _model: {
            "session_roles": [
                _role("late_d13", 13, "wednesday"),
                _role("late_d12", 12, "thursday"),
            ]
        },
    )

    calls: list[tuple[str, tuple[int, ...]]] = []

    monkeypatch.setattr(fillers, "_ensure_tactical_watch", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        fillers,
        "_ensure_coordination_support",
        lambda week, *_args, **_kwargs: calls.append(
            ("coordination", tuple(week.get("late_fight_tail_days") or ()))
        ) or False,
    )
    monkeypatch.setattr(
        fillers,
        "_fill_week",
        lambda week, *_args, **_kwargs: calls.append(
            ("fill", tuple(week.get("late_fight_tail_days") or ()))
        ),
    )

    fillers.apply_camp_week_fillers(weekly_role_map, athlete_model)

    week = weekly_role_map["weeks"][0]
    role_keys = {role["role_key"] for role in week["session_roles"]}

    assert "normal_d14" in role_keys
    assert "normal_d13" not in role_keys
    assert "normal_d12" not in role_keys
    assert "late_d13" in role_keys
    assert "late_d12" in role_keys

    # Tail ownership is per D-day, not per whole week.
    assert week["late_fight_tail_days"] == [12, 13]
    assert "late_fight_tail_owned" not in week

    # Mixed week still runs the normal D-14 filler/coordination path.
    assert ("coordination", (12, 13)) in calls
    assert ("fill", (12, 13)) in calls
