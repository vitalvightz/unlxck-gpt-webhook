from fightcamp import strength


def test_taper_strength_selection_excludes_nordic_hamstring(monkeypatch):
    monkeypatch.setattr(
        strength,
        "get_exercise_bank",
        lambda: [
            {
                "name": "Nordic Hamstring Curl",
                "phases": ["GPP", "SPP", "TAPER"],
                "tags": ["rehab_friendly", "posterior_chain"],
                "equipment": ["bodyweight"],
                "movement": "hinge",
                "method": "",
                "notes": "",
            },
            {
                "name": "Hamstring Bridge ISO",
                "phases": ["GPP", "SPP", "TAPER"],
                "tags": ["rehab_friendly", "low_eccentric", "neural_primer", "speed"],
                "equipment": ["bodyweight"],
                "movement": "hinge",
                "method": "",
                "notes": "",
            },
        ],
    )
    monkeypatch.setattr(strength, "get_style_exercises", lambda: [])
    monkeypatch.setattr(strength, "get_universal_strength_names", lambda: set())

    result = strength.generate_strength_block(
        flags={
            "phase": "TAPER",
            "fatigue": "low",
            "equipment": ["bodyweight"],
            "fight_format": "boxing",
            "training_days": ["Mon", "Wed", "Fri"],
            "training_frequency": 3,
            "days_available": 3,
            "days_until_fight": 6,
        }
    )

    names = [entry.get("name", "").lower() for entry in result.get("exercises", [])]
    assert all("nordic" not in name for name in names)
