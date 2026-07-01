from __future__ import annotations

from types import SimpleNamespace

from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_payload import build_planning_brief, build_stage2_payload
from fightcamp.training_context import TrainingContext
from fightcamp.weekly_plan_render import render_weekly_schedule_section


def _normal_camp_transition_brief() -> dict:
    phase_weeks = {
        "GPP": 1,
        "SPP": 2,
        "TAPER": 1,
        "days": {"GPP": 7, "SPP": 14, "TAPER": 7},
    }
    training_context = TrainingContext(
        fatigue="low",
        training_frequency=3,
        days_available=6,
        training_days=["Mon", "Tue", "Thu", "Fri", "Sat"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure"],
        weaknesses=["gas tank", "power"],
        equipment=["bodyweight", "medicine_ball", "bands", "sled"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["power", "conditioning"],
        training_preference="short sessions",
        mental_block=[],
        age=25,
        weight=70.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks=phase_weeks,
        days_until_fight=28,
        hard_sparring_days=["Tue"],
        support_work_days=["Thu"],
    )
    payload = build_stage2_payload(
        training_context=training_context,
        mapped_format="boxing",
        record="0-0",
        rounds_format="3x3",
        camp_len=4,
        short_notice=False,
        restrictions=[],
        phase_weeks=phase_weeks,
        strength_blocks={},
        conditioning_blocks={},
        rehab_blocks={},
    )
    return build_planning_brief(
        athlete_model=payload["athlete_model"],
        restrictions=payload["restrictions"],
        phase_briefs=payload["phase_briefs"],
        candidate_pools=payload["candidate_pools"],
        omission_ledger=payload["omission_ledger"],
        rewrite_guidance=payload["rewrite_guidance"],
    )


def test_normal_camp_late_weeks_morph_without_switching_payloads():
    brief = _normal_camp_transition_brief()

    assert brief.get("payload_variant") is None
    transition = brief["late_camp_transition"]
    assert transition["active"] is True
    assert transition["model"] == "normal_camp_taper_morph.v1"
    assert transition["carried_focus"] == ["power / speed", "gas tank"]

    weeks = brief["weekly_role_map"]["weeks"]
    late_spp = next(week for week in weeks if week.get("countdown_range") == [13, 7])
    roles = late_spp["session_roles"]

    assert any(
        role.get("role_key") == "strength_touch_day"
        and role.get("transition_from_role_key") == "neural_plus_strength_day"
        and role.get("athlete_facing_label") == "Power Transfer Touch"
        for role in roles
    )
    assert any(
        role.get("role_key") == "light_fight_pace_touch_day"
        and role.get("transition_from_role_key") == "fight_pace_repeatability_day"
        and role.get("athlete_facing_label") == "Technical Rhythm Touch"
        for role in roles
    )
    assert any(
        role.get("category") == "support_insert"
        and role.get("late_camp_transition") is True
        and "Carry power / speed" in role.get("transition_continuity", "")
        for role in roles
    )


def test_normal_camp_transition_is_compact_finalizer_context():
    brief = _normal_camp_transition_brief()

    packet = build_stage2_finalizer_packet(stage2_payload={}, planning_brief=brief)

    selected = packet["selected_plan"]
    assert selected["late_camp_transition"]["active"] is True
    assert any("taper morph" in rule for rule in packet["hard_rules"])
    compact_roles = [
        role
        for week in selected["weekly_role_map"]["weeks"]
        for role in week.get("session_roles", [])
        if role.get("late_camp_transition") is True
    ]
    assert compact_roles
    assert all("transition_continuity" in role for role in compact_roles)


def test_transition_support_inserts_render_real_prescription_text():
    brief = _normal_camp_transition_brief()
    rendered = render_weekly_schedule_section(
        planning_brief=brief,
        blocks=SimpleNamespace(strength_blocks={}, conditioning_blocks={}),
    )

    assert "Fight Tactical Watch" in rendered or "Tactical Cue Card" in rendered
    assert "Purpose: Carry power / speed" in rendered
    assert "Coach-led session aligned with this week's focus" not in rendered

