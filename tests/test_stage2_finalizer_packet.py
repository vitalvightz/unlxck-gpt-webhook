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
