from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet


def test_finalizer_packet_passes_open_plan_spec_and_render_mode():
    stage2_payload = {
        "payload_mode": "open_ongoing_payload",
        "render_mode": "open_ongoing_system",
        "athlete_model": {"days_until_fight": None, "fight_date": None, "next_fight_date": None},
        "open_plan_spec": {"plan_type": "open_ongoing_system", "structure": ["Immediate Coach Summary"]},
    }
    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    assert packet["render_mode"] == "open_ongoing_system"
    assert packet["selected_plan"]["open_plan_spec"]["plan_type"] == "open_ongoing_system"


def test_open_ongoing_finalizer_packet_does_not_include_phase_briefs():
    stage2_payload = {
        "payload_mode": "open_ongoing_payload",
        "render_mode": "open_ongoing_system",
        "athlete_model": {"days_until_fight": None, "fight_date": None, "next_fight_date": None},
        "open_plan_spec": {"plan_type": "open_ongoing_system", "structure": ["Immediate Coach Summary"]},
        "phase_briefs": {"GPP": {}, "SPP": {}, "TAPER": {}},
    }
    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload)
    assert packet["render_mode"] == "open_ongoing_system"
    assert "phase_briefs" not in packet


def test_finalizer_packet_preserves_injury_context_fields_in_athlete_model():
    stage2_payload = {
        "athlete_model": {
            "has_active_injury": True,
            "injuries_raw_text": "shoulder pain after grappling",
            "parsed_injuries": [
                {
                    "injury_type": "pain",
                    "injury_type_source": "parser",
                    "guided_source_injury_subtypes": ["pain", "instability", "tightness"],
                }
            ],
            "guided_injury": {"area": "left shoulder", "injury_type": "pain"},
            "injury_restrictions": [{"restriction": "avoid overhead work", "region": "shoulder"}],
        }
    }

    packet = build_stage2_finalizer_packet(stage2_payload=stage2_payload, planning_brief={})
    athlete_model = packet["athlete_model"]

    assert athlete_model["has_active_injury"] is True
    assert athlete_model["injuries_raw_text"] == "shoulder pain after grappling"
    assert athlete_model["parsed_injuries"][0]["injury_type"] == "pain"
    assert athlete_model["parsed_injuries"][0]["guided_source_injury_subtypes"] == ["pain", "instability", "tightness"]
    assert athlete_model["guided_injury"] == {"area": "left shoulder", "injury_type": "pain"}
    assert athlete_model["injury_restrictions"] == [{"restriction": "avoid overhead work", "region": "shoulder"}]


def test_finalizer_packet_hard_rules_include_subtype_context_guardrail():
    packet = build_stage2_finalizer_packet(stage2_payload={"athlete_model": {}}, planning_brief={})
    assert any(
        "Use parsed_injuries and guided_source_injury_subtypes as injury context only." in rule
        for rule in packet["hard_rules"]
    )
