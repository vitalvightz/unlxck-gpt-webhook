"""Category promotion must be a viable substitution, not a temporary insertion."""

from collections import Counter

import pytest

from fightcamp import strength
from fightcamp.plan_pipeline_blocks import _is_rotational_power_anchor
from fightcamp.strength_session_quality import classify_strength_item, missing_base_categories


def _generate(monkeypatch, rows, scores, *, goals=(), seed=None, target=3, camp_gap=False):
    bank = [dict(name=name, phases=["SPP"], movement=movement, method=method,
                 equipment=equipment, tags=[name, *tags])
            for name, movement, method, equipment, tags in rows]
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_a, **_k: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_a, **_k: {"strength": target})
    monkeypatch.setattr(strength, "score_exercise", lambda **kw: (
        scores[kw["exercise_tags"][0]], {"final_score": scores[kw["exercise_tags"][0]]}))
    return strength.generate_strength_block(flags={
        "phase": "SPP", "fatigue": "low", "equipment": ["dumbbells", "bodyweight"],
        "fight_format": "mma", "training_days": ["Mon"], "training_frequency": 1,
        "days_until_fight": 56, "key_goals": list(goals), "random_seed": seed,
        "rotational_power_camp_gap": camp_gap,
    })["exercises"]


@pytest.mark.parametrize("seed", [None, 0, 1, 2, 3, 4, 5])
def test_promoted_squat_replaces_a_squat_so_it_survives_the_movement_cap(monkeypatch, seed):
    rows = [
        ("Back Squat", "squat", "strength", "dumbbells", []),
        ("Front Squat", "squat", "strength", "dumbbells", []),
        ("Bench Press", "push", "strength", "dumbbells", []),
        ("Split Squat", "squat", "strength", "dumbbells", ["unilateral"]),
    ]
    exercises = _generate(monkeypatch, rows, dict(zip([r[0] for r in rows], [6, 5, 4, 3])), seed=seed)
    assert {ex["name"] for ex in exercises} == {"Back Squat", "Bench Press", "Split Squat"}
    assert not missing_base_categories(exercises)
    assert max(Counter(ex["movement"] for ex in exercises).values()) <= 2


def test_later_promotion_keeps_the_lower_body_anchor_it_just_added(monkeypatch):
    rows = [
        ("Bench Press", "push", "strength", "dumbbells", []),
        ("Bent-Over Row", "pull", "strength", "dumbbells", []),
        ("Clap Push-Up", "horizontal_push", "plyometric", "bodyweight", ["explosive"]),
        ("Front Squat", "squat", "strength", "dumbbells", []),
        ("Single-Leg Box Jump", "vertical_jump", "plyometric", "bodyweight", ["mech_lower_jump"]),
    ]
    exercises = _generate(monkeypatch, rows, dict(zip([r[0] for r in rows], [6, 5, 4, 3, 2])))
    assert not missing_base_categories(exercises)
    assert "Front Squat" in {ex["name"] for ex in exercises}
    assert any(classify_strength_item(ex)["power_pattern"] for ex in exercises)


def test_no_promotion_when_it_would_remove_the_only_selected_strength_stimulus(monkeypatch):
    rows = [
        ("Bench Press", "push", "strength", "dumbbells", []),
        ("Squat Jump", "vertical_jump", "plyometric", "bodyweight", ["mech_lower_jump"]),
        ("Clap Push-Up", "horizontal_push", "plyometric", "bodyweight", ["explosive"]),
        ("Single-Leg Box Jump", "vertical_jump", "plyometric", "bodyweight", ["mech_lower_jump"]),
    ]
    exercises = _generate(monkeypatch, rows, dict(zip([r[0] for r in rows], [1, 6, 5, 0])), goals=["strength"])
    assert "Bench Press" in {ex["name"] for ex in exercises}


@pytest.mark.parametrize("goals,camp_gap", [(["power"], False), ([], True)])
def test_promotion_preserves_power_priority_or_the_camp_rotation_witness(monkeypatch, goals, camp_gap):
    rows = [
        ("Front Squat", "squat", "strength", "dumbbells", []),
        ("Bench Press", "push", "strength", "dumbbells", []),
        ("Rotational Hop", "rotation", "plyometric", "bodyweight", ["mech_trunk_rotation"]),
        ("Split Squat", "squat", "strength", "dumbbells", ["unilateral"]),
    ]
    exercises = _generate(monkeypatch, rows, dict(zip([r[0] for r in rows], [6, 5, 4, 3])), goals=goals, camp_gap=camp_gap)
    assert {ex["name"] for ex in exercises} == {"Bench Press", "Rotational Hop", "Split Squat"}
    assert not missing_base_categories(exercises)


def test_no_promotion_when_no_slot_can_preserve_the_existing_base_roles(monkeypatch):
    rows = [
        ("Front Squat", "squat", "strength", "dumbbells", []),
        ("Bench Press", "push", "strength", "dumbbells", []),
        ("Single-Leg Box Jump", "vertical_jump", "plyometric", "bodyweight", ["mech_lower_jump"]),
    ]
    exercises = _generate(monkeypatch, rows, dict(zip([r[0] for r in rows], [6, 5, 2])), target=2)
    assert {ex["name"] for ex in exercises} == {"Front Squat", "Bench Press"}
    assert missing_base_categories(exercises) == ["unilateral"]


@pytest.mark.parametrize("seed", [2837615948, None, 0, 1, 2, 3, 4, 5])
def test_promotion_keeps_the_contrast_pattern_and_trades_the_other_squat(monkeypatch, seed):
    rows = [
        ("Back Squat → Box Jump", "squat", "contrast", "dumbbells", ["explosive"]),
        ("Barbell Thruster", "squat", "strength", "dumbbells", ["explosive"]),
        ("Bench Press", "push", "strength", "dumbbells", []),
        ("Split Squat", "squat", "strength", "dumbbells", ["unilateral"]),
    ]
    exercises = _generate(monkeypatch, rows, dict(zip([r[0] for r in rows], [4, 6, 5, 3])), seed=seed)
    assert {ex["name"] for ex in exercises} == {"Back Squat → Box Jump", "Bench Press", "Split Squat"}
    assert not missing_base_categories(exercises)


def test_promotion_tries_a_safe_alternative_to_the_highest_ranked_provider(monkeypatch):
    rows = [
        ("Back Squat", "squat", "strength", "dumbbells", []),
        ("Front Squat", "squat", "strength", "dumbbells", []),
        ("Bench Press", "push", "strength", "dumbbells", []),
        ("Split Squat", "squat", "strength", "dumbbells", ["unilateral"]),
        ("Step-Up", "lunge", "strength", "dumbbells", ["unilateral"]),
    ]

    def decide(exercise):
        return strength.Decision(
            action="exclude" if exercise["name"] == "Split Squat" else "allow",
            risk_score=0, threshold=1, matched_tags=[], mods=[], reason={},
        )

    monkeypatch.setattr(strength, "make_guarded_decision_factory", lambda *_a, **_k: decide)
    exercises = _generate(monkeypatch, rows, dict(zip([r[0] for r in rows], [6, 5, 4, 3, 2])))
    assert "Split Squat" not in {ex["name"] for ex in exercises}
    assert "Step-Up" in {ex["name"] for ex in exercises}
    assert not missing_base_categories(exercises)


FULL_EQUIPMENT = [
    "barbell", "dumbbells", "kettlebell", "bands", "medicine_ball", "sled", "cable",
    "pullup_bar", "trap_bar", "landmine", "bench", "machine", "sandbag", "bodyweight", "trx", "cable_machine",
]


@pytest.mark.parametrize("equipment, goal, style, fatigue", [
    (FULL_EQUIPMENT, "strength", "pressure_fighter", "low"),
    (["dumbbells", "kettlebell", "bands", "pullup_bar", "bodyweight"], "power", "wrestler", "moderate"),
    (["bodyweight", "bands"], "power", "counter_striker", "low"),
])
def test_real_spp_regressions_with_gpp_continuity(equipment, goal, style, fatigue):
    flags = dict(phase="GPP", equipment=equipment, key_goals=[goal], style_tactical=[style],
                 fatigue=fatigue, fight_format="mma", training_frequency=3,
                 training_days=["Mon", "Tue", "Wed"], days_until_fight=56,
                 injuries=[], rotational_power_camp_gap=True)
    gpp = strength.generate_strength_block(flags=flags)["exercises"]
    flags.update(phase="SPP", prev_exercises=[ex["name"] for ex in gpp],
                 recent_exercises=sorted({ex["movement"] for ex in gpp}),
                 rotational_power_camp_gap=not any(_is_rotational_power_anchor(ex) for ex in gpp))
    spp = strength.generate_strength_block(flags=flags)["exercises"]
    assert not missing_base_categories(spp)
    assert max(Counter(ex["movement"] for ex in spp if ex["movement"] != "unknown").values()) <= 2
    assert any(classify_strength_item(ex)["power_pattern"] for ex in spp)


@pytest.mark.parametrize("seed", [4, 5])
def test_real_seeded_gpp_unilateral_regression(seed):
    exercises = strength.generate_strength_block(flags={
        "phase": "GPP", "equipment": FULL_EQUIPMENT, "key_goals": ["injury_prevention"],
        "style_tactical": ["pressure_fighter"], "fatigue": "low", "fight_format": "mma",
        "training_frequency": 3, "training_days": ["Mon", "Tue", "Wed"], "days_until_fight": 56,
        "injuries": [], "random_seed": seed, "rotational_power_camp_gap": True,
    }, weaknesses=["core"])["exercises"]
    assert not missing_base_categories(exercises)
    assert max(Counter(ex["movement"] for ex in exercises if ex["movement"] != "unknown").values()) <= 2
