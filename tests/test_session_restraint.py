import inspect

from fightcamp.session_restraint import sort_weighted_candidates


def _names(candidates):
    return [candidate["name"] for candidate in candidates]


def test_higher_scored_candidates_stay_ahead_across_groups():
    ordered = sort_weighted_candidates(
        [
            {"name": "Gamma", "score": 9.0, "fatigue_cost": 5},
            {"name": "Alpha", "score": 8.55, "fatigue_cost": 1},
            {"name": "Beta", "score": 8.1, "fatigue_cost": 0},
        ],
        near_equal_score_band=0.2,
    )

    assert _names(ordered) == ["Gamma", "Alpha", "Beta"]


def test_near_equal_group_prefers_lower_fatigue_cost():
    ordered = sort_weighted_candidates(
        [
            {"name": "Alpha", "score": 8.5, "fatigue_cost": 4},
            {"name": "Beta", "score": 8.45, "fatigue_cost": 1},
            {"name": "Gamma", "score": 8.41, "fatigue_cost": 2},
        ],
        near_equal_score_band=0.1,
    )

    assert _names(ordered) == ["Beta", "Gamma", "Alpha"]


def test_name_fallback_is_stable_for_equal_score_and_fatigue():
    ordered = sort_weighted_candidates(
        [
            {"name": "Zulu", "score": 7.0, "fatigue_cost": 2},
            {"name": "Alpha", "score": 7.0, "fatigue_cost": 2},
            {"name": "Mike", "score": 7.0, "fatigue_cost": 2},
        ],
        near_equal_score_band=0.2,
    )

    assert _names(ordered) == ["Alpha", "Mike", "Zulu"]


def test_rule_2_uses_grouping_not_pairwise_comparator():
    source = inspect.getsource(sort_weighted_candidates)

    assert "cmp_to_key" not in source
    assert "sorted(group" in source
    assert "group" in source
