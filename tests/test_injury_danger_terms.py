from fightcamp.injury_danger_terms import detect_danger_terms


def test_popliteus_soreness_does_not_match_pop_danger_term():
    matches = detect_danger_terms("popliteus soreness after runs")
    assert matches == []


def test_snapping_turtle_non_injury_text_does_not_trigger_danger_terms():
    matches = detect_danger_terms("I saw a snapping turtle at the lake")
    assert matches == []


def test_functional_loss_variants_match_restricted_route():
    for text in (
        "can't bear weight on right ankle",
        "cant bear weight on right ankle",
        "unable to bear weight today",
        "not able to bear weight on left foot",
        "can't walk after the roll",
        "cant walk after the roll",
    ):
        matches = detect_danger_terms(text)
        assert any(item["signal"] == "cannot_bear_weight" for item in matches)
        assert any(item["route"] == "restricted_rehab_only" for item in matches)
