from fightcamp.camp_phases import calculate_phase_weeks
from fightcamp.gap_fill_inserts import _watch_phase_for_offset, apply_gap_fill_inserts


def _athlete(*, days_until_fight: int, phase_weeks: dict, style: str = "pressure fighter") -> dict:
    return {
        "sport": "boxing",
        "days_until_fight": days_until_fight,
        "camp_length_weeks": max(1, round(days_until_fight / 7)),
        "phase_weeks": phase_weeks,
        "tactical_styles": [style],
        "plan_creation_weekday": "friday",
        "hard_sparring_days": [],
        "fatigue": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": [],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
    }


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


def test_watch_phase_uses_authoritative_phase_days_not_a_d7_cutoff():
    taper_reaches_d8 = {
        "GPP": 0,
        "SPP": 1,
        "TAPER": 1,
        "days": {"GPP": 0, "SPP": 5, "TAPER": 9},
    }
    spp_reaches_d6 = {
        "GPP": 0,
        "SPP": 1,
        "TAPER": 1,
        "days": {"GPP": 0, "SPP": 11, "TAPER": 3},
    }

    assert _watch_phase_for_offset(_athlete(days_until_fight=14, phase_weeks=taper_reaches_d8), 8) == "TAPER"
    assert _watch_phase_for_offset(_athlete(days_until_fight=14, phase_weeks=spp_reaches_d6), 6) == "SPP"


def test_pressure_fighter_watch_phase_matches_real_phase_engine():
    phase_weeks = calculate_phase_weeks(
        2,
        "boxing",
        ["pressure fighter"],
        fatigue="low",
        days_until_fight=14,
    )
    athlete = _athlete(days_until_fight=14, phase_weeks=phase_weeks)

    assert _watch_phase_for_offset(athlete, 8) == "SPP"
    assert _watch_phase_for_offset(athlete, 7) == "TAPER"


def test_final_visible_fight_week_gets_mandatory_watch_after_gap_fill():
    phase_weeks = calculate_phase_weeks(
        2,
        "boxing",
        ["pressure fighter"],
        fatigue="low",
        days_until_fight=14,
    )
    athlete = _athlete(days_until_fight=14, phase_weeks=phase_weeks)

    # The incoming sequence represents only D-14..D-8. Ordinary gap filling
    # creates visible work inside D-7..D-1; the mandatory pass must run after
    # that so the newly represented final window cannot miss its watch.
    sequence = apply_gap_fill_inserts([_role(14), _role(8)], athlete)

    final_week_roles = [
        role
        for role in sequence
        if isinstance(role.get("countdown_offset"), int)
        and 1 <= int(role["countdown_offset"]) <= 7
    ]
    assert final_week_roles

    watches = [
        role
        for role in final_week_roles
        if role.get("role_key") == "tactical_watch"
        and role.get("mandatory_tactical_watch") is True
    ]
    assert len(watches) == 1
    watch = watches[0]
    assert watch["tactical_watch_phase"] == "TAPER"
    assert int(watch["countdown_offset"]) > 0

    # Mandatory placement shares a day already present in the final sequence;
    # it must not invent a standalone training day just to satisfy the rule.
    watch_offset = int(watch["countdown_offset"])
    assert any(
        role is not watch and int(role.get("countdown_offset") or 0) == watch_offset
        for role in sequence
    )

    keys = [
        role["tactical_watch_key"]
        for role in sequence
        if role.get("role_key") == "tactical_watch" and role.get("tactical_watch_key")
    ]
    assert len(keys) == len(set(keys))
    assert all(int(role.get("countdown_offset") or 0) > 0 for role in sequence if role.get("role_key") == "tactical_watch")
