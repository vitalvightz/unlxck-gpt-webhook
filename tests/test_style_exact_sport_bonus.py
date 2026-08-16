import pytest

from fightcamp import conditioning


TACTICAL_STYLES = (
    "distance_striker",
    "counter_striker",
    "pressure_fighter",
    "brawler",
    "clinch_fighter",
    "kicker",
    "wrestler",
    "grappler",
    "scrambler",
    "submission_hunter",
)


def _style_drill(name: str, style: str, sport: str | None) -> dict:
    tags = [style]
    if sport:
        tags.insert(0, sport)
    return {
        "name": name,
        "equipment": ["bodyweight"],
        "phases": ["GPP", "SPP"],
        "system": "aerobic",
        "modality": "controlled technical conditioning",
        "duration": "180s work / 60s rest x 3 rounds",
        "intensity": "moderate",
        "tags": tags,
        "notes": "Sustainable technical conditioning with clean mechanics.",
        "equipment_note": "Bodyweight only.",
        "work_sec": 180,
        "rest_sec": 60,
        "rounds": 3,
        "rpe": 5,
        "impact_cost": "low",
        "lactate_load": "low",
        "movement_cost": "low",
        "mechanical_risk_tags": [],
    }


def _flags(style: str, sport: str = "mma") -> dict:
    technical = {"mma": "mma", "boxing": "boxing", "kickboxing": "kickboxing", "muay_thai": "muay thai"}[sport]
    return {
        "phase": "GPP",
        "sport": sport,
        "style_technical": [technical],
        "style_tactical": [style.replace("_", " ")],
        "key_goals": ["conditioning"],
        "weaknesses": [],
        "fatigue": "low",
        "equipment": [],
        "training_frequency": 2,
        "days_available": 2,
        "days_until_fight": 35,
        "time_to_fight_days": 35,
        "injuries": [],
        "restrictions": [],
    }


def _run_pair(monkeypatch, style: str, sport: str = "mma", other_sport: str | None = None):
    exact = _style_drill(f"Exact {style}", style, sport)
    other = _style_drill(f"Other {style}", style, other_sport)
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [other, exact])
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [])
    result = conditioning.generate_conditioning_block(_flags(style, sport))
    reservoir = result[5]
    candidates = {
        entry["drill"]["name"]: entry
        for entry in reservoir.get("aerobic", [])
        if entry.get("drill", {}).get("name") in {exact["name"], other["name"]}
    }
    return exact, other, candidates, reservoir["__style_conditioning__"]


def test_raw_exact_sport_helper_uses_pre_rewrite_tags():
    assert conditioning._style_exact_sport_bonus(["boxing", "counter_striker"], "boxing") == 0.5
    assert conditioning._style_exact_sport_bonus(["muay_thai", "counter_striker"], "boxing") == 0.0
    assert conditioning._style_exact_sport_bonus(["kickboxing", "muay_thai", "brawler"], "kickboxing") == 0.5
    assert conditioning._style_exact_sport_bonus(["kickboxing", "muay_thai", "brawler"], "muay_thai") == 0.5
    assert conditioning._style_exact_sport_bonus(["brawler"], "mma") == 0.0


@pytest.mark.parametrize("style", TACTICAL_STYLES)
def test_exact_sport_bonus_is_global_across_all_tactical_styles(monkeypatch, style):
    exact, other, candidates, diagnostics = _run_pair(monkeypatch, style)
    assert set(candidates) == {exact["name"], other["name"]}
    exact_entry = candidates[exact["name"]]
    other_entry = candidates[other["name"]]
    assert exact_entry["score"] == pytest.approx(other_entry["score"] + 0.5)
    assert exact_entry["reasons"]["sport_specificity_bonus"] == 0.5
    assert exact_entry["reasons"]["exact_sport_match"] is True
    assert "exact_sport_match:+0.5" in exact_entry["reasons"]["reason_codes"]
    assert other_entry["reasons"]["sport_specificity_bonus"] == 0.0
    assert other_entry["reasons"]["exact_sport_match"] is False
    assert diagnostics["entries_exact_sport_bonus_applied"] == 1
    assert exact["name"] in diagnostics["final_selected_style_conditioning_names"]
    assert exact["name"] in diagnostics["final_selected_exact_sport_names"]


def test_cross_sport_tie_is_broken_by_exact_sport(monkeypatch):
    exact, other, candidates, _ = _run_pair(monkeypatch, "counter_striker", "mma", "boxing")
    assert candidates[exact["name"]]["score"] == pytest.approx(candidates[other["name"]]["score"] + 0.5)


def test_boxing_runtime_rewrite_cannot_fake_exact_sport_bonus(monkeypatch):
    exact, converted, candidates, diagnostics = _run_pair(monkeypatch, "counter_striker", "boxing", "muay_thai")
    assert set(candidates) == {exact["name"], converted["name"]}
    assert candidates[exact["name"]]["reasons"]["sport_specificity_bonus"] == 0.5
    assert candidates[converted["name"]]["reasons"]["sport_specificity_bonus"] == 0.0
    assert candidates[exact["name"]]["score"] == pytest.approx(candidates[converted["name"]]["score"] + 0.5)
    assert diagnostics["entries_exact_sport_bonus_applied"] == 1
