from __future__ import annotations

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import apply_gap_fill_inserts


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "days_until_fight": 21,
        "plan_creation_weekday": "monday",
        "hard_sparring_days": [],
        "fatigue": "low",
        "fatigue_level": "low",
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
    athlete.update(overrides)
    return athlete


def _session(offset: int, role_key: str = "strength_touch_day") -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": role_key,
        "scheduled_day_hint": "monday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def _week(phase: str, d_day: int, *, compressed: bool = False) -> dict:
    return {
        "phase": phase,
        "session_roles": [
            {
                "role_key": "primary_strength_day",
                "category": "strength",
                "scheduled_day_hint": "Monday",
            }
        ],
        "calendar_days": [
            {"weekday": "monday", "d_day": d_day},
            {"weekday": "wednesday", "d_day": d_day - 2},
            {"weekday": "friday", "d_day": d_day - 4},
        ],
        "intentionally_unused_days": [
            {"day": "Wednesday", "role": "recovery_only_day"},
            {"day": "Friday", "role": "off_day"},
        ],
        "declared_training_days": ["Monday", "Wednesday", "Friday"],
        "intentional_compression": {"active": compressed},
    }


def _watches(roles: list[dict]) -> list[dict]:
    return [role for role in roles if role.get("role_key") == "tactical_watch"]


def test_fight_dated_normal_camp_reserves_one_watch_in_every_phase():
    role_map = {
        "weeks": [
            _week("GPP", 42),
            _week("SPP", 28),
            _week("TAPER", 7),
        ]
    }

    apply_camp_week_fillers(role_map, _athlete(days_until_fight=42))

    filler_counts = []
    for week in role_map["weeks"]:
        watches = _watches(week["session_roles"])
        assert len(watches) == 1
        assert watches[0]["mandatory_tactical_watch"] is True
        assert watches[0]["weekly_requirement"] == "fight_tactical_watch"
        assert watches[0]["governance"]["meaningful_stress"] is False
        filler_counts.append(
            sum(1 for role in week["session_roles"] if role.get("camp_week_filler"))
        )

    assert filler_counts == [1, 2, 1]


def test_compressed_week_keeps_watch_but_blocks_optional_fillers():
    week = _week("SPP", 28, compressed=True)

    apply_camp_week_fillers(
        {"weeks": [week]},
        _athlete(days_until_fight=28, fatigue="high", fatigue_level="high"),
    )

    fillers = [role for role in week["session_roles"] if role.get("camp_week_filler")]
    assert len(fillers) == 1
    assert fillers[0]["role_key"] == "tactical_watch"


def test_non_fight_dated_gpp_retains_legacy_no_filler_behaviour():
    week = _week("GPP", 42)

    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=None))

    assert _watches(week["session_roles"]) == []
    assert week["intentionally_unused_days"]


def test_late_fight_sequence_has_one_watch_per_seven_day_segment():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6)],
        _athlete(days_until_fight=21),
    )

    watches = _watches(sequence)
    assert len(watches) == 3
    assert {watch["tactical_watch_segment"] for watch in watches} == {0, 1, 2}
    assert all(watch["mandatory_tactical_watch"] is True for watch in watches)
    assert all(watch["countdown_offset"] > 0 for watch in watches)


def test_existing_watch_satisfies_segment_without_duplicate_watch():
    existing = {
        **_session(1, "tactical_watch"),
        "category": "support_insert",
        "stress_class": "support",
        "cost_class": "low",
        "governance": {"meaningful_stress": False},
    }

    sequence = apply_gap_fill_inserts(
        [existing],
        _athlete(days_until_fight=1, hard_sparring_days=["tuesday"]),
    )

    assert len(_watches(sequence)) == 1


def test_fight_day_never_receives_tactical_watch():
    sequence = apply_gap_fill_inserts(
        [_session(0, "fight_week_freshness_day")],
        _athlete(days_until_fight=0),
    )

    assert _watches(sequence) == []
