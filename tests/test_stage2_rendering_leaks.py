from fightcamp.stage2_render_guards import (
    _meaningful_injury_values,
    _has_active_injury_from_athlete_model,
    _render_guard_flags,
)


def test_stage2_payload_reexports_render_guards():
    """The render guard helpers must remain importable from stage2_payload for
    callers that haven't migrated to the new module yet."""
    from fightcamp import stage2_payload
    from fightcamp import stage2_render_guards

    for name in (
        "_NO_ACTIVE_INJURY_MARKERS",
        "_meaningful_injury_values",
        "_has_active_injury_from_training_context",
        "_has_active_injury_from_athlete_model",
        "_render_guard_flags",
        "_append_render_guard_writing_rules",
    ):
        assert getattr(stage2_payload, name) is getattr(stage2_render_guards, name)


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

    # Punctuation-tolerant negative markers
    assert _meaningful_injury_values(["none."]) == []
    assert _meaningful_injury_values(["n/a!"]) == []
    assert _meaningful_injury_values(["nothing"]) == []
    assert _meaningful_injury_values(["all clear"]) == []

    # Real injuries (should stay)
    assert _meaningful_injury_values(["left knee"]) == ["left knee"]
    assert _meaningful_injury_values(["none", "right shoulder"]) == ["right shoulder"]
    assert _meaningful_injury_values(["none", "left shoulder"]) == ["left shoulder"]
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
    assert guards["render_mode"] == "camp_plan"

    # Scenario: Late fight, injured
    guards = _render_guard_flags(
        athlete_model=injured_athlete,
        payload_mode="late_fight_week_payload",
        days_until_fight=5
    )
    assert guards["suppress_rehab_headings"] is False
    assert guards["suppress_phase_toolbox_sections"] is True
    assert guards["render_mode"] == "late_fight_countdown_only"

    # Scenario: Normal camp, injured
    guards = _render_guard_flags(
        athlete_model=injured_athlete,
        payload_mode="camp_payload",
        days_until_fight=40
    )
    assert guards["suppress_rehab_headings"] is False
    assert guards["suppress_phase_toolbox_sections"] is False
    assert guards["render_mode"] == "camp_plan"

    # Scenario: Normal camp mode does not suppress phase toolbox sections,
    # regardless of injury state.
    guards = _render_guard_flags(
        athlete_model=no_injury_athlete,
        payload_mode="camp_payload",
        days_until_fight=42,
    )
    assert guards["suppress_phase_toolbox_sections"] is False


def test_surface_only_injury_suppresses_rehab_but_keeps_injury_flag():
    # A stable surface/skin injury still reads as an active injury (so the hygiene
    # note renders) but must never license rehab/prehab rendering.
    surface_athlete = {
        "has_active_injury": True,
        "injuries": ["moderate stable lower-back abrasion"],
        "parsed_injuries": [
            {
                "injury_type": "abrasion",
                "canonical_location": "lower_back",
                "severity": "moderate",
                "flags": [],
            }
        ],
    }
    guards = _render_guard_flags(
        athlete_model=surface_athlete, payload_mode="camp_payload", days_until_fight=28
    )
    assert guards["has_active_injury"] is True
    assert guards["surface_injury_only"] is True
    assert guards["suppress_rehab_headings"] is True


def test_structural_injury_still_allows_rehab():
    structural_athlete = {
        "has_active_injury": True,
        "injuries": ["moderate lower-back sprain"],
        "parsed_injuries": [
            {"injury_type": "sprain", "canonical_location": "lower_back", "severity": "moderate", "flags": []}
        ],
    }
    guards = _render_guard_flags(
        athlete_model=structural_athlete, payload_mode="camp_payload", days_until_fight=28
    )
    assert guards["surface_injury_only"] is False
    assert guards["suppress_rehab_headings"] is False


def test_surface_plus_real_injury_is_not_surface_only():
    mixed_athlete = {
        "has_active_injury": True,
        "injuries": ["lower-back graze", "knee sprain"],
        "parsed_injuries": [
            {"injury_type": "graze", "canonical_location": "lower_back", "severity": "moderate", "flags": []},
            {"injury_type": "sprain", "canonical_location": "knee", "severity": "moderate", "flags": []},
        ],
    }
    guards = _render_guard_flags(
        athlete_model=mixed_athlete, payload_mode="camp_payload", days_until_fight=28
    )
    assert guards["surface_injury_only"] is False
    assert guards["suppress_rehab_headings"] is False


def test_build_planning_brief_includes_render_guards():
    from fightcamp.stage2_payload import build_planning_brief
    
    athlete_model = {
        "has_active_injury": False,
        "days_until_fight": 5  # Should trigger late fight guards
    }
    
    brief = build_planning_brief(
        athlete_model=athlete_model,
        restrictions=[],
        phase_briefs={},
        candidate_pools={},
        omission_ledger={},
        rewrite_guidance={"writing_rules": []}
    )
    
    decision_rules = brief.get("decision_rules", {})
    assert "render_guards" in decision_rules
    assert decision_rules["render_guards"]["suppress_rehab_headings"] is True
    assert decision_rules["render_guards"]["suppress_phase_toolbox_sections"] is True
    
    # Verify writing rules were appended
    writing_rules = decision_rules.get("writing_rules", [])
    assert any("do not render any section, heading, or line titled Rehab" in r for r in writing_rules)
    assert any("do not render standalone GPP, SPP, or TAPER toolbox" in r for r in writing_rules)
