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
    assert result["injury_type"] == "shin splints"


def test_score_injury_phrase_records_red_flags():
    result = score_injury_phrase("Knee keeps giving way and feels numb.")
    assert "instability_event" in result["flags"]
    assert "nerve_involvement" in result["flags"]
