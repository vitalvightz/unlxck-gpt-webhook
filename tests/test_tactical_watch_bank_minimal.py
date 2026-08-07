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
    build_watch_display_text,
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


def _session(offset: int) -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": "strength_touch_day",
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


def test_sport_does_not_invent_tactical_style():
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
    actual = tuple(select_tactical_watch(style, phase).name for phase in PHASES)
    assert actual == expected


def test_selection_advances_without_repeating():
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


def test_generic_bank_has_capacity_for_supported_phase_lengths():
    assert len(ordered_phase_bank("generic", "GPP")) >= 7
    assert len(ordered_phase_bank("generic", "SPP")) >= 9
    assert len(ordered_phase_bank("generic", "TAPER")) >= 2


def test_every_watch_has_unique_visible_content():
    watches = all_watches()
    keys = [watch.key for watch in watches]
    signatures = [canonical_watch_signature(watch) for watch in watches]
    instruction_sets = [watch.instructions for watch in watches]
    assert len(keys) == len(set(keys))
    assert len(signatures) == len(set(signatures))
    assert len(instruction_sets) == len(set(instruction_sets))


def test_render_is_normal_session_plus_named_drill():
    watch = select_tactical_watch("distance_striker", "SPP")
    text = build_watch_display_text(watch)
    assert text.startswith("Fight Tactical Watch\n")
    assert "Why:" in text
    assert "Mindset:" in text
    assert "Intercept the Entry" in text
    assert "Duration: 10 minutes" in text
    assert "Prescription:" in text
    assert "Progress:" in text
    assert "write exactly these 4 lines" not in text.lower()


def test_full_distance_striker_camp_uses_distinct_named_drills():
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
        role
        for week in role_map["weeks"]
        for role in week["session_roles"]
        if role.get("role_key") == "tactical_watch"
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
    assert all(watch.get("mandatory_tactical_watch") is True for watch in watches)


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
    assert compact["governance"]["selected_drill_locked"] is True
    assert compact["governance"]["selected_drill_name"] == "Intercept the Entry"
    assert compact["governance"]["do_not_reselect_or_generalize"] is True


def test_late_fight_path_uses_distinct_style_aware_watches():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6)],
        _athlete(days_until_fight=21, tactical_styles=["pressure fighter"]),
    )
    watches = [
        role
        for role in sequence
        if role.get("role_key") == "tactical_watch" and role.get("mandatory_tactical_watch")
    ]
    assert len(watches) == 3
    assert len({watch["tactical_watch_key"] for watch in watches}) == 3
    assert all(watch["tactical_watch_style"] == "brawler" for watch in watches)
    fight_week = next(watch for watch in watches if watch["countdown_offset"] <= 7)
    assert fight_week["tactical_watch_phase"] == "TAPER"
