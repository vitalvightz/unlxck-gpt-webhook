from __future__ import annotations

from types import SimpleNamespace

from fightcamp.late_camp_transition import apply_late_camp_transition_overlay
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


def _late_gap_role_map(*, unused_day: dict | None = None, week_overrides: dict | None = None) -> dict:
    week = {
        "week_index": 1,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": "monday", "d_day": 20},
            {"weekday": "tuesday", "d_day": 19},
            {"weekday": "wednesday", "d_day": 18},
            {"weekday": "thursday", "d_day": 17},
            {"weekday": "friday", "d_day": 16},
        ],
        "declared_training_days": ["monday", "wednesday", "friday"],
        "intentionally_unused_days": [unused_day or {"day": "wednesday", "role": "off_day"}],
        "session_roles": [
            {
                "session_index": 1,
                "category": "conditioning",
                "role_key": "fight_pace_repeatability_day",
                "preferred_system": "glycolytic",
                "scheduled_day_hint": "monday",
                "combat_pressure_floor": True,
                "mandatory_hard_conditioning_exposure": True,
                "prescribed_intensity_rpe": "8-9",
                "prescribed_dose": "4-6 x 2-3 min fight-pace on / 60 sec off @ RPE 8-9",
                "athlete_facing_label": "Fight-pace conditioning",
            },
            {
                "session_index": 2,
                "category": "strength",
                "role_key": "neural_plus_strength_day",
                "scheduled_day_hint": "friday",
            },
        ],
    }
    week.update(week_overrides or {})
    return {"weeks": [week]}


def _single_role_map(role: dict, *, d_day: int, weekday: str = "monday") -> dict:
    return {
        "weeks": [
            {
                "week_index": 1,
                "phase": "SPP",
                "calendar_days": [{"weekday": weekday, "d_day": d_day}],
                "declared_training_days": [weekday],
                "intentionally_unused_days": [],
                "session_roles": [role],
            }
        ]
    }


def _late_gap_athlete(**overrides) -> dict:
    athlete = {
        "sport": "boxing",
        "days_until_fight": 21,
        "training_days": ["monday", "wednesday", "friday"],
        "key_goals": ["conditioning"],
        "weaknesses": ["gas tank"],
        "fatigue": "low",
        "cut_severity_bucket": "low",
        "injury_mode": "full_plan",
    }
    athlete.update(overrides)
    return athlete


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


def test_d21_to_d18_combat_pressure_floor_is_preserved():
    role_map = _late_gap_role_map()
    context = apply_late_camp_transition_overlay(role_map, _late_gap_athlete())

    role = role_map["weeks"][0]["session_roles"][0]
    assert role["role_key"] == "fight_pace_repeatability_day"
    assert role["combat_pressure_floor"] is True
    assert role["mandatory_hard_conditioning_exposure"] is True
    assert role["prescribed_intensity_rpe"] == "8-9"
    assert role["athlete_facing_label"] == "Fight-pace conditioning"
    assert any("pressure_floor_preserved_d20" in action for action in context["weeks"][0]["actions"])


def test_morphed_rhythm_touch_drops_hard_conditioning_metadata():
    hard_role = {
        "session_index": 1,
        "category": "conditioning",
        "role_key": "fight_pace_repeatability_day",
        "preferred_system": "glycolytic",
        "scheduled_day_hint": "monday",
        "combat_pressure_floor": True,
        "mandatory_hard_conditioning_exposure": True,
        "prescribed_intensity_rpe": "8-9",
        "prescribed_dose": "4-6 x 2-3 min fight-pace on / 60 sec off @ RPE 8-9",
        "floor_purpose": "Controlled fight-pace pressure exposure.",
        "floor_stop_rule": "Stop when technique clearly drops.",
    }
    role_map = _single_role_map(hard_role, d_day=11)

    apply_late_camp_transition_overlay(role_map, _late_gap_athlete())

    role = role_map["weeks"][0]["session_roles"][0]
    assert role["role_key"] == "light_fight_pace_touch_day"
    assert role["athlete_facing_label"] == "Technical Rhythm Touch"
    for stale_key in (
        "combat_pressure_floor",
        "mandatory_hard_conditioning_exposure",
        "prescribed_intensity_rpe",
        "prescribed_dose",
        "floor_purpose",
        "floor_stop_rule",
    ):
        assert stale_key not in role


def test_safe_unused_late_day_can_receive_low_cost_support_insert():
    role_map = _late_gap_role_map()

    apply_late_camp_transition_overlay(role_map, _late_gap_athlete())

    support_roles = [
        role for role in role_map["weeks"][0]["session_roles"] if role.get("category") == "support_insert"
    ]
    assert len(support_roles) == 1
    assert support_roles[0]["countdown_offset"] == 18
    assert role_map["weeks"][0]["intentionally_unused_days"] == []


def test_safety_or_compression_unused_days_are_not_refilled():
    cases = [
        (_late_gap_athlete(fatigue="moderate"), {}),
        (_late_gap_athlete(weight_cut_risk=True, weight_cut_pct=3.0, readiness_flags=["active_weight_cut"]), {}),
        (
            _late_gap_athlete(
                readiness_flags=["injury_management"],
                injuries=["moderate knee sprain"],
                parsed_injuries=[{"injury_type": "sprain", "severity": "moderate"}],
            ),
            {"intentional_compression": {"active": True, "reason_codes": ["injury_management"]}},
        ),
    ]

    for athlete, week_overrides in cases:
        role_map = _late_gap_role_map(week_overrides=week_overrides)
        apply_late_camp_transition_overlay(role_map, athlete)
        support_roles = [
            role for role in role_map["weeks"][0]["session_roles"] if role.get("category") == "support_insert"
        ]
        assert support_roles == []
        assert role_map["weeks"][0]["intentionally_unused_days"] == [{"day": "wednesday", "role": "off_day"}]


def test_unused_day_safety_reason_blocks_late_transition_insert():
    role_map = _late_gap_role_map(
        unused_day={
            "day": "wednesday",
            "role": "off_day",
            "reason_codes": ["hard_sparring_compression"],
        }
    )

    apply_late_camp_transition_overlay(role_map, _late_gap_athlete())

    support_roles = [
        role for role in role_map["weeks"][0]["session_roles"] if role.get("category") == "support_insert"
    ]
    assert support_roles == []
    assert role_map["weeks"][0]["intentionally_unused_days"][0]["reason_codes"] == [
        "hard_sparring_compression"
    ]


def test_surface_injury_signal_does_not_create_mobility_rehab_insert():
    role_map = _late_gap_role_map()
    athlete = _late_gap_athlete(
        key_goals=["mobility"],
        injuries=["stable shin graze"],
        parsed_injuries=[{"injury_type": "graze", "severity": "low"}],
    )

    apply_late_camp_transition_overlay(role_map, athlete)

    role_keys = [role.get("role_key") for role in role_map["weeks"][0]["session_roles"]]
    assert "mobility_rehab" not in role_keys
    assert "joint_prep" not in role_keys


def test_hard_sparring_d17_and_closer_stays_technical_only():
    role = {
        "session_index": 1,
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "scheduled_day_hint": "monday",
        "athlete_facing_label": "Coach-led sparring",
    }
    role_map = _single_role_map(role, d_day=17)

    apply_late_camp_transition_overlay(role_map, _late_gap_athlete())

    updated = role_map["weeks"][0]["session_roles"][0]
    assert updated["role_key"] == "hard_sparring_day"
    assert updated["late_camp_transition"] is True
    assert "technical-only" in updated["display_text"]
    assert "No extra S&C" in updated["display_text"]

