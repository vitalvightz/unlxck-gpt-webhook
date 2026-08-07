from fightcamp.camp_phases import calculate_phase_weeks
from fightcamp.gap_fill_inserts import MAX_INSERTS_TOTAL_D21_TO_D0, apply_gap_fill_inserts


def _role(offset: int) -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": "strength_touch_day",
        "scheduled_day_hint": "friday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def test_mandatory_weekly_watches_stay_inside_total_insert_budget():
    phase_weeks = calculate_phase_weeks(
        3,
        "boxing",
        ["pressure fighter"],
        fatigue="low",
        days_until_fight=21,
    )
    athlete = {
        "sport": "boxing",
        "days_until_fight": 21,
        "camp_length_weeks": 3,
        "phase_weeks": phase_weeks,
        "tactical_styles": ["pressure fighter"],
        "plan_creation_weekday": "friday",
        "hard_sparring_days": [],
        "fatigue": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": ["conditioning"],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
    }

    sequence = apply_gap_fill_inserts(
        [_role(21), _role(15), _role(8), _role(1)],
        athlete,
    )
    generated = [role for role in sequence if role.get("category") == "support_insert"]

    assert len(generated) <= MAX_INSERTS_TOTAL_D21_TO_D0
    for low, high in ((1, 7), (8, 14), (15, 21)):
        segment = [
            role
            for role in sequence
            if isinstance(role.get("countdown_offset"), int)
            and low <= int(role["countdown_offset"]) <= high
        ]
        watches = [
            role
            for role in segment
            if role.get("role_key") == "tactical_watch"
            and role.get("mandatory_tactical_watch") is True
        ]
        assert len(watches) == 1
