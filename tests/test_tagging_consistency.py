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

    assert normalized == ["muay_thai", "pressure_fighter", "decision_speed"]


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


def test_trunk_strength_alias_resolves_to_core_stability_tags():
    assert WEAKNESS_NORMALIZER["trunk_strength"] == ["core stability"]
    assert WEAKNESS_TAG_MAP["core stability"] == ["core", "anti_rotation"]


def test_style_and_goal_tags_stay_normalized_for_curated_entries():
    sample_tags = (
        STYLE_TAG_MAP["pressure fighter"]
        + STYLE_TAG_MAP["distance striker"]
        + GOAL_TAG_MAP["skill_refinement"]
        + WEAKNESS_TAG_MAP["coordination / proprioception"]
    )

    for tag in sample_tags:
        assert normalize_tag(tag) == tag.lower().replace("-", "_").replace(" ", "_")
