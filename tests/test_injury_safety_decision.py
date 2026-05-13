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
