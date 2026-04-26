import pytest
from fightcamp.stage2_payload import (
    _meaningful_injury_values,
    _has_active_injury_from_athlete_model,
    _render_guard_flags,
)

def test_injury_marker_normalization():
    # Empty/None
    assert _meaningful_injury_values(None) == []
    assert _meaningful_injury_values([]) == []
    assert _meaningful_injury_values("") == []
    
    # Negative markers (should be filtered out)
    assert _meaningful_injury_values(["none"]) == []
    assert _meaningful_injury_values(["N/A"]) == []
    assert _meaningful_injury_values(["nil"]) == []
    assert _meaningful_injury_values(["no injuries"]) == []
    assert _meaningful_injury_values(["  none reported  "]) == []
    
    # Real injuries (should stay)
    assert _meaningful_injury_values(["left knee"]) == ["left knee"]
    assert _meaningful_injury_values(["none", "right shoulder"]) == ["right shoulder"]
    assert _meaningful_injury_values(["Grade 2 Hamstring"]) == ["Grade 2 Hamstring"]

def test_has_active_injury_from_athlete_model():
    # Case 1: Pre-computed flag is true
    assert _has_active_injury_from_athlete_model({"has_active_injury": True}) is True
    
    # Case 2: Pre-computed flag is false (overrides content checks)
    assert _has_active_injury_from_athlete_model({
        "has_active_injury": False,
        "injuries": ["broken leg"]
    }) is False
    
    # Case 3: Content-based detection (no flag present)
    assert _has_active_injury_from_athlete_model({"injuries": ["left wrist"]}) is True
    assert _has_active_injury_from_athlete_model({"injuries": ["none"]}) is False
    assert _has_active_injury_from_athlete_model({"parsed_injuries": [{"location": "hand"}]}) is True
    assert _has_active_injury_from_athlete_model({}) is False

def test_render_guard_flags_triggering():
    no_injury_athlete = {"has_active_injury": False}
    injured_athlete = {"has_active_injury": True}
    
    # Scenario: Normal camp, no injury
    guards = _render_guard_flags(
        athlete_model=no_injury_athlete,
        payload_mode="camp_payload",
        days_until_fight=30
    )
    assert guards["suppress_rehab_headings"] is True
    assert guards["suppress_phase_toolbox_sections"] is False
    
    # Scenario: Late fight, injured
    guards = _render_guard_flags(
        athlete_model=injured_athlete,
        payload_mode="late_fight_week_payload",
        days_until_fight=5
    )
    assert guards["suppress_rehab_headings"] is False
    assert guards["suppress_phase_toolbox_sections"] is True
    
    # Scenario: Normal camp, injured
    guards = _render_guard_flags(
        athlete_model=injured_athlete,
        payload_mode="camp_payload",
        days_until_fight=40
    )
    assert guards["suppress_rehab_headings"] is False
    assert guards["suppress_phase_toolbox_sections"] is False
