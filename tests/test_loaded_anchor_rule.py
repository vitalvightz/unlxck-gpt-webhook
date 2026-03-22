from __future__ import annotations

from fightcamp import strength
from fightcamp.strength import generate_strength_block
from fightcamp.strength_session_quality import classify_strength_item


def test_classify_strength_item_distinguishes_true_loaded_anchor_from_broad_anchor_bucket():
    trap_bar_deadlift = {
        "name": "Trap Bar Deadlift",
        "movement": "hinge",
        "tags": ["compound", "posterior_chain", "hinge"],
        "equipment": ["trap_bar"],
        "method": "4x4",
    }
    landmine_press = {
        "name": "Landmine Press",
        "movement": "push",
        "tags": ["compound", "press", "upper_body"],
        "equipment": ["landmine"],
        "method": "4x5",
    }
    deadlift_isometric = {
        "name": "Deadlift Isometric",
        "movement": "hinge",
        "tags": ["isometric", "posterior_chain"],
        "equipment": ["barbell"],
        "method": "4x10 sec",
    }
    med_ball_throw = {
        "name": "Rotational Med Ball Throw",
        "movement": "rotation",
        "tags": ["explosive", "medicine_ball", "rotational"],
        "equipment": ["medicine_ball"],
        "method": "4x4 each side",
    }

    assert classify_strength_item(trap_bar_deadlift)["true_loaded_anchor"] is True
    assert classify_strength_item(landmine_press)["anchor_capable"] is True
    assert classify_strength_item(landmine_press)["true_loaded_anchor"] is False
    assert classify_strength_item(deadlift_isometric)["anchor_capable"] is True
    assert classify_strength_item(deadlift_isometric)["true_loaded_anchor"] is False
    assert classify_strength_item(med_ball_throw)["anchor_capable"] is True
    assert classify_strength_item(med_ball_throw)["true_loaded_anchor"] is False


def test_generate_strength_block_restores_true_loaded_anchor_in_spp(monkeypatch):
    exercise_bank = [
        {
            "name": "Landmine Press",
            "phases": ["SPP"],
            "tags": ["press", "compound", "upper_body"],
            "equipment": ["landmine"],
            "movement": "push",
            "method": "4x5",
        },
        {
            "name": "Rotational Med Ball Throw",
            "phases": ["SPP"],
            "tags": ["explosive", "medicine_ball", "rotational"],
            "equipment": ["medicine_ball"],
            "movement": "rotation",
            "method": "4x4 each side",
        },
        {
            "name": "Trap Bar Deadlift",
            "phases": ["SPP"],
            "tags": ["compound", "posterior_chain", "hinge"],
            "equipment": ["trap_bar"],
            "movement": "hinge",
            "method": "4x4",
        },
    ]
    score_map = {
        "Landmine Press": 10.0,
        "Rotational Med Ball Throw": 9.95,
        "Trap Bar Deadlift": 8.6,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 2})
    def _score(**kwargs):
        exercise_tags = set(kwargs["exercise_tags"])
        if "trap_bar" in exercise_tags or {"posterior_chain", "hinge"} <= exercise_tags:
            score = score_map["Trap Bar Deadlift"]
        elif "medicine_ball" in exercise_tags or "explosive" in exercise_tags:
            score = score_map["Rotational Med Ball Throw"]
        else:
            score = score_map["Landmine Press"]
        return score, {"final_score": score}
    monkeypatch.setattr(
        strength,
        "score_exercise",
        _score,
    )

    result = generate_strength_block(
        flags={
            "phase": "SPP",
            "fatigue": "low",
            "equipment": ["landmine", "medicine_ball", "trap_bar"],
            "fight_format": "boxing",
            "training_days": ["Mon", "Thu"],
            "training_frequency": 2,
            "key_goals": [],
            "style_tactical": [],
        }
    )

    assert result["true_loaded_anchor_present"] is True
    assert result["loaded_anchor_limited"] is False
    assert result["exercises"][0]["name"] == "Trap Bar Deadlift"


def test_generate_strength_block_marks_injury_limited_when_no_true_loaded_anchor_exists(monkeypatch):
    exercise_bank = [
        {
            "name": "Landmine Press",
            "phases": ["SPP"],
            "tags": ["press", "compound", "upper_body"],
            "equipment": ["landmine"],
            "movement": "push",
            "method": "4x5",
        },
        {
            "name": "Rotational Med Ball Throw",
            "phases": ["SPP"],
            "tags": ["explosive", "medicine_ball", "rotational"],
            "equipment": ["medicine_ball"],
            "movement": "rotation",
            "method": "4x4 each side",
        },
    ]
    score_map = {
        "Landmine Press": 10.0,
        "Rotational Med Ball Throw": 9.95,
    }

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 2})
    def _score(**kwargs):
        exercise_tags = set(kwargs["exercise_tags"])
        if "medicine_ball" in exercise_tags or "explosive" in exercise_tags:
            score = score_map["Rotational Med Ball Throw"]
        else:
            score = score_map["Landmine Press"]
        return score, {"final_score": score}
    monkeypatch.setattr(
        strength,
        "score_exercise",
        _score,
    )

    result = generate_strength_block(
        flags={
            "phase": "SPP",
            "fatigue": "moderate",
            "equipment": ["landmine", "medicine_ball"],
            "fight_format": "boxing",
            "training_days": ["Mon", "Thu"],
            "training_frequency": 2,
            "key_goals": [],
            "style_tactical": [],
        }
    )

    assert result["true_loaded_anchor_present"] is False
    assert result["loaded_anchor_limited"] is True
    assert "injury-limited" in result["loaded_anchor_note"].lower()
    assert "Loaded Anchor Status" in result["block"]
