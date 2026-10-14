from fightcamp.camp_phases import calculate_phase_weeks
from fightcamp.gap_fill_inserts import (
    MAX_INSERTS_TOTAL_D21_TO_D0,
    apply_gap_fill_inserts,
    budgeted_insert_count,
)


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


def test_mandatory_weekly_watches_do_not_spend_the_insert_budget():
    """Zero-load inserts are outside the allowance, so they cannot crowd it out.

    The Tactical Watch and cue card carry no physical load and coexist with real
    sessions. Counting them against the camp's support-insert allowance let a
    week of tactical reading consume the room the athlete's physical goals need,
    so only load-bearing inserts are charged to it.
    """
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

    assert budgeted_insert_count(generated) <= MAX_INSERTS_TOTAL_D21_TO_D0
    watches = sorted(int(role["countdown_offset"]) for role in sequence
                     if role.get("role_key") == "tactical_watch")
    assert all(day > 6 for day in watches)
    assert all(b - a >= 14 for a, b in zip(watches, watches[1:]))
    assert budgeted_insert_count([r for r in generated if r.get("role_key") == "tactical_watch"]) == 0
    # Reducing the reading cadence must not remove the existing physical work.
    assert {21, 15, 8, 1} <= {r["countdown_offset"] for r in sequence if r["role_key"] == "strength_touch_day"}


def test_zero_cost_inserts_are_not_charged_to_the_allowance():
    from fightcamp.gap_fill_inserts import consumes_insert_budget

    for zero_cost in ("tactical_watch", "tactical_cue_card", "self_review", "neural_visualization"):
        assert consumes_insert_budget(zero_cost) is False
    for load_bearing in ("breathing_reset", "aerobic_shadow_flow", "mobility_rehab", "walk_flush"):
        assert consumes_insert_budget(load_bearing) is True


def test_budgeted_count_ignores_zero_cost_inserts():
    inserts = [
        {"role_key": "tactical_watch"},
        {"role_key": "tactical_cue_card"},
        {"role_key": "breathing_reset"},
        {"role_key": "aerobic_shadow_flow"},
    ]
    assert budgeted_insert_count(inserts) == 2
    assert budgeted_insert_count([]) == 0
