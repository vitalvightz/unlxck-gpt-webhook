from copy import deepcopy

from fightcamp.stage2_validator import validate_stage2_output
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet


def _brief() -> dict:
    shadow = {
        "name": "Shadowboxing Power Bursts",
        "prescription": "10 x 15 sec work; 45 sec rest; RPE 9",
        "selection_metadata": {"rpe": 9, "intensity": "high"},
    }
    return {
        "weekly_role_map": {
            "weeks": [{
                "phase": "GPP",
                "calendar_days": [{"weekday": "sunday", "d_day": 18}],
                "session_roles": [{
                    "category": "conditioning",
                    "role_key": "controlled_repeatability_day",
                    "athlete_facing_label": "Fight-pace conditioning",
                    "preferred_system": "glycolytic",
                    "scheduled_day_hint": "sunday",
                    "scheduled_countdown_label": "D-18",
                    "conditioning_composition_policy": {
                        "stage2_composes_membership": True,
                        "source_phase": "GPP",
                    },
                }],
            }]
        },
        "candidate_pools": {
            "GPP": {"conditioning_slots": [{
                "role": "glycolytic", "selected": shadow, "alternates": [],
            }]}
        },
    }


def _codes(plan: str) -> set[str]:
    return {item["code"] for item in validate_stage2_output(planning_brief=_brief(), final_plan_text=plan)["errors"]}


def test_candidate_on_another_same_day_card_does_not_satisfy_conditioning_membership():
    codes = _codes(
        "D-18 (Sunday) — Strength\n"
        "- Shadowboxing Power Bursts: 10 x 15 sec work; 45 sec rest; RPE 9\n"
        "D-18 (Sunday) — Fight-pace conditioning\n"
        "- Invented Sled Circuit: 6 x 20 sec work; 60 sec rest; RPE 8\n"
    )
    assert "normal_conditioning_candidate_missing" in codes


def test_every_rendered_candidate_dose_contributes_to_session_workload():
    codes = _codes(
        "D-18 (Sunday) — Fight-pace conditioning\n"
        "- Shadowboxing Power Bursts: 10 x 15 sec work; 45 sec rest; RPE 9\n"
        "- Shadowboxing Power Bursts: 10 x 15 sec work; 45 sec rest; RPE 9\n"
        "- Shadowboxing Power Bursts: 10 x 15 sec work; 45 sec rest; RPE 9\n"
    )
    assert "normal_conditioning_combined_workload_exceeded" in codes


def test_underfill_reason_must_be_inside_the_owning_session_card():
    codes = _codes(
        "D-19 (Monday) — Recovery\n"
        "- Underfill: unrelated recovery constraint.\n"
        "D-18 (Sunday) — Fight-pace conditioning\n"
        "- Shadowboxing Power Bursts: 10 x 15 sec work; 45 sec rest; RPE 9\n"
    )
    assert "normal_conditioning_underfill_reason_missing" in codes


def test_general_packet_compacts_repeated_candidate_diagnostics_but_keeps_bank_evidence():
    brief = _brief()
    candidate = brief["candidate_pools"]["GPP"]["conditioning_slots"][0]["selected"]
    brief["candidate_pools"]["GPP"]["conditioning_slots"][0]["alternates"] = [
        {
            **deepcopy(candidate),
            "name": f"Eligible alternate {index}",
        }
        for index in range(1, 5)
    ]
    candidate["notes"] = "Keep guard and stance disciplined throughout the burst."
    candidate["selection_metadata"].update(
        {
            "tags": ["kickboxing", "mech_ballistic"],
            "equipment": ["heavy_bag"],
            "work_sec": 15,
            "rest_sec": 45,
            "rounds": 10,
            "mechanical_risk_tags": ["mech_ballistic"],
            "description": "A short sport-specific power burst.",
            "raw_score_trace": {"large_internal": "x" * 10_000},
            "_schema_source": "style_conditioning_bank.json",
        }
    )
    packet = build_stage2_finalizer_packet(
        stage2_payload={"athlete_model": {}}, planning_brief=brief
    )
    rendered = packet["selected_plan"]["normal_conditioning_composition"][0][
        "eligible_candidates_ranked"
    ]

    assert [option["name"] for option in rendered] == [
        "Shadowboxing Power Bursts",
        "Eligible alternate 1",
        "Eligible alternate 2",
        "Eligible alternate 3",
        "Eligible alternate 4",
    ]
    first = rendered[0]
    assert first["notes"].startswith("Keep guard")
    assert first["selection_metadata"]["description"] == "A short sport-specific power burst."
    assert first["selection_metadata"]["work_sec"] == 15
    assert first["selection_metadata"]["mechanical_risk_tags"] == ["mech_ballistic"]
    assert "raw_score_trace" not in first["selection_metadata"]
    assert "_schema_source" not in first["selection_metadata"]
