from fightcamp.session_restraint import NEAR_EQUAL_SCORE_BAND, sort_weighted_candidates
from fightcamp import strength


def _names(candidates: list[dict]) -> list[str]:
    return [candidate["name"] for candidate in candidates]


def test_exact_default_band_boundary_is_included_in_leader_group():
    ordered = sort_weighted_candidates(
        [
            {"name": "Leader", "score": 10.0, "fatigue_cost": 4},
            {"name": "Boundary", "score": 9.85, "fatigue_cost": 1},
        ],
        near_equal_score_band=NEAR_EQUAL_SCORE_BAND,
    )

    assert _names(ordered) == ["Boundary", "Leader"]


def test_just_outside_default_band_starts_a_new_group():
    ordered = sort_weighted_candidates(
        [
            {"name": "Leader", "score": 10.0, "fatigue_cost": 4},
            {"name": "Outside", "score": 9.84, "fatigue_cost": 0},
        ],
        near_equal_score_band=NEAR_EQUAL_SCORE_BAND,
    )

    assert _names(ordered) == ["Leader", "Outside"]


def test_grouping_is_leader_anchored_under_custom_wider_band_not_chain_based():
    ordered = sort_weighted_candidates(
        [
            {"name": "A", "score": 10.00, "fatigue_cost": 4},
            {"name": "B", "score": 9.85, "fatigue_cost": 3},
            {"name": "C", "score": 9.81, "fatigue_cost": 1},
            {"name": "D", "score": 9.79, "fatigue_cost": 0},
        ],
        # Wider custom band keeps this focused on the leader-anchored grouping rule.
        near_equal_score_band=0.2,
    )

    assert _names(ordered) == ["C", "B", "A", "D"]


def test_lower_fatigue_can_overtake_slightly_higher_score_within_group_under_custom_band():
    ordered = sort_weighted_candidates(
        [
            {"name": "HigherScore", "score": 8.5, "fatigue_cost": 5},
            {"name": "LowerFatigue", "score": 8.45, "fatigue_cost": 1},
            {"name": "Middle", "score": 8.41, "fatigue_cost": 3},
        ],
        near_equal_score_band=0.1,
    )

    assert _names(ordered) == ["LowerFatigue", "Middle", "HigherScore"]


def test_cross_group_order_remains_score_driven_after_local_reordering_with_default_band():
    ordered = sort_weighted_candidates(
        [
            {"name": "Group1High", "score": 10.0, "fatigue_cost": 5},
            {"name": "Group1LowFatigue", "score": 9.9, "fatigue_cost": 1},
            {"name": "Group2High", "score": 9.6, "fatigue_cost": 0},
            {"name": "Group2Low", "score": 9.45, "fatigue_cost": 2},
        ],
        near_equal_score_band=NEAR_EQUAL_SCORE_BAND,
    )

    assert _names(ordered) == ["Group1LowFatigue", "Group1High", "Group2High", "Group2Low"]


def test_name_fallback_is_stable_for_equal_score_and_fatigue_with_default_band():
    ordered = sort_weighted_candidates(
        [
            {"name": "Zulu", "score": 7.0, "fatigue_cost": 2},
            {"name": "Alpha", "score": 7.0, "fatigue_cost": 2},
            {"name": "Mike", "score": 7.0, "fatigue_cost": 2},
        ],
        near_equal_score_band=NEAR_EQUAL_SCORE_BAND,
    )

    assert _names(ordered) == ["Alpha", "Mike", "Zulu"]


def test_generate_strength_block_uses_derived_fatigue_cost_for_live_near_equal_ordering(monkeypatch):
    exercise_bank = [
        {
            "name": "Heavy Pull",
            "phases": ["SPP"],
            "tags": ["Heavy Pull", "compound", "posterior_chain", "hinge", "high_volume"],
            "equipment": ["barbell"],
            "movement": "hinge",
        },
        {
            "name": "Snap Down",
            "phases": ["SPP"],
            "tags": ["Snap Down", "explosive", "hinge"],
            "equipment": [],
            "movement": "hinge",
        },
        {
            "name": "Later Group",
            "phases": ["SPP"],
            "tags": ["Later Group", "hinge"],
            "equipment": [],
            "movement": "hinge",
        },
    ]
    score_map = {"Heavy Pull": 10.0, "Snap Down": 9.95, "Later Group": 9.7}

    monkeypatch.setattr(strength, "get_exercise_bank", lambda: exercise_bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_args, **_kwargs: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"strength": 3})
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (score_map[kwargs["exercise_tags"][0]], {"final_score": score_map[kwargs["exercise_tags"][0]]}),
    )

    result = strength.generate_strength_block(
        flags={
            "phase": "SPP",
            "fatigue": "low",
            "equipment": ["barbell"],
            "fight_format": "mma",
            "training_days": ["Mon", "Wed"],
            "training_frequency": 2,
            "key_goals": [],
            "style_tactical": [],
        }
    )

    hinge_reservoir = result["candidate_reservoir"]["hinge"]
    assert [entry["exercise"]["name"] for entry in hinge_reservoir[:3]] == [
        "Snap Down",
        "Heavy Pull",
        "Later Group",
    ]
    assert hinge_reservoir[0]["reasons"]["fatigue_cost"] < hinge_reservoir[1]["reasons"]["fatigue_cost"]
    assert score_map["Heavy Pull"] - score_map["Snap Down"] <= NEAR_EQUAL_SCORE_BAND
    assert score_map["Heavy Pull"] - score_map["Later Group"] > NEAR_EQUAL_SCORE_BAND
