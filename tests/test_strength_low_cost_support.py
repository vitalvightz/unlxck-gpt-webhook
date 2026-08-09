from __future__ import annotations

from fightcamp import strength
from fightcamp.strength_session_quality import (
    classify_strength_item,
    count_support_only,
    support_budget_cost,
)


def _support(name: str, *, movement: str, tags: list[str], method: str = "strength", equipment="bodyweight") -> dict:
    return {
        "name": name,
        "phases": ["SPP"],
        "method": method,
        "movement": movement,
        "type": "bilateral",
        "tags": tags,
        "equipment": equipment,
    }


def test_rehab_and_prehab_are_zero_cost_but_remain_support_classified():
    normal = _support("Mobility Reset", movement="mobility", tags=["mobility"])
    rehab = _support("Ankle Rehab Control", movement="ankle_control", tags=["rehab"], method="rehab")
    prehab = _support("Shoulder Prehab Reset", movement="shoulder_control", tags=["stability"], method="prehab")

    assert count_support_only([normal, rehab, prehab]) == 3
    assert classify_strength_item(rehab)["rehab_support"] is True
    assert classify_strength_item(prehab)["rehab_support"] is True
    assert support_budget_cost([normal, rehab, prehab]) == 1


def test_one_core_or_balance_support_item_gets_the_low_cost_bonus():
    normal = _support("Mobility Reset", movement="mobility", tags=["mobility"])
    core = _support("Pallof Hold", movement="core", tags=["core", "anti_rotation"], equipment="bands")
    balance = _support("Balance Hold", movement="balance", tags=["balance", "stability"])

    assert support_budget_cost([normal, core, balance], core_balance_bonus=0) == 3
    assert support_budget_cost([normal, core, balance], core_balance_bonus=1) == 2
    assert classify_strength_item(core)["core_balance_support"] is True
    assert classify_strength_item(balance)["core_balance_support"] is True


def test_mech_trunk_stability_on_compound_does_not_fake_core_bonus():
    compound = _support(
        "Barbell Back Squat",
        movement="squat",
        tags=["compound", "mech_lower_squat", "mech_trunk_stability"],
        equipment="barbell",
    )

    profile = classify_strength_item(compound)
    assert profile["anchor_capable"] is True
    assert profile["core_balance_support"] is False
    assert support_budget_cost([compound], core_balance_bonus=1) == 0


def _patch_minimal_strength_runtime(monkeypatch, exercise_bank: list[dict], score_map: dict[str, float]) -> None:
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(
        strength,
        "strength_quality_adjustment",
        lambda exercise, phase=None: (0.0, strength.classify_strength_item(exercise)),
    )
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]], "reason_codes": []},
        ),
    )


def _flags(**overrides) -> dict:
    base = {
        "phase": "SPP",
        "fatigue": "low",
        "fight_format": "boxing",
        "sport": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "equipment": ["bodyweight", "bands"],
        "training_days": ["Mon"],
        "training_frequency": 1,
        "days_available": 1,
        "key_goals": ["power"],
        "weaknesses": [],
        "injuries": [],
        "days_until_fight": 30,
    }
    return {**base, **overrides}


def test_explicit_core_priority_adds_only_one_dedicated_support_exercise(monkeypatch):
    anchor = _support(
        "Anchor Row",
        movement="horizontal_pull",
        tags=["anchor_score", "upper_body", "pull", "compound"],
    )
    core = _support(
        "Pallof Hold",
        movement="core",
        tags=["core_score", "core", "anti_rotation"],
        equipment="bands",
    )
    _patch_minimal_strength_runtime(monkeypatch, [anchor, core], {"anchor_score": 10.0, "core_score": 9.0})

    baseline = strength.generate_strength_block(flags=_flags(), weaknesses=[])
    prioritized = strength.generate_strength_block(
        flags=_flags(weaknesses=["core stability"]),
        weaknesses=["core stability"],
    )

    assert [exercise["name"] for exercise in baseline["exercises"]] == ["Anchor Row"]
    assert [exercise["name"] for exercise in prioritized["exercises"]] == ["Anchor Row", "Pallof Hold"]
    assert "core_balance_low_cost_bonus" in prioritized["why_log"][1]["reasons"]["reason_codes"]

def test_core_balance_bonus_cannot_bypass_existing_movement_cap(monkeypatch):
    anchor_core = _support(
        "Core Pattern Anchor",
        movement="core",
        tags=["anchor_core_score", "upper_body", "pull", "compound"],
    )
    core_one = _support(
        "Pallof Hold One",
        movement="core",
        tags=["core_one_score", "core", "anti_rotation"],
        equipment="bands",
    )
    core_two = _support(
        "Pallof Hold Two",
        movement="core",
        tags=["core_two_score", "core", "stability"],
        equipment="bands",
    )
    _patch_minimal_strength_runtime(
        monkeypatch,
        [anchor_core, core_one, core_two],
        {"anchor_core_score": 10.0, "core_one_score": 9.0, "core_two_score": 8.0},
    )
    monkeypatch.setattr(
        strength,
        "calculate_exercise_numbers",
        lambda *_args, **_kwargs: {"strength": 2},
    )

    prioritized = strength.generate_strength_block(
        flags=_flags(weaknesses=["core stability"]),
        weaknesses=["core stability"],
    )

    names = [exercise["name"] for exercise in prioritized["exercises"]]
    movements = [exercise.get("movement") for exercise in prioritized["exercises"]]
    assert len(names) == 2
    assert movements.count("core") == 2
    assert "Pallof Hold Two" not in names
