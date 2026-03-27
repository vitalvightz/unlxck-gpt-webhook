from fightcamp.conditioning import generate_conditioning_block, _conditioning_constraint_adjustment
from fightcamp.injury_guard import derive_constraint_sensitivity
from fightcamp.selector_policy import (
    FALLBACK_CLASS_DOWNRANKED,
    FALLBACK_CLASS_LAST_RESORT,
    FALLBACK_CLASS_NORMAL,
    conditioning_fallback_class,
    is_safe_boxing_specific,
)
from fightcamp.strength import generate_strength_block


def _hip_flexor_injury(*, trend: str, functional_impact: str) -> dict:
    return {
        "injury_type": "unspecified",
        "canonical_location": "hip_flexor",
        "severity": "moderate",
        "trend": trend,
        "functional_impact": functional_impact,
        "aggravators": [
            "deep hip flexion",
            "hard rotation",
            "heavy hinging",
            "fast direction changes",
            "prolonged stance/load",
        ],
        "notes": "pain spikes when driving the knee up, after sparring, or when loading the stance",
        "original_phrase": "Hip / groin",
    }


def _boxing_flags(parsed_injuries: list[dict], *, fatigue: str = "high") -> dict:
    return {
        "phase": "SPP",
        "fatigue": fatigue,
        "fight_format": "boxing",
        "sport": "boxing",
        "style_technical": ["boxing"],
        "style_tactical": ["distance_striker"],
        "key_goals": ["power", "strength", "conditioning", "mobility", "weight_cut"],
        "weaknesses": ["conditioning", "power", "mobility", "trunk_strength"],
        "training_days": ["Mon", "Tue", "Thu", "Sat"],
        "training_frequency": 4,
        "days_until_fight": 17,
        "hard_sparring_days": ["Tue", "Thu"],
        "weight_cut_risk": True,
        "weight_cut_pct": 5.8,
        "equipment": [
            "bodyweight",
            "bands",
            "dumbbell",
            "medicine_ball",
            "heavy_bag",
            "bench",
            "rower",
            "assault_bike",
        ],
        "injuries": ["hip flexor issue"],
        "parsed_injuries": parsed_injuries,
        "random_seed": 11,
    }


def test_constraint_sensitivity_state_distinguishes_improving_vs_critical():
    improving = derive_constraint_sensitivity(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")],
        fatigue="high",
        support_flags=["weight_cut_support"],
        hard_sparring_days=["Tue", "Thu"],
        days_until_fight=17,
        weight_cut_pressure=True,
    )
    worsening = derive_constraint_sensitivity(
        [_hip_flexor_injury(trend="worsening", functional_impact="cannot do key movements properly")],
        fatigue="high",
        support_flags=["weight_cut_support"],
        hard_sparring_days=["Tue", "Thu"],
        days_until_fight=17,
        weight_cut_pressure=True,
    )

    assert improving.state == "constrained"
    assert worsening.state == "critical"
    assert worsening.score > improving.score


def test_constrained_boxing_profile_stays_strict_without_flattening():
    flags = _boxing_flags(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")]
    )

    strength = generate_strength_block(flags=flags)
    strength_names = [exercise["name"] for exercise in strength["exercises"]]
    assert "Band-Resisted Punch" in strength_names
    assert "Band-Resisted Straight Punch" in strength_names
    assert "Banded Row (Speed Focus)" in strength_names
    assert not any("Split Squat" in name for name in strength_names)
    assert not any("Russian Twist" in name or "Rotational" in name for name in strength_names)
    assert sum("Lunge" in name or "Bound" in name for name in strength_names) <= 1

    _, conditioning_names, _, grouped_drills, _, _ = generate_conditioning_block(flags)
    assert "Distance Angle Exit Shadow Tempo" in conditioning_names
    assert "Assault Bike Capacity Builder" in conditioning_names
    assert not any("Exit-and-Reenter" in name for name in conditioning_names)
    assert grouped_drills["aerobic"][0]["name"] == "Distance Angle Exit Shadow Tempo"


def test_critical_boxing_profile_becomes_much_simpler():
    flags = _boxing_flags(
        [_hip_flexor_injury(trend="worsening", functional_impact="cannot do key movements properly")]
    )

    strength = generate_strength_block(flags=flags)
    strength_names = [exercise["name"] for exercise in strength["exercises"]]
    assert "Lateral Bound-to-Slip" not in strength_names
    assert "Jump Lunge (Alternating)" not in strength_names
    assert "Dynamic Plank-to-Punch" in strength_names

    _, conditioning_names, _, grouped_drills, _, _ = generate_conditioning_block(flags)
    assert grouped_drills["aerobic"][0]["name"] == "Swimming (Freestyle Laps)"
    assert "Distance Angle Exit Shadow Tempo" not in conditioning_names
    assert not any("Exit-and-Reenter" in name for name in conditioning_names)
    assert "Explosive Boxing Burst Intervals" not in conditioning_names


def test_healthy_boxing_control_keeps_sport_specific_outputs():
    flags = _boxing_flags([], fatigue="low")
    flags["injuries"] = []
    flags.pop("parsed_injuries")
    flags["weight_cut_risk"] = False
    flags["weight_cut_pct"] = 0.0
    flags["hard_sparring_days"] = ["Tue"]

    strength = generate_strength_block(flags=flags)
    strength_names = [exercise["name"] for exercise in strength["exercises"]]
    assert "Lateral Bound-to-Slip" in strength_names
    assert "Jump Lunge (Alternating)" in strength_names

    _, conditioning_names, _, grouped_drills, _, _ = generate_conditioning_block(flags)
    assert "Distance Exit-and-Reenter Bag Repeats" in conditioning_names
    assert grouped_drills["alactic"][0]["name"] == "Explosive Boxing Burst Intervals"


# ---------------------------------------------------------------------------
# is_safe_boxing_specific: broader recognition beyond narrow token heuristics
# ---------------------------------------------------------------------------

def test_is_safe_boxing_specific_recognizes_modality_based_safety():
    """Shadowbox and bag_work modalities are safe without requiring name tokens."""
    assert is_safe_boxing_specific(
        {"name": "Jab Flow Work", "tags": [], "modality": "shadowbox"},
        sport="boxing",
    )
    assert is_safe_boxing_specific(
        {"name": "Heavy Bag Circuit", "tags": [], "modality": "bag_work"},
        sport="boxing",
    )
    assert is_safe_boxing_specific(
        {"name": "Pad Session Drill", "tags": [], "modality": "pad_work"},
        sport="boxing",
    )


def test_is_safe_boxing_specific_recognizes_expanded_token_set():
    """Expanded tokens like 'flow', 'controlled', 'steady' should qualify."""
    assert is_safe_boxing_specific(
        {"name": "Low-Intensity Shadow Boxing Flow", "tags": ["boxing"], "modality": ""},
        sport="boxing",
    )
    assert is_safe_boxing_specific(
        {"name": "Controlled Jab-Cross Drill", "tags": ["boxing"], "modality": ""},
        sport="boxing",
    )
    assert is_safe_boxing_specific(
        {"name": "Steady State Boxing Bag Work", "tags": ["boxing"], "modality": ""},
        sport="boxing",
    )


def test_is_safe_boxing_specific_blocks_hard_excludes():
    """Drills with reenter / chase / decel are NOT safe regardless of other tokens."""
    assert not is_safe_boxing_specific(
        {"name": "Distance Exit-and-Reenter Bag Repeats", "tags": ["boxing"], "modality": "bag_work"},
        sport="boxing",
    )
    assert not is_safe_boxing_specific(
        {"name": "Chase the Angle Shadow Tempo", "tags": ["boxing"], "modality": "shadowbox"},
        sport="boxing",
    )
    assert not is_safe_boxing_specific(
        {"name": "Deceleration Shadow Drill", "tags": ["boxing"], "modality": ""},
        sport="boxing",
    )


def test_is_safe_boxing_specific_requires_boxing_identification():
    """Non-boxing drills and generic drills do not qualify as safe-boxing-specific."""
    assert not is_safe_boxing_specific(
        {"name": "Tempo Run Intervals", "tags": ["aerobic"], "modality": ""},
        sport="boxing",
    )
    assert not is_safe_boxing_specific(
        {"name": "Assault Bike Capacity Builder", "tags": ["aerobic"], "modality": ""},
        sport="boxing",
    )


def test_is_safe_boxing_specific_non_boxing_sport_returns_false():
    """The guard is sport-specific; other sports always return False."""
    assert not is_safe_boxing_specific(
        {"name": "Shadow Boxing Tempo", "tags": ["boxing"], "modality": "shadowbox"},
        sport="mma",
    )


def test_is_safe_boxing_specific_risky_boxing_drills_not_safe():
    """Boxing-tagged direction-change drills without safe tokens are not safe-specific."""
    assert not is_safe_boxing_specific(
        {"name": "Explosive Boxing Burst Intervals", "tags": ["boxing", "alactic", "high_cns"], "modality": ""},
        sport="boxing",
    )
    assert not is_safe_boxing_specific(
        {"name": "Distance Angle Exit-and-Reenter Bag Work", "tags": ["boxing"], "modality": ""},
        sport="boxing",
    )


# ---------------------------------------------------------------------------
# Penalty budgeting: same risk family not fully penalized in multiple layers
# ---------------------------------------------------------------------------

def _make_constraint(*, state: str, worsening: bool = False, cannot_do_key: bool = False) -> dict:
    """Return keyword args for derive_constraint_sensitivity to reproduce a named state."""
    if state == "constrained":
        return {
            "injuries": [_hip_flexor_injury(
                trend="worsening" if worsening else "improving",
                functional_impact="cannot do key movements properly" if cannot_do_key else "can train with modifications",
            )],
            "fatigue": "high",
            "support_flags": ["weight_cut_support"],
            "hard_sparring_days": ["Tue", "Thu"],
            "days_until_fight": 17,
            "weight_cut_pressure": True,
        }
    raise ValueError(f"Unknown state preset: {state}")


def test_penalty_budgeting_reduces_constraint_adjustment_after_last_resort_fallback():
    """A LAST_RESORT fallback for the same risk should reduce the constraint_adjustment.

    Without budgeting, a direction-change drill could accumulate:
      LAST_RESORT (-4.0) + constraint_adjustment direction_change (-1.4) = -5.4
    With budgeting (budget_factor=0.35), the stacked total is reduced:
      LAST_RESORT (-4.0) + constraint_adjustment direction_change (-1.4 * 0.35 ≈ -0.49) = -4.49
    """
    risky_drill = {
        "name": "Pivot Angle Exit Drill",
        "tags": ["aerobic"],
        "modality": "",
        "notes": "",
        "purpose": "pivot and angle exit",
        "equipment_note": "",
    }
    constraint = derive_constraint_sensitivity(
        **_make_constraint(state="constrained"),
    )

    adj_normal, reasons_normal = _conditioning_constraint_adjustment(
        risky_drill,
        system="aerobic",
        sport="boxing",
        constraint_context=constraint,
        fallback_class=FALLBACK_CLASS_NORMAL,
    )
    adj_last_resort, reasons_last_resort = _conditioning_constraint_adjustment(
        risky_drill,
        system="aerobic",
        sport="boxing",
        constraint_context=constraint,
        fallback_class=FALLBACK_CLASS_LAST_RESORT,
    )
    adj_downranked, _ = _conditioning_constraint_adjustment(
        risky_drill,
        system="aerobic",
        sport="boxing",
        constraint_context=constraint,
        fallback_class=FALLBACK_CLASS_DOWNRANKED,
    )

    # LAST_RESORT fallback should reduce constraint penalty significantly
    assert adj_last_resort > adj_normal, (
        f"LAST_RESORT budget should reduce penalty: normal={adj_normal}, last_resort={adj_last_resort}"
    )
    # DOWNRANKED should be between NORMAL and LAST_RESORT
    assert adj_normal <= adj_downranked <= 0 or adj_last_resort <= adj_downranked <= adj_normal, (
        f"DOWNRANKED should be intermediate: normal={adj_normal}, downranked={adj_downranked}, last_resort={adj_last_resort}"
    )
    # The direction_change risk is still the active reason in all cases
    assert "exit_reentry" in reasons_normal or "direction_change" in reasons_normal
    assert "exit_reentry" in reasons_last_resort or "direction_change" in reasons_last_resort


def test_penalty_budgeting_strict_in_critical_state():
    """Budget factor must be 1.0 (no discount) in critical / worsening states."""
    critical_constraint = derive_constraint_sensitivity(
        [_hip_flexor_injury(trend="worsening", functional_impact="cannot do key movements properly")],
        fatigue="high",
        support_flags=["weight_cut_support"],
        hard_sparring_days=["Tue", "Thu"],
        days_until_fight=17,
        weight_cut_pressure=True,
    )
    assert critical_constraint.state == "critical"

    risky_drill = {
        "name": "Pivot Angle Exit Drill",
        "tags": ["aerobic"],
        "modality": "",
        "notes": "",
        "purpose": "pivot and angle exit",
        "equipment_note": "",
    }

    adj_normal, _ = _conditioning_constraint_adjustment(
        risky_drill,
        system="aerobic",
        sport="boxing",
        constraint_context=critical_constraint,
        fallback_class=FALLBACK_CLASS_NORMAL,
    )
    adj_last_resort, _ = _conditioning_constraint_adjustment(
        risky_drill,
        system="aerobic",
        sport="boxing",
        constraint_context=critical_constraint,
        fallback_class=FALLBACK_CLASS_LAST_RESORT,
    )

    # In critical state, budget_factor is always 1.0 — no discount allowed
    assert adj_normal == adj_last_resort, (
        f"Critical state must not apply budget discount: "
        f"normal={adj_normal}, last_resort={adj_last_resort}"
    )


# ---------------------------------------------------------------------------
# Cross-module calibration: strength and conditioning degrade at similar rates
# ---------------------------------------------------------------------------

def test_cross_module_calibration_healthy_vs_constrained_vs_critical():
    """Strength and conditioning should both degrade under constraint, but at
    comparable rates.  Conditioning must not collapse dramatically faster than
    strength for the same moderate-constrained hip-flexor profile.

    Calibration criteria:
    - Both healthy and constrained produce at least some sport-specific output.
    - The number of sport-specific drills/exercises does not drop to zero in
      the constrained state for either module.
    - Critical state simplification is allowed for both, but safe band/bag
      strength options survive critical state too.
    """
    # ---- healthy baseline ----
    flags_h = _boxing_flags([], fatigue="low")
    flags_h["injuries"] = []
    flags_h.pop("parsed_injuries")
    flags_h["weight_cut_risk"] = False
    flags_h["weight_cut_pct"] = 0.0
    flags_h["hard_sparring_days"] = ["Tue"]

    strength_h = generate_strength_block(flags=flags_h)
    _, _, _, groups_h, _, _ = generate_conditioning_block(flags_h)

    strength_names_h = [ex["name"] for ex in strength_h["exercises"]]
    cond_aerobic_h = [d["name"] for d in groups_h.get("aerobic", [])]

    # ---- constrained ----
    flags_c = _boxing_flags(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")]
    )
    strength_c = generate_strength_block(flags=flags_c)
    _, _, _, groups_c, _, _ = generate_conditioning_block(flags_c)

    strength_names_c = [ex["name"] for ex in strength_c["exercises"]]
    cond_aerobic_c = [d["name"] for d in groups_c.get("aerobic", [])]

    # ---- critical ----
    flags_cr = _boxing_flags(
        [_hip_flexor_injury(trend="worsening", functional_impact="cannot do key movements properly")]
    )
    strength_cr = generate_strength_block(flags=flags_cr)
    _, _, _, groups_cr, _, _ = generate_conditioning_block(flags_cr)

    strength_names_cr = [ex["name"] for ex in strength_cr["exercises"]]
    cond_aerobic_cr = [d["name"] for d in groups_cr.get("aerobic", [])]

    # Both modules produce output in healthy state
    assert len(strength_names_h) > 0
    assert len(cond_aerobic_h) > 0

    # Both modules produce output in constrained state (not flattened to zero)
    assert len(strength_names_c) > 0
    assert len(cond_aerobic_c) > 0

    # Critical: both still produce some output (no total collapse)
    assert len(strength_names_cr) > 0
    assert len(cond_aerobic_cr) > 0

    # Strength: safe band-based boxing exercises survive in both constrained and critical
    band_or_bag = [n for n in strength_names_c if "Band" in n or "Bag" in n or "Banded" in n]
    assert len(band_or_bag) >= 1, (
        f"Constrained strength should still include band/bag options: {strength_names_c}"
    )

    # Conditioning: a safe boxing-specific drill should survive the constrained state
    safe_boxing_cond = [d for d in cond_aerobic_c if any(
        t in d.lower() for t in ("shadow", "tempo", "rhythm", "bag", "pad")
    )]
    assert len(safe_boxing_cond) >= 1, (
        f"Constrained conditioning aerobic should include at least one safe boxing option: {cond_aerobic_c}"
    )

    # Critical simplification is expected: generic/safe options dominate critical aerobic
    # but strength still retains band/bag options
    band_or_bag_cr = [n for n in strength_names_cr if "Band" in n or "Bag" in n or "Banded" in n]
    assert len(band_or_bag_cr) >= 1, (
        f"Critical strength should still include safe band/bag options: {strength_names_cr}"
    )


def test_improving_vs_worsening_both_modules_show_clear_difference():
    """Improving and worsening cases must produce clearly different outputs in
    both strength and conditioning — confirming the calibration is sensitive
    without being binary.
    """
    flags_improving = _boxing_flags(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")]
    )
    flags_worsening = _boxing_flags(
        [_hip_flexor_injury(trend="worsening", functional_impact="cannot do key movements properly")]
    )

    strength_imp = generate_strength_block(flags=flags_improving)
    strength_wor = generate_strength_block(flags=flags_worsening)
    _, _, _, groups_imp, _, _ = generate_conditioning_block(flags_improving)
    _, _, _, groups_wor, _, _ = generate_conditioning_block(flags_worsening)

    names_imp_s = [ex["name"] for ex in strength_imp["exercises"]]
    names_wor_s = [ex["name"] for ex in strength_wor["exercises"]]
    aerobic_imp = [d["name"] for d in groups_imp.get("aerobic", [])]
    aerobic_wor = [d["name"] for d in groups_wor.get("aerobic", [])]

    # Improving allows more reactive/sport-specific options
    reactive_imp = sum(1 for n in names_imp_s if any(t in n for t in ("Bound", "Jump", "Lunge", "Lateral")))
    reactive_wor = sum(1 for n in names_wor_s if any(t in n for t in ("Bound", "Jump", "Lunge", "Lateral")))
    assert reactive_imp >= reactive_wor, (
        f"Improving should have ≥ reactive options vs worsening: imp={reactive_imp}, wor={reactive_wor}"
    )

    # Worsening aerobic should not include direction-change boxing drills
    direction_change_wor = [n for n in aerobic_wor if any(t in n for t in ("Exit", "Reenter", "Angle"))]
    assert len(direction_change_wor) == 0, (
        f"Worsening aerobic should not have direction-change drills: {direction_change_wor}"
    )

    # The conditioning outputs differ between improving and worsening
    assert aerobic_imp != aerobic_wor, (
        "Improving and worsening cases should produce different aerobic conditioning outputs"
    )


# ---------------------------------------------------------------------------
# Ranking-delta tests: relative ordering, not just inclusion/exclusion
# ---------------------------------------------------------------------------

def test_ranking_delta_safe_boxing_drill_outranks_risky_drill_when_constrained():
    """In constrained state with direction-change aggravator, a safe boxing drill
    should rank above a risky direction-change drill.

    This test catches selector drift: if safe drills are over-penalized, they
    would fall behind generic/risky options.
    """
    from fightcamp.conditioning import _conditioning_constraint_adjustment
    from fightcamp.selector_policy import conditioning_fallback_class

    constraint = derive_constraint_sensitivity(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")],
        fatigue="high",
        support_flags=["weight_cut_support"],
        hard_sparring_days=["Tue", "Thu"],
        days_until_fight=17,
        weight_cut_pressure=True,
    )
    assert constraint.state == "constrained"

    # Safe boxing drill (shadow + tempo → safe_specific=True)
    safe_drill = {
        "name": "Shadow Boxing Tempo Drill",
        "tags": ["boxing", "aerobic"],
        "modality": "shadowbox",
        "notes": "",
        "purpose": "build boxing rhythm at steady pace",
        "equipment_note": "",
    }
    # Risky drill (pivot + angle → risky for direction-change aggravator)
    risky_drill = {
        "name": "Pivot Angle Exit Combo",
        "tags": ["aerobic", "reactive"],
        "modality": "",
        "notes": "",
        "purpose": "reactive pivot and angle exit",
        "equipment_note": "",
    }

    # Fallback classification
    profile_args = dict(
        sport="boxing",
        goal_keys=["conditioning"],
        weakness_keys=["conditioning"],
        weakness_secondary=[],
        constraint_context=constraint,
    )
    safe_fallback = conditioning_fallback_class(safe_drill, **profile_args)
    risky_fallback = conditioning_fallback_class(risky_drill, **profile_args)

    from fightcamp.selector_policy import FALLBACK_CLASS_PENALTY
    safe_fallback_penalty = FALLBACK_CLASS_PENALTY.get(safe_fallback, 0.0)
    risky_fallback_penalty = FALLBACK_CLASS_PENALTY.get(risky_fallback, 0.0)

    safe_adj, safe_reasons = _conditioning_constraint_adjustment(
        safe_drill, system="aerobic", sport="boxing",
        constraint_context=constraint, fallback_class=safe_fallback,
    )
    risky_adj, risky_reasons = _conditioning_constraint_adjustment(
        risky_drill, system="aerobic", sport="boxing",
        constraint_context=constraint, fallback_class=risky_fallback,
    )

    safe_total_penalty = safe_fallback_penalty + safe_adj
    risky_total_penalty = risky_fallback_penalty + risky_adj

    # Safe drill should incur a less negative (or positive) combined penalty
    assert safe_total_penalty > risky_total_penalty, (
        f"Safe drill should outrank risky drill in constrained state.\n"
        f"  safe: fallback={safe_fallback}({safe_fallback_penalty}), adj={safe_adj:.3f}, total={safe_total_penalty:.3f}\n"
        f"  risky: fallback={risky_fallback}({risky_fallback_penalty}), adj={risky_adj:.3f}, total={risky_total_penalty:.3f}\n"
        f"  safe_reasons={safe_reasons}, risky_reasons={risky_reasons}"
    )


def test_ranking_delta_risky_drills_demoted_vs_healthy():
    """Direction-change drills should rank lower in constrained vs healthy state.

    This catches the scenario where the constraint system has no effect and
    risky drills continue to rank as if there were no injury.
    """
    from fightcamp.conditioning import _conditioning_constraint_adjustment
    from fightcamp.selector_policy import FALLBACK_CLASS_PENALTY, conditioning_fallback_class

    constraint = derive_constraint_sensitivity(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")],
        fatigue="high",
        support_flags=["weight_cut_support"],
        hard_sparring_days=["Tue", "Thu"],
        days_until_fight=17,
        weight_cut_pressure=True,
    )
    no_constraint = derive_constraint_sensitivity(
        [], fatigue="low",
    )

    risky_drill = {
        "name": "Pivot Angle Exit Combo",
        "tags": ["aerobic", "reactive"],
        "modality": "",
        "notes": "",
        "purpose": "reactive pivot and angle exit",
        "equipment_note": "",
    }
    profile_args_constrained = dict(
        sport="boxing",
        goal_keys=["conditioning"],
        weakness_keys=["conditioning"],
        weakness_secondary=[],
        constraint_context=constraint,
    )
    profile_args_healthy = dict(
        sport="boxing",
        goal_keys=["conditioning"],
        weakness_keys=["conditioning"],
        weakness_secondary=[],
        constraint_context=None,
    )

    risky_fallback_constrained = conditioning_fallback_class(risky_drill, **profile_args_constrained)
    risky_fallback_healthy = conditioning_fallback_class(risky_drill, **profile_args_healthy)

    risky_fp_constrained = FALLBACK_CLASS_PENALTY.get(risky_fallback_constrained, 0.0)
    risky_fp_healthy = FALLBACK_CLASS_PENALTY.get(risky_fallback_healthy, 0.0)

    risky_adj_constrained, _ = _conditioning_constraint_adjustment(
        risky_drill, system="aerobic", sport="boxing",
        constraint_context=constraint, fallback_class=risky_fallback_constrained,
    )
    risky_adj_healthy, _ = _conditioning_constraint_adjustment(
        risky_drill, system="aerobic", sport="boxing",
        constraint_context=no_constraint, fallback_class=risky_fallback_healthy,
    )

    risky_total_constrained = risky_fp_constrained + risky_adj_constrained
    risky_total_healthy = risky_fp_healthy + risky_adj_healthy

    assert risky_total_constrained < risky_total_healthy, (
        f"Risky drill should be demoted in constrained vs healthy state.\n"
        f"  constrained: fallback={risky_fallback_constrained}({risky_fp_constrained:.2f}), "
        f"adj={risky_adj_constrained:.3f}, total={risky_total_constrained:.3f}\n"
        f"  healthy: fallback={risky_fallback_healthy}({risky_fp_healthy:.2f}), "
        f"adj={risky_adj_healthy:.3f}, total={risky_total_healthy:.3f}"
    )


def test_ranking_delta_safe_drill_not_excessively_suppressed_vs_healthy():
    """A safe boxing drill's combined penalty in constrained state should be small
    enough that it can still be competitive.  This would catch the case where the
    safe_specific bonus is offset by other stacked penalties causing selector drift.
    """
    from fightcamp.conditioning import _conditioning_constraint_adjustment
    from fightcamp.selector_policy import FALLBACK_CLASS_PENALTY, conditioning_fallback_class

    constraint = derive_constraint_sensitivity(
        [_hip_flexor_injury(trend="improving", functional_impact="can train with modifications")],
        fatigue="high",
        support_flags=["weight_cut_support"],
        hard_sparring_days=["Tue", "Thu"],
        days_until_fight=17,
        weight_cut_pressure=True,
    )

    safe_drill = {
        "name": "Distance Angle Exit Shadow Tempo",
        "tags": ["boxing", "aerobic"],
        "modality": "",
        "notes": "",
        "purpose": "shadow boxing at controlled pace",
        "equipment_note": "",
    }
    profile_args = dict(
        sport="boxing",
        goal_keys=["conditioning"],
        weakness_keys=["conditioning"],
        weakness_secondary=[],
        constraint_context=constraint,
    )

    safe_fallback = conditioning_fallback_class(safe_drill, **profile_args)
    safe_fp = FALLBACK_CLASS_PENALTY.get(safe_fallback, 0.0)
    safe_adj, safe_reasons = _conditioning_constraint_adjustment(
        safe_drill, system="aerobic", sport="boxing",
        constraint_context=constraint, fallback_class=safe_fallback,
    )
    total_penalty = safe_fp + safe_adj

    # The combined penalty for a safe boxing-specific drill in constrained state
    # should not be excessively negative — it should be able to survive ranking.
    # Threshold: no more than -2.0 combined penalty (fallback + adjustment)
    assert total_penalty >= -2.0, (
        f"Safe boxing drill over-suppressed in constrained state: "
        f"fallback={safe_fallback}({safe_fp}), adj={safe_adj:.3f}, "
        f"total={total_penalty:.3f}, reasons={safe_reasons}"
    )
    # The safe_specificity bonus should appear
    assert "safe_specificity" in safe_reasons, (
        f"Safe boxing drill should receive safe_specificity bonus: {safe_reasons}"
    )
