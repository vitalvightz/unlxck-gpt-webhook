"""test_scoring_audit.py — Tests for the Scoring Audit / Selector Transparency Patch.

Verifies:
1. Audit output exists and is structurally consistent across modules.
2. Selected candidates include full breakdowns.
3. Rejected top candidates include full breakdowns.
4. Constants / multipliers snapshot is populated.
5. Hard-gated candidates are distinguishable from penalized candidates.
6. Debug mode does not change normal selection behaviour.
7. Side-by-side comparison helper reports correct delta values.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from fightcamp.scoring_audit import (
    SCORING_CONSTANTS,
    build_audit_reservoir,
    build_candidate_audit,
    build_debug_report,
    compare_candidates,
    get_constants_snapshot,
    score_deltas,
)
from fightcamp.strength import generate_strength_block
from fightcamp.conditioning import generate_conditioning_block


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_STRENGTH_FLAGS = {
    "phase": "GPP",
    "fatigue": "low",
    "style_technical": ["mma"],
    "style_tactical": ["brawler"],
    "key_goals": ["strength"],
    "weaknesses": ["posterior_chain"],
    "injuries": [],
    "equipment": ["barbell", "bodyweight"],
    "training_frequency": 3,
    "fight_format": "mma",
}

MINIMAL_CONDITIONING_FLAGS = {
    "phase": "GPP",
    "fatigue": "low",
    "style_technical": ["mma"],
    "style_tactical": ["brawler"],
    "key_goals": ["conditioning"],
    "weaknesses": ["gas_tank"],
    "injuries": [],
    "equipment": ["bodyweight", "assault_bike"],
    "training_frequency": 3,
    "fight_format": "mma",
    "sport": "mma",
}


def _make_audit(**overrides):
    """Return a minimal audit record with optional field overrides."""
    base = dict(
        name="Dummy Exercise",
        module="strength",
        final_score=1.5,
        selected=False,
    )
    base.update(overrides)
    return build_candidate_audit(**base)


# ---------------------------------------------------------------------------
# 1. Audit schema structure is consistent across modules
# ---------------------------------------------------------------------------

REQUIRED_AUDIT_KEYS = {
    "name", "module", "system", "category", "tags", "cluster_ids",
    "base_score", "goal_score", "weakness_score", "style_score",
    "cluster_score", "quality_adjustment",
    "support_flag_adjustment", "restriction_penalty", "fallback_penalty",
    "constraint_adjustment", "injury_guard_adjustment",
    "fallback_class", "constraint_state", "injury_decision",
    "reasons",
    "positive_total", "negative_total", "net_score",
    "final_score", "selected", "selection_stage", "rejection_reason",
}


def test_audit_schema_has_all_required_keys_strength():
    audit = _make_audit(module="strength")
    assert REQUIRED_AUDIT_KEYS.issubset(audit.keys()), (
        f"Missing keys: {REQUIRED_AUDIT_KEYS - audit.keys()}"
    )


def test_audit_schema_has_all_required_keys_conditioning():
    audit = _make_audit(module="conditioning")
    assert REQUIRED_AUDIT_KEYS.issubset(audit.keys())


def test_audit_schema_has_all_required_keys_coordination():
    audit = _make_audit(module="coordination")
    assert REQUIRED_AUDIT_KEYS.issubset(audit.keys())


def test_audit_schema_field_types():
    audit = _make_audit(
        name="Romanian Deadlift",
        module="strength",
        tags=["posterior_chain", "hinge"],
        cluster_ids=["C1"],
        goal_score=0.5,
        weakness_score=1.2,
        style_score=0.3,
        final_score=2.0,
        selected=True,
        rejection_reason="",
    )
    assert isinstance(audit["name"], str)
    assert isinstance(audit["tags"], list)
    assert isinstance(audit["cluster_ids"], list)
    assert isinstance(audit["final_score"], float)
    assert isinstance(audit["selected"], bool)
    assert isinstance(audit["reasons"], dict)
    assert isinstance(audit["positive_total"], float)
    assert isinstance(audit["negative_total"], float)
    assert isinstance(audit["net_score"], float)


# ---------------------------------------------------------------------------
# 2. Selected candidates include full breakdowns
# ---------------------------------------------------------------------------

def test_strength_debug_mode_returns_audit_key():
    flags = {**MINIMAL_STRENGTH_FLAGS, "debug_scoring": True}
    result = generate_strength_block(flags=flags)
    assert "audit" in result, "debug_scoring=True must produce 'audit' key in result"


def test_strength_audit_has_selected_candidates():
    flags = {**MINIMAL_STRENGTH_FLAGS, "debug_scoring": True}
    result = generate_strength_block(flags=flags)
    reservoir = result["audit"]["reservoir"]
    assert "selected" in reservoir
    # Every selected audit record must have all required keys
    for rec in reservoir["selected"]:
        assert REQUIRED_AUDIT_KEYS.issubset(rec.keys()), (
            f"Selected record missing keys: {REQUIRED_AUDIT_KEYS - rec.keys()}"
        )
        assert rec["selected"] is True


def test_conditioning_debug_mode_returns_audit():
    flags = {**MINIMAL_CONDITIONING_FLAGS, "debug_scoring": True}
    *_, audit = generate_conditioning_block(flags)
    assert audit is not None, "debug_scoring=True must produce non-None audit"
    assert "reservoir" in audit
    assert "constants" in audit
    assert "module" in audit
    assert "phase" in audit


def test_conditioning_audit_selected_records_are_complete():
    flags = {**MINIMAL_CONDITIONING_FLAGS, "debug_scoring": True}
    *_, audit = generate_conditioning_block(flags)
    for rec in audit["reservoir"]["selected"]:
        assert REQUIRED_AUDIT_KEYS.issubset(rec.keys())
        assert rec["selected"] is True


# ---------------------------------------------------------------------------
# 3. Rejected top candidates include full breakdowns
# ---------------------------------------------------------------------------

def test_strength_audit_has_rejected_candidates():
    flags = {**MINIMAL_STRENGTH_FLAGS, "debug_scoring": True}
    result = generate_strength_block(flags=flags)
    reservoir = result["audit"]["reservoir"]
    # There should be rejected candidates available (bank is large enough)
    rejected = reservoir.get("rejected_top", [])
    assert isinstance(rejected, list)
    for rec in rejected:
        assert REQUIRED_AUDIT_KEYS.issubset(rec.keys()), (
            f"Rejected record missing keys: {REQUIRED_AUDIT_KEYS - rec.keys()}"
        )
        assert rec["selected"] is False


def test_conditioning_audit_has_rejected_candidates():
    flags = {**MINIMAL_CONDITIONING_FLAGS, "debug_scoring": True}
    *_, audit = generate_conditioning_block(flags)
    rejected = audit["reservoir"].get("rejected_top", [])
    assert isinstance(rejected, list)
    for rec in rejected:
        assert REQUIRED_AUDIT_KEYS.issubset(rec.keys())
        assert rec["selected"] is False


def test_audit_reservoir_top_n_limit():
    """Reservoir should not return more than top_n records."""
    items = [
        ({"name": f"Drill{i}", "tags": [], "cluster_ids": []}, float(i), {})
        for i in range(20)
    ]
    selected = {"Drill19"}
    res = build_audit_reservoir(items, selected, module="conditioning", top_n=10)
    assert len(res["selected"]) + len(res["rejected_top"]) <= 10


# ---------------------------------------------------------------------------
# 4. Constants / multipliers snapshot is populated
# ---------------------------------------------------------------------------

def test_scoring_constants_contains_top_level_modules():
    assert "strength" in SCORING_CONSTANTS
    assert "conditioning" in SCORING_CONSTANTS
    assert "fallback_class_penalties" in SCORING_CONSTANTS
    assert "coordination" in SCORING_CONSTANTS


def test_scoring_constants_strength_weights():
    st = SCORING_CONSTANTS["strength"]
    assert "weakness_weight" in st
    assert "goal_weight" in st
    assert "style_weight" in st
    assert "cluster_bonus_per_hit" in st
    assert st["weakness_weight"] > 0


def test_scoring_constants_conditioning_weights():
    cond = SCORING_CONSTANTS["conditioning"]
    assert "primary_weakness_weight" in cond
    assert "primary_goal_weight" in cond
    assert "cluster_bonus_per_hit" in cond
    assert cond["primary_weakness_weight"] > 0


def test_scoring_constants_fallback_penalties():
    fp = SCORING_CONSTANTS["fallback_class_penalties"]
    assert fp["normal"] == 0.0
    assert fp["downranked"] < 0
    assert fp["last_resort"] < fp["downranked"]
    assert fp["blocked_for_profile"] <= -999.0


def test_get_constants_snapshot_returns_copy():
    snap1 = get_constants_snapshot()
    snap2 = get_constants_snapshot()
    # Mutating one copy should not affect the other
    snap1["strength"]["weakness_weight"] = 999
    assert snap2["strength"]["weakness_weight"] != 999


def test_debug_report_includes_constants():
    flags = {**MINIMAL_STRENGTH_FLAGS, "debug_scoring": True}
    result = generate_strength_block(flags=flags)
    constants = result["audit"]["constants"]
    assert "strength" in constants
    assert "conditioning" in constants
    assert "fallback_class_penalties" in constants


# ---------------------------------------------------------------------------
# 5. Hard-gated vs penalised candidates are distinguishable
# ---------------------------------------------------------------------------

def test_hard_gate_vs_penalised_in_reservoir():
    """Hard-gated items appear in gate_excluded; penalised items appear in
    rejected_top with a non-zero restriction_penalty or fallback_penalty."""
    gate_ex = [{"name": "GatedExercise", "gate_reason": "sport_context_failed"}]
    penalised = (
        {"name": "PenalisedDrill", "tags": [], "cluster_ids": []},
        1.5,
        {"restriction_hits": 2, "restrictions_penalty": -0.75, "fallback_class": "downranked",
         "penalties": -1.25, "final_score": 0.25},
    )
    normal = (
        {"name": "NormalDrill", "tags": [], "cluster_ids": []},
        3.0,
        {"fallback_class": "normal", "penalties": 0.0, "final_score": 3.0},
    )
    selected = {"NormalDrill"}
    res = build_audit_reservoir(
        [normal, penalised],
        selected,
        module="strength",
        top_n=10,
        gate_excluded=gate_ex,
    )

    # Gate-excluded items are stored separately, not in scored lists
    assert len(res["gate_excluded"]) == 1
    assert res["gate_excluded"][0]["name"] == "GatedExercise"
    assert res["gate_excluded"][0]["gate_reason"] == "sport_context_failed"

    # Penalised item should be in rejected_top
    rejected_names = {r["name"] for r in res["rejected_top"]}
    assert "PenalisedDrill" in rejected_names


def test_injury_excluded_distinguished_from_scored():
    injury_ex = [{"name": "InjuryExcluded", "region": "shoulder"}]
    normal = (
        {"name": "SafeDrill", "tags": [], "cluster_ids": []},
        2.0,
        {"fallback_class": "normal", "penalties": 0.0, "final_score": 2.0},
    )
    res = build_audit_reservoir(
        [normal],
        {"SafeDrill"},
        module="conditioning",
        top_n=10,
        injury_excluded=injury_ex,
    )
    assert res["injury_excluded"][0]["name"] == "InjuryExcluded"
    assert res["injury_excluded"][0]["region"] == "shoulder"


def test_restriction_blocked_stored_separately():
    blocked = [{"name": "BlockedExercise", "match": {"restriction": "high_impact"}, "risk": 0.9}]
    res = build_audit_reservoir(
        [],
        set(),
        module="strength",
        top_n=10,
        restriction_blocked=blocked,
    )
    assert res["restriction_blocked"][0]["name"] == "BlockedExercise"


# ---------------------------------------------------------------------------
# 6. Debug mode does not change normal selection behaviour
# ---------------------------------------------------------------------------

def test_strength_debug_mode_does_not_change_exercises():
    """Exercises selected with and without debug_scoring should be identical."""
    flags_nodebug = dict(MINIMAL_STRENGTH_FLAGS)
    # Use a deterministic seed so noise doesn't affect comparison
    flags_nodebug["random_seed"] = 42
    flags_debug = {**flags_nodebug, "debug_scoring": True}

    result_nodebug = generate_strength_block(flags=flags_nodebug)
    result_debug = generate_strength_block(flags=flags_debug)

    names_nodebug = [ex.get("name") for ex in result_nodebug.get("exercises", [])]
    names_debug = [ex.get("name") for ex in result_debug.get("exercises", [])]
    assert names_nodebug == names_debug, (
        f"Debug mode changed exercise selection:\n  nodebug={names_nodebug}\n  debug={names_debug}"
    )


def test_conditioning_debug_mode_does_not_change_drills():
    """Drills selected with and without debug_scoring should be identical."""
    base_flags = {**MINIMAL_CONDITIONING_FLAGS, "random_seed": 42}
    flags_nodebug = dict(base_flags)
    flags_debug = {**base_flags, "debug_scoring": True}

    *rest_nodebug, audit_nodebug = generate_conditioning_block(flags_nodebug)
    *rest_debug, audit_debug = generate_conditioning_block(flags_debug)

    # Position 1 in return tuple is selected_drill_names
    names_nodebug = rest_nodebug[1]
    names_debug = rest_debug[1]
    assert names_nodebug == names_debug, (
        f"Debug mode changed drill selection:\n  nodebug={names_nodebug}\n  debug={names_debug}"
    )

    # Without debug flag: audit must be None
    assert audit_nodebug is None

    # With debug flag: audit must be populated
    assert audit_debug is not None


def test_audit_selector_alias_also_works():
    """audit_selector=True is an alias for debug_scoring=True."""
    flags = {**MINIMAL_STRENGTH_FLAGS, "audit_selector": True}
    result = generate_strength_block(flags=flags)
    assert "audit" in result


# ---------------------------------------------------------------------------
# 7. Score-delta helpers and comparison utilities
# ---------------------------------------------------------------------------

def test_score_deltas_returns_correct_values():
    audit = build_candidate_audit(
        name="Test",
        module="strength",
        goal_score=1.0,
        weakness_score=2.0,
        restriction_penalty=-0.5,
        final_score=2.5,
        selected=True,
    )
    deltas = score_deltas(audit)
    assert deltas["positive_total"] > 0
    assert deltas["negative_total"] <= 0
    assert deltas["final_score"] == pytest.approx(2.5)
    assert deltas["net_score"] == pytest.approx(audit["net_score"])


def test_score_deltas_positive_and_negative_totals():
    audit = build_candidate_audit(
        name="Heavily Penalised",
        module="strength",
        goal_score=3.0,
        weakness_score=2.0,
        restriction_penalty=-2.0,
        fallback_penalty=-1.25,
        final_score=1.75,
        selected=False,
    )
    assert audit["positive_total"] == pytest.approx(5.0)
    assert audit["negative_total"] == pytest.approx(-3.25)
    assert audit["net_score"] == pytest.approx(1.75)


def test_compare_candidates_winner_identified():
    audit_a = build_candidate_audit(
        name="Exercise A", module="strength", final_score=3.0, selected=True
    )
    audit_b = build_candidate_audit(
        name="Exercise B", module="strength", final_score=1.5, selected=False
    )
    comparison = compare_candidates(audit_a, audit_b)
    assert comparison["winner"] == "Exercise A"
    assert comparison["loser"] == "Exercise B"
    assert "final_score" in comparison["score_components"]


def test_compare_candidates_tie():
    audit_a = build_candidate_audit(name="X", module="strength", final_score=2.0)
    audit_b = build_candidate_audit(name="Y", module="strength", final_score=2.0)
    comparison = compare_candidates(audit_a, audit_b)
    assert comparison["winner"] == "tie"


def test_compare_candidates_score_component_delta():
    audit_a = build_candidate_audit(
        name="Strong Goal Match",
        module="conditioning",
        goal_score=2.1,
        weakness_score=0.0,
        final_score=2.1,
    )
    audit_b = build_candidate_audit(
        name="Strong Weakness Match",
        module="conditioning",
        goal_score=0.0,
        weakness_score=2.75,
        final_score=2.75,
    )
    comparison = compare_candidates(audit_a, audit_b)
    # goal_score should differ
    assert "goal_score" in comparison["score_components"]
    assert comparison["score_components"]["goal_score"]["delta"] == pytest.approx(2.1)
    # weakness_score should differ
    assert "weakness_score" in comparison["score_components"]
    assert comparison["score_components"]["weakness_score"]["delta"] == pytest.approx(-2.75)


def test_compare_candidates_all_components_included():
    audit_a = build_candidate_audit(name="A", module="strength")
    audit_b = build_candidate_audit(name="B", module="strength")
    comparison = compare_candidates(audit_a, audit_b)
    # all_components must contain every numeric audit field
    from fightcamp.scoring_audit import _AUDIT_NUMERIC_FIELDS
    for field in _AUDIT_NUMERIC_FIELDS:
        assert field in comparison["all_components"]


def test_compare_candidates_classification_fields():
    audit_a = build_candidate_audit(
        name="Safe",
        module="strength",
        fallback_class="normal",
        injury_decision="pass",
        final_score=2.0,
    )
    audit_b = build_candidate_audit(
        name="Risky",
        module="strength",
        fallback_class="downranked",
        injury_decision="pass",
        final_score=0.75,
    )
    comparison = compare_candidates(audit_a, audit_b)
    assert comparison["classification"]["fallback_class"]["a"] == "normal"
    assert comparison["classification"]["fallback_class"]["b"] == "downranked"
    assert comparison["classification"]["fallback_class"]["same"] == "False"


# ---------------------------------------------------------------------------
# Integration: full debug report structure
# ---------------------------------------------------------------------------

def test_debug_report_structure_strength():
    flags = {**MINIMAL_STRENGTH_FLAGS, "debug_scoring": True}
    result = generate_strength_block(flags=flags)
    audit = result["audit"]
    assert audit["module"] == "strength"
    assert audit["phase"] == "GPP"
    assert isinstance(audit["constants"], dict)
    assert isinstance(audit["reservoir"], dict)


def test_debug_report_structure_conditioning():
    flags = {**MINIMAL_CONDITIONING_FLAGS, "debug_scoring": True}
    *_, audit = generate_conditioning_block(flags)
    assert audit["module"] == "conditioning"
    assert audit["phase"] == "GPP"
    assert isinstance(audit["constants"], dict)
    assert isinstance(audit["reservoir"], dict)


def test_reservoir_module_field_matches():
    flags = {**MINIMAL_STRENGTH_FLAGS, "debug_scoring": True}
    result = generate_strength_block(flags=flags)
    reservoir = result["audit"]["reservoir"]
    assert reservoir["module"] == "strength"

    flags_c = {**MINIMAL_CONDITIONING_FLAGS, "debug_scoring": True}
    *_, audit_c = generate_conditioning_block(flags_c)
    assert audit_c["reservoir"]["module"] == "conditioning"


def test_reservoir_total_scored_field():
    """total_scored should be >= number of selected + rejected candidates."""
    flags = {**MINIMAL_STRENGTH_FLAGS, "debug_scoring": True}
    result = generate_strength_block(flags=flags)
    res = result["audit"]["reservoir"]
    counted = len(res["selected"]) + len(res["rejected_top"])
    assert res["total_scored"] >= counted


# ---------------------------------------------------------------------------
# build_candidate_audit edge cases
# ---------------------------------------------------------------------------

def test_audit_negative_quality_adjustment_goes_to_negative_total():
    audit = build_candidate_audit(
        name="Rehab Support",
        module="strength",
        quality_adjustment=-0.5,
    )
    assert audit["negative_total"] <= -0.5
    assert audit["positive_total"] == 0.0


def test_audit_positive_quality_adjustment_goes_to_positive_total():
    audit = build_candidate_audit(
        name="Anchor Loaded",
        module="strength",
        quality_adjustment=0.75,
    )
    assert audit["positive_total"] >= 0.75
    assert audit["negative_total"] == 0.0
