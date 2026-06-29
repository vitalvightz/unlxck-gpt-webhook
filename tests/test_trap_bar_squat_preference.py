from __future__ import annotations

from fightcamp import strength


def _flags(**overrides) -> dict:
    base = {
        "phase": "GPP",
        "fatigue": "low",
        "fight_format": "boxing",
        "sport": "boxing",
        "style_tactical": [],
        "style_technical": ["boxing"],
        "equipment": ["barbell", "trap_bar"],
        "training_days": ["Mon"],
        "training_frequency": 1,
        "days_available": 1,
        "key_goals": ["strength"],
        "weaknesses": [],
        "injuries": [],
        # Far from the fight so no late-selector window is active and the
        # barbell/trap-bar anchors are not taper-gated out.
        "days_until_fight": 60,
    }
    return {**base, **overrides}


def _back_squat() -> dict:
    return {
        "name": "Back Squat",
        "phases": ["GPP"],
        "method": "strength",
        "movement": "squat",
        "tags": ["quad_dominant", "compound"],
        "equipment": "barbell",
    }


def _trap_bar_deadlift() -> dict:
    return {
        "name": "Trap Bar Deadlift",
        "phases": ["GPP"],
        "method": "strength",
        "movement": "hinge",
        "tags": ["posterior_chain", "compound"],
        "equipment": "trap_bar",
    }


def _patch_two_anchor_runtime(monkeypatch, score_map: dict[str, float]) -> None:
    bank = [_back_squat(), _trap_bar_deadlift()]
    monkeypatch.setattr(strength, "get_exercise_bank", lambda: bank)
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())
    monkeypatch.setattr(strength, "allocate_sessions", lambda *_a, **_k: {"strength": 1})
    monkeypatch.setattr(strength, "calculate_exercise_numbers", lambda *_a, **_k: {"strength": 1})
    monkeypatch.setattr(
        strength,
        "strength_quality_adjustment",
        lambda exercise, phase=None: (0.0, strength.classify_strength_item(exercise)),
    )
    monkeypatch.setattr(
        strength,
        "score_exercise",
        lambda **kwargs: (
            score_map[kwargs["exercise_tags"][0]],
            {"final_score": score_map[kwargs["exercise_tags"][0]], "reason_codes": []},
        ),
    )


def _selected_names(result: dict) -> list[str]:
    return [entry["name"] for entry in result["why_log"]]


# --- _trap_bar_preference_context ---------------------------------------------


def test_no_risk_conditions_leaves_preference_inactive():
    active, reasons = strength._trap_bar_preference_context(_flags(), cut_bucket="none")
    assert active is False
    assert reasons == []


def test_bar_position_injury_activates_preference():
    for region in ("wrist", "shoulder", "elbow", "neck"):
        active, reasons = strength._trap_bar_preference_context(
            _flags(injuries=[f"{region} pain"]), cut_bucket="none"
        )
        assert active is True
        assert any(r.startswith("trap_bar_pref_injury") and region in r for r in reasons)


def test_unrelated_injury_does_not_activate_preference():
    active, reasons = strength._trap_bar_preference_context(
        _flags(injuries=["knee pain", "ankle sprain"]), cut_bucket="none"
    )
    assert active is False
    assert reasons == []


def test_active_weight_cut_activates_preference():
    active, reasons = strength._trap_bar_preference_context(_flags(), cut_bucket="high")
    assert active is True
    assert "trap_bar_pref_active_cut" in reasons

    active, reasons = strength._trap_bar_preference_context(
        _flags(weight_cut_risk=True), cut_bucket="none"
    )
    assert active is True
    assert "trap_bar_pref_active_cut" in reasons


def test_moderate_and_high_fatigue_activate_preference():
    for level in ("moderate", "high"):
        active, reasons = strength._trap_bar_preference_context(
            _flags(fatigue=level), cut_bucket="none"
        )
        assert active is True
        assert "trap_bar_pref_fatigue" in reasons

    active, _ = strength._trap_bar_preference_context(_flags(fatigue="low"), cut_bucket="none")
    assert active is False


def test_compressed_camp_activates_preference():
    explicit = _flags(camp_compressed=True)
    active, reasons = strength._trap_bar_preference_context(explicit, cut_bucket="none")
    assert active is True
    assert "trap_bar_pref_compressed_camp" in reasons

    short = _flags(phase_weeks={"GPP": 0, "SPP": 1, "TAPER": 1, "days": {"GPP": 0, "SPP": 6, "TAPER": 6}})
    active, reasons = strength._trap_bar_preference_context(short, cut_bucket="none")
    assert active is True
    assert "trap_bar_pref_compressed_camp" in reasons

    long_camp = _flags(phase_weeks={"GPP": 4, "SPP": 3, "TAPER": 1, "days": {"GPP": 28, "SPP": 21, "TAPER": 7}})
    active, _ = strength._trap_bar_preference_context(long_camp, cut_bucket="none")
    assert active is False


def test_poor_squat_tolerance_activates_preference():
    active, reasons = strength._trap_bar_preference_context(
        _flags(poor_squat_tolerance=True), cut_bucket="none"
    )
    assert active is True
    assert "trap_bar_pref_poor_squat_tolerance" in reasons

    active, reasons = strength._trap_bar_preference_context(
        _flags(squat_tolerance="poor"), cut_bucket="none"
    )
    assert active is True
    assert "trap_bar_pref_poor_squat_tolerance" in reasons

    active, _ = strength._trap_bar_preference_context(
        _flags(squat_tolerance="good"), cut_bucket="none"
    )
    assert active is False


# --- _trap_bar_anchor_preference_adjustment -----------------------------------


def test_adjustment_penalises_barbell_squat_anchor():
    adj, reasons = strength._trap_bar_anchor_preference_adjustment(
        _back_squat(), active=True, context_reasons=["trap_bar_pref_fatigue"]
    )
    assert adj == strength.TRAP_BAR_PREFERENCE_SQUAT_PENALTY
    assert "trap_bar_pref_squat_anchor_penalty" in reasons


def test_adjustment_boosts_trap_bar_hinge_anchor():
    adj, reasons = strength._trap_bar_anchor_preference_adjustment(
        _trap_bar_deadlift(), active=True, context_reasons=["trap_bar_pref_fatigue"]
    )
    assert adj == strength.TRAP_BAR_PREFERENCE_HINGE_BOOST
    assert "trap_bar_pref_trap_bar_anchor_boost" in reasons


def test_adjustment_inactive_is_neutral():
    adj, reasons = strength._trap_bar_anchor_preference_adjustment(
        _back_squat(), active=False, context_reasons=["trap_bar_pref_fatigue"]
    )
    assert adj == 0.0
    assert reasons == []


def test_adjustment_ignores_trap_bar_jump_squat_and_bodyweight_squat():
    jump = {"name": "Trap Bar Jump Squat", "movement": "squat", "equipment": "trap_bar", "tags": []}
    adj, _ = strength._trap_bar_anchor_preference_adjustment(jump, active=True, context_reasons=[])
    assert adj == 0.0

    goblet = {"name": "Goblet Squat", "movement": "squat", "equipment": "dumbbell", "tags": ["quad_dominant"]}
    adj, _ = strength._trap_bar_anchor_preference_adjustment(goblet, active=True, context_reasons=[])
    assert adj == 0.0


# --- end-to-end selection -----------------------------------------------------


def test_risk_condition_flips_anchor_to_trap_bar_deadlift(monkeypatch):
    # Back Squat edges Trap Bar Deadlift on the base score, but moderate/high
    # fatigue should tip the anchor to the trap-bar deadlift.
    _patch_two_anchor_runtime(monkeypatch, {"quad_dominant": 10.0, "posterior_chain": 9.8})
    result = strength.generate_strength_block(flags=_flags(fatigue="high"))
    assert _selected_names(result) == ["Trap Bar Deadlift"]
    reasons = result["why_log"][0]["reasons"]["reason_codes"]
    assert "trap_bar_pref_trap_bar_anchor_boost" in reasons
    assert "trap_bar_pref_fatigue" in reasons


def test_no_risk_keeps_back_squat_anchor(monkeypatch):
    _patch_two_anchor_runtime(monkeypatch, {"quad_dominant": 10.0, "posterior_chain": 9.8})
    result = strength.generate_strength_block(flags=_flags(fatigue="low"))
    assert _selected_names(result) == ["Back Squat"]
    reasons = result["why_log"][0]["reasons"]["reason_codes"]
    assert not any(r.startswith("trap_bar_pref_") for r in reasons)
