from fightcamp.injury_safety_decision import evaluate_injury_safety


def test_negated_fracture_does_not_trigger_urgent():
    d = evaluate_injury_safety("no fracture, just ankle pain")
    assert d.red_flag_level not in {"urgent", "emergency"}
    assert d.training_status != "no_training"
    assert all("fracture" not in r.lower() for r in d.reasons)


def test_achilles_snap_triggers_urgent():
    d = evaluate_injury_safety("felt a snap in achilles")
    assert d.red_flag_level == "urgent"
    assert d.clearance_required is True
    assert d.training_status == "no_training"
    assert {"strength", "conditioning", "rehab"}.issubset(set(d.blocked_modules))


def test_numbness_tingling_triggers_urgent_nerve_gate():
    d = evaluate_injury_safety("numbness and tingling down arm")
    assert d.red_flag_level == "urgent"
    assert d.clearance_required is True
    reason_text = " ".join(d.reasons).lower()
    assert any(x in reason_text for x in ["numb", "tingling", "nerve"])


def test_cold_blue_foot_after_tackle_is_emergency():
    d = evaluate_injury_safety("foot is cold and blue after tackle")
    assert d.red_flag_level == "emergency"
    assert d.training_status == "emergency_care"
    assert d.clearance_required is True


def test_pus_cut_triggers_infection_or_contact_safety():
    d = evaluate_injury_safety("cut is leaking pus")
    assert d.red_flag_level in {"urgent", "emergency"}
    assert d.clearance_required is True
    assert {"contact", "sparring"}.issubset(set(d.blocked_modules))


def test_headache_after_sparring_blocks_contact():
    d = evaluate_injury_safety("headache after sparring")
    assert d.red_flag_level == "urgent"
    assert d.clearance_required is True
    assert {"contact", "sparring", "conditioning"}.issubset(set(d.blocked_modules))


def test_blacked_out_in_sparring_blocks_contact():
    d = evaluate_injury_safety("blacked out in sparring but feel okay now")
    assert d.red_flag_level == "urgent"
    assert d.clearance_required is True
    assert {"contact", "sparring"}.issubset(set(d.blocked_modules))


def test_minor_blister_not_urgent():
    d = evaluate_injury_safety("minor blister on heel")
    assert d.red_flag_level in {"none", "caution"}
    assert d.red_flag_level != "urgent"
    assert d.training_status in {"allow", "allow_modified"}


def test_open_bleeding_blister_grappling_no_contact():
    d = evaluate_injury_safety("open blister bleeding during grappling")
    assert d.training_status == "no_contact"
    assert {"contact", "sparring", "grappling"}.issubset(set(d.blocked_modules))


def test_ankle_clicking_no_pain_no_instability_not_urgent():
    d = evaluate_injury_safety("ankle clicking but no pain or instability")
    assert d.red_flag_level != "urgent"
    assert d.training_status != "no_training"


def test_ankle_clicking_with_pain_and_catching_is_caution():
    d = evaluate_injury_safety("ankle clicking with pain and catching")
    assert d.red_flag_level == "caution"
    assert d.training_status == "allow_modified"


def test_athlete_facing_reasons_do_not_expose_internal_tags():
    d = evaluate_injury_safety("fracture with severe swelling")
    text = " ".join(d.reasons).lower()
    assert "structural_red_flag" not in text
    assert "suspected_fracture" not in text


def test_blocked_strength_and_conditioning_shapes_after_coach_review_preserve_blocking():
    import pytest
    pytest.importorskip("dateutil")

    from fightcamp.plan_pipeline_blocks import _safety_block_message
    from fightcamp.injury_safety_decision import evaluate_injury_safety

    decision = evaluate_injury_safety("headache after sparring")
    msg = _safety_block_message(decision)
    strength_block = {"block": msg, "exercises": [], "why_log": [{"name": "blocked", "explanation": msg}]}
    conditioning_block = {"block": msg, "names": [], "why_log": [{"name": "blocked", "explanation": msg}], "grouped_drills": {}, "missing_systems": [], "candidate_reservoir": [], "phase_color": "#4CAF50", "num_sessions": 1, "diagnostic_context": {}, "sport": "mma"}
    assert "block" in strength_block
    assert strength_block["exercises"] == []
    assert conditioning_block["block"] == msg
    assert conditioning_block["grouped_drills"] == {}


def test_no_contact_message_text_present_for_blocked_contact_guidance():
    import pytest
    pytest.importorskip("dateutil")

    from types import SimpleNamespace
    from fightcamp.plan_pipeline_rendering import _build_coach_notes

    ctx = SimpleNamespace(training_context=SimpleNamespace(prev_exercises=[]), apply_muay_thai_filters=False, sanitize_labels=())
    blocks = SimpleNamespace(strength_names={}, conditioning_names={}, coach_review_notes="keep hard sparring", injury_safety_decision={"blocked_modules": ["sparring", "contact"]})
    note = _build_coach_notes(ctx, blocks)
    assert "sparring/contact blocked by injury safety decision" in note.lower()


def test_rendering_sparring_lines_suppress_hard_sparring_when_contact_blocked():
    import pytest
    pytest.importorskip("dateutil")

    from types import SimpleNamespace
    from fightcamp.plan_pipeline_rendering import _sparring_adjustment_lines, _sparring_nutrition_lines

    context = SimpleNamespace(
        plan_input=SimpleNamespace(
            hard_sparring_days=["Tuesday", "Saturday"],
            support_work_days=["Monday"],
            next_fight_date="2026-05-22",
            days_until_fight=18,
            athlete_timezone="UTC",
        ),
    )

    blocked_modules = ["sparring", "contact"]
    lines = _sparring_adjustment_lines(context, blocked_modules=blocked_modules)
    nutrition_lines = _sparring_nutrition_lines(context, blocked_modules=blocked_modules)
    text = "\n".join(lines + nutrition_lines).lower()

    assert "expected hard sparring days" not in text
    assert "on expected hard sparring days" not in text
    assert "sparring/contact blocked by injury safety decision" in text
