from __future__ import annotations

import json
from collections import Counter

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.conditioning import get_coordination_bank
from fightcamp.config import DATA_DIR
from fightcamp.coordination_support_library import (
    BANK_FILES,
    SUPPORTED_SPORTS,
    TACTICAL_STYLES,
    all_coordination_drills,
    extract_coordination_sport,
    extract_coordination_style,
    has_coordination_target,
    select_coordination_support,
)


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "technical_styles": ["boxing"],
        "tactical_styles": ["distance_striker"],
        "weaknesses": ["coordination"],
        "key_goals": [],
        "equipment": [],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "fatigue": "low",
        "days_until_fight": 0,
        "hard_sparring_days": [],
        "support_work_days": [],
    }
    athlete.update(overrides)
    return athlete


def _week(*, phase="GPP", hard_days=None, d_days=None, compressed=False):
    d_days = d_days or {"monday": 21, "wednesday": 19, "friday": 17}
    roles = [
        {
            "role_key": "primary_strength_day",
            "category": "strength",
            "scheduled_day_hint": "Monday",
        },
        {
            "role_key": "primary_conditioning_day",
            "category": "conditioning",
            "scheduled_day_hint": "Wednesday",
        },
    ]
    week = {
        "phase": phase,
        "session_roles": roles,
        "calendar_days": [
            {"weekday": day, "d_day": d_day} for day, d_day in d_days.items()
        ],
        "declared_training_days": ["Monday", "Wednesday", "Friday"],
        "declared_hard_sparring_days": hard_days or [],
        "declared_support_work_days": [],
        "intentionally_unused_days": [],
    }
    if compressed:
        week["intentional_compression"] = {"active": True}
    return week


def _coordination_roles(week):
    return [
        role
        for role in week["session_roles"]
        if isinstance(role, dict) and role.get("role_key") == "coordination_support"
    ]


def test_v2_bank_is_small_deliberate_and_split():
    all_coordination_drills.cache_clear()
    drills = all_coordination_drills()
    assert 50 <= len(drills) <= 70
    assert len(BANK_FILES) == 5
    assert len({drill.key for drill in drills}) == len(drills)
    assert len({drill.name for drill in drills}) == len(drills)

    banned_novelty = ("blindfold", "strobe", "slackline", "trampoline", "bosu", "office chair")
    assert not [drill.name for drill in drills if any(term in drill.name.lower() for term in banned_novelty)]

    for drill in drills:
        assert drill.raw["placement"] == "support"
        assert "system" not in drill.raw
        assert drill.raw["support_only"] is True
        assert drill.raw["meaningful_stress"] is False
        assert drill.raw["stress_class"] == "support"
        assert drill.raw["cost_class"] == "low"
        assert set(drill.equipment) <= {"bodyweight", "partner"}


def test_v2_bank_covers_every_sport_and_tactical_style_with_overlap():
    drills = all_coordination_drills()
    sport_counts = Counter(sport for drill in drills for sport in drill.sports if sport != "universal")
    style_counts = Counter(style for drill in drills for style in drill.styles)

    assert set(SUPPORTED_SPORTS) <= set(sport_counts)
    assert set(TACTICAL_STYLES) <= set(style_counts)
    assert min(style_counts[style] for style in TACTICAL_STYLES) >= 6
    assert sum(1 for drill in drills if len(drill.sports) > 1) >= 30
    assert sum(1 for drill in drills if len(drill.styles) > 1) >= 40


def test_legacy_conditioning_bank_is_an_empty_shim():
    raw = json.loads((DATA_DIR / "coordination_bank.json").read_text(encoding="utf-8"))
    flattened = [entry for value in raw.values() if isinstance(value, list) for entry in value]
    assert flattened == []
    assert get_coordination_bank() == []


def test_coordination_target_gate_is_explicit():
    assert has_coordination_target(_athlete())
    assert has_coordination_target(_athlete(weaknesses=["coordination / proprioception"]))
    assert not has_coordination_target(_athlete(weaknesses=["balance"], key_goals=["speed"]))


def test_sport_and_style_normalization_match_current_intake_taxonomy():
    athlete = _athlete(technical_styles=["muay thai"], tactical_styles=["Pressure Fighter"])
    assert extract_coordination_sport(athlete) == "muay_thai"
    assert extract_coordination_style(athlete) == "pressure_fighter"


def test_selection_prefers_real_sport_and_style_without_duplicate_bank_entries():
    athlete = _athlete(technical_styles=["boxing"], tactical_styles=["distance_striker"])
    drill = select_coordination_support(athlete, "GPP")
    assert drill is not None
    assert "boxing" in drill.sports
    assert "distance_striker" in drill.styles
    assert drill.equipment == ("bodyweight",)


def test_selection_rotates_instead_of_repeating_the_same_drill():
    athlete = _athlete()
    first = select_coordination_support(athlete, "GPP")
    assert first is not None
    second = select_coordination_support(athlete, "GPP", {first.key})
    assert second is not None
    assert second.key != first.key


def test_mma_grappler_gets_mma_relevant_coordination():
    athlete = _athlete(
        sport="mma",
        technical_styles=["mma"],
        tactical_styles=["grappler"],
    )
    drill = select_coordination_support(athlete, "GPP")
    assert drill is not None
    assert "mma" in drill.sports
    assert "grappler" in drill.styles


def test_normal_week_gets_one_coordination_support_role_only_when_targeted():
    targeted = {"weeks": [_week()]}
    apply_camp_week_fillers(targeted, _athlete())
    roles = _coordination_roles(targeted["weeks"][0])
    assert len(roles) == 1
    role = roles[0]
    assert role["category"] == "support_insert"
    assert role["support_insert_category"] == "coordination"
    assert role["weekly_requirement"] == "coordination_target"
    assert role["stress_class"] == "support"
    assert role["cost_class"] == "low"
    assert role["governance"]["selected_drill_locked"] is True
    assert "coordination support" in role["display_text"].lower()

    untargeted = {"weeks": [_week()]}
    apply_camp_week_fillers(untargeted, _athlete(weaknesses=["balance"]))
    assert _coordination_roles(untargeted["weeks"][0]) == []


def test_coordination_support_avoids_hard_sparring_days():
    role_map = {"weeks": [_week(hard_days=["Monday"]) ]}
    apply_camp_week_fillers(role_map, _athlete(hard_sparring_days=["Monday"]))
    roles = _coordination_roles(role_map["weeks"][0])
    assert len(roles) == 1
    assert roles[0]["scheduled_day_hint"] == "Wednesday"


def test_coordination_support_does_not_create_fight_eve_or_compressed_work():
    fight_eve_week = _week(d_days={"monday": 1, "wednesday": 1, "friday": 1})
    fight_eve = {"weeks": [fight_eve_week]}
    apply_camp_week_fillers(fight_eve, _athlete())
    assert _coordination_roles(fight_eve_week) == []

    compressed_week = _week(compressed=True)
    compressed = {"weeks": [compressed_week]}
    apply_camp_week_fillers(compressed, _athlete())
    assert _coordination_roles(compressed_week) == []
