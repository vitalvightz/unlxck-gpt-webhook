import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_filtering import is_injury_safe, normalize_injury_regions
from fightcamp.injury_synonyms import parse_injury_phrase, remove_negated_phrases, split_injury_text


def test_split_injury_text_handles_mixed_separators():
    sample = "Right shin splints; left shoulder impingement, elbow pain and knee soreness.\nHip tightness"
    assert split_injury_text(sample) == [
        "right shin splints",
        "left shoulder impingement",
        "elbow pain",
        "knee soreness",
        "hip tightness",
    ]


def test_split_injury_text_preserves_multiword_locations():
    sample = "left shoulder blade soreness and upper back stiffness"
    assert split_injury_text(sample) == ["left shoulder blade soreness", "upper back stiffness"]


def test_split_injury_text_drops_empty_chunks():
    sample = "and; ,\n"
    assert split_injury_text(sample) == []


def test_remove_negated_phrases_regex_window_clears_text():
    assert remove_negated_phrases("no shoulder pain after sparring") == ""


def test_parse_injury_phrase_handles_shoulder_punctuation_variants():
    for phrase in ["shoulder.", "left shoulder,", "(shoulder) pain"]:
        _, location = parse_injury_phrase(phrase)
        assert location == "shoulder"


def test_parse_injury_phrase_maps_shin_splints_to_pain_and_shin():
    injury_type, location = parse_injury_phrase("shin splints.")
    assert injury_type == "pain"
    assert location == "shin"


def test_parse_injury_phrase_does_not_drop_clear_location():
    _, location = parse_injury_phrase("left shoulder impingement (mild)")
    assert location == "shoulder"


def test_normalize_injury_regions_marks_shin_mild():
    regions = normalize_injury_regions(["shin splints (mild)"])
    assert "shin_mild" in regions
    assert "shin" not in regions


def test_shin_mild_guard_blocks_jump_rope_allows_low_impact():
    injuries = ["shin splints (mild)"]
    jump_rope = {"name": "Jump rope intervals", "tags": ["impact_rebound_high"]}
    bike = {"name": "Assault bike tempo", "tags": ["low_impact"]}
    assert is_injury_safe(jump_rope, injuries) is False
    assert is_injury_safe(bike, injuries) is True
