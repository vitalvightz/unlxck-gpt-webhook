import pytest

from fightcamp.injury_formatting import parse_injury_entry
from fightcamp.injury_negation import remove_negated_phrases
from fightcamp.injury_scoring import score_injury_phrase
from fightcamp.injury_triage import MEDICAL_HOLD, triage_injuries
from fightcamp.input_parsing import PlanInput
from support import _build_request


def _payload_with_injury(injury_text: str) -> dict:
    payload = _build_request().to_payload()
    for field in payload["data"]["fields"]:
        if field.get("label") == "Any injuries or areas you need to work around?":
            field["value"] = injury_text
            break
    return payload


def test_central_function_strips_simple_negation():
    assert remove_negated_phrases("no shoulder pain - knee soreness") == "knee soreness"


def test_central_function_handles_dash_variants():
    assert remove_negated_phrases("no shoulder pain — knee soreness") == "knee soreness"


def test_central_function_handles_mojibake_dash_variants():
    assert remove_negated_phrases("no shoulder pain â€” knee soreness") == "knee soreness"


def test_negation_target_coverage_keeps_shin_splints():
    assert remove_negated_phrases("no shin splints") == ""


def test_parse_injury_entry_respects_central_negation():
    parsed = parse_injury_entry("no shoulder pain - knee soreness")
    assert parsed["canonical_location"] == "knee"
    assert parsed["injury_type"] == "soreness"


def test_score_injury_phrase_respects_central_negation():
    scored = score_injury_phrase("no fracture, just ankle pain")
    assert "urgent_fracture" not in scored.get("flags", [])
    assert scored.get("location") in {"ankle", "unspecified"}


def test_injury_triage_respects_central_negation():
    result = triage_injuries(PlanInput.from_payload(_payload_with_injury("no concussion symptoms, just tired")))
    assert result.mode != MEDICAL_HOLD


def test_clinical_gate_respects_central_negation_if_present():
    clinical_gate = pytest.importorskip("fightcamp.clinical_gate")
    result = clinical_gate.evaluate_clinical_gate("no numbness or tingling")
    assert result.red_flag_level != "urgent"
    assert result.training_status != "no_training"


def test_clinical_gate_respects_fracture_negation_if_present():
    clinical_gate = pytest.importorskip("fightcamp.clinical_gate")
    result = clinical_gate.evaluate_clinical_gate("doctor ruled out fracture but ankle hurts")
    assert result.red_flag_level != "urgent"
    assert result.training_status in {"allow", "allow_modified"}
