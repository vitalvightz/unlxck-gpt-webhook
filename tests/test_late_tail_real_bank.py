"""Production-shaped selection: real banks, real Stage 1, real calendar splice."""
import asyncio
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from fightcamp.conditioning import generate_conditioning_block
from fightcamp.strength import generate_strength_block
from fightcamp.stage2_payload import (
    _build_conditioning_slots, _build_late_tail_candidates, _build_strength_slots,
    _build_late_fight_allowed_exercises_by_day, build_planning_brief,
)
from fightcamp.session_composition import attach_late_fight_assignments
from fightcamp.planner_authority_integrity import late_physical_planner_preflight
from fightcamp.style_taper_governance import style_taper_window_for_days
from fightcamp.training_context import normalize_athlete_equipment_list


PHASE_DAYS = {"GPP": 6, "SPP": 13, "TAPER": 6}
EQUIPMENT = ["bands", "heavy_bag", "partner", "medicine_ball", "barbell",
             "kettlebell", "assault_bike", "rower"]
BANK = {item["name"]: item for item in json.loads(
    (Path(__file__).resolve().parents[1] / "data/style_taper_conditioning.json").read_text())}


def real_brief(sport="mma", **overrides):
    athlete = {
        "sport": sport, "fight_format": sport, "days_until_fight": 25,
        "style_tactical": ["pressure_fighter"], "style_technical": [sport],
        "tactical_style": "pressure_fighter", "key_goals": ["speed", "strength"],
        "weaknesses": ["footwork", "power"], "equipment": EQUIPMENT,
        "injuries": [], "restrictions": [], "fatigue": "low",
        "training_frequency": 5, "days_available": 5,
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": [], "plan_creation_weekday": "monday",
        "phase_weeks": {"GPP": 0, "SPP": 1, "TAPER": 0, "days": PHASE_DAYS},
        **overrides,
    }
    pools = {}
    for phase in PHASE_DAYS:
        flags = {**athlete, "phase": phase}
        _, _, why, grouped, _, reservoir = generate_conditioning_block(flags)
        block = {"why_log": why, "grouped_drills": grouped, "candidate_reservoir": reservoir}
        pools[phase] = {
            "strength_slots": _build_strength_slots(generate_strength_block(flags=flags), phase),
            "conditioning_slots": _build_conditioning_slots(block, phase),
            "late_tail_candidates": _build_late_tail_candidates(block, phase),
            "rehab_slots": [],
        }
    return build_planning_brief(
        athlete_model=athlete, restrictions=athlete["restrictions"],
        phase_briefs={phase: {"days": days, "weeks": days // 7,
                             "objective": "", "emphasize": [], "deprioritize": [],
                             "risk_flags": [], "selection_guardrails": {}}
                      for phase, days in PHASE_DAYS.items()},
        candidate_pools=pools, omission_ledger={}, rewrite_guidance={},
    )


def late_roles(brief):
    return [role for week in brief["weekly_role_map"]["weeks"]
            for role in week["session_roles"] if role.get("late_fight_tail_owned")]


@pytest.fixture(scope="module")
def mma_brief():
    return real_brief()


def assert_assignment(brief, role, sport):
    assignments = role["selected_exercise_assignments"]
    assert assignments, role
    day = int(role["scheduled_countdown_label"][2:])
    phase = "SPP" if day > 6 else "TAPER"
    for assignment in assignments:
        item = BANK[assignment["name"]]
        assert assignment["source_phase"] == phase
        assert phase in item["phases"]
        assert style_taper_window_for_days(day) in item["late_windows"]
        assert sport in item["tags"]
        assert set(normalize_athlete_equipment_list(item["equipment"])) <= set(normalize_athlete_equipment_list(brief["athlete_snapshot"]["equipment"]))
        if role["role_key"] in {"strength_touch_day", "neural_primer_day", "alactic_sharpness_day"}:
            assert item["system"] == "alactic"
        assert item["support_only"] is True and item["meaningful_stress"] is False
        assert item["lactate_load"] in {"low", "none"}
        slots = brief["candidate_pools"][phase]["late_tail_candidates"]
        option = next(slot["selected"] for slot in slots if slot["selected"]["name"] == item["name"])
        assert option["source"] == "style_taper"
        assert option["system"] == item["system"]
        for key in ("phases", "late_windows", "tags", "equipment", "impact_cost", "movement_cost",
                    "contact_level", "support_only", "meaningful_stress", "lactate_load"):
            assert option["selection_metadata"][key] == item[key]
        assert isinstance(option["bank_order"], int)
        assert "score_evidence" in option


def test_production_mma_d13_d7_d2(mma_brief):
    # Observed production roles; phase is resolved from Stage 1 day allocation,
    # never injected into the roles. Unspecified calendar inputs need not be guessed.
    brief = deepcopy(mma_brief)
    roles = [{"scheduled_countdown_label": f"D-{day}", "role_key": key,
              "category": "conditioning" if day == 2 else "strength",
              "late_fight_tail_owned": True}
             for day, key in ((13, "strength_touch_day"), (7, "neural_primer_day"), (2, "alactic_sharpness_day"))]
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": roles, "athlete_model": brief["athlete_snapshot"]},
        candidate_pools=brief["candidate_pools"])
    attach_late_fight_assignments(roles, assignments)
    brief["weekly_role_map"] = {"weeks": [{"session_roles": roles}]}
    roles = {r["scheduled_countdown_label"]: r for r in roles}
    for day, key in ((13, "strength_touch_day"), (7, "neural_primer_day"), (2, "alactic_sharpness_day")):
        role = roles[f"D-{day}"]
        assert role["role_key"] == key
        assert_assignment(brief, role, "mma")
        print(day, role["selected_exercise_assignments"])
    assert not late_physical_planner_preflight(brief)


@pytest.mark.parametrize("sport", ["boxing", "kickboxing", "muay_thai", "mma", "wrestling", "bjj"])
def test_all_sports_real_bank(sport, mma_brief):
    brief = mma_brief if sport == "mma" else real_brief(sport, equipment=[*EQUIPMENT, "mat"])
    physical = [role for role in late_roles(brief) if role["category"] in {"strength", "conditioning"}]
    assert physical
    for role in physical:
        assert_assignment(brief, role, sport)
    assert not late_physical_planner_preflight(brief)
    print(sport, [(r["scheduled_countdown_label"], [a["name"] for a in r["selected_exercise_assignments"]]) for r in physical])


def test_empty_membership_still_renders_stage2(mma_brief):
    """A missing exposure is admin-review material, not a reason to skip Stage 2.

    Only AUTHORITY_RELEASE_HOLD_CODES (genuinely unsafe scheduled output) may
    prevent the model call. Skipping it here produced a plan that reported
    stage2_pass with no Stage 2 attempt and no Stage 2 text.
    """
    from api.stage2_automation import OpenAIStage2Automator
    brief = deepcopy(mma_brief)
    role = next(role for role in late_roles(brief) if role["role_key"] == "alactic_sharpness_day")
    role["selected_exercise_assignments"] = []
    client = AsyncMock()
    automator = OpenAIStage2Automator(client=client, model="test")
    automator._generate_text = AsyncMock(return_value=("# Stage 2 plan", {}))
    result = asyncio.run(automator.finalize(stage1_result={
        "planning_brief": brief, "stage2_payload": {}, "stage2_handoff_text": "test", "plan_text": "draft",
    }))
    automator._generate_text.assert_called_once()
    assert result["stage2_attempt_count"] == 1
    assert result["final_plan_text"] == "# Stage 2 plan"
    assert result["draft_plan_text"] == "draft"
    codes = {
        str(item.get("code"))
        for key in ("errors", "review_flags", "warnings", "blocking_warnings")
        for item in result["stage2_validator_report"].get(key) or []
    }
    assert "late_physical_role_missing_assignment" in codes


@pytest.mark.parametrize("day", [13, 7, 5, 2, 1])
def test_each_late_window_uses_real_qualified_reservoir(mma_brief, day):
    role = {"scheduled_countdown_label": f"D-{day}", "role_key": "neural_primer_day",
            "category": "strength", "late_fight_tail_owned": True}
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role], "athlete_model": mma_brief["athlete_snapshot"]},
        candidate_pools=mma_brief["candidate_pools"])
    attach_late_fight_assignments([role], assignments)
    assert_assignment(mma_brief, role, "mma")


def test_original_equipment_legal_reservoir_has_no_d2_alactic_candidate(mma_brief):
    # Prove the narrow content exception: remove only the new item, leaving all
    # real Stage 1 winners and original alternates/qualified support untouched.
    pools = deepcopy(mma_brief["candidate_pools"])
    for pool in pools.values():
        pool["late_tail_candidates"] = [s for s in pool["late_tail_candidates"]
                                         if s["selected"]["name"] != "Standing Stance-Set Cue"]
        pool["conditioning_slots"] = [s for s in pool["conditioning_slots"]
                                      if s["selected"]["name"] != "Standing Stance-Set Cue"]
        for slot in pool["conditioning_slots"]:
            slot["alternates"] = [a for a in slot["alternates"] if a["name"] != "Standing Stance-Set Cue"]
    role = {"scheduled_countdown_label": "D-2", "role_key": "alactic_sharpness_day",
            "category": "conditioning", "late_fight_tail_owned": True}
    _, assignments = _build_late_fight_allowed_exercises_by_day(
        spec={"visible_session_sequence": [role], "athlete_model": mma_brief["athlete_snapshot"]},
        candidate_pools=pools)
    assert assignments["D-2"] == []
    existing = [item for name, item in BANK.items() if name != "Standing Stance-Set Cue"
                and item["system"] == "alactic" and "d4_to_d2" in item["late_windows"]]
    assert [item["name"] for item in existing] == ["Hip-Heist-Re-square"]
    assert existing[0]["equipment"] == ["mat"]
    assert "mat" not in mma_brief["athlete_snapshot"]["equipment"]


def test_direct_countdown_preflight_uses_final_visible_sequence(mma_brief):
    brief = deepcopy(mma_brief)
    brief["late_fight_session_sequence"] = [{
        "scheduled_countdown_label": "D-2", "role_key": "alactic_sharpness_day",
        "category": "conditioning", "selected_exercise_assignments": [],
    }]
    findings = late_physical_planner_preflight(brief)
    assert [item["code"] for item in findings] == ["late_physical_role_missing_assignment"]
    assert findings[0]["scheduled_phase"] == "TAPER"


def test_original_bank_authority_checks_style_taper_phase(mma_brief):
    brief = deepcopy(mma_brief)
    role = {"scheduled_countdown_label": "D-7", "role_key": "neural_primer_day",
            "category": "strength", "late_fight_tail_owned": True,
            "selected_exercise_assignments": [{"name": "Standing Stance-Set Cue",
                                                "slot_group": "conditioning_slots", "source_phase": "SPP"}]}
    brief["weekly_role_map"] = {"weeks": [{"session_roles": [role]}]}
    assert "selected_exercise_phase_ineligible" in {f["code"] for f in late_physical_planner_preflight(brief)}
