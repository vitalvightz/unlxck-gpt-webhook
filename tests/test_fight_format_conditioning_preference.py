"""A declared gas-tank limiter must pick fight-format round work first.

Fight-specific conditioning - heavy bag, pads and shadowboxing dosed in the
athlete's own rounds - is the most specific answer there is to a conditioning
goal or a gas-tank weakness. Before this preference existed scoring could not
tell such a session apart from a merely goal-tagged hill run, so generic
aerobic work, carries and low-dose neural drills kept winning the fight-pace
slot.

The preference is deliberately a *preference*: it reorders candidates that
scoring already received, and scoring runs only after every eligibility filter
(injury and medical restrictions, equipment, contact, phase and session-type
gating), so it can never make an ineligible drill selectable.
"""
import json
from pathlib import Path

import pytest

from fightcamp import conditioning
from fightcamp.config import (
    athlete_round_seconds,
    conditioning_round_prescription,
)
from fightcamp.priority_profile import build_priority_profile


BANK = json.loads((Path("data/conditioning_bank.json")).read_text())
ROUND_BASED = [entry for entry in BANK if entry.get("round_based")]


def _profile(*, goals, weaknesses, primary_goal="", primary_weak_area=""):
    return build_priority_profile(
        {
            "key_goals": goals,
            "primary_goal": primary_goal,
            "weak_areas": weaknesses,
            "primary_weak_area": primary_weak_area,
        }
    )


def _flags(**over):
    flags = {
        "phase": "SPP",
        "sport": "boxing",
        "key_goals": ["Conditioning"],
        "weaknesses": ["Gas tank"],
        "equipment": ["heavy_bag", "pads", "kettlebells", "jump_rope"],
        "equipment_access": ["heavy_bag", "pads", "kettlebells", "jump_rope"],
        "injuries": [],
        "fatigue": "moderate",
        "training_frequency": 4,
        "days_until_fight": 60,
        "rounds_format": "3 x 3",
        "style_technical": ["Boxer"],
        "style_tactical": ["Pressure"],
    }
    flags.update(over)
    return flags


def _glycolytic_scores(**over):
    *_rest, reservoir = conditioning.generate_conditioning_block(_flags(**over))
    return {
        (candidate.get("drill") or {}).get("name"): candidate.get("score")
        for candidate in (reservoir.get("glycolytic") or [])
    }


# TEST 1 - a primary conditioning + gas-tank athlete gets fight-format rounds.
def test_primary_gas_tank_selects_a_fight_format_round_session():
    _text, names, *_rest = conditioning.generate_conditioning_block(_flags())
    round_names = {entry["name"] for entry in ROUND_BASED}
    assert round_names & set(names), names


# TEST 2 - the boost is large enough to be a dominant preference, not a nudge.
def test_fight_format_rounds_clearly_outrank_a_generic_tagged_drill():
    scores = _glycolytic_scores()
    fight_format = {
        name: score
        for name, score in scores.items()
        if name in {entry["name"] for entry in ROUND_BASED}
    }
    assert fight_format, scores
    generic = scores.get("Tempo Hill Runs")
    assert generic is not None
    assert min(fight_format.values()) > generic


# TEST 3 - strength-primary athletes get no fight-format boost at all.
def test_strength_primary_athlete_gets_no_fight_format_boost():
    profile = _profile(goals=["Strength"], weaknesses=["Trunk strength"])
    for entry in ROUND_BASED:
        assert conditioning._conditioning_fight_format_priority_bonus(entry, profile) == 0.0


# TEST 4 - a secondary conditioning goal keeps only ordinary secondary weight.
def test_secondary_conditioning_goal_gets_no_dominant_preference():
    profile = _profile(
        goals=["Speed", "Conditioning"],
        weaknesses=["Hand speed"],
        primary_goal="Speed",
        primary_weak_area="Hand speed",
    )
    assert not conditioning._conditioning_priority_is_primary_gas_tank(profile)
    for entry in ROUND_BASED:
        assert conditioning._conditioning_fight_format_priority_bonus(entry, profile) == 0.0


# TEST 5 - the preference keys off the bank marker, never a drill name.
@pytest.mark.parametrize("name", ["Heavy Bag Power Rounds", "Shadowboxing Intervals"])
def test_preference_keys_off_the_round_based_marker_not_the_name(name):
    profile = _profile(goals=["Conditioning"], weaknesses=["Gas tank"])
    marked = next(entry for entry in ROUND_BASED if entry["name"] == name)
    assert conditioning._conditioning_fight_format_priority_bonus(marked, profile) > 0

    unmarked = {key: value for key, value in marked.items() if key != "round_based"}
    assert conditioning._conditioning_fight_format_priority_bonus(unmarked, profile) == 0.0


# TEST 6 - nothing is special-cased to one sport. Every striking format that
# reaches selection gets a fight-format round session from the same records.
@pytest.mark.parametrize("sport", ["boxing", "kickboxing", "muay_thai", "mma"])
def test_every_striking_format_reaches_a_fight_format_round_session(sport):
    scores = _glycolytic_scores(sport=sport, style_technical=[sport])
    round_names = {entry["name"] for entry in ROUND_BASED}
    assert round_names & set(scores), (sport, sorted(scores))


# TEST 7 - the dose is the athlete's real format, not a hardcoded 3 x 3.
@pytest.mark.parametrize(
    "rounds_format,expected",
    [("3 x 3", "3 min round"), ("3 x 2", "2 min round"), ("5 x 5", "5 min round"), ("12 x 3", "3 min round")],
)
def test_round_prescription_renders_the_athletes_own_round_length(rounds_format, expected):
    round_seconds = athlete_round_seconds(rounds_format)
    rendered = conditioning_round_prescription(6, round_seconds, rest_sec=60, rpe=6)
    assert expected in rendered
    assert rendered.startswith("6 x ")


# TEST 8 - with no usable format the bank's authored duration stands; nothing
# infers a round length from amateur/pro status or anywhere else.
def test_no_usable_fight_format_leaves_the_bank_duration_alone():
    assert athlete_round_seconds("") is None
    assert athlete_round_seconds("amateur") is None
    assert conditioning_round_prescription(6, None) == ""


# TEST 9 - scoring cannot resurrect a drill an eligibility filter removed. The
# athlete has no heavy bag, so bag rounds never reach the candidate pool no
# matter how dominant the preference is.
def test_preference_never_overrides_an_equipment_filter():
    scores = _glycolytic_scores(
        equipment=["kettlebells"], equipment_access=["kettlebells"]
    )
    bag_only = {
        entry["name"]
        for entry in ROUND_BASED
        if "heavy_bag" in (entry.get("equipment") or [])
    }
    assert bag_only
    assert not bag_only & set(scores)


# TEST 10 - the families stay distinct. A short max-effort primer is never
# tagged as conditioning, so it can never be scored as a round session.
@pytest.mark.parametrize(
    "name", ["Shadowboxing Power Bursts", "Agility Ladder Sprints"]
)
def test_neural_primers_are_not_treated_as_fight_conditioning(name):
    entry = next(item for item in BANK if item["name"] == name)
    assert not entry.get("round_based")
    assert not {"conditioning", "work_capacity"} & set(entry["tags"])
    profile = _profile(goals=["Conditioning"], weaknesses=["Gas tank"])
    assert conditioning._conditioning_fight_format_priority_bonus(entry, profile) == 0.0
