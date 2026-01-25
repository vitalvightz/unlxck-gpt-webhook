import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import normalize_injury_regions
from fightcamp.injury_formatting import parse_injury_entry
from fightcamp.injury_synonyms import parse_injury_phrase, split_injury_text
from fightcamp.rehab_protocols import format_injury_guardrails, generate_rehab_protocols


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


def test_split_injury_text_handles_bullets_and_commas():
    sample = "• right shoulder pain\n- left knee sprain, ankle stiffness and elbow soreness"
    phrases = split_injury_text(sample)
    assert phrases == [
        "right shoulder pain",
        "left knee sprain",
        "ankle stiffness",
        "elbow soreness",
    ]


def test_split_injury_text_drops_empty_phrases():
    sample = " , ; and \n -- "
    assert split_injury_text(sample) == []


def test_parse_injury_phrase_handles_punctuated_locations():
    for sample in ["shoulder.", "shoulder,", "(shoulder)"]:
        injury_type, location = parse_injury_phrase(sample)
        assert location == "shoulder"
        assert injury_type is None


def test_parse_injury_phrase_shin_splints_maps_to_pain_and_shin():
    injury_type, location = parse_injury_phrase("right shin splints (mild)")
    assert injury_type == "pain"
    assert location == "shin"


def test_parse_injury_phrase_keeps_multiword_locations():
    injury_type, location = parse_injury_phrase("shoulder blade soreness")
    assert injury_type == "soreness"
    assert location == "shoulder"


def test_injury_guardrails_no_phantom_swelling():
    summary = format_injury_guardrails(
        "GPP",
        "Right shin splints (mild), left shoulder impingement (mild)",
    )
    assert "Swelling" not in summary
    assert "Shin" in summary
    assert "Shoulder" in summary


def test_negation_window_prevents_phantom_injury():
    assert parse_injury_entry("no shoulder pain after sparring") is None


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
