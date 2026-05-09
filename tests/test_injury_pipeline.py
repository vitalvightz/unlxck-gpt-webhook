import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import normalize_injury_regions
from fightcamp.injury_formatting import parse_injury_entry, parse_injuries_and_restrictions
import fightcamp.injury_synonyms as injury_synonyms
from fightcamp.injury_synonyms import parse_injury_phrase, remove_negated_phrases, split_injury_text
from fightcamp.rehab_protocols import generate_rehab_protocols


def test_negation_strips_injury_phrases():
    samples = [
        "no shoulder pain",
        "not injured",
        "no shin splints",
        "never had knee issues",
    ]
    for sample in samples:
        assert parse_injury_entry(sample) is None
        assert normalize_injury_regions([sample]) == set()


def test_multi_injury_split_and_parse():
    sample = "Left ankle sprain / right wrist pain; shoulder tightness, knee soreness."
    phrases = split_injury_text(sample)
    assert len(phrases) == 4
    entries = [parse_injury_entry(phrase) for phrase in phrases]
    entries = [entry for entry in entries if entry]
    locations = {entry.get("canonical_location") for entry in entries}
    assert {"ankle", "wrist", "shoulder", "knee"} <= locations


def test_raw_knee_mechanism_phrase_stays_single_injury_entry():
    sample = "Right knee went back as I planted it I think I overextended it"
    injuries, restrictions = parse_injuries_and_restrictions(sample)
    assert restrictions == []
    assert len(injuries) == 1
    assert injuries[0].get("canonical_location") == "knee"
    locations = {str(entry.get("canonical_location") or "").lower() for entry in injuries}
    assert "lower back" not in locations
    assert "lower_back" not in locations


def test_raw_knee_phrase_with_and_stays_single_injury_entry():
    sample = "Right knee went back and gave way on plant"
    injuries, restrictions = parse_injuries_and_restrictions(sample)
    assert restrictions == []
    assert len(injuries) == 1
    assert injuries[0].get("canonical_location") == "knee"
    locations = {str(entry.get("canonical_location") or "").lower() for entry in injuries}
    assert "lower back" not in locations
    assert "lower_back" not in locations


def test_raw_knee_planted_and_twisted_stays_single_injury_entry():
    sample = "Right knee planted and twisted"
    injuries, restrictions = parse_injuries_and_restrictions(sample)
    assert restrictions == []
    assert len(injuries) == 1
    assert injuries[0].get("canonical_location") == "knee"


def test_raw_legacy_multi_injury_with_semicolon_still_splits():
    sample = "right knee sprain; left ankle soreness"
    injuries, restrictions = parse_injuries_and_restrictions(sample)
    assert restrictions == []
    assert len(injuries) == 2
    assert {entry.get("canonical_location") for entry in injuries} == {"knee", "ankle"}


def test_raw_legacy_multi_injury_with_comma_still_splits():
    sample = "right knee sprain, left ankle soreness"
    injuries, restrictions = parse_injuries_and_restrictions(sample)
    assert restrictions == []
    assert len(injuries) == 2
    assert {entry.get("canonical_location") for entry in injuries} == {"knee", "ankle"}


def test_and_split_still_works_for_distinct_body_parts():
    sample = "right wrist pain and shoulder tightness"
    injuries, restrictions = parse_injuries_and_restrictions(sample)
    assert restrictions == []
    assert len(injuries) == 2
    assert {entry.get("canonical_location") for entry in injuries} == {"wrist", "shoulder"}


def test_and_split_still_works_for_ankle_and_wrist():
    sample = "ankle sprain and wrist pain"
    injuries, restrictions = parse_injuries_and_restrictions(sample)
    assert restrictions == []
    assert len(injuries) == 2
    assert {entry.get("canonical_location") for entry in injuries} == {"ankle", "wrist"}


def test_punctuation_and_hyphenated_phrases_parse():
    sample = "Shoulder. left-ankle sprain (mild); knee pain."
    phrases = split_injury_text(sample)
    entries = [parse_injury_phrase(phrase) for phrase in phrases]
    locations = {loc for _, loc in entries if loc}
    assert {"shoulder", "ankle", "knee"} <= locations


def test_negated_phrase_fallback_normalizes_dash_variants(monkeypatch):
    monkeypatch.setattr(injury_synonyms, "get_nlp", lambda: None)

    assert remove_negated_phrases("no shoulder pain — knee soreness") == "knee soreness"
    assert (
        remove_negated_phrases(
            f"no shoulder pain {chr(0x00E2)}{chr(0x20AC)}{chr(0x201D)} knee soreness"
        )
        == "knee soreness"
    )


def test_parse_injury_entry_checks_negation_availability_at_parse_time(monkeypatch):
    monkeypatch.setattr(injury_synonyms, "get_nlp", lambda: None)

    assert not injury_synonyms.negation_detection_available()

    entry = parse_injury_entry("no shoulder pain - knee soreness")

    assert entry is not None
    assert entry["canonical_location"] == "knee"
    assert entry["injury_type"] == "soreness"


def test_canonical_injury_types_are_allowed():
    allowed = {
        "sprain",
        "strain",
        "tightness",
        "contusion",
        "swelling",
        "tendonitis",
        "impingement",
        "instability",
        "stiffness",
        "pain",
        "soreness",
        "hyperextension",
        "abrasion",
        "cut",
        "laceration",
        "graze",
        "blister",
        "unspecified",
    }
    entry = parse_injury_entry("shin splints")
    assert entry is not None
    assert entry.get("injury_type") in allowed
    assert entry.get("injury_type") != "shin splints"


def test_rehab_lookup_fallbacks_for_location_aliases():
    text, _ = generate_rehab_protocols(
        injury_string="lower back pain, biceps strain",
        exercise_data=[],
        current_phase="GPP",
    )
    assert "No rehab options" not in text


def test_surface_injury_types_parse_as_first_class_types():
    cases = [
        ("neck abrasion", "abrasion", "neck"),
        ("neck cut", "cut", "neck"),
        ("neck laceration", "laceration", "neck"),
        ("neck graze", "graze", "neck"),
        ("foot blister", "blister", "foot"),
        ("scraped knee", "abrasion", "knee"),
        ("grazed elbow", "graze", "elbow"),
        ("deep gash on cheek", "laceration", "face"),
        ("boot rub on heel", "blister", "heel"),
    ]
    for phrase, expected_type, expected_location in cases:
        parsed_type, parsed_location = parse_injury_phrase(phrase)
        assert parsed_type == expected_type
        assert parsed_location == expected_location


def test_cut_above_eye_parses_to_cut_type_and_eye_adjacent_location():
    parsed_type, parsed_location = parse_injury_phrase("cut above eye")
    assert parsed_type == "cut"
    assert parsed_location in {"eye", "face"}


def test_surface_terms_do_not_fall_back_to_old_pain_or_contusion_buckets():
    assert parse_injury_phrase("neck abrasion")[0] != "contusion"
    assert parse_injury_phrase("grazed elbow")[0] != "pain"
    assert parse_injury_phrase("neck cut")[0] != "strain"
    assert parse_injury_phrase("neck graze")[0] != "strain"
    assert parse_injury_phrase("neck abrasion")[0] != "strain"

    parsed_type, _ = parse_injury_phrase("surface scrape on knee")
    assert parsed_type == "abrasion"
    assert parsed_type != "pain"


def test_build_rehab_injury_string_prefers_structured_knee_instability():
    from types import SimpleNamespace

    from fightcamp.plan_pipeline_blocks import _build_rehab_injury_string

    context = SimpleNamespace(
        plan_input=SimpleNamespace(
            parsed_injuries=[
                {
                    "original_phrase": "Right knee went back as I planted it I think I overextended it",
                    "canonical_location": "knee",
                    "display_location": "right knee",
                    "laterality": "right",
                    "injury_type": "sprain",
                    "severity": "mild",
                    "trend": "stable",
                }
            ],
            guided_injury=SimpleNamespace(
                injury_type="instability / giving way",
                notes="knee gave way on plant",
                area="right knee",
            ),
        ),
        injuries_only_text="Right knee went back as I planted it I think I overextended it",
    )

    assert _build_rehab_injury_string(context) == "right knee instability mild stable"


def test_build_rehab_injury_string_falls_back_to_raw_when_no_parsed_entries():
    from types import SimpleNamespace

    from fightcamp.plan_pipeline_blocks import _build_rehab_injury_string

    raw_text = "Right knee went back as I planted it I think I overextended it"
    context = SimpleNamespace(
        plan_input=SimpleNamespace(parsed_injuries=[], guided_injury=None),
        injuries_only_text=raw_text,
    )

    assert _build_rehab_injury_string(context) == raw_text
