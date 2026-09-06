from __future__ import annotations

from datetime import datetime

from fightcamp import conditioning
from fightcamp import stage2_planning_brief as stage2_planning_brief_module
import fightcamp.empty_combat_week_policy as policy
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import build_planning_brief, build_stage2_payload
from fightcamp.stage2_role_map import _build_weekly_role_map
from fightcamp.training_context import TrainingContext


LIMITER = {"key": "aerobic_repeatability"}


def _athlete(**overrides):
    data = {
        "sport": "boxing",
        "status": "amateur",
        "record": "0-0",
        "competitive_maturity": "novice_amateur",
        "rounds_format": "3 x 3",
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
        "readiness_flags": ["moderate_fatigue", "reduced_contact_requested"],
        "key_goals": ["conditioning", "speed"],
        "primary_goal": "conditioning",
        "weaknesses": ["gas_tank", "trunk_strength"],
        "training_frequency": 4,
        "training_days": ["Monday", "Friday", "Wednesday", "Sunday", "Thursday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "technical_skill_days": [],
        "tactical_styles": ["distance_striker"],
    }
    data.update(overrides)
    return data


def _progression():
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase": "GPP",
                "stage_key": "general_capacity",
                "span_days": 7,
                "session_counts": {"strength": 2, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["aerobic", "glycolytic", "alactic"],
            },
            {
                "week_index": 2,
                "phase": "SPP",
                "stage_key": "specific_density_to_peak",
                "span_days": 8,
                "session_counts": {"strength": 1, "conditioning": 2, "recovery": 1},
                "conditioning_sequence": ["glycolytic", "alactic", "aerobic"],
            },
            {
                "week_index": 3,
                "phase": "TAPER",
                "stage_key": "fight_week_survival_rhythm",
                "span_days": 7,
                "session_counts": {"strength": 1, "conditioning": 1, "recovery": 1},
                "conditioning_sequence": ["alactic", "aerobic", "glycolytic"],
            },
        ]
    }


def test_pressure_eligibility_can_start_well_before_d21(monkeypatch):
    monkeypatch.setattr(policy, "_bridge_allows_glycolytic_on_day", lambda athlete, d_day: True)
    athlete = _athlete(training_days=["Monday", "Wednesday"])
    week = {
        "phase": "GPP",
        "declared_training_days": ["Monday", "Wednesday"],
        "calendar_days": [
            {"weekday": "monday", "d_day": 35},
            {"weekday": "wednesday", "d_day": 33},
        ],
    }

    assert policy._earliest_safe_pressure_slot(week, athlete) == ("monday", 35)
    assert not hasattr(policy, "_MIN_DEVELOPMENT_D_DAY")
    assert not hasattr(policy, "_move_pressure_to_early_slot")


def test_canonical_bridge_not_local_cutoff_blocks_d7_inward():
    athlete = _athlete(
        fatigue="low",
        readiness_flags=[],
        training_days=["Monday"],
    )
    week = {
        "phase": "SPP",
        "declared_training_days": ["Monday"],
        "calendar_days": [{"weekday": "monday", "d_day": 7}],
    }

    assert policy._earliest_safe_pressure_slot(week, athlete) is None


def test_body_mass_and_moderate_fatigue_do_not_force_low_impact_modality():
    assert policy._prefer_low_impact_repeatability(_athlete(body_mass_kg=103)) is False
    assert policy._prefer_low_impact_repeatability(
        _athlete(fatigue="moderate", readiness_flags=["moderate_fatigue"])
    ) is False
    assert policy._prefer_low_impact_repeatability(
        _athlete(fatigue="low", readiness_flags=[], body_mass_kg=80)
    ) is False


def test_real_injury_restriction_can_bias_modality_without_downgrading_system():
    restriction = {"restriction": "single_leg_loading", "region": "knee"}
    athlete = _athlete(
        fatigue="low",
        readiness_flags=["baseline"],
        body_mass_kg=80,
        injury_restrictions=[restriction],
    )
    assert policy._prefer_low_impact_repeatability(athlete) is True

    role_map = _build_weekly_role_map(athlete, _progression(), LIMITER)
    week = role_map["weeks"][0]
    pressure = next(
        role
        for role in week["session_roles"]
        if role.get("upgraded_from_hard_stimulus_deficit")
    )

    assert pressure["low_impact_preferred"] is True
    assert "low_impact" in pressure["preferred_tags"]
    assert pressure["preferred_system"] == "glycolytic"
    assert pressure.get("mandatory_hard_conditioning_exposure") is True


def test_exact_profile_keeps_hard_system_without_body_mass_low_impact_bias():
    role_map = _build_weekly_role_map(_athlete(body_mass_kg=103), _progression(), LIMITER)
    week = role_map["weeks"][0]
    pressure = next(
        role
        for role in week["session_roles"]
        if role.get("upgraded_from_hard_stimulus_deficit")
    )

    assert pressure["preferred_system"] == "glycolytic"
    assert pressure["low_impact_preferred"] is False
    assert "low_impact" not in pressure["preferred_tags"]
    assert "distance_striker" in pressure["preferred_tags"]
    assert pressure.get("mandatory_hard_conditioning_exposure") is True


def _real_training_context() -> TrainingContext:
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
        style_technical=["boxing"],
        style_tactical=["distance_striker"],
        weaknesses=["gas_tank", "trunk_strength"],
        equipment=["bodyweight", "partner", "heavy_bag", "assault_bike", "rower"],
        weight_cut_risk=False,
        weight_cut_pct=2.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["conditioning", "speed"],
        training_preference="",
        mental_block=[],
        age=23,
        weight=103.0,
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


def _real_conditioning_block(context: TrainingContext, phase: str) -> dict:
    flags = {
        **context.to_flags(),
        "phase": phase,
        "sport": "boxing",
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


def test_real_stage1_to_finalizer_path_preserves_hard_distance_striker_contract(monkeypatch):
    # Freeze plan creation so the real calendar is the exact D-22 profile rather
    # than depending on the date the test suite happens to run.
    monkeypatch.setattr(
        stage2_planning_brief_module,
        "_utc_now",
        lambda: datetime(2026, 9, 6, 10, 0),
    )
    context = _real_training_context()
    phase_weeks = context.phase_weeks
    conditioning_blocks = {
        phase: _real_conditioning_block(context, phase)
        for phase in ("GPP", "SPP", "TAPER")
    }

    payload = build_stage2_payload(
        training_context=context,
        mapped_format="boxing",
        record="0-0",
        rounds_format="3 x 3",
        camp_len=4,
        short_notice=False,
        restrictions=[],
        phase_weeks=phase_weeks,
        strength_blocks={"GPP": None, "SPP": None, "TAPER": None},
        conditioning_blocks=conditioning_blocks,
        rehab_blocks={},
    )

    gpp_slots = payload["candidate_pools"]["GPP"]["conditioning_slots"]
    hard_slots = []
    for slot in gpp_slots:
        selected = slot.get("selected") or {}
        metadata = selected.get("selection_metadata") or {}
        if (
            str(slot.get("role") or "").lower() == "glycolytic"
            and float(metadata.get("rpe") or 0) >= 7
            and str(metadata.get("lactate_load") or "").lower() == "high"
        ):
            hard_slots.append(slot)

    assert hard_slots, [slot.get("selected", {}).get("name") for slot in gpp_slots]
    assert any(
        "distance_striker" in (slot.get("selected", {}).get("selection_metadata", {}).get("tags") or [])
        for slot in hard_slots
    )

    brief = build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload["restrictions"],
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )

    hard_role = next(
        role
        for week in brief["weekly_role_map"]["weeks"]
        for role in week["session_roles"]
        if role.get("upgraded_from_hard_stimulus_deficit")
    )
    assert hard_role["preferred_system"] == "glycolytic"
    assert hard_role["mandatory_hard_conditioning_exposure"] is True
    assert hard_role["prescribed_intensity_rpe"] in {"8", "8-9"}
    assert "distance_striker" in hard_role["preferred_tags"]

    packet = build_stage2_finalizer_packet(
        stage2_payload=payload,
        planning_brief=brief,
    )
    packet_hard_role = next(
        role
        for week in packet["selected_plan"]["weekly_role_map"]["weeks"]
        for role in week["session_roles"]
        if role.get("mandatory_hard_conditioning_exposure") is True
    )

    # The LLM boundary must receive the deterministic hard-dose contract. This is
    # what prevents the finalizer from turning the required role back into Zone 2.
    assert packet_hard_role["preferred_system"] == "glycolytic"
    assert packet_hard_role["prescribed_intensity_rpe"] in {"8", "8-9"}
    assert "hard" in packet_hard_role["prescribed_dose"].lower() or "fight-pace" in packet_hard_role["prescribed_dose"].lower()
    assert packet_hard_role["floor_stop_rule"]
    assert any(
        "mandatory_hard_conditioning_exposure" in rule
        for rule in packet["hard_rules"]
    )
