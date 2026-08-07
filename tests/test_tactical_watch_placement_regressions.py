from fightcamp.camp_week_fillers import apply_camp_week_fillers


def _athlete(days_until_fight: int) -> dict:
    return {
        "sport": "boxing",
        "days_until_fight": days_until_fight,
        "tactical_styles": ["out-boxer"],
        "hard_sparring_days": [],
        "fatigue": "low",
        "readiness_flags": [],
        "weaknesses": [],
        "key_goals": [],
        "injuries": [],
        "parsed_injuries": [],
        "injury_restrictions": [],
    }


def test_mandatory_watch_uses_declared_day_when_week_has_no_existing_session():
    week = {
        "phase": "GPP",
        "session_roles": [],
        "calendar_days": [
            {"weekday": "monday", "d_day": 21},
            {"weekday": "wednesday", "d_day": 19},
        ],
        "declared_training_days": ["Monday", "Wednesday"],
        "intentionally_unused_days": [
            {"day": "Wednesday", "role": "recovery_only_day"},
        ],
    }

    apply_camp_week_fillers({"weeks": [week]}, _athlete(21))

    watches = [role for role in week["session_roles"] if role.get("role_key") == "tactical_watch"]
    assert len(watches) == 1
    assert watches[0]["scheduled_day_hint"] == "Monday"
    assert watches[0]["mandatory_tactical_watch"] is True
    assert watches[0]["countdown_offset"] == 21


def test_invalid_existing_watch_is_removed_before_valid_replacement():
    week = {
        "phase": "TAPER",
        "session_roles": [
            {
                "role_key": "tactical_watch",
                "category": "support_insert",
                "scheduled_day_hint": "Friday",
            },
            {
                "role_key": "primary_strength_day",
                "category": "strength",
                "scheduled_day_hint": "Monday",
            },
        ],
        "calendar_days": [
            {"weekday": "monday", "d_day": 7},
            {"weekday": "friday", "d_day": 0},
        ],
        "declared_training_days": ["Monday", "Friday"],
        "intentionally_unused_days": [],
    }

    apply_camp_week_fillers({"weeks": [week]}, _athlete(7))

    watches = [role for role in week["session_roles"] if role.get("role_key") == "tactical_watch"]
    assert len(watches) == 1
    assert watches[0]["scheduled_day_hint"] == "Monday"
    assert watches[0]["countdown_offset"] == 7
    assert watches[0]["mandatory_tactical_watch"] is True
