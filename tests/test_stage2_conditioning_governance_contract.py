from __future__ import annotations

from fightcamp import bank_schema, conditioning
from fightcamp.session_composition import _conditioning_active_work_seconds
from fightcamp.stage2_payload import _build_conditioning_slots, _serialize_conditioning_option
from fightcamp.strength_session_quality import classify_strength_item


def _fresh_conditioning_banks() -> None:
    conditioning._conditioning_bank_cache = None
    conditioning._style_conditioning_bank_cache = None
    conditioning._technical_footwork_bank_cache = None


def test_production_gpp_aerobic_regression_keeps_support_out_of_fulfillment():
    """Regression for production plan 42d13f18-3d28-4302-bbb1-ba7587811980."""
    _fresh_conditioning_banks()
    try:
        bank = conditioning.get_conditioning_bank()
        by_name = {item["name"]: item for item in bank}
        ladder = by_name["Agility Ladder (Recovery)"]

        result = conditioning.generate_conditioning_block(
            {
                "phase": "GPP",
                "fatigue": "low",
                "style_technical": ["boxing"],
                "style_tactical": ["out-boxer"],
                "sport": "boxing",
                "key_goals": ["conditioning"],
                "weaknesses": ["gas tank"],
                "injuries": ["right forearm tightness"],
                "restrictions": [],
                "equipment": ["assault_bike", "treadmill", "jump_rope", "bodyweight"],
                "training_frequency": 5,
                "days_available": 5,
                "weight_cut_pct": 0,
            }
        )
        _text, selected_names, _why, grouped, missing_systems, reservoir = result
        aerobic = grouped["aerobic"]

        assert "Agility Ladder (Recovery)" not in [item["name"] for item in aerobic]
        assert all(
            bank_schema.has_meaningful_fulfillment_authority(
                item,
                source_kind="conditioning",
                source=str(item.get("_schema_source") or "conditioning_bank.json"),
            )
            for item in aerobic
        )
        assert "aerobic" not in missing_systems
        assert any("bike" in name.lower() or "zone 2" in name.lower() or "jog" in name.lower() for name in selected_names)
        assert any(
            (candidate.get("drill") or {}).get("name") == "Nasal Jog"
            for candidate in reservoir["aerobic"]
        )
        assert any("assault bike" in item["name"].lower() for item in aerobic)

        support_option = _serialize_conditioning_option(ladder, "aerobic", "optional recovery support")
        assert support_option["fulfillment_authority"] is False
        assert _conditioning_active_work_seconds(support_option) == 0.0

        support_slots = _build_conditioning_slots(
            {"grouped_drills": {"conditioning_support": [ladder]}, "why_log": [], "candidate_reservoir": {}},
            "GPP",
        )
        assert support_slots[0]["role"] == "conditioning_support"
        assert support_slots[0]["selected"]["support_only"] is True
        assert support_slots[0]["selected"]["fulfillment_authority"] is False
    finally:
        _fresh_conditioning_banks()


def test_meaningful_stress_false_cannot_satisfy_a_mandatory_system():
    item = {
        "name": "False meaningful declaration",
        "system": "aerobic",
        "total_minutes": 30,
        "rpe": 5,
        "stress_class": "anchor",
        "cost_class": "low",
        "support_only": False,
        "meaningful_stress": False,
    }

    assert not bank_schema.has_meaningful_fulfillment_authority(
        item,
        source_kind="conditioning",
        source="conditioning_bank.json",
    )


def test_generic_selector_prefers_meaningful_aerobic_authority_for_mma(monkeypatch):
    meaningful = {
        "name": "Meaningful Aerobic Base",
        "placement": "conditioning",
        "system": "aerobic",
        "phases": ["GPP"],
        "tags": ["aerobic"],
        "total_minutes": 25,
        "rpe": 5,
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "late_windows": ["d21_to_d14"],
        "stress_class": "anchor",
        "cost_class": "low",
        "support_only": False,
        "meaningful_stress": True,
        "_schema_source": "conditioning_bank.json",
    }
    support = {
        **meaningful,
        "name": "MMA Recovery Footwork",
        "tags": ["aerobic", "conditioning", "mma", "reactive", "footwork"],
        "stress_class": "support",
        "support_only": True,
        "meaningful_stress": False,
        "_schema_source": "style_conditioning_bank.json",
    }
    monkeypatch.setattr(conditioning, "get_conditioning_bank", lambda: [meaningful])
    monkeypatch.setattr(conditioning, "get_style_conditioning_bank", lambda: [support])
    monkeypatch.setattr(conditioning, "get_coordination_bank", lambda: [])
    monkeypatch.setattr(conditioning, "select_coordination_drill", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(conditioning, "_load_bank", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(conditioning, "allocate_sessions", lambda *_args, **_kwargs: {"conditioning": 1})
    monkeypatch.setattr(conditioning, "calculate_exercise_numbers", lambda *_args, **_kwargs: {"conditioning": 1})

    result = conditioning.generate_conditioning_block(
        {
            "phase": "GPP",
            "sport": "mma",
            "style_technical": ["mma"],
            "style_tactical": ["pressure"],
            "key_goals": ["conditioning"],
            "weaknesses": ["gas tank"],
            "fatigue": "low",
            "equipment": ["bodyweight"],
            "training_frequency": 3,
            "days_available": 3,
            "injuries": [],
            "restrictions": [],
        }
    )

    assert result[1] == ["Meaningful Aerobic Base"]
    assert result[3]["aerobic"][0]["name"] == "Meaningful Aerobic Base"


def test_style_taper_primers_remain_explicit_support():
    style_taper = conditioning._load_bank(
        conditioning.DATA_DIR / "style_taper_conditioning.json",
        source="style_taper_conditioning.json",
        enforce_conditioning_systems=True,
    )

    assert style_taper
    assert all(item["support_only"] is True for item in style_taper)
    assert all(item["meaningful_stress"] is False for item in style_taper)
    assert all(
        not bank_schema.has_meaningful_fulfillment_authority(
            item,
            source_kind="conditioning",
            source="style_taper_conditioning.json",
        )
        for item in style_taper
    )


def test_missing_late_windows_remains_fail_closed():
    item = {
        "name": "No inferred late permission",
        "tags": ["aerobic"],
        "phases": ["TAPER"],
        "system": "aerobic",
        "total_minutes": 20,
        "rpe": 4,
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "stress_class": "anchor",
        "cost_class": "low",
        "support_only": False,
        "meaningful_stress": True,
    }

    validated = bank_schema.validate_training_item(
        item, source="conditioning_bank.json", mode="runtime"
    )

    assert "late_windows" not in validated
    assert "missing_late_windows" in validated["_schema_issues"]
    assert validated["_schema_safety"]["late_fight_eligible"] is False


def test_explicit_strength_support_governance_blocks_anchor_authority():
    profile = classify_strength_item(
        {
            "name": "Loaded carry support",
            "method": "strength",
            "movement": "compound",
            "equipment": ["sandbag"],
            "tags": ["compound", "posterior_chain"],
            "stress_class": "support",
            "cost_class": "moderate",
            "support_only": True,
            "meaningful_stress": False,
        }
    )

    assert profile["support_only"] is True
    assert profile["anchor_capable"] is False
