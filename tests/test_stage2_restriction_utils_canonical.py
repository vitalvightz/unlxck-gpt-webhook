"""Canonical Stage 2 restriction-helper tests.

These guard against future drift between `stage2_payload`,
`stage2_planning_brief`, and `stage2_restriction_utils`. There must be
exactly one real implementation of restriction/mechanical-tag helpers,
and the tag vocabulary must stay aligned with the rest of the codebase
(``injury_filtering``, ``injury_guard``, ``injury_exclusion_rules`` all
read ``"cervical_load"`` and ``"cod_high"``).
"""
from __future__ import annotations

from fightcamp import stage2_payload
from fightcamp import stage2_planning_brief
from fightcamp import stage2_restriction_utils


# ── Identity ────────────────────────────────────────────────────────────────


def test_extract_restriction_tags_is_canonical_across_modules():
    assert (
        stage2_payload._extract_restriction_tags
        is stage2_planning_brief._extract_restriction_tags
        is stage2_restriction_utils._extract_restriction_tags
    )


def test_extract_mechanical_risk_tags_is_canonical_across_modules():
    assert (
        stage2_payload._extract_mechanical_risk_tags
        is stage2_planning_brief._extract_mechanical_risk_tags
        is stage2_restriction_utils._extract_mechanical_risk_tags
    )


def test_serialize_restrictions_is_canonical_across_modules():
    assert (
        stage2_payload._serialize_restrictions
        is stage2_planning_brief._serialize_restrictions
        is stage2_restriction_utils._serialize_restrictions
    )


def test_restriction_constants_are_canonical_across_modules():
    for name in (
        "RESTRICTION_PATTERN_HINTS",
        "_RESTRICTION_CANONICAL_KEYS",
        "_MECHANICAL_TAGS",
        "_MECHANICAL_TAG_PREFIXES",
    ):
        canonical = getattr(stage2_restriction_utils, name)
        assert getattr(stage2_payload, name) is canonical, name
        assert getattr(stage2_planning_brief, name) is canonical, name


# ── Restriction-tag extraction behaviour ────────────────────────────────────


def test_extract_restriction_tags_overhead_press_phrase():
    item = {"name": "Barbell Overhead Press", "tags": ["press", "overhead"], "movement": ""}
    assert stage2_restriction_utils._extract_restriction_tags(item) == [
        "heavy_overhead_pressing",
        "overhead",
        "press",
    ]


def test_extract_restriction_tags_picks_up_text_derived_phrases():
    """Phrases inside text fields drive restriction-tag extraction even when
    explicit tags aren't supplied."""
    item = {"name": "Bulgarian Split Squat", "tags": [], "movement": ""}
    assert "deep_knee_flexion" in stage2_restriction_utils._extract_restriction_tags(item)


# ── Mechanical-risk tag behaviour ───────────────────────────────────────────


def test_extract_mechanical_risk_tags_high_impact_plyometric():
    item = {"name": "Depth Jump", "tags": ["plyometric", "high_impact_plyo"], "movement": ""}
    assert stage2_restriction_utils._extract_mechanical_risk_tags(item) == [
        "high_impact",
        "high_impact_lower",
        "high_impact_plyo",
        "plyometric",
    ]


def test_extract_mechanical_risk_tags_uses_canonical_neck_and_cod_names():
    """`cervical_load` and `cod_high` are the canonical tag names — the rest
    of the codebase reads these. Stage 2 must emit them, not the previous
    stage2_payload variants `cervical_loading` / `change_of_direction`."""
    neck_tags = stage2_restriction_utils._extract_mechanical_risk_tags(
        {"name": "Neck Bridge", "tags": ["neck_bridge", "cervical_load"], "movement": ""}
    )
    assert "cervical_load" in neck_tags
    assert "cervical_loading" not in neck_tags

    cod_tags = stage2_restriction_utils._extract_mechanical_risk_tags(
        {"name": "Pro Agility", "tags": ["cod_high"], "movement": ""}
    )
    assert "cod_high" in cod_tags
    assert "change_of_direction" not in cod_tags


# ── Serialization behaviour ─────────────────────────────────────────────────


def test_serialize_restrictions_emits_blocked_patterns_and_mechanical_equivalents():
    serialized = stage2_restriction_utils._serialize_restrictions(
        [
            {
                "restriction": "deep_knee_flexion",
                "region": "knee",
                "side": "left",
                "original_phrase": "left knee",
            }
        ]
    )
    assert len(serialized) == 1
    row = serialized[0]
    assert row["restriction"] == "deep_knee_flexion"
    assert row["region"] == "knee"
    assert row["side"] == "left"
    assert row["source_phrase"] == "left knee"
    assert row["blocked_patterns"][:5] == [
        "deep bilateral squat",
        "full ROM lunge",
        "split squat",
        "rear-foot-elevated split squat",
        "deep knee-dominant step-up",
    ]
    # mechanical_equivalents is the first 6 of blocked_patterns
    assert row["mechanical_equivalents"] == row["blocked_patterns"][:6]


def test_serialize_restrictions_drops_empty_or_none_fields():
    serialized = stage2_restriction_utils._serialize_restrictions(
        [
            {
                "restriction": "max_velocity",
                "region": None,
                "side": "",
                "original_phrase": "max sprint",
            }
        ]
    )
    row = serialized[0]
    assert "region" not in row
    assert "side" not in row
    assert row["source_phrase"] == "max sprint"


def test_serialize_restrictions_handles_empty_input():
    assert stage2_restriction_utils._serialize_restrictions([]) == []
    assert stage2_restriction_utils._serialize_restrictions(None) == []


# ── Backwards-compat imports ────────────────────────────────────────────────


def test_legacy_imports_still_work():
    """Existing call sites that imported from stage2_payload or
    stage2_planning_brief must continue to function unchanged."""
    from fightcamp.stage2_payload import (
        _extract_restriction_tags as payload_extract,
        _extract_mechanical_risk_tags as payload_mech,
        _serialize_restrictions as payload_serialize,
    )
    from fightcamp.stage2_planning_brief import (
        _extract_restriction_tags as brief_extract,
        _extract_mechanical_risk_tags as brief_mech,
        _serialize_restrictions as brief_serialize,
    )
    assert payload_extract is brief_extract is stage2_restriction_utils._extract_restriction_tags
    assert payload_mech is brief_mech is stage2_restriction_utils._extract_mechanical_risk_tags
    assert payload_serialize is brief_serialize is stage2_restriction_utils._serialize_restrictions
