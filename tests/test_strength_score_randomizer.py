import random

from fightcamp.strength import score_exercise


def test_score_exercise_randomizer_disabled_even_with_rng():
    """Scoring should stay deterministic even when RNG instances differ."""
    base_kwargs = {
        "exercise_tags": ["pull", "compound", "posterior_chain"],
        "weakness_tags": ["pull"],
        "goal_tags": ["power"],
        "style_tags": ["pressure_fighter"],
        "must_have_tags": ["compound"],
        "phase_tags": ["power"],
        "current_phase": "SPP",
        "fatigue_level": "moderate",
        "available_equipment": ["dumbbells", "bands"],
        "required_equipment": ["bands"],
        "is_rehab": False,
    }

    score_a, reasons_a = score_exercise(**base_kwargs, rng=random.Random(7))
    score_b, reasons_b = score_exercise(**base_kwargs, rng=random.Random(999))

    assert score_a == score_b
    assert reasons_a["randomness"] == 0.0
    assert reasons_b["randomness"] == 0.0
