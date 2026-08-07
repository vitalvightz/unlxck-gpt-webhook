from __future__ import annotations

import pytest

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import apply_gap_fill_inserts
from fightcamp.stage2_finalizer_packet import _compact_role
from fightcamp.tactical_watch_library import (
    PHASES,
    STYLE_FAMILIES,
    TacticalWatchBankExhausted,
    all_watches,
    canonical_watch_signature,
    extract_tactical_style,
    normalize_tactical_style,
    ordered_phase_bank,
    select_tactical_watch,
)


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "days_until_fight": 49,
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


def _week(phase: str, d_day: int) -> dict:
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
    }


def _late_role(offset: int, role_key: str = "strength_touch_day") -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": role_key,
        "scheduled_day_hint": "monday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("out-boxer", "distance_striker"),
        ("distance striker", "distance_striker"),
        ("pressure fighter", "brawler"),
        ("swarmer", "brawler"),
        ("counter puncher", "counter_striker"),
        ("reactive counter fighter", "counter_striker"),
        ("wrestler", "generic"),
        (None, "generic"),
    ],
)
def test_style_normalization(raw, expected):
    assert normalize_tactical_style(raw) == expected


def test_boxing_does_not_invent_tactical_style():
    assert extract_tactical_style({"sport": "boxing"}) == "generic"


@pytest.mark.parametrize(
    "style, expected",
    [
        ("distance_striker", ("Range Map", "Intercept the Entry", "First-Round Range Script")),
        ("brawler", ("Pressure Route Scan", "Pocket Exchange Map", "First-Round Pressure Script")),
        ("counter_striker", ("Trigger Library", "First Beat or Second Beat", "First-Round Patience Script")),
        ("generic", ("Opponent Pattern Scan", "Trigger-Response Builder", "Familiar Round-One Rehearsal")),
    ],
)
def test_first_watch_is_style_and_phase_specific(style, expected):
    assert tuple(select_tactical_watch(style, phase).name for phase in PHASES) == expected


def test_bank_never_silently_repeats_after_exhaustion():
    for style in STYLE_FAMILIES:
        for phase in PHASES:
            used: set[str] = set()
            bank = ordered_phase_bank(style, phase)
            for _ in bank:
                watch = select_tactical_watch(style, phase, used)
                assert watch.key not in used
                used.add(watch.key)
            with pytest.raises(TacticalWatchBankExhausted):
                select_tactical_watch(style, phase, used)


def test_generic_bank_covers_supported_phase_capacity():
    assert len(ordered_phase_bank("generic", "GPP")) >= 7
    assert len(ordered_phase_bank("generic", "SPP")) >= 9
    assert len(ordered_phase_bank("generic", "TAPER")) >= 2


def test_every_bank_entry_has_unique_athlete_visible_content():
    watches = all_watches()
    assert len({watch.key for watch in watches}) == len(watches)
    assert len({canonical_watch_signature(watch) for watch in watches}) == len(watches)
    assert len({watch.instructions for watch in watches}) == len(watches)


def test_normal_fight_camp_gets_one_named_watch_every_week():
    role_map = {
        "weeks": [
            _week("GPP", 49),
            _week("GPP", 42),
            _week("GPP", 35),
            _week("SPP", 28),
            _week("SPP", 21),
            _week("SPP", 14),
            _week("TAPER", 7),
        ]
    }
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["out-boxer"]))

    watches = [
        next(
            role
            for role in week["session_roles"]
            if role.get("role_key") == "tactical_watch"
        )
        for week in role_map["weeks"]
    ]
    assert [watch["tactical_watch_name"] for watch in watches] == [
        "Range Map",
        "Lead-Hand Battle",
        "Exit Discipline",
        "Intercept the Entry",
        "Exit Lane Audit",
        "Rope and Corner Escape",
        "First-Round Range Script",
    ]
    assert len({watch["tactical_watch_key"] for watch in watches}) == len(watches)
    assert len({watch["display_text"] for watch in watches}) == len(watches)
    assert all(watch["mandatory_tactical_watch"] is True for watch in watches)
    assert all(watch["weekly_requirement"] == "fight_tactical_watch" for watch in watches)


def test_compressed_fight_week_keeps_zero_load_tactical_watch():
    week = _week("SPP", 21)
    week["intentional_compression"] = {"active": True, "reason": "high fatigue"}
    role_map = {"weeks": [week]}
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["counter puncher"], fatigue="high"))
    watches = [role for role in week["session_roles"] if role.get("role_key") == "tactical_watch"]
    assert len(watches) == 1
    assert watches[0]["tactical_watch_name"] == "First Beat or Second Beat"
    assert watches[0]["governance"]["meaningful_stress"] is False


def test_d0_is_never_used_for_mandatory_normal_camp_watch():
    week = {
        "phase": "TAPER",
        "session_roles": [
            {
                "role_key": "fight_day",
                "category": "fight",
                "scheduled_day_hint": "Friday",
            }
        ],
        "calendar_days": [{"weekday": "friday", "d_day": 0}],
        "intentionally_unused_days": [],
        "declared_training_days": ["Friday"],
    }
    role_map = {"weeks": [week]}
    apply_camp_week_fillers(role_map, _athlete(days_until_fight=1))
    assert not any(role.get("role_key") == "tactical_watch" for role in week["session_roles"])


def test_selected_drill_identity_survives_finalizer_compaction():
    role_map = {"weeks": [_week("SPP", 28)]}
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["out-boxer"]))
    role = next(
        role
        for role in role_map["weeks"][0]["session_roles"]
        if role.get("role_key") == "tactical_watch"
    )
    compact = _compact_role(role)
    assert compact["athlete_facing_label"] == "Fight Tactical Watch"
    assert compact["preferred_exercise_names"] == ["Intercept the Entry"]
    assert "Intercept the Entry" in compact["display_text"]
    assert compact["mandatory_tactical_watch"] is True
    assert compact["governance"]["selected_drill_locked"] is True
    assert compact["governance"]["selected_drill_name"] == "Intercept the Entry"
    assert compact["governance"]["do_not_reselect_or_generalize"] is True


def test_late_fight_path_gets_one_named_watch_per_visible_seven_day_segment():
    sequence = apply_gap_fill_inserts(
        [
            _late_role(21),
            _late_role(16),
            _late_role(11),
            _late_role(6),
            _late_role(1),
        ],
        _athlete(days_until_fight=21, tactical_styles=["pressure fighter"]),
    )
    watches = [
        role
        for role in sequence
        if role.get("role_key") == "tactical_watch" and role.get("mandatory_tactical_watch")
    ]
    assert {role["tactical_watch_segment"] for role in watches} == {0, 1, 2}
    assert len(watches) == 3
    assert len({role["tactical_watch_key"] for role in watches}) == 3
    assert all(role["tactical_watch_style"] == "brawler" for role in watches)
    taper_watch = next(role for role in watches if role["tactical_watch_segment"] == 0)
    assert taper_watch["tactical_watch_phase"] == "TAPER"
    assert "First-Round Pressure Script" in taper_watch["display_text"]
    assert all(int(role["countdown_offset"]) > 0 for role in watches)


def test_late_watch_is_exact_tactical_watch_not_generic_tactical_support():
    sequence = apply_gap_fill_inserts(
        [_late_role(14), _late_role(9), _late_role(4)],
        _athlete(days_until_fight=14, tactical_styles=["counter striker"]),
    )
    watches = [role for role in sequence if role.get("mandatory_tactical_watch")]
    assert len(watches) == 2
    assert all(role["role_key"] == "tactical_watch" for role in watches)
    assert all(role.get("preferred_exercise_names") for role in watches)
