import pytest

from fightcamp.injury_negation import remove_negated_phrases
from fightcamp.injury_formatting import parse_injury_entry
from fightcamp.injury_scoring import score_injury_phrase
from fightcamp.injury_triage import triage_injuries


def test_central_function_strips_simple_negation():
    assert remove_negated_phrases("no shoulder pain - knee soreness") == "knee soreness"


def test_central_function_handles_dash_variants():
    assert remove_negated_phrases("no shoulder pain — knee soreness") == "knee soreness"


def test_parse_injury_entry_respects_central_negation():
    parsed = parse_injury_entry("no shoulder pain - knee soreness")
    assert parsed.canonical_location == "knee"
    assert parsed.injury_type == "soreness"


def test_score_injury_phrase_respects_central_negation():
    scored = score_injury_phrase("no fracture, just ankle pain")
    assert "urgent_fracture" not in scored.get("flags", [])
    assert scored.get("canonical_location") in {"ankle", "unknown"}


def test_injury_triage_respects_central_negation():
    result = triage_injuries("no concussion symptoms, just tired")
    assert result.training_status != "MEDICAL_HOLD"


def test_clinical_gate_respects_central_negation_if_present():
    clinical_gate = pytest.importorskip("fightcamp.clinical_gate")
    result = clinical_gate.evaluate_clinical_gate("no numbness or tingling")
    assert result.get("red_flag_level") != "urgent"
    assert result.get("training_status") != "no_training"


def test_clinical_gate_respects_fracture_negation_if_present():
    clinical_gate = pytest.importorskip("fightcamp.clinical_gate")
    result = clinical_gate.evaluate_clinical_gate("doctor ruled out fracture but ankle hurts")
    assert result.get("red_flag_level") != "urgent"
    assert result.get("training_status") in {"allow", "allow_modified"}
