"""The athlete's full bout format is a first-class, deterministic planning fact.

Before this module existed the intake string "<rounds> x <minutes>" was parsed
only for its round duration, so a 3 x 5 bout and a 5 x 5 bout looked
physiologically identical to the planner even though one is 900 seconds of
scheduled fight work and the other is 1500.

These tests pin the demand facts and their conservative quota integration. The
snapshot test at the bottom proves a 3 x 3 plan still renders exactly as it did
before.
"""
import json
from pathlib import Path

import pytest

from fightcamp import conditioning
from fightcamp.bout_format import (
    BASELINE_WORK_SECONDS,
    BoutFormat,
    bout_energy_modifiers,
    bout_format_metadata,
    parse_bout_format,
)
from fightcamp.config import athlete_round_seconds


# TEST 1 - every canonical intake format resolves to its own demand facts.
@pytest.mark.parametrize(
    "rounds_format,rounds,round_seconds,total_work_seconds",
    [
        ("3 x 2", 3, 120.0, 360.0),
        ("3 x 3", 3, 180.0, 540.0),
        ("5 x 3", 5, 180.0, 900.0),
        ("3 x 5", 3, 300.0, 900.0),
        ("5 x 5", 5, 300.0, 1500.0),
        ("12 x 3", 12, 180.0, 2160.0),
    ],
)
def test_canonical_formats_resolve_to_their_own_demand(
    rounds_format, rounds, round_seconds, total_work_seconds
):
    bout = parse_bout_format(rounds_format)
    assert bout == BoutFormat(
        rounds=rounds,
        round_seconds=round_seconds,
        total_work_seconds=total_work_seconds,
    )


# TEST 2 - the fact this whole module exists for: same round length, different
# bout. 3 x 5 and 5 x 5 are no longer indistinguishable.
def test_same_round_length_different_total_fight_work():
    three_by_five = parse_bout_format("3 x 5")
    five_by_five = parse_bout_format("5 x 5")
    assert three_by_five.round_seconds == five_by_five.round_seconds
    assert three_by_five.total_work_seconds != five_by_five.total_work_seconds


# TEST 3 - malformed, blank and absent formats stay explicitly unresolved.
# Nothing infers 3 x 3, and nothing infers a format from amateur/pro status.
@pytest.mark.parametrize(
    "rounds_format",
    ["", "   ", None, "amateur", "pro", "three x three", "3x", "x 3", "0 x 3", "3 x 0", "3 x 3 x 3"],
)
def test_unresolved_formats_do_not_assume_3x3(rounds_format):
    assert parse_bout_format(rounds_format) is None
    assert bout_format_metadata(rounds_format) == {}


# TEST 4 - separators the intake actually produces all parse the same.
@pytest.mark.parametrize("rounds_format", ["5 x 5", "5x5", "5 X 5", " 5 × 5 "])
def test_accepted_separators_agree(rounds_format):
    assert parse_bout_format(rounds_format) == parse_bout_format("5 x 5")


# TEST 5 - the demand facts the model exposes, and the neutral 3 x 3 ratio.
# The ratio is a comparison of two measured durations, nothing more; no energy
# system modifier is derived from it here.
def test_exposed_demand_facts_and_neutral_baseline_ratio():
    bout = parse_bout_format("5 x 5")
    assert BASELINE_WORK_SECONDS == 540.0
    assert bout.round_minutes == 5.0
    assert bout.total_work_minutes == 25.0
    assert bout.total_work_ratio_vs_baseline == pytest.approx(1500.0 / 540.0)
    assert parse_bout_format("3 x 3").total_work_ratio_vs_baseline == 1.0
    assert bout_format_metadata("5 x 5") == {
        "rounds": 5,
        "round_seconds": 300.0,
        "total_work_seconds": 1500.0,
        "total_work_minutes": 25.0,
        "total_work_ratio_vs_3x3": 2.7778,
    }


@pytest.mark.parametrize(
    "rounds_format,expected",
    [
        ("3 x 2", {"aerobic": 0.94, "glycolytic": 1.03, "alactic": 1.06}),
        ("3 x 3", {"aerobic": 1.0, "glycolytic": 1.0, "alactic": 1.0}),
        ("5 x 3", {"aerobic": 1.08, "glycolytic": 1.03, "alactic": 0.96}),
        ("3 x 5", {"aerobic": 1.10, "glycolytic": 1.06, "alactic": 0.94}),
        ("5 x 5", {"aerobic": 1.18, "glycolytic": 1.05, "alactic": 0.90}),
    ],
)
def test_known_bout_energy_modifiers_are_explicit_and_bounded(rounds_format, expected):
    assert bout_energy_modifiers(parse_bout_format(rounds_format)) == expected


def test_unknown_valid_format_uses_a_conservative_non_linear_derivation():
    modifiers = bout_energy_modifiers(parse_bout_format("12 x 3"))
    assert all(0.90 <= value <= 1.18 for value in modifiers.values())
    assert modifiers["aerobic"] == 1.12
    assert modifiers["aerobic"] != pytest.approx(4.0)


# TEST 6 - athlete_round_seconds() keeps its exact public behaviour while
# delegating to the one canonical parser.
@pytest.mark.parametrize(
    "rounds_format,expected",
    [
        ("3 x 2", 120.0),
        ("3 x 3", 180.0),
        ("5 x 3", 180.0),
        ("3 x 5", 300.0),
        ("5 x 5", 300.0),
        ("12 x 3", 180.0),
        ("3 x 1.5", 90.0),
        ("", None),
        (None, None),
        ("amateur", None),
        ("3 x 0", None),
    ],
)
def test_athlete_round_seconds_behaviour_is_unchanged(rounds_format, expected):
    assert athlete_round_seconds(rounds_format) == expected


# TEST 7 - the demand is observable in planner metadata, and it is metadata
# only: the competition round count is a demand input, never a prescription, so
# it does not become the drill round count.
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
        "random_seed": 1234,
        "style_technical": ["Boxer"],
        "style_tactical": ["Pressure"],
    }
    flags.update(over)
    return flags


def test_planner_metadata_exposes_the_bout_format():
    *_rest, reservoir = conditioning.generate_conditioning_block(_flags(rounds_format="5 x 5"))
    assert reservoir["__bout_format__"] == {
        "rounds": 5,
        "round_seconds": 300.0,
        "total_work_seconds": 1500.0,
        "total_work_minutes": 25.0,
        "total_work_ratio_vs_3x3": 2.7778,
    }


def test_planner_metadata_stays_unresolved_without_a_format():
    *_rest, reservoir = conditioning.generate_conditioning_block(_flags(rounds_format=""))
    assert reservoir["__bout_format__"] == {}


def _energy_demand(rounds_format, **over):
    *_rest, reservoir = conditioning.generate_conditioning_block(
        _flags(rounds_format=rounds_format, **over)
    )
    return reservoir["__energy_demand__"]


def test_3x3_demand_and_quota_keep_the_historical_phase_owner():
    for phase in ("GPP", "SPP", "TAPER"):
        demand = _energy_demand("3 x 3", phase=phase)
        assert demand["bout_format_modifiers"] == {
            "aerobic": 1.0,
            "glycolytic": 1.0,
            "alactic": 1.0,
        }
        assert demand["effective_system_demand"] == conditioning.PHASE_SYSTEM_RATIOS[phase]


def test_only_bout_format_changes_effective_demand_without_adding_sessions():
    formats = {
        rounds_format: _energy_demand(rounds_format)
        for rounds_format in ("3 x 2", "3 x 3", "5 x 3", "3 x 5", "5 x 5")
    }
    aerobic = {
        rounds_format: demand["effective_system_demand"]["aerobic"]
        for rounds_format, demand in formats.items()
    }
    assert aerobic["3 x 2"] < aerobic["5 x 3"] < aerobic["5 x 5"]
    assert aerobic["3 x 3"] < aerobic["5 x 3"]
    assert formats["3 x 5"]["effective_system_demand"] != formats["3 x 3"]["effective_system_demand"]
    assert formats["5 x 3"]["system_quota"] != formats["3 x 3"]["system_quota"]
    assert all(
        value > 0
        for value in formats["5 x 5"]["effective_system_demand"].values()
    )
    assert all(
        sum(demand["system_quota"].values()) == demand["total_conditioning_drills"]
        for rounds_format, demand in formats.items()
        if rounds_format != "3 x 3"
    )
    assert {demand["conditioning_sessions"] for demand in formats.values()} == {2}


def test_missing_or_malformed_format_preserves_existing_phase_demand():
    for rounds_format in (None, "", "not a format"):
        demand = _energy_demand(rounds_format)
        assert demand["bout_format_modifiers"] == {}
        assert demand["effective_system_demand"] == conditioning.PHASE_SYSTEM_RATIOS["SPP"]


def test_muay_thai_energy_profile_is_consumed_without_changing_drill_family(monkeypatch):
    weights = {
        "kickboxing": {"aerobic": 0.1, "glycolytic": 0.8, "alactic": 0.1},
        "muay_thai": {"aerobic": 0.5, "glycolytic": 0.35, "alactic": 0.15},
    }
    monkeypatch.setattr(conditioning, "get_format_weights", lambda: weights)
    demand = _energy_demand(
        "5 x 3", sport="muay_thai", style_technical=["muay_thai"]
    )
    assert demand["sport_energy_weights"] == weights["muay_thai"]


# TEST 8 - a representative 3 x 3 conditioning plan is byte-identical to the
# one this branch inherited. The foundation changes no programme output.
BASELINE = json.loads(
    (Path(__file__).parent / "data" / "conditioning_3x3_baseline.json").read_text()
)


@pytest.mark.parametrize("phase", ["GPP", "SPP", "TAPER"])
def test_3x3_conditioning_plan_is_unchanged(phase):
    text, names, _why, grouped, missing, _reservoir = conditioning.generate_conditioning_block(
        _flags(phase=phase)
    )
    expected = BASELINE[phase]
    assert text == expected["block"]
    assert names == expected["names"]
    assert missing == expected["missing_systems"]
    assert {k: [d.get("name") for d in v] for k, v in grouped.items()} == expected["grouped"]
