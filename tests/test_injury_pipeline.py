import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import normalize_injury_regions
from fightcamp.injury_formatting import parse_injury_entry
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
    sample = "Left ankle sprain / right wrist pain and shoulder tightness, knee soreness."
    phrases = split_injury_text(sample)
    assert len(phrases) == 4
    entries = [parse_injury_entry(phrase) for phrase in phrases]
    entries = [entry for entry in entries if entry]
    locations = {entry.get("canonical_location") for entry in entries}
    assert {"ankle", "wrist", "shoulder", "knee"} <= locations


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
