from __future__ import annotations

from fightcamp.tag_maps import GOAL_NORMALIZER, GOAL_TAG_MAP, STYLE_TAG_MAP, WEAKNESS_NORMALIZER, WEAKNESS_TAG_MAP
from fightcamp.tagging import load_tag_vocabulary, normalize_item_tags, normalize_tag, normalize_tags


def test_normalize_tags_canonicalizes_synonyms_and_removes_duplicates():
    normalized = normalize_tags([
        "Muay Thai",
        "muay-thai",
        "pressure fighter",
        "pressure_fighter",
        "decision speed",
        "Decision Speed",
    ])

    assert normalized == ["muay_thai", "pressure_fighter", "reactive"]


def test_normalize_tags_maps_legacy_drill_tags_to_scoring_vocab():
    normalized = normalize_tags(["boxer", "breathing", "technical", "rhythm"])

    assert normalized == ["boxing", "recovery", "skill", "coordination"]


def test_normalize_item_tags_mutates_item_with_canonical_tags():
    item = {"tags": ["skill refinement", "counter striker", "counter_striker"]}

    normalized = normalize_item_tags(item)

    assert normalized == ["skill_refinement", "counter_striker"]
    assert item["tags"] == normalized


def test_selected_goal_aliases_resolve_to_supported_goal_entries():
    vocabulary = load_tag_vocabulary()

    for alias in [
        "Skill Refinement",
        "Coordination / Proprioception",
        "Grappling",
        "Striking",
        "Injury Prevention",
        "Mental Resilience",
    ]:
        canonical = GOAL_NORMALIZER[alias]
        assert canonical in GOAL_TAG_MAP or canonical in vocabulary


def test_weakness_aliases_resolve_to_existing_canonical_weakness_entries():
    vocabulary = load_tag_vocabulary()

    for alias, canonical_entries in WEAKNESS_NORMALIZER.items():
        for canonical in canonical_entries:
            assert canonical in WEAKNESS_TAG_MAP or canonical in vocabulary


def test_trunk_strength_alias_resolves_to_live_core_stability_tags():
    assert WEAKNESS_NORMALIZER["trunk_strength"] == ["trunk_strength"]
    assert WEAKNESS_TAG_MAP["trunk_strength"] == ["core", "anti_rotation", "stability"]
    assert WEAKNESS_NORMALIZER["trunk strength"] == ["core stability"]
    assert WEAKNESS_TAG_MAP["core stability"] == ["core", "anti_rotation"]


def test_current_ui_performance_values_resolve_to_live_scoring_tags():
    key_goal_required_tags = {
        "power": {"rate_of_force", "plyometric"},
        "strength": {"posterior_chain", "upper_body"},
        "conditioning": {"aerobic", "glycolytic", "work_capacity"},
        "speed": {"speed", "reactive"},
        "skill_refinement": {"skill_refinement", "coordination", "cognitive"},
        "mobility": {"mobility", "movement_quality", "stability"},
        "recovery": {"recovery", "cns_freshness", "parasympathetic"},
        "weight_cut": {"recovery", "low_impact", "cns_freshness"},
    }
    weak_area_required_tags = {
        "gas_tank": {"aerobic", "glycolytic", "conditioning", "work_capacity"},
        "strength": {"posterior_chain", "quad_dominant", "upper_body", "core"},
        "power": {"explosive", "rate_of_force", "plyometric"},
        "speed": {"speed", "reaction", "reactive", "coordination"},
        "footwork": {
            "footwork",
            "lateral",
            "lateral_movement",
            "ringcraft",
            "angles",
            "pivot",
            "stance",
            "stance_reset",
            "angle_exit",
            "movement_quality",
            "coordination",
        },
        "balance": {"balance", "stability", "unilateral"},
        "mobility": {"mobility", "hip_dominant", "movement_quality"},
        "coordination": {"coordination", "balance", "reactive"},
        "trunk_strength": {"core", "anti_rotation", "stability"},
    }

    for value, required_tags in key_goal_required_tags.items():
        canonical = GOAL_NORMALIZER.get(value, value)
        assert required_tags.issubset(set(GOAL_TAG_MAP[canonical]))

    for value, required_tags in weak_area_required_tags.items():
        canonical_entries = WEAKNESS_NORMALIZER.get(value, [value])
        assert canonical_entries
        resolved_tags = {tag for canonical in canonical_entries for tag in WEAKNESS_TAG_MAP[canonical]}
        assert required_tags.issubset(resolved_tags)


def test_footwork_does_not_leak_into_speed_tags():
    assert "footwork" not in GOAL_TAG_MAP["speed"]
    assert "speed" not in WEAKNESS_TAG_MAP["footwork"]
    assert "reactive" not in WEAKNESS_TAG_MAP["footwork"]


def test_goal_tag_aliases_use_copied_scoring_routes():
    assert GOAL_TAG_MAP["conditioning"] == GOAL_TAG_MAP["endurance"]
    assert GOAL_TAG_MAP["conditioning"] is not GOAL_TAG_MAP["endurance"]
    assert GOAL_TAG_MAP["explosive"] == GOAL_TAG_MAP["power"]
    assert GOAL_TAG_MAP["explosive"] is not GOAL_TAG_MAP["power"]
    assert GOAL_TAG_MAP["reactive"] == GOAL_TAG_MAP["speed"]
    assert GOAL_TAG_MAP["reactive"] is not GOAL_TAG_MAP["speed"]


def test_style_and_goal_tags_stay_normalized_for_curated_entries():
    sample_tags = (
        STYLE_TAG_MAP["pressure fighter"]
        + STYLE_TAG_MAP["distance striker"]
        + GOAL_TAG_MAP["skill_refinement"]
        + WEAKNESS_TAG_MAP["coordination / proprioception"]
    )

    for tag in sample_tags:
        assert normalize_tag(tag) == tag.lower().replace("-", "_").replace(" ", "_")
