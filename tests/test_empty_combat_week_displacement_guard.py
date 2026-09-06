from __future__ import annotations

import fightcamp.empty_combat_week_policy as policy


def test_pressure_move_does_not_push_existing_work_into_d14_to_d8(monkeypatch):
    monkeypatch.setattr(
        policy,
        "_earliest_safe_pressure_slot",
        lambda week_entry, athlete_model: ("monday", 14),
    )
    athlete = {"training_days": ["Monday", "Wednesday", "Friday"]}
    week = {
        "declared_training_days": ["Monday", "Wednesday", "Friday"],
        "calendar_days": [
            {"weekday": "monday", "d_day": 14},
            {"weekday": "wednesday", "d_day": 12},
            {"weekday": "friday", "d_day": 10},
        ],
    }
    roles = [
        {
            "category": "conditioning",
            "role_key": "controlled_repeatability_day",
            "preferred_system": "glycolytic",
            "upgraded_from_empty_combat_week": True,
            "scheduled_day_hint": "friday",
        },
        {
            "category": "strength",
            "role_key": "primary_strength_day",
            "scheduled_day_hint": "monday",
        },
    ]

    moved = policy._move_pressure_to_early_slot(roles, week, athlete)

    pressure = next(role for role in moved if role["category"] == "conditioning")
    strength = next(role for role in moved if role["category"] == "strength")
    assert pressure["scheduled_day_hint"] == "friday"
    assert strength["scheduled_day_hint"] == "monday"
