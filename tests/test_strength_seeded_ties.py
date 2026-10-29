"""A generation seed decides between equally rated strength candidates.

The bank is shuffled with the seed and that order breaks ties inside a
near-equal score group (after fatigue cost). Before, the name sort undid the
shuffle, so every seed produced the alphabetical winner.
"""
from __future__ import annotations

from fightcamp import strength


def _bank_item(name: str) -> dict:
    return {
        "name": name,
        "phases": ["GPP"],
        "movement": "hinge",
        "method": "strength",
        "equipment": "bodyweight",
        "tags": [name, "posterior_chain", "mech_lower_hip_hinge"],
    }


def _block(monkeypatch, seed, *, scores: dict[str, float], target: int) -> list[str]:
    bank = [_bank_item(name) for name in scores]
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_a, **_k: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_a, **_k: {"strength": target})
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (scores[kwargs["exercise_tags"][0]], {"final_score": scores[kwargs["exercise_tags"][0]]}),
    )
    result = strength.generate_strength_block(
        flags={
            "phase": "GPP", "fatigue": "low", "equipment": ["bodyweight"], "fight_format": "mma",
            "training_days": ["Mon"], "training_frequency": 1, "key_goals": [], "style_tactical": [],
            "random_seed": seed,
        }
    )
    return [ex["name"] for ex in result["exercises"]]


TIED = {"Alpha Hinge": 1.0, "Bravo Hinge": 1.0, "Charlie Hinge": 1.0, "Delta Hinge": 1.0}


def test_unseeded_ties_keep_the_name_order(monkeypatch):
    assert _block(monkeypatch, None, scores=TIED, target=1) == ["Alpha Hinge"]


def test_same_seed_reproduces_the_same_block(monkeypatch):
    assert _block(monkeypatch, 41, scores=TIED, target=1) == _block(monkeypatch, 41, scores=TIED, target=1)


def test_different_seeds_give_tied_candidates_a_turn(monkeypatch):
    winners = {_block(monkeypatch, seed, scores=TIED, target=1)[0] for seed in range(20)}
    assert len(winners) > 1


def test_seed_never_promotes_a_lower_scored_candidate(monkeypatch):
    scores = {"Best Hinge": 2.0, "Zulu Weaker": 1.0, "Yankee Weaker": 1.0}
    for seed in range(20):
        assert _block(monkeypatch, seed, scores=scores, target=1) == ["Best Hinge"]
