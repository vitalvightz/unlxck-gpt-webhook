import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.clinical_gate import evaluate_clinical_gate
from fightcamp.injury_synonyms import parse_injury_phrase
from fightcamp.rehab_protocols import generate_rehab_protocols


def test_no_fracture_just_ankle_pain_respects_negation():
    gate = evaluate_clinical_gate("no fracture, just ankle pain")
    assert gate.red_flag_level != "urgent"
    assert gate.training_status in {"allow", "allow_modified"}
    parsed_type, parsed_location = parse_injury_phrase("ankle pain")
    assert parsed_type == "pain"
    assert parsed_location == "ankle"


def test_snap_in_achilles_is_urgent_and_blocks_normal_rehab():
    gate = evaluate_clinical_gate("felt a snap in achilles")
    assert gate.red_flag_level == "urgent"
    assert gate.clearance_required is True
    text, _ = generate_rehab_protocols(injury_string="felt a snap in achilles", exercise_data=[], current_phase="GPP")
    assert "Training Safety Flag Detected" in text


def test_numbness_and_tingling_is_urgent_no_training():
    gate = evaluate_clinical_gate("numbness and tingling down arm")
    assert gate.red_flag_level == "urgent"
    assert gate.training_status == "no_training"
    assert any("nerve" in reason for reason in gate.reasons)


def test_cold_blue_foot_is_emergency():
    gate = evaluate_clinical_gate("foot is cold and blue after tackle")
    assert gate.red_flag_level == "emergency"
    assert gate.training_status == "emergency_care"


def test_cut_leaking_pus_is_urgent_infection():
    gate = evaluate_clinical_gate("cut is leaking pus")
    assert gate.red_flag_level == "urgent"
    assert any("infection" in reason for reason in gate.reasons)
    assert gate.training_status in {"no_contact", "no_training"}


def test_headache_after_sparring_is_urgent_no_contact():
    gate = evaluate_clinical_gate("headache after sparring")
    assert gate.red_flag_level == "urgent"
    assert gate.training_status == "no_contact"
    assert "sparring" in gate.blocked_modules


def test_blacked_out_in_sparring_is_urgent():
    gate = evaluate_clinical_gate("blacked out in sparring but feel okay now")
    assert gate.red_flag_level == "urgent"
    assert gate.training_status in {"no_contact", "no_training"}
    assert gate.clearance_required is True


def test_minor_blister_is_caution_not_urgent():
    gate = evaluate_clinical_gate("minor blister on heel")
    assert gate.red_flag_level in {"caution", "none"}
    assert gate.red_flag_level not in {"urgent", "emergency"}


def test_open_blister_bleeding_during_grappling_is_no_contact():
    gate = evaluate_clinical_gate("open blister bleeding during grappling")
    assert gate.training_status == "no_contact"
    assert {"sparring", "contact", "grappling"}.issubset(set(gate.blocked_modules))


def test_clicking_without_pain_or_instability_not_escalated():
    gate = evaluate_clinical_gate("ankle clicking but no pain or instability")
    assert gate.red_flag_level in {"none", "caution"}
    assert gate.red_flag_level != "urgent"


def test_clicking_with_pain_and_catching_is_caution():
    gate = evaluate_clinical_gate("ankle clicking with pain and catching")
    assert gate.red_flag_level == "caution"
    assert gate.training_status == "allow_modified"
