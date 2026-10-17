"""Running conditioning contracts: real doses, safe selection, and no fake equipment."""

import json
from pathlib import Path

import pytest

from fightcamp.bank_schema import (
    conditioning_dose_shape, has_meaningful_fulfillment_authority,
    is_late_fight_metadata_safe, D13_TO_D8,
)
from fightcamp.conditioning_boxing import (
    _boxing_aerobic_preference_rank, _boxing_aerobic_priority_adjustment,
)
from fightcamp.config import conditioning_dose_active_work_seconds

BANK = {row["name"]: row for row in json.loads(Path("data/conditioning_bank.json").read_text())}
RUNS = (
    "5K Steady Run", "One-Mile Timed Run", "Continuous Tempo Run",
    "Running Fartlek (1:2)", "Running Aerobic Intervals (6x4min)",
    "800m Running Repeats (8x)", "Short Hill Sprints (5x10s)",
    "Long Hill Intervals (12x2min)", "Descending Sprint Ladder (80-60-40m)",
    "Boxing Round Running Intervals (10-10-10)",
)


@pytest.mark.parametrize("name", RUNS)
def test_running_workouts_have_real_equipment_free_doses(name):
    item = BANK[name]
    assert item["equipment"] == []
    assert item["modality"] == "run"
    assert item["rpe"] > 0
    assert conditioning_dose_shape(item, source="conditioning_bank.json")
    assert has_meaningful_fulfillment_authority(
        item, source_kind="conditioning", source="conditioning_bank.json"
    )


@pytest.mark.parametrize("name", [
    "5K Steady Run", "One-Mile Timed Run",
    "800m Running Repeats (8x)", "Descending Sprint Ladder (80-60-40m)",
])
def test_distance_running_never_invents_timed_work(name):
    item = BANK[name]
    assert conditioning_dose_shape(item) == "distance"
    assert conditioning_dose_active_work_seconds(item) is None


def test_distance_dose_rejects_missing_or_invalid_distance():
    assert conditioning_dose_shape({"distance_m": -5000}) is None
    assert conditioning_dose_shape({"distance_m": 800, "rounds": 0}) is None
    assert conditioning_dose_shape({"distance_m": 800}) == "distance"


def test_hill_work_and_existing_legacy_doses_are_authorised():
    hill = BANK["Tempo Hill Runs"]
    assert (hill["work_sec"], hill["rounds"], hill["rest_sec"]) == (20, 6, 60)
    assert conditioning_dose_shape(hill) == "interval"
    assert has_meaningful_fulfillment_authority(
        hill, source_kind="conditioning", source="conditioning_bank.json"
    )
    assert (BANK["Hill Sprint Repeats"]["rounds"], BANK["Hill Sprint Repeats"]["work_sec"]) == (8, 8)


def test_no_equipment_does_not_authorise_a_physical_ladder():
    for name in ("Agility Ladder Sprints", "Agility Ladder (Recovery)"):
        assert BANK[name]["equipment"] == ["agility_ladder"]
    assert not has_meaningful_fulfillment_authority(
        BANK["Agility Ladder (Recovery)"],
        source_kind="conditioning", source="conditioning_bank.json",
    )


def test_running_priority_depends_on_lower_limb_safety():
    run = BANK["Nasal Jog"]
    args = dict(weaknesses=[], goals=["conditioning"], restrictions=None, equipment_access_set=set())
    assert _boxing_aerobic_preference_rank(run, injuries=[], **args) == 2
    assert _boxing_aerobic_priority_adjustment(run, injuries=[], **args) > 0
    assert _boxing_aerobic_preference_rank(run, injuries=["Achilles pain"], **args) == 5
    assert _boxing_aerobic_priority_adjustment(run, injuries=["Achilles pain"], **args) < 0


@pytest.mark.parametrize("name", [
    "800m Running Repeats (8x)", "Short Hill Sprints (5x10s)",
    "Long Hill Intervals (12x2min)", "Descending Sprint Ladder (80-60-40m)",
    "Boxing Round Running Intervals (10-10-10)",
])
def test_hard_running_is_not_accidentally_taper_cleared(name):
    result = is_late_fight_metadata_safe(BANK[name], "conditioning_bank.json", D13_TO_D8)
    assert not result["safe"]


def test_tempo_has_no_fabricated_total_minutes():
    for name in ("5K Steady Run", "One-Mile Timed Run", "800m Running Repeats (8x)"):
        assert "total_minutes" not in BANK[name]


def test_no_machine_boxer_keeps_an_outdoor_run_in_the_aerobic_shortlist():
    from fightcamp.conditioning import generate_conditioning_block

    flags = {
        "phase": "GPP", "sport": "boxing", "style_technical": ["boxing"],
        "style_tactical": ["counter_striker"], "key_goals": ["conditioning"],
        "primary_goal": "conditioning", "weaknesses": ["endurance"],
        "equipment": [], "injuries": [], "fatigue": "low",
        "training_frequency": 4, "days_until_fight": 49,
        "hard_sparring_days": [], "support_work_days": ["Wednesday"],
        "rounds_format": "3 x 3",
    }
    *_, candidates = generate_conditioning_block(flags)
    names = {item["drill"]["name"] for item in candidates.get("aerobic", [])}
    assert names & {"Nasal Jog", "5K Steady Run", "Continuous Tempo Run"}, names
