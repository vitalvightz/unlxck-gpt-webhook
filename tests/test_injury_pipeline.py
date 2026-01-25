import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import normalize_injury_regions
from fightcamp.injury_formatting import parse_injury_entry
from fightcamp.injury_synonyms import parse_injury_phrase, split_injury_text
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
