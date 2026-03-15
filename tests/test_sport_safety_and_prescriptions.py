import re

from fightcamp.conditioning import (
    _sanitize_sport_language,
    generate_conditioning_block,
    render_conditioning_block,
)
from fightcamp.strength import _is_over_100_percent_isometric, generate_strength_block


def test_boxing_sport_language_is_sanitized_in_rendered_output():
    grouped_drills = {
        "alactic": [
            {
                "name": "Dirty TD setup elbows",
                "timing": "8 x 8s",
                "rest": "90s",
                "load": "max",
                "purpose": "dirty TD setups from clinch against cage",
            }
        ]
    }
    output = render_conditioning_block(
        grouped_drills,
        phase="SPP",
        phase_color="#000",
        sport="boxing",
    )
    forbidden = ["td", "takedown", "elbow", "cage", "octagon"]
    lowered = output.lower()
    for token in forbidden:
        assert token not in lowered


def test_boxing_spp_gets_alactic_fallback_when_not_suppressed():
    flags = {
        "phase": "SPP",
        "fatigue": "low",
        "style_technical": ["boxing"],
        "style_tactical": ["counter_striker"],
        "key_goals": [],
        "weaknesses": [],
        "injuries": [],
        "equipment": ["bodyweight", "heavy_bag"],
        "training_frequency": 4,
        "sport": "boxing",
        "days_until_fight": 12,
    }
    _, _, _, grouped_drills, _, _ = generate_conditioning_block(flags)
    assert grouped_drills.get("alactic")
    assert "6–10 sec" in grouped_drills["alactic"][0].get("timing", "")
    assert re.search(r"75.?120", grouped_drills["alactic"][0].get("rest", ""))


def test_boxing_gpp_prefers_easy_bike_over_pool_treading_when_available():
    flags = {
        "phase": "GPP",
        "fatigue": "low",
        "style_technical": ["boxing"],
        "style_tactical": ["pressure_fighter"],
        "key_goals": ["conditioning"],
        "weaknesses": ["conditioning"],
        "injuries": [],
        "equipment": ["assault_bike"],
        "training_frequency": 4,
        "sport": "boxing",
        "days_until_fight": 35,
    }
    _, _, _, grouped_drills, _, _ = generate_conditioning_block(flags)

    assert grouped_drills.get("aerobic")
    assert grouped_drills["aerobic"][0]["name"] != "Pool Treading Conditioning"
    assert "Bike" in grouped_drills["aerobic"][0]["name"]


def test_boxing_gpp_uses_pool_treading_only_when_unloading_is_clearly_justified():
    flags = {
        "phase": "GPP",
        "fatigue": "moderate",
        "style_technical": ["boxing"],
        "style_tactical": ["counter_striker"],
        "key_goals": ["conditioning"],
        "weaknesses": ["conditioning"],
        "injuries": ["ankle soreness", "shoulder irritation"],
        "restrictions": [{"restriction": "high_impact_lower", "strength": "avoid"}],
        "equipment": [],
        "training_frequency": 4,
        "sport": "boxing",
        "days_until_fight": 28,
    }
    _, _, _, grouped_drills, _, _ = generate_conditioning_block(flags)

    assert grouped_drills.get("aerobic")
    assert grouped_drills["aerobic"][0]["name"] == "Pool Treading Conditioning"


def test_supra_max_isometrics_are_gated_without_1rm_and_setup():
    flags = {
        "phase": "SPP",
        "fatigue": "low",
        "fight_format": "boxing",
        "style_tactical": ["pressure_fighter"],
        "key_goals": ["max_strength"],
        "training_days": ["Mon", "Tue", "Thu", "Sat"],
        "training_frequency": 4,
        "equipment": ["bodyweight", "dumbbell"],
        "tested_1rm_available": False,
    }
    result = generate_strength_block(flags=flags)
    names = [ex.get("name", "") for ex in result["exercises"]]
    assert not any("115% 1RM" in name or "120% 1RM" in name for name in names)


def test_boxing_language_helper_rewrites_terms():
    text = "dirty TD setups and elbows from thai clinch at the cage"
    sanitized = _sanitize_sport_language(text, fight_format="boxing").lower()
    assert "td" not in sanitized
    assert "elbow" not in sanitized
    assert "thai clinch" not in sanitized
    assert "cage" not in sanitized


def test_boxing_plain_clinch_language_is_allowed():
    text = "inside clinch hand-fighting rounds"
    sanitized = _sanitize_sport_language(text, fight_format="boxing").lower()
    assert "clinch" in sanitized


def test_over_100_percent_max_based_isometrics_are_detected():
    assert _is_over_100_percent_isometric({"name": "Atlas Stone Load Isometric (120% max stone @ lap)", "movement": "isometric", "tags": ["isometric"]})
    assert _is_over_100_percent_isometric({"name": "Sled Push Isometric (130% max push @ start position)", "movement": "isometric", "tags": ["isometric"]})


def test_over_100_percent_isometrics_are_banned_in_spp_even_with_setup():
    flags = {
        "phase": "SPP",
        "fatigue": "low",
        "fight_format": "boxing",
        "style_tactical": ["pressure_fighter"],
        "key_goals": ["max_strength"],
        "training_days": ["Mon", "Tue", "Thu", "Sat"],
        "training_frequency": 4,
        "equipment": ["power_rack", "barbell", "plates"],
        "tested_1rm_available": True,
    }
    result = generate_strength_block(flags=flags)
    names = [ex.get("name", "") for ex in result["exercises"]]
    assert not any("% 1RM" in name and any(p in name for p in ["105%", "110%", "115%", "120%", "125%", "130%"]) for name in names)
