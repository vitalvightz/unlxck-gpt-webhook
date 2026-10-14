import pytest

from fightcamp import conditioning
from fightcamp.conditioning_boxing import _boxing_heavy_bag_preference
from fightcamp.conditioning_preferences import striking_heavy_bag_preference
from fightcamp.config import athlete_round_seconds, conditioning_effective_dose, conditioning_phase_workload_envelope
from fightcamp.session_composition import _conditioning_partition_high_load


def _flags(**changes):
    flags = {"phase": "SPP", "sport": "boxing", "style_technical": ["boxing"],
             "style_tactical": ["Pressure Fighter"], "key_goals": ["conditioning", "speed", "power"],
             "primary_goal": "conditioning", "weaknesses": ["gas_tank"], "primary_weak_area": "gas_tank",
             "fatigue": "low", "equipment": ["bodyweight", "heavy_bag", "assault_bike"],
             "training_frequency": 6, "days_available": 6, "days_until_fight": 35,
             "time_to_fight_days": 35, "rounds_format": "10 x 3", "injuries": [], "restrictions": []}
    flags.update(changes)
    return flags


def test_real_bank_prefers_varied_boxing_bag_work_while_retaining_aerobic_work(monkeypatch):
    preference = conditioning.striking_heavy_bag_preference
    monkeypatch.setattr(conditioning, "striking_heavy_bag_preference", lambda *args, **kwargs: 0.0)
    before = conditioning.generate_conditioning_block(_flags())[1]
    monkeypatch.setattr(conditioning, "striking_heavy_bag_preference", preference)
    _, after, _, grouped, _, _ = conditioning.generate_conditioning_block(_flags())
    banks = conditioning.get_conditioning_bank() + conditioning.get_style_conditioning_bank()
    bag = {drill["name"] for drill in banks if "heavy_bag" in drill.get("equipment", [])}
    assert len(set(after) & bag) > len(set(before) & bag)
    assert len(set(after) & bag) >= 2
    assert {"Heavy Bag Power Rounds", "Max-Power Bag Burst"}.issubset(after)
    assert grouped["aerobic"]  # Recovery/base work remains a real selected system.
    assert len(set(after)) == len(after)


def test_no_heavy_bag_access_never_selects_a_bag_drill():
    selected = conditioning.generate_conditioning_block(_flags(equipment=["bodyweight", "assault_bike"]))[1]
    bag = {d["name"] for d in conditioning.get_conditioning_bank() + conditioning.get_style_conditioning_bank()
           if "heavy_bag" in d.get("equipment", [])}
    assert not set(selected) & bag


@pytest.mark.parametrize("sport", ["boxing", "kickboxing", "muay_thai", "mma"])
def test_bag_preference_applies_to_each_striking_sport_with_real_bank_selection(sport):
    flags = _flags(sport=sport, style_technical=[sport])
    _, names, _, grouped, _, _ = conditioning.generate_conditioning_block(flags)
    bank = conditioning.get_conditioning_bank() + conditioning.get_style_conditioning_bank()
    bag = {d["name"] for d in bank if "heavy_bag" in d.get("equipment", [])}
    assert set(names) & bag
    assert grouped["aerobic"]
    for system in ("aerobic", "alactic", "glycolytic"):
        assert striking_heavy_bag_preference({"equipment": ["heavy_bag"]}, sport=sport,
            phase="SPP", system=system, fatigue="low", days_until_fight=35,
            equipment_access_set={"heavy_bag"}, injuries=[], hard_sparring_days=[]) > 0


@pytest.mark.parametrize("sport", ["wrestling", "bjj"])
def test_grappling_only_sports_do_not_receive_a_striking_bag_bonus(sport):
    assert striking_heavy_bag_preference({"equipment": ["heavy_bag"]}, sport=sport,
        phase="SPP", system="glycolytic", fatigue="low", days_until_fight=35,
        equipment_access_set={"heavy_bag"}, injuries=[], hard_sparring_days=[]) == 0


@pytest.mark.parametrize("changes", [
    {"phase": "TAPER"}, {"days_until_fight": 7}, {"fatigue": "high"},
    {"injuries": ["right wrist pain"]}, {"hard_sparring_days": ["Monday", "Wednesday", "Friday"]},
    {"equipment_access_set": {"bodyweight"}},
])
def test_bag_preference_yields_to_taper_readiness_contact_and_equipment_context(changes):
    kwargs = {"phase": "SPP", "system": "glycolytic", "fatigue": "low", "days_until_fight": 35,
              "equipment_access_set": {"heavy_bag"}, "injuries": [], "hard_sparring_days": []}
    kwargs.update(changes)
    assert _boxing_heavy_bag_preference({"equipment": ["heavy_bag"]}, **kwargs) == 0


def test_alactic_workload_uses_short_bursts_and_full_rounds_use_the_fighters_format():
    assert conditioning_phase_workload_envelope(phase="GPP", system="alactic")[0] == 30
    assert conditioning_phase_workload_envelope(phase="SPP", system="alactic")[0] == 40
    assert conditioning_phase_workload_envelope(phase="TAPER", system="alactic") == (None, None)
    drill = next(d for d in conditioning.get_style_conditioning_bank() if d["name"] == "Pressure Combination Rounds")
    dose = conditioning_effective_dose(drill, athlete_round_seconds("10 x 3"))
    assert dose["work_sec"] == 180 and dose["rounds"] == drill["rounds"] == 4
    assert dose["rest_sec"] == drill["rest_sec"] == 60
    assert dose["total_minutes"] == 15


def test_full_authored_round_can_cross_workload_floor_without_exceeding_bank_or_elapsed_caps():
    options = [({}, {"name": name, "selection_metadata": {"rpe": 8, "rounds": 4,
                "work_sec": 180, "rest_sec": 60}}, True) for name in ("Bag combinations", "Repeat effort")]
    selected, rounds, _, _ = _conditioning_partition_high_load(options, phase="SPP", system="glycolytic")
    assert sum(rounds.values()) == 3  # 9 active minutes clears the 8-minute floor.
    assert all(rounds.get(option["name"], 0) <= 4 for _, option, _ in selected)
    assert sum(count * 240 - 60 for count in rounds.values()) <= 25 * 60
