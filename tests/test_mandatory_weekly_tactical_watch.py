from __future__ import annotations

import pytest

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


def _supports(roles: list[dict]) -> list[dict]:
    return [
        role
        for role in roles
        if role.get("camp_week_filler") or role.get("category") == "support_insert"
    ]


def test_fight_dated_normal_camp_reserves_one_watch_in_every_phase():
    role_map = {"weeks": [_week("GPP", 42), _week("SPP", 28), _week("TAPER", 7)]}
    apply_camp_week_fillers(role_map, _athlete(days_until_fight=42))

    support_counts = []
    for week in role_map["weeks"]:
        watches = _watches(week["session_roles"])
        assert len(watches) == 1
        assert watches[0]["mandatory_tactical_watch"] is True
        assert watches[0]["weekly_requirement"] == "fight_tactical_watch"
        assert watches[0]["governance"]["authority"] == "gap_fill_support_insert"
        assert watches[0]["governance"]["meaningful_stress"] is False
        support_counts.append(len(_supports(week["session_roles"])))

    assert support_counts == [1, 2, 1]


def test_compressed_week_keeps_watch_but_blocks_optional_fillers():
    week = _week("SPP", 28, compressed=True)
    apply_camp_week_fillers(
        {"weeks": [week]},
        _athlete(days_until_fight=28, fatigue="high", fatigue_level="high"),
    )
    supports = _supports(week["session_roles"])
    assert len(supports) == 1
    assert supports[0]["role_key"] == "tactical_watch"


def test_non_fight_dated_gpp_retains_legacy_no_filler_behaviour():
    week = _week("GPP", 42)
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=None))
    assert _watches(week["session_roles"]) == []
    assert week["intentionally_unused_days"]


def test_full_normal_camp_week_uses_least_loaded_calendar_fallback():
    week = {
        "phase": "SPP",
        "session_roles": [
            {"role_key": "strength_a", "category": "strength", "scheduled_day_hint": "Monday"},
            {"role_key": "conditioning_a", "category": "conditioning", "scheduled_day_hint": "Monday"},
            {"role_key": "strength_b", "category": "strength", "scheduled_day_hint": "Wednesday"},
            {"role_key": "technical_b", "category": "technical", "scheduled_day_hint": "Wednesday"},
            {"role_key": "strength_c", "category": "strength", "scheduled_day_hint": "Friday"},
            {"role_key": "recovery_c", "category": "recovery", "scheduled_day_hint": "Friday"},
        ],
        "calendar_days": [
            {"weekday": "monday", "d_day": 28},
            {"weekday": "wednesday", "d_day": 26},
            {"weekday": "friday", "d_day": 24},
        ],
        "intentionally_unused_days": [],
        "declared_training_days": ["Monday", "Wednesday", "Friday"],
    }
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=28))
    watches = _watches(week["session_roles"])
    assert len(watches) == 1
    assert watches[0]["scheduled_day_hint"] in {"Monday", "Wednesday", "Friday"}


def test_phase_cap_replaces_lowest_priority_optional_support():
    week = _week("SPP", 28)
    week["intentionally_unused_days"] = []
    week["session_roles"].extend(
        [
            {
                "role_key": "mobility_rehab",
                "category": "support_insert",
                "scheduled_day_hint": "Wednesday",
                "camp_week_filler": True,
                "support_insert_cost_category": "physical",
            },
            {
                "role_key": "breathing_reset",
                "category": "support_insert",
                "scheduled_day_hint": "Friday",
                "camp_week_filler": True,
                "support_insert_cost_category": "low_cost_recovery",
            },
        ]
    )
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=28))
    assert len(_supports(week["session_roles"])) == 2
    assert len(_watches(week["session_roles"])) == 1
    assert any(
        "mandatory_tactical_watch_reserved_slot" in role.get("reason_codes", [])
        for role in week.get("suppressed_roles", [])
    )


def test_existing_normal_camp_watch_is_promoted_in_place():
    week = _week("SPP", 28)
    week["session_roles"].append(
        {
            "role_key": "tactical_watch",
            "category": "support_insert",
            "scheduled_day_hint": "Wednesday",
            "display_text": "old text",
        }
    )
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=28))
    watches = _watches(week["session_roles"])
    assert len(watches) == 1
    watch = watches[0]
    assert watch["mandatory_tactical_watch"] is True
    assert watch["weekly_requirement"] == "fight_tactical_watch"
    assert watch["governance"]["authority"] == "gap_fill_support_insert"
    assert "confirmed opponent" in watch["display_text"].lower()


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


def test_late_fight_horizon_uses_fight_date_not_last_main_session():
    sequence = apply_gap_fill_inserts(
        [_session(11), _session(4)],
        _athlete(days_until_fight=21),
    )
    assert {watch["tactical_watch_segment"] for watch in _watches(sequence)} == {0, 1, 2}
    assert any(watch["countdown_offset"] >= 15 for watch in _watches(sequence))


def test_existing_late_fight_watch_is_promoted_without_duplicate():
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
    watches = _watches(sequence)
    assert len(watches) == 1
    assert watches[0]["mandatory_tactical_watch"] is True
    assert watches[0]["weekly_requirement"] == "fight_tactical_watch"
    assert watches[0]["governance"]["authority"] == "gap_fill_support_insert"
    assert "familiar opponent footage" in watches[0]["display_text"].lower()


def test_fight_day_never_receives_tactical_watch():
    sequence = apply_gap_fill_inserts(
        [_session(0, "fight_week_freshness_day")],
        _athlete(days_until_fight=0),
    )
    assert _watches(sequence) == []


def test_late_fight_watch_shares_existing_day_when_no_spaced_day_exists():
    sequence = apply_gap_fill_inserts(
        [_session(16), _session(14), _session(9), _session(4)],
        _athlete(days_until_fight=16),
    )
    outer_watch = next(
        role
        for role in sequence
        if role.get("mandatory_tactical_watch")
        and role.get("tactical_watch_segment") == 2
    )
    assert outer_watch["countdown_offset"] == 16
    assert not any(
        role.get("mandatory_tactical_watch") and role.get("countdown_offset") == 15
        for role in sequence
    )



def test_duplicate_existing_late_fight_watches_are_suppressed_to_one():
    first = {
        **_session(6, "tactical_watch"),
        "category": "support_insert",
        "stress_class": "support",
        "governance": {"meaningful_stress": False},
    }
    duplicate = {
        **_session(4, "tactical_watch"),
        "category": "support_insert",
        "stress_class": "support",
        "governance": {"meaningful_stress": False},
    }

    sequence = apply_gap_fill_inserts(
        [first, duplicate],
        _athlete(days_until_fight=7),
    )

    watches = _watches(sequence)
    assert len(watches) == 1
    assert watches[0]["mandatory_tactical_watch"] is True
    assert watches[0]["weekly_requirement"] == "fight_tactical_watch"
    assert watches[0]["governance"]["authority"] == "gap_fill_support_insert"


def test_malformed_fight_dated_normal_week_raises_generation_error():
    week = _week("SPP", 0)
    week["calendar_days"] = [
        {"weekday": "monday", "d_day": 0},
        {"weekday": "wednesday", "d_day": -2},
    ]

    with pytest.raises(RuntimeError, match="no positive countdown calendar day"):
        apply_camp_week_fillers(
            {"weeks": [week]},
            _athlete(days_until_fight=28),
        )
