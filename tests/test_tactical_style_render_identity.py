from fightcamp.stage2_render_guards import (
    _append_render_guard_writing_rules,
    _render_guard_flags,
)


def _identity_rules_for(style: str) -> tuple[dict, str]:
    guidance = _append_render_guard_writing_rules(
        {"writing_rules": []},
        athlete_model={
            "has_active_injury": False,
            "tactical_styles": [style],
        },
        payload_mode="camp_payload",
        days_until_fight=30,
    )
    return guidance, "\n".join(guidance["writing_rules"])


def test_pressure_fighter_remains_pressure_fighter_in_athlete_view():
    guidance, rules = _identity_rules_for("Pressure Fighter")

    assert guidance["render_guards"]["declared_tactical_styles"] == ["Pressure Fighter"]
    assert "The athlete declared: Pressure Fighter." in rules
    assert "use only the declared label(s) exactly as supplied" in rules
    assert "Never substitute them for" in rules


def test_brawler_remains_brawler_in_athlete_view():
    guidance, rules = _identity_rules_for("Brawler")

    assert guidance["render_guards"]["declared_tactical_styles"] == ["Brawler"]
    assert "The athlete declared: Brawler." in rules
    assert "use only the declared label(s) exactly as supplied" in rules
    assert "Never substitute them for" in rules


def test_declared_style_labels_are_deduped_without_aliasing_or_reordering():
    guards = _render_guard_flags(
        athlete_model={
            "has_active_injury": False,
            "tactical_styles": ["Pressure Fighter", "Brawler", "Pressure Fighter"],
        },
        payload_mode="camp_payload",
        days_until_fight=30,
    )

    assert guards["declared_tactical_styles"] == ["Pressure Fighter", "Brawler"]


def test_no_declared_style_does_not_invent_identity_contract():
    guidance = _append_render_guard_writing_rules(
        {"writing_rules": []},
        athlete_model={"has_active_injury": False},
        payload_mode="camp_payload",
        days_until_fight=30,
    )

    assert guidance["render_guards"]["declared_tactical_styles"] == []
    assert not any("ATHLETE IDENTITY CONTRACT" in rule for rule in guidance["writing_rules"])
