"""Tactical Watch selection wired through fight-camp role generation.

Proves the scheduler stamps a style/phase-aware watch (name, metadata and the
rendering-ready projection) onto every mandatory Tactical Watch, that repeated
watches within a camp are distinct, and that PR #2221's mandatory placement and
metadata survive promotion.
"""

from __future__ import annotations

import pytest

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import apply_gap_fill_inserts


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


def _watches(roles):
    return [r for r in roles if r.get("role_key") == "tactical_watch"]


def _full_camp_watches(style_value):
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
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=[style_value]))
    watches = []
    for week in role_map["weeks"]:
        for watch in _watches(week["session_roles"]):
            watches.append((week["phase"], watch))
    return watches


# --- distance striker (the spec's worked example) --------------------------


def test_distance_striker_camp_matches_spec_example():
    watches = _full_camp_watches("out-boxer")
    names = [(phase, w["tactical_watch_name"]) for phase, w in watches]
    assert names == [
        ("GPP", "Range Map"),
        ("GPP", "Lead-Hand Battle"),
        ("GPP", "Exit Discipline"),
        ("SPP", "Intercept the Entry"),
        ("SPP", "Exit Lane Audit"),
        ("SPP", "Rope and Corner Escape"),
        ("TAPER", "First-Round Range Script"),
    ]


def test_distance_striker_gpp_spp_taper_cards_are_all_different():
    # Take the first card of each phase; their display texts (which the normal
    # conversion turns into cards) must be genuinely different, not a shared
    # template with a swapped title.
    picked = {}
    for phase, watch in _full_camp_watches("out-boxer"):
        picked.setdefault(phase, watch)
    display_texts = [picked[p]["display_text"] for p in ("GPP", "SPP", "TAPER")]
    names = [picked[p]["tactical_watch_name"] for p in ("GPP", "SPP", "TAPER")]
    assert len(set(display_texts)) == 3, "phase cards share content"
    assert len(set(names)) == 3
    # Each display text carries its own WHY, mindset and instructions.
    for phase in ("GPP", "SPP", "TAPER"):
        text = picked[phase]["display_text"]
        assert "Why:" in text and "Intent:" in text
        assert "Instructions:" in text and "Progress:" in text


@pytest.mark.parametrize(
    "style_value, expected",
    [
        ("out-boxer", ("Range Map", "Intercept the Entry", "First-Round Range Script")),
        ("pressure fighter", ("Pressure Route Scan", "Pocket Exchange Map", "First-Round Pressure Script")),
        ("counter puncher", ("Trigger Library", "First Beat or Second Beat", "First-Round Patience Script")),
        ("wrestler", ("Opponent Pattern Scan", "Trigger-Response Builder", "Corner Instruction Translation")),
    ],
)
def test_first_watch_per_phase_is_style_appropriate(style_value, expected):
    first_by_phase = {}
    for phase, watch in _full_camp_watches(style_value):
        first_by_phase.setdefault(phase, watch["tactical_watch_name"])
    assert (first_by_phase["GPP"], first_by_phase["SPP"], first_by_phase["TAPER"]) == expected


# --- metadata + display-text content ---------------------------------------


def test_every_mandatory_watch_carries_metadata_and_content():
    for phase, watch in _full_camp_watches("out-boxer"):
        assert watch["mandatory_tactical_watch"] is True
        assert watch["tactical_watch_key"]
        assert watch["tactical_watch_name"]
        assert watch["tactical_watch_style"] == "distance_striker"
        assert watch["tactical_watch_phase"] == phase
        # The selected watch's content lives in the ordinary filler display_text
        # that the normal conversion renders — no special pipeline.
        text = watch["display_text"]
        assert "Fight Tactical Watch" in text
        assert watch["tactical_watch_name"] in text
        assert "Why:" in text and "Instructions:" in text and "Progress:" in text
        # The retired four-line output must not appear.
        assert "write exactly these 4 lines" not in text.lower()


def test_camp_never_repeats_a_watch_key():
    keys = [w["tactical_watch_key"] for _, w in _full_camp_watches("out-boxer")]
    assert len(keys) == len(set(keys))


def test_missing_style_uses_generic_bank():
    watches = _full_camp_watches("")  # no declared style
    for _, watch in watches:
        assert watch["tactical_watch_style"] == "generic"


# --- late-fight path -------------------------------------------------------


def test_late_fight_watches_are_distinct_and_style_aware():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6)],
        _athlete(days_until_fight=21, tactical_styles=["pressure fighter"]),
    )
    watches = [w for w in _watches(sequence) if w.get("mandatory_tactical_watch")]
    assert len(watches) == 3
    names = {w["tactical_watch_name"] for w in watches}
    assert len(names) == 3  # no repeats across segments
    keys = [w["tactical_watch_key"] for w in watches]
    assert len(keys) == len(set(keys))
    # Fight-week segment (offset <= 7) is a TAPER watch.
    fight_week = next(w for w in watches if w["countdown_offset"] <= 7)
    assert fight_week["tactical_watch_phase"] == "TAPER"


# --- PR #2221 preservation -------------------------------------------------


def test_promotion_preserves_metadata_not_generic_template():
    # An existing tactical watch role must be promoted WITH real watch content,
    # never replaced by a generic template.
    week = _week("SPP", 28)
    week["session_roles"].append(
        {
            "role_key": "tactical_watch",
            "category": "support_insert",
            "scheduled_day_hint": "Wednesday",
            "display_text": "old text",
        }
    )
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=28, tactical_styles=["out-boxer"]))
    watches = _watches(week["session_roles"])
    assert len(watches) == 1
    watch = watches[0]
    assert watch["mandatory_tactical_watch"] is True
    assert watch["tactical_watch_style"] == "distance_striker"
    assert watch["tactical_watch_phase"] == "SPP"
    assert watch["tactical_watch_name"] in watch["display_text"]
    assert watch["display_text"] != "old text"
    # PR #2221 camp guidance still rides along in the display text.
    assert "confirmed opponent" in watch["display_text"].lower()


def test_exactly_one_mandatory_watch_per_week_all_phases():
    role_map = {"weeks": [_week("GPP", 49), _week("SPP", 28), _week("TAPER", 7)]}
    apply_camp_week_fillers(role_map, _athlete(tactical_styles=["out-boxer"]))
    for week in role_map["weeks"]:
        mandatory = [w for w in _watches(week["session_roles"]) if w.get("mandatory_tactical_watch")]
        assert len(mandatory) == 1
