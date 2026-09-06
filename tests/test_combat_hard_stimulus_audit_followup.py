from __future__ import annotations

from datetime import datetime

import pytest

from fightcamp import conditioning
import fightcamp.empty_combat_week_policy as policy
from fightcamp import stage2_planning_brief as stage2_planning_brief_module
from fightcamp import stage2_role_map
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import build_planning_brief, build_stage2_payload
from fightcamp.training_context import TrainingContext


LIMITER = {"key": "aerobic_repeatability"}


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "fight_format": "boxing",
        "rounds_format": "3 x 3",
        "status": "amateur",
        "record": "0-0",
        "days_until_fight": 22,
        "fight_date": "2026-09-28",
        "plan_creation_weekday": "sunday",
        "fatigue": "moderate",
        "cut_severity_bucket": "low",
        "weight_cut_pct": 2.0,
        "weight_cut_risk": False,
        "injury_mode": "full_plan",
        "injuries": [],
        "injury_restrictions": [],
        "readiness_flags": ["moderate_fatigue"],
        "primary_goal": "conditioning",
        "key_goals": ["conditioning", "speed"],
        "weaknesses": ["gas_tank", "trunk_strength"],
        "training_frequency": 4,
        "training_days": ["Monday", "Tuesday", "Wednesday", "Thursday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "technical_skill_days": [],
        "tactical_styles": ["distance_striker"],
    }
    athlete.update(overrides)
    return athlete


def _mandatory_role():
    return {
        "session_index": 1,
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_pool": "conditioning_slots",
        "preferred_system": "glycolytic",
        "preferred_tags": ["glycolytic", "fight_pace", "repeatability", "gas_tank"],
        "mandatory_hard_conditioning_exposure": True,
        "upgraded_from_hard_stimulus_deficit": True,
        "placement_rule": "Use the main density slot.",
        "governance": {},
    }


def _support_role(index: int, category: str = "strength"):
    role_key = "primary_strength_day" if category == "strength" else "recovery_reset_day"
    return {
        "session_index": index,
        "category": category,
        "role_key": role_key,
        "preferred_pool": "strength_slots" if category == "strength" else "rehab_slots_or_recovery_only",
        "placement_rule": "normal placement",
        "governance": {},
    }


def test_mixed_bridge_week_places_mandatory_hard_role_only_on_exact_legal_day(monkeypatch):
    monkeypatch.setattr(policy, "_bridge_allows_glycolytic_on_day", lambda athlete, d_day: d_day >= 18)
    athlete = _athlete(training_days=["Monday", "Tuesday", "Wednesday"])
    week = {
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "monday", "d_day": 18},
            {"weekday": "tuesday", "d_day": 17},
            {"weekday": "wednesday", "d_day": 16},
        ],
        "declared_training_days": ["Monday", "Tuesday", "Wednesday"],
    }
    roles = [_support_role(1), _mandatory_role(), _support_role(3, "recovery")]

    assigned = stage2_role_map._assign_declared_day_hints(
        roles,
        athlete,
        hard_sparring_plan=[],
        week_entry=week,
    )
    hard = next(role for role in assigned if role.get("mandatory_hard_conditioning_exposure"))

    assert hard["scheduled_day_hint"] == "monday"
    assert hard["scheduled_day_hint"] not in {"tuesday", "wednesday"}


def test_mixed_bridge_week_never_falls_back_onto_forbidden_day(monkeypatch):
    monkeypatch.setattr(policy, "_bridge_allows_glycolytic_on_day", lambda athlete, d_day: False)
    athlete = _athlete(training_days=["Monday", "Tuesday"])
    week = {
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "monday", "d_day": 17},
            {"weekday": "tuesday", "d_day": 16},
        ],
        "declared_training_days": ["Monday", "Tuesday"],
    }
    assigned = stage2_role_map._assign_declared_day_hints(
        [_mandatory_role(), _support_role(2)],
        athlete,
        hard_sparring_plan=[],
        week_entry=week,
    )
    hard = next(role for role in assigned if role.get("mandatory_hard_conditioning_exposure"))
    assert hard.get("scheduled_day_hint", "") == ""


def test_explicit_hard_pad_or_high_rpe_external_work_counts_as_hard_load():
    week = {"phase": "GPP"}
    hard_pad = _athlete(
        session_loads_by_day={"monday": {"session_type": "pads", "rpe": 9}},
    )
    technical = _athlete(
        session_types_by_day={"monday": "technical"},
    )

    assert policy._effective_hard_exposure_days(week, hard_pad) == {"monday"}
    assert policy._effective_hard_exposure_days(week, technical) == set()


def test_one_external_hard_exposure_uses_budget_instead_of_blanket_yes_or_no():
    week = {"phase": "GPP"}
    normal_budget = _athlete(
        hard_sparring_days=["Monday"],
        training_frequency=4,
        training_days=["Monday", "Tuesday", "Thursday", "Friday"],
    )
    roomy_low_risk = _athlete(
        hard_sparring_days=["Monday"],
        training_frequency=5,
        training_days=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        fatigue="low",
        readiness_flags=[],
        cut_severity_bucket="low",
        weight_cut_pct=0.0,
    )

    assert policy._weekly_hard_exposure_target(week, normal_budget) == 1
    assert policy._hard_stimulus_deficit(week, normal_budget) is False
    assert policy._weekly_hard_exposure_target(week, roomy_low_risk) == 2
    assert policy._hard_stimulus_deficit(week, roomy_low_risk) is True


@pytest.mark.parametrize(
    ("sport", "rounds_format", "expected_fragment"),
    [
        ("boxing", "3 x 3", "3 min"),
        ("mma", "3 x 5", "5 min mma format"),
        ("wrestling", "3 x 2", "2 min"),
        ("bjj", "1 x 5", "5 min bjj format"),
    ],
)
def test_spp_hard_dose_uses_real_bout_format(sport, rounds_format, expected_fragment):
    metadata = policy._sport_specific_pressure_metadata(
        _athlete(sport=sport, fight_format=sport, rounds_format=rounds_format),
        "SPP",
    )
    assert metadata["dose_basis"] == "athlete_rounds_format"
    assert expected_fragment in metadata["prescribed_dose"].lower()
    assert metadata["prescribed_intensity_rpe"] == "8-9"


def _context(sport: str) -> TrainingContext:
    phase_weeks = {
        "GPP": 1,
        "SPP": 1,
        "TAPER": 1,
        "days": {"GPP": 7, "SPP": 8, "TAPER": 7},
    }
    return TrainingContext(
        fatigue="moderate",
        training_frequency=4,
        days_available=5,
        training_days=["Monday", "Friday", "Wednesday", "Sunday", "Thursday"],
        injuries=[],
        style_technical=[sport],
        style_tactical=[],
        weaknesses=["gas_tank", "trunk_strength"],
        equipment=["bodyweight", "partner", "heavy_bag", "assault_bike", "rower"],
        weight_cut_risk=False,
        weight_cut_pct=2.0,
        fight_format=sport,
        status="amateur",
        key_goals=["conditioning", "speed"],
        training_preference="",
        mental_block=[],
        age=23,
        weight=90.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks=phase_weeks,
        days_until_fight=22,
        hard_sparring_days=[],
        support_work_days=[],
        technical_skill_days=[],
        athlete_timezone="Europe/London",
        next_fight_date="2026-09-28",
        injury_restrictions=[],
    )


def _conditioning_block(context: TrainingContext, sport: str, phase: str) -> dict:
    flags = {
        **context.to_flags(),
        "phase": phase,
        "sport": sport,
        "time_to_fight_days": context.days_until_fight,
        "primary_goal": "conditioning",
        "priority_focus": {
            "primary_goal": "conditioning",
            "primary_weakness": "gas_tank",
            "derived_clarification_tags": ["glycolytic", "work_capacity", "conditioning"],
        },
    }
    _text, _names, why_log, grouped, missing, reservoir = conditioning.generate_conditioning_block(flags)
    return {
        "grouped_drills": grouped,
        "why_log": why_log,
        "candidate_reservoir": reservoir,
        "missing_systems": missing,
    }


@pytest.mark.parametrize(
    ("sport", "rounds_format"),
    [
        ("boxing", "3 x 3"),
        ("mma", "3 x 5"),
        ("bjj", "1 x 5"),
    ],
)
def test_real_stage1_payload_brief_finalizer_path_is_not_boxing_only(
    monkeypatch, sport, rounds_format
):
    monkeypatch.setattr(
        stage2_planning_brief_module,
        "_utc_now",
        lambda: datetime(2026, 9, 6, 10, 0),
    )
    context = _context(sport)
    blocks = {
        phase: _conditioning_block(context, sport, phase)
        for phase in ("GPP", "SPP", "TAPER")
    }
    payload = build_stage2_payload(
        training_context=context,
        mapped_format=sport,
        record="0-0",
        rounds_format=rounds_format,
        camp_len=4,
        short_notice=False,
        restrictions=[],
        phase_weeks=context.phase_weeks,
        strength_blocks={"GPP": None, "SPP": None, "TAPER": None},
        conditioning_blocks=blocks,
        rehab_blocks={},
    )
    brief = build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload["restrictions"],
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )
    hard_roles = [
        role
        for week in brief["weekly_role_map"]["weeks"]
        for role in week["session_roles"]
        if role.get("mandatory_hard_conditioning_exposure") is True
    ]
    assert hard_roles, sport
    assert all(role.get("preferred_system") == "glycolytic" for role in hard_roles)

    packet = build_stage2_finalizer_packet(stage2_payload=payload, planning_brief=brief)
    packet_hard_roles = [
        role
        for week in packet["selected_plan"]["weekly_role_map"]["weeks"]
        for role in week["session_roles"]
        if role.get("mandatory_hard_conditioning_exposure") is True
    ]
    assert packet_hard_roles, sport
    assert all(role.get("floor_stop_rule") for role in packet_hard_roles)
