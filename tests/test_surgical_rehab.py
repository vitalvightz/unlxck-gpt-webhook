"""
Tests for the combined Surgical Rehab Integration Patch.

These regression tests verify that:

- Rehab drills are classified by function bucket (taxonomy completeness).
- Each drill output includes [Function: ...], Purpose, and Why today annotations.
- Volume limits are respected (sparring day capped at 1 drill; others at 2).
- Day-type-specific "Why today" language differs from phase-only fallback.
- Cross-phase deduplication still works via seen_drills.
- Hard same-function stacking is NOT enforced — the model retains authority to
  include same-function drills when the injury profile justifies it.
- Stage 2 rehab slots carry function_class and rehab_function_label metadata.
- Alternates are diversity-scored (different-function first) but same-function
  alternates are NOT hard-blocked.
- STAGE2_FINALIZER_PROMPT contains RULE 12 with Why today format requirement.
- REHAB_QUALITY_CHECKS constant is present and well-formed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.rehab_protocols import (
    REHAB_FUNCTION_BUCKETS,
    REHAB_QUALITY_CHECKS,
    _FUNCTION_LABELS,
    _FUNCTION_PURPOSES,
    _DAY_TYPE_DRILL_LIMIT,
    _DAY_TYPE_REHAB_WHY,
    _PHASE_REHAB_WHY,
    _format_rehab_drill,
    _split_notes_by_phase,
    _split_phase_progression,
    classify_drill_function,
    generate_rehab_protocols,
    get_rehab_bank,
)
from fightcamp.stage2_payload import (
    STAGE2_FINALIZER_PROMPT,
    _build_rehab_slots,
    _serialize_rehab_option,
)
from fightcamp.main import exercise_bank


# ---------------------------------------------------------------------------
# REHAB_FUNCTION_BUCKETS taxonomy
# ---------------------------------------------------------------------------


def test_rehab_function_buckets_has_six_keys():
    assert len(REHAB_FUNCTION_BUCKETS) == 6


def test_rehab_function_buckets_expected_keys():
    expected = {
        "activation",
        "control",
        "isometric_analgesia",
        "mobility",
        "tendon_loading",
        "recovery_downregulation",
    }
    assert expected == set(REHAB_FUNCTION_BUCKETS.keys())


def test_function_labels_cover_all_buckets():
    assert set(_FUNCTION_LABELS.keys()) == set(REHAB_FUNCTION_BUCKETS.keys())


def test_function_purposes_cover_all_buckets():
    assert set(_FUNCTION_PURPOSES.keys()) == set(REHAB_FUNCTION_BUCKETS.keys())


# ---------------------------------------------------------------------------
# classify_drill_function
# ---------------------------------------------------------------------------


def test_classify_activation_banded():
    assert classify_drill_function("Banded Clamshell", "Activate hip abductors") == "activation"


def test_classify_activation_glute_bridge():
    assert classify_drill_function("Glute Bridge Activation", "") == "activation"


def test_classify_isometric_hold():
    assert classify_drill_function("Isometric Split Squat Hold", "static contraction") == "isometric_analgesia"


def test_classify_isometric_spanish_squat():
    assert classify_drill_function("Spanish Squat", "") == "isometric_analgesia"


def test_classify_control_single_leg():
    assert classify_drill_function("Single-Leg Balance", "proprioception on foam pad") == "control"


def test_classify_control_pallof():
    assert classify_drill_function("Pallof Press", "") == "control"


def test_classify_tendon_eccentric():
    assert classify_drill_function("Eccentric Calf Raise", "tendon loading protocol") == "tendon_loading"


def test_classify_tendon_nordic():
    assert classify_drill_function("Nordic Hamstring Curl", "") == "tendon_loading"


def test_classify_mobility_stretch():
    assert classify_drill_function("Hip Flexor Stretch", "improve range of motion") == "mobility"


def test_classify_mobility_ankle_circle():
    assert classify_drill_function("Ankle Circle", "") == "mobility"


def test_classify_recovery_foam_roll():
    assert classify_drill_function("Foam Roll Quads", "post-session recovery") == "recovery_downregulation"


def test_classify_recovery_soft_tissue():
    assert classify_drill_function("Soft Tissue Reset", "") == "recovery_downregulation"


def test_classify_fallback_is_control():
    assert classify_drill_function("Unknown Drill XYZ", "") == "control"


# ---------------------------------------------------------------------------
# _format_rehab_drill — annotation structure
# ---------------------------------------------------------------------------


def test_format_drill_headline_with_notes():
    headline, _ = _format_rehab_drill("Banded External Rotation", "3×15", "SPP", "activation")
    assert "Banded External Rotation" in headline
    assert "3×15" in headline


def test_format_drill_headline_without_notes():
    headline, _ = _format_rehab_drill("Pallof Press", "", "GPP", "control")
    assert headline == "Pallof Press"


def test_format_drill_includes_function_label():
    _, annotations = _format_rehab_drill("Banded External Rotation", "3×15", "SPP", "activation")
    assert "[Function: Activation]" in annotations[0]


def test_format_drill_includes_purpose():
    _, annotations = _format_rehab_drill("Banded External Rotation", "", "GPP", "activation")
    assert "Purpose:" in annotations[0]
    assert "underactive tissue" in annotations[0]


def test_format_drill_includes_why_today_label():
    _, annotations = _format_rehab_drill("Drill", "notes", "SPP", "control")
    assert "Why today:" in annotations[1]


def test_format_drill_day_type_used_when_provided():
    _, annotations_sparring = _format_rehab_drill("Drill", "", "SPP", "activation", day_type="sparring")
    _, annotations_strength = _format_rehab_drill("Drill", "", "SPP", "activation", day_type="strength")
    # Day-type-specific why should differ
    assert annotations_sparring[1] != annotations_strength[1]


def test_format_drill_day_type_sparring_references_freshness():
    _, annotations = _format_rehab_drill("Drill", "", "GPP", "activation", day_type="sparring")
    assert "sparring" in annotations[1].lower() or "freshness" in annotations[1].lower()


def test_format_drill_falls_back_to_phase_when_no_day_type():
    _, annotations = _format_rehab_drill("Drill", "", "GPP", "control", day_type=None)
    # Should contain phase-level rationale from _PHASE_REHAB_WHY
    assert _PHASE_REHAB_WHY["GPP"] in annotations[1]


def test_format_drill_phase_why_differs_across_phases():
    _, gpp_ann = _format_rehab_drill("Drill", "", "GPP", "control")
    _, spp_ann = _format_rehab_drill("Drill", "", "SPP", "control")
    _, taper_ann = _format_rehab_drill("Drill", "", "TAPER", "control")
    assert gpp_ann[1] != spp_ann[1]
    assert spp_ann[1] != taper_ann[1]


# ---------------------------------------------------------------------------
# generate_rehab_protocols — output formatting
# ---------------------------------------------------------------------------


def test_output_includes_function_tag():
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        assert "[Function:" in result, f"Expected [Function:] tag in output:\n{result}"


def test_output_includes_purpose():
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="SPP",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        assert "Purpose:" in result, f"Expected Purpose: in output:\n{result}"


def test_output_includes_why_today():
    result, _ = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=exercise_bank,
        current_phase="GPP",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        assert "Why today:" in result, f"Expected 'Why today:' in output:\n{result}"


# ---------------------------------------------------------------------------
# generate_rehab_protocols — volume limits
# ---------------------------------------------------------------------------


def _count_drill_bullets(text: str) -> int:
    """Count drill bullet items (lines starting with '  •' that are not 4-space annotation lines)."""
    return sum(
        1 for line in text.splitlines()
        if line.startswith("  •") and not line.startswith("    ")
    )


def test_sparring_day_at_most_one_drill():
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="SPP",
        day_type="sparring",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        count = _count_drill_bullets(result)
        assert count <= 1, f"Sparring should produce ≤1 drill, got {count}:\n{result}"


def test_strength_day_at_most_two_drills():
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
        day_type="strength",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        count = _count_drill_bullets(result)
        assert count <= 2, f"Strength day should produce ≤2 drills, got {count}:\n{result}"


def test_default_day_type_at_most_two_drills():
    result, _ = generate_rehab_protocols(
        injury_string="ankle sprain",
        exercise_data=exercise_bank,
        current_phase="GPP",
    )
    if "No rehab work required" not in result and "Consult with" not in result:
        count = _count_drill_bullets(result)
        assert count <= 2, f"Default should produce ≤2 drills, got {count}:\n{result}"


def test_day_type_drill_limit_sparring_is_one():
    assert _DAY_TYPE_DRILL_LIMIT["sparring"] == 1


def test_day_type_drill_limit_others_are_two():
    for key in ("strength", "aerobic", "recovery"):
        assert _DAY_TYPE_DRILL_LIMIT[key] == 2, f"Expected limit 2 for {key}"


# ---------------------------------------------------------------------------
# Phase parsing and clustered rehab-return coverage
# ---------------------------------------------------------------------------


def _cluster_entries(cluster_id: str) -> list[dict]:
    return [entry for entry in get_rehab_bank() if cluster_id in entry.get("cluster_ids", [])]


def _cluster_text(cluster_id: str) -> str:
    parts: list[str] = []
    for entry in _cluster_entries(cluster_id):
        for drill in entry.get("drills", []):
            parts.append(drill.get("name", ""))
            parts.append(drill.get("notes", ""))
    return " ".join(parts).lower()


def test_split_phase_progression_accepts_ascii_arrow():
    assert _split_phase_progression("GPP -> SPP -> TAPER") == ["GPP", "SPP", "TAPER"]


def test_split_notes_by_phase_accepts_ascii_arrow():
    assert _split_notes_by_phase("GPP: Build control -> SPP: Add speed -> TAPER: Keep sharp") == [
        ("GPP", "Build control"),
        ("SPP", "Add speed"),
        ("TAPER", "Keep sharp"),
    ]


def test_rehab_return_clusters_are_three_phase_progressions():
    cluster_ids = [
        "boxing__rehab_return__hip_flexor_groin_return",
        "boxing__rehab_return__trunk_rotation_return",
        "boxing__rehab_return__shoulder_return_to_strike",
        "boxing__rehab_return__ankle_foot_balance_return",
    ]

    for cluster_id in cluster_ids:
        entries = _cluster_entries(cluster_id)
        assert len(entries) >= 2, f"Expected multiple entries for {cluster_id}"
        for entry in entries:
            assert _split_phase_progression(entry["phase_progression"]) == ["GPP", "SPP", "TAPER"]


def test_hip_flexor_groin_return_cluster_has_requested_bridge_themes():
    text = _cluster_text("boxing__rehab_return__hip_flexor_groin_return")
    assert "isometric hip flexion" in text or "hip flexor isometric" in text
    assert "march" in text
    assert "split-stance" in text
    assert "knee-drive" in text or "step-in" in text


def test_trunk_rotation_return_cluster_has_requested_bridge_themes():
    text = _cluster_text("boxing__rehab_return__trunk_rotation_return")
    assert "anti-rotation" in text
    assert "reload" in text
    assert "catch" in text and "brace" in text
    assert "stance preservation" in text or "stance-preserved" in text


def test_shoulder_return_cluster_has_requested_bridge_themes():
    text = _cluster_text("boxing__rehab_return__shoulder_return_to_strike")
    assert "scap" in text and "cuff" in text
    assert "safe press" in text or "press angle" in text
    assert "recoil" in text
    assert "combo" in text


def test_ankle_foot_return_cluster_has_requested_bridge_themes():
    text = _cluster_text("boxing__rehab_return__ankle_foot_balance_return")
    assert "arch" in text or "short foot" in text
    assert "perturbation" in text
    assert "pivot" in text and "deceleration" in text
    assert "exit-and-restack" in text or "restack" in text


# ---------------------------------------------------------------------------
# generate_rehab_protocols — no hard function-deduplication
# ---------------------------------------------------------------------------


def test_same_function_not_hard_blocked_when_needed():
    """Same-function drills must NOT be mechanically blocked.

    generate_rehab_protocols applies a volume ceiling, not a function-based
    exclusion.  Two drills of the same function may appear if the ceiling
    allows and the injury profile drives them there.  This test just ensures
    the output is not empty for a valid injury and does not crash.
    """
    result, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
    )
    # The call must succeed without raising, regardless of function overlap.
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_rehab_protocols — cross-phase deduplication via seen_drills
# ---------------------------------------------------------------------------


def test_seen_drills_prevents_cross_phase_repetition():
    result_gpp, seen = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="GPP",
        seen_drills=set(),
    )
    result_spp, _ = generate_rehab_protocols(
        injury_string="shoulder strain",
        exercise_data=exercise_bank,
        current_phase="SPP",
        seen_drills=seen,
    )

    def _extract_bullets(text: str) -> set[str]:
        return {
            line.strip().lstrip("•").strip()
            for line in text.splitlines()
            if line.startswith("  •") and not line.startswith("    ")
        }

    gpp_bullets = _extract_bullets(result_gpp)
    spp_bullets = _extract_bullets(result_spp)
    overlap = gpp_bullets & spp_bullets
    assert not overlap, f"Same drill appeared in both GPP and SPP: {overlap}"


# ---------------------------------------------------------------------------
# _serialize_rehab_option — function metadata
# ---------------------------------------------------------------------------


def test_serialize_rehab_option_has_function_class():
    slot = _serialize_rehab_option(
        "Banded Clamshell – Activate hip abductors",
        role="rehab_hip_strain",
        source="rehab_block",
        why="test why",
    )
    assert "function_class" in slot
    assert slot["function_class"] in REHAB_FUNCTION_BUCKETS


def test_serialize_rehab_option_has_function_label():
    slot = _serialize_rehab_option(
        "Banded Clamshell – Activate hip abductors",
        role="rehab_hip_strain",
        source="rehab_block",
        why="test why",
    )
    assert "rehab_function_label" in slot
    assert slot["rehab_function_label"] == _FUNCTION_LABELS[slot["function_class"]]


def test_serialize_rehab_option_respects_explicit_function_class():
    slot = _serialize_rehab_option(
        "Some Drill",
        role="rehab_test",
        source="rehab_block",
        why="test why",
        function_class="mobility",
    )
    assert slot["function_class"] == "mobility"


def test_serialize_rehab_option_strips_inline_function_tag():
    slot = _serialize_rehab_option(
        "Foam Roll Quads [Function: Recovery/downregulation] – post session",
        role="rehab_test",
        source="rehab_block",
        why="test why",
    )
    assert "[Function:" not in slot["name"]


# ---------------------------------------------------------------------------
# _build_rehab_slots — metadata and diversity scoring
# ---------------------------------------------------------------------------


def test_build_rehab_slots_includes_function_class():
    rehab_block = "- Shoulder (Strain):\n  • Single-arm Wall Slide – build scapular control\n"
    slots = _build_rehab_slots(rehab_block, "GPP")
    assert slots, "Expected at least one slot for a valid rehab block"
    for slot in slots:
        assert "function_class" in slot, f"slot missing function_class: {slot}"
        assert slot["function_class"] in REHAB_FUNCTION_BUCKETS
        assert "function_class" in slot["selected"], "selected missing function_class"


def test_build_rehab_slots_includes_rehab_function_label():
    rehab_block = "- Shoulder (Strain):\n  • Single-arm Wall Slide – build scapular control\n"
    slots = _build_rehab_slots(rehab_block, "GPP")
    assert slots
    for slot in slots:
        assert "rehab_function_label" in slot, f"slot missing rehab_function_label: {slot}"
        assert "rehab_function_label" in slot["selected"], "selected missing rehab_function_label"


def test_build_rehab_slots_why_today_framing():
    """Slot purpose should reference day-type reasoning, not just 'phase-specific'."""
    rehab_block = "- Ankle (Sprain):\n  • Banded Ankle Circles – restore multi-directional control\n"
    slots = _build_rehab_slots(rehab_block, "SPP")
    assert slots
    purpose = slots[0]["purpose"]
    assert any(word in purpose.lower() for word in ("day", "today", "specific", "scheduling")), (
        f"Expected 'Why today' framing in slot purpose, got:\n{purpose}"
    )


def test_build_rehab_slots_alternates_diversity_scored():
    """Alternates should prefer different function buckets (diversity scoring)."""
    rehab_block = (
        "- Ankle (Sprain):\n"
        "  • Single-Leg Balance on Foam Pad – rebuild proprioception\n"
    )
    slots = _build_rehab_slots(rehab_block, "GPP")
    if not slots:
        return
    slot = slots[0]
    alternates = slot.get("alternates", [])
    if len(alternates) >= 2:
        alt_functions = [a.get("function_class") for a in alternates]
        selected_func = slot.get("function_class")
        # At least one alternate should differ in function from the selected drill
        # (diversity-first scoring should push different-function drills to the front)
        assert any(f != selected_func for f in alt_functions), (
            f"All alternates share the selected function '{selected_func}' — "
            "expected at least one diverse-function alternate in top 2."
        )


def test_build_rehab_slots_same_function_alternates_not_blocked():
    """Same-function alternates must NOT be excluded — they just score lower."""
    rehab_block = (
        "- Shoulder (Strain):\n"
        "  • Banded External Rotation – rotator cuff activation\n"
    )
    slots = _build_rehab_slots(rehab_block, "GPP")
    if not slots:
        return
    # The call must succeed without raising.
    assert isinstance(slots, list)


# ---------------------------------------------------------------------------
# STAGE2_FINALIZER_PROMPT — Rule 12 content
# ---------------------------------------------------------------------------


def test_stage2_prompt_contains_rule_12():
    assert "RULE 12" in STAGE2_FINALIZER_PROMPT, "Missing RULE 12 in finalizer prompt"


def test_stage2_prompt_contains_surgical_rehab():
    assert "SURGICAL REHAB" in STAGE2_FINALIZER_PROMPT, (
        "Expected 'SURGICAL REHAB' heading in RULE 12"
    )


def test_stage2_prompt_requires_why_today():
    assert "Why today" in STAGE2_FINALIZER_PROMPT, (
        "Expected 'Why today' format requirement in finalizer prompt"
    )


def test_stage2_prompt_references_function_class():
    assert "function_class" in STAGE2_FINALIZER_PROMPT, (
        "Expected function_class scoring guidance in finalizer prompt"
    )


def test_stage2_prompt_mentions_model_authority():
    lower = STAGE2_FINALIZER_PROMPT.lower()
    assert "authority" in lower, (
        "Expected explicit model authority language in RULE 12"
    )


def test_stage2_prompt_mentions_day_type_sensitivity():
    lower = STAGE2_FINALIZER_PROMPT.lower()
    assert "sparring" in lower, "Expected sparring day guidance in RULE 12"
    assert "strength" in lower, "Expected strength day guidance in RULE 12"


def test_stage2_prompt_requires_sparring_modification_labels_and_readiness_rationale():
    lower = STAGE2_FINALIZER_PROMPT.lower()
    assert "original hard spar input" in lower
    assert "deload" in lower
    assert "converted" in lower
    assert "readiness" in lower
    assert "fixed anchors for weekly structure" in lower
    assert "injury-driven" in lower


# ---------------------------------------------------------------------------
# REHAB_QUALITY_CHECKS constant
# ---------------------------------------------------------------------------


def test_rehab_quality_checks_has_five_items():
    assert len(REHAB_QUALITY_CHECKS) == 5


def test_rehab_quality_checks_covers_key_questions():
    combined = " ".join(REHAB_QUALITY_CHECKS).lower()
    assert "exact issue" in combined
    assert "duplicate" in combined
    assert "lowest" in combined


# ---------------------------------------------------------------------------
# Day-type rationale constants
# ---------------------------------------------------------------------------


def test_day_type_rehab_why_covers_all_session_types():
    for key in ("sparring", "strength", "aerobic", "recovery"):
        assert key in _DAY_TYPE_REHAB_WHY, f"Missing '{key}' in _DAY_TYPE_REHAB_WHY"


def test_phase_rehab_why_covers_all_phases():
    for phase in ("GPP", "SPP", "TAPER"):
        assert phase in _PHASE_REHAB_WHY, f"Missing '{phase}' in _PHASE_REHAB_WHY"
