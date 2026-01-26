import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fightcamp.injury_scoring import score_injury_phrase


def test_score_injury_phrase_detects_side_location_and_type():
    result = score_injury_phrase("Left ankle sprain after rolling it.")
    assert result["side"] == "left"
    assert result["location"] == "ankle"
    assert result["injury_type"] == "sprain"


def test_score_injury_phrase_detects_urgent_flags_without_overriding():
    result = score_injury_phrase("Right ankle fracture with swelling.")
    assert result["injury_type"] == "unspecified"
    assert result["location"] == "ankle"
    assert "urgent" in result["flags"]
    assert "urgent_fracture" in result["flags"]


def test_score_injury_phrase_handles_shin_splints():
    result = score_injury_phrase("Bilateral shin splints after runs.")
    assert result["side"] == "both"
    assert result["location"] == "shin"
    assert result["injury_type"] == "pain"
    assert "shin_splints_variant" in result["flags"]


def test_score_injury_phrase_records_red_flags():
    result = score_injury_phrase("Knee keeps giving way and feels numb.")
    assert "instability_event" in result["flags"]
    assert "nerve_involvement" in result["flags"]


def test_patellar_tendon_classified_as_tendonitis():
    """Test that patellar tendon is classified as tendonitis, not contusion."""
    result = score_injury_phrase("left knee pain (patellar tendon)")
    assert result["injury_type"] == "tendonitis"
    assert result["location"] == "knee"
    assert result["side"] == "left"


def test_patellar_tendinopathy_classified_as_tendonitis():
    """Test that patellar tendinopathy is classified as tendonitis, not contusion."""
    result = score_injury_phrase("right knee patellar tendinopathy")
    assert result["injury_type"] == "tendonitis"
    assert result["location"] == "knee"
    assert result["side"] == "right"


def test_jumpers_knee_classified_as_tendonitis():
    """Test that jumper's knee is classified as tendonitis, not contusion."""
    result = score_injury_phrase("left jumper's knee")
    assert result["injury_type"] == "tendonitis"
    assert result["location"] == "knee"
    assert result["side"] == "left"


def test_tendon_pain_classified_as_tendonitis():
    """Test that tendon pain is classified as tendonitis, not contusion."""
    result = score_injury_phrase("knee tendon pain")
    assert result["injury_type"] == "tendonitis"
    assert result["location"] == "knee"


def test_knee_contusion_still_works():
    """Test that actual knee contusions are still correctly classified."""
    result = score_injury_phrase("knee bruise from kick")
    assert result["injury_type"] == "contusion"
    assert result["location"] == "knee"
