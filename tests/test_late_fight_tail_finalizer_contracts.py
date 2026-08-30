from __future__ import annotations

from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet


def test_long_camp_tail_carries_actual_d1_contract_into_finalizer_packet():
    athlete = {
        "sport": "boxing",
        "days_until_fight": 24,
        "training_days": ["monday", "wednesday", "friday"],
    }
    planning_brief = {
        "athlete_snapshot": athlete,
        "weekly_role_map": {
            "late_fight_tail_handoff": {
                "active": True,
                "normal_planner_through_d": 14,
                "late_fight_planner_from_d": 13,
                "source": "finished_existing_late_fight_path",
            },
            "weeks": [
                {
                    "week_index": 4,
                    "phase": "TAPER",
                    "calendar_days": [
                        {"weekday": "thursday", "d_day": 1},
                        {"weekday": "friday", "d_day": 0, "is_fight_day": True},
                    ],
                    "session_roles": [],
                    "late_fight_tail_segments": [
                        {
                            "stage_key": "d1",
                            "payload_mode": "pre_fight_day_payload",
                            "countdown_span": {"start_day": 1, "end_day": 1},
                        }
                    ],
                }
            ],
        },
    }
    stage2_payload = {
        "athlete_model": athlete,
        "payload_mode": "camp_payload",
        "rewrite_guidance": {},
    }

    packet = build_stage2_finalizer_packet(
        stage2_payload=stage2_payload,
        planning_brief=planning_brief,
    )

    handoff = packet["selected_plan"]["late_fight_tail_handoff"]
    assert handoff["active"] is True
    assert handoff["normal_planner_through_d"] == 14
    assert handoff["late_fight_planner_from_d"] == 13
    assert len(handoff["segments"]) == 1

    d1 = handoff["segments"][0]
    assert d1["payload_mode"] == "pre_fight_day_payload"
    contract = d1["render_contract"].lower()
    assert "no equipment of any kind on d-1" in contract
    assert "no bands" in contract
    assert "no med ball" in contract
    assert "no heavy bag" in contract
    assert "no weights" in contract

    assert any(
        "late_fight_tail_handoff.active" in rule
        and "render_contract" in rule
        and "d-14" in rule
        for rule in packet["hard_rules"]
    )


def test_no_tail_handoff_does_not_add_contract_payload():
    athlete = {"sport": "boxing", "days_until_fight": 24}
    packet = build_stage2_finalizer_packet(
        stage2_payload={
            "athlete_model": athlete,
            "payload_mode": "camp_payload",
            "rewrite_guidance": {},
        },
        planning_brief={
            "athlete_snapshot": athlete,
            "weekly_role_map": {"weeks": []},
        },
    )

    assert "late_fight_tail_handoff" not in packet["selected_plan"]
