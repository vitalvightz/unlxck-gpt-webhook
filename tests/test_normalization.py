from fightcamp.normalization import phrase_in_text


def test_phrase_in_text_matches_unicode_hyphen_variants():
    text = "Band‑Resisted Jab‑Cross Primer"
    assert phrase_in_text(text, "band-resisted")
    assert phrase_in_text(text, "resisted jab-cross")

