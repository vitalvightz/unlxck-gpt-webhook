from __future__ import annotations

from fightcamp import stage2_payload as stage2_payload_module
from fightcamp.gap_fill_inserts import (
    LOW_COST_AEROBIC_INSERTS,
    LOW_COST_RECOVERY_INSERTS,
    PHYSICAL_INSERTS,
    TACTICAL_INSERTS,
    ZERO_COST_INSERTS,
    _allowed_inserts,
    apply_gap_fill_inserts,
    select_gap_fill_insert,
)
from fightcamp.stage2_payload import _is_meaningful_stressor, build_stage2_payload
from fightcamp.training_context import TrainingContext


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "status": "professional",
        "training_days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"],
        "hard_sparring_days": [],
        "fatigue": "low",
        "fatigue_level": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": [],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
        "days_until_fight": 21,
        "plan_creation_weekday": "monday",
    }
    athlete.update(overrides)
    return athlete


def _session(offset: int, role_key: str = "strength_touch_day") -> dict:
    return {
        "session_index": 1,
        "category": "strength" if role_key == "strength_touch_day" else "recovery",
        "role_key": role_key,
        "scheduled_day_hint": "monday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def _insert_roles(sequence: list[dict]) -> list[dict]:
    return [role for role in sequence if role.get("category") == "support_insert"]


def _training_context(days: int) -> TrainingContext:
    return TrainingContext(
        fatigue="moderate",
        training_frequency=5,
        days_available=5,
        training_days=["Mon", "Tue", "Wed", "Thu", "Fri"],
        injuries=[],
        style_technical=["boxing"],
        style_tactical=["pressure"],
        weaknesses=["cardio"],
        equipment=["bodyweight", "dumbbells"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["power"],
        training_preference="short sessions",
        mental_block=[],
        age=26,
        weight=155.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 0, "SPP": 0, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": days}},
        days_until_fight=days,
        hard_sparring_days=["Tue", "Thu"],
        support_work_days=["Fri"],
    )


def test_tactical_insert_appears_in_every_fight_plan():
    sequence = apply_gap_fill_inserts(
        [_session(12), _session(9, "fight_week_freshness_day")],
        _athlete(days_until_fight=12),
    )

    inserts = _insert_roles(sequence)
    assert any(insert["role_key"] in TACTICAL_INSERTS for insert in inserts)


def test_three_day_gap_can_receive_one_insert():
    sequence = apply_gap_fill_inserts(
        [_session(12), _session(9, "fight_week_freshness_day")],
        _athlete(days_until_fight=12),
    )

    inserts = _insert_roles(sequence)
    gap_inserts = [insert for insert in inserts if 9 < insert["countdown_offset"] < 12]
    assert len(gap_inserts) == 1
    assert gap_inserts[0]["countdown_offset"] not in {12, 9}


def test_five_day_gap_can_receive_two_inserts_max_one_per_day():
    sequence = apply_gap_fill_inserts(
        [_session(12), _session(7, "fight_week_freshness_day")],
        _athlete(days_until_fight=12),
    )

    inserts = _insert_roles(sequence)
    gap_inserts = [insert for insert in inserts if 7 < insert["countdown_offset"] < 12]
    assert len(gap_inserts) == 2
    assert len({insert["countdown_offset"] for insert in gap_inserts}) == 2


def test_exact_same_role_key_does_not_repeat_within_seven_days():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6, "fight_week_freshness_day")],
        _athlete(days_until_fight=21),
    )

    inserts = _insert_roles(sequence)
    for index, insert in enumerate(inserts):
        for other in inserts[index + 1 :]:
            if abs(insert["countdown_offset"] - other["countdown_offset"]) <= 7:
                assert insert["role_key"] != other["role_key"]


def test_tactical_category_can_repeat_with_different_role_key():
    sequence = apply_gap_fill_inserts(
        [_session(13), _session(8, "fight_week_freshness_day")],
        _athlete(days_until_fight=13, weight_cut_risk=True, readiness_flags=["active_weight_cut"]),
    )

    tactical_inserts = [insert for insert in _insert_roles(sequence) if insert["role_key"] in TACTICAL_INSERTS]
    assert len(tactical_inserts) >= 2
    assert len({insert["role_key"] for insert in tactical_inserts}) >= 2


def test_weight_cut_prefers_breathing_tactical_sleep_over_physical_filler():
    insert = select_gap_fill_insert(
        _athlete(
            weight_cut_risk=True,
            readiness_flags=["active_weight_cut"],
            weaknesses=["footwork"],
        ),
        9,
    )

    assert insert is not None
    assert insert["role_key"] in TACTICAL_INSERTS | {"breathing_reset", "sleep_downshift", "recovery_reset"}
    assert insert["role_key"] not in PHYSICAL_INSERTS


def test_footwork_weakness_prefers_footwork_filler():
    insert = select_gap_fill_insert(_athlete(weaknesses=["footwork"]), 12)

    assert insert is not None
    assert insert["role_key"] in {"footwork_walkthrough", "technical_shadow_rhythm"}


def test_injury_or_mobility_need_prefers_mobility_or_joint_prep():
    insert = select_gap_fill_insert(
        _athlete(
            weaknesses=["mobility"],
            parsed_injuries=[{"area": "ankle", "severity": "mild", "trend": "stable"}],
        ),
        12,
    )

    assert insert is not None
    assert insert["role_key"] in {"mobility_rehab", "joint_prep"}


def test_d1_allows_only_zero_or_recovery_inserts():
    allowed = _allowed_inserts(_athlete(), 1)
    insert = select_gap_fill_insert(_athlete(), 1)

    assert allowed <= ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS
    assert not (allowed & PHYSICAL_INSERTS)
    assert insert is not None
    assert insert["role_key"] in ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS


def test_gap_inserts_do_not_increase_meaningful_stress_count():
    sessions = [_session(12), _session(7, "fight_week_freshness_day")]
    meaningful_before = sum(1 for role in sessions if _is_meaningful_stressor(role))

    sequence = apply_gap_fill_inserts(sessions, _athlete(days_until_fight=12))
    meaningful_after = sum(1 for role in sequence if _is_meaningful_stressor(role))

    assert meaningful_before == meaningful_after
    assert all(insert["stress_class"] == "support" for insert in _insert_roles(sequence))
    assert all(insert["governance"]["meaningful_stress"] is False for insert in _insert_roles(sequence))


def test_gap_inserts_do_not_satisfy_strength_maintenance_touch():
    sessions = [_session(12), _session(7, "fight_week_freshness_day")]
    strength_touches_before = sum(1 for role in sessions if role.get("role_key") == "strength_touch_day")

    sequence = apply_gap_fill_inserts(sessions, _athlete(days_until_fight=12))
    strength_touches_after = sum(1 for role in sequence if role.get("role_key") == "strength_touch_day")

    assert strength_touches_before == strength_touches_after
    assert all(insert["category"] == "support_insert" for insert in _insert_roles(sequence))
    assert all(insert["cost_class"] == "low" for insert in _insert_roles(sequence))


def test_active_cut_gap_prefers_tactical_support_not_conditioning():
    sequence = apply_gap_fill_inserts(
        [_session(12), _session(8, "fight_week_freshness_day")],
        _athlete(weight_cut_risk=True, readiness_flags=["active_weight_cut"], days_until_fight=12),
    )

    inserts = _insert_roles(sequence)
    assert inserts[0]["role_key"] in TACTICAL_INSERTS
    assert inserts[0]["category"] == "support_insert"
    assert inserts[0]["stress_class"] == "support"
    assert all(insert["role_key"] not in {"conditioning", "main_conditioning_stressor"} for insert in inserts)


def test_active_cut_mild_stable_injury_can_choose_mobility_rehab():
    insert = select_gap_fill_insert(
        _athlete(
            weight_cut_risk=True,
            readiness_flags=["active_weight_cut"],
            weaknesses=["mobility"],
            parsed_injuries=[{"area": "ankle", "severity": "mild", "trend": "stable"}],
        ),
        8,
    )

    assert insert is not None
    assert insert["role_key"] in {"mobility_rehab", "joint_prep"}


def test_mild_stable_injury_d1_does_not_readd_physical_inserts():
    allowed = _allowed_inserts(
        _athlete(parsed_injuries=[{"area": "ankle", "severity": "mild", "trend": "stable"}]),
        1,
    )

    assert not (allowed & PHYSICAL_INSERTS)


def test_high_fatigue_mild_stable_injury_does_not_readd_physical_inserts():
    allowed = _allowed_inserts(
        _athlete(
            fatigue="",
            fatigue_level="",
            readiness_flags=["high_fatigue"],
            parsed_injuries=[{"area": "ankle", "severity": "mild", "trend": "stable"}],
        ),
        8,
    )

    assert not (allowed & PHYSICAL_INSERTS)


def test_power_speed_low_risk_gap_chooses_neural_or_technical_support():
    insert = select_gap_fill_insert(
        _athlete(key_goals=["power"], fatigue="low", fatigue_level="low"),
        12,
    )

    assert insert is not None
    assert insert["role_key"] in {"neural_visualization", "technical_shadow_rhythm"}


def test_high_fatigue_blocks_physical_inserts():
    athlete = _athlete(readiness_flags=["high_fatigue"], fatigue="", fatigue_level="")
    allowed = _allowed_inserts(athlete, 12)
    insert = select_gap_fill_insert(athlete, 12)

    assert allowed <= ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS
    assert insert is not None
    assert insert["role_key"] not in PHYSICAL_INSERTS


def test_d0_never_gets_insert():
    sequence = apply_gap_fill_inserts([_session(0, "fight_week_freshness_day")], _athlete(days_until_fight=0))

    assert _insert_roles(sequence) == []


def test_hard_sparring_day_blocks_physical_inserts():
    insert = select_gap_fill_insert(
        _athlete(weaknesses=["footwork"]),
        10,
        on_hard_sparring_day=True,
    )

    assert insert is not None
    assert insert["role_key"] not in PHYSICAL_INSERTS


def test_apply_gap_fill_inserts_is_wired_into_live_stage2_payload_path(monkeypatch):
    called = {"value": False}
    real_apply = stage2_payload_module.apply_gap_fill_inserts

    def spy(session_sequence, athlete_model):
        called["value"] = True
        return real_apply(session_sequence, athlete_model)

    monkeypatch.setattr(stage2_payload_module, "apply_gap_fill_inserts", spy)

    payload = build_stage2_payload(
        training_context=_training_context(13),
        mapped_format="boxing",
        record="5-0",
        rounds_format="3x3",
        camp_len=6,
        short_notice=False,
        restrictions=[],
        phase_weeks={"TAPER": 1, "days": {"TAPER": 13}},
        strength_blocks={},
        conditioning_blocks={},
        rehab_blocks={},
    )

    assert called["value"] is True
    assert payload["payload_variant"] == "late_fight_stage2_payload"


def test_no_aerobic_maintenance_without_conditioning_goal():
    allowed = _allowed_inserts(_athlete(key_goals=["power"], weaknesses=["footwork"]), 12)
    assert not (allowed & LOW_COST_AEROBIC_INSERTS)

    insert = select_gap_fill_insert(_athlete(key_goals=["power"], weaknesses=["footwork"]), 12)
    assert insert is not None
    assert insert["role_key"] not in LOW_COST_AEROBIC_INSERTS


def test_conditioning_goal_keeps_aerobic_maintenance_under_weight_cut_and_fatigue():
    # The example symptom: power + gas-tank, active cut, high fatigue, no bike.
    # Conditioning must remain visible as a low-risk aerobic-maintenance slot
    # instead of being replaced entirely by tactical/breathing filler.
    sequence = apply_gap_fill_inserts(
        [
            _session(18),
            _session(13, "fight_week_freshness_day"),
            _session(8, "fight_week_freshness_day"),
            _session(3, "fight_week_freshness_day"),
        ],
        _athlete(
            key_goals=["power", "conditioning"],
            weaknesses=["gas_tank"],
            weight_cut_risk=True,
            weight_cut_pct=8.0,
            readiness_flags=["active_weight_cut", "high_fatigue"],
            fatigue="high",
            fatigue_level="high",
            days_until_fight=18,
        ),
    )

    inserts = _insert_roles(sequence)
    aerobic = [insert for insert in inserts if insert["role_key"] in LOW_COST_AEROBIC_INSERTS]
    assert aerobic, "conditioning goal should keep at least one aerobic-maintenance slot"
    # Under active cut + high fatigue only the zero-impact options are safe.
    assert all(insert["role_key"] in {"aerobic_shadow_flow", "aerobic_walk_flush"} for insert in aerobic)
    assert all(insert["rpe_max"] <= 4 for insert in aerobic)
    # The slot stays a non-meaningful support insert (no forced conditioning stress).
    assert all(insert["stress_class"] == "support" for insert in aerobic)
    assert all(insert["governance"]["meaningful_stress"] is False for insert in aerobic)
    # Tactical support is still guaranteed.
    assert any(insert["role_key"] in TACTICAL_INSERTS for insert in inserts)


def test_aerobic_maintenance_does_not_depend_on_bike_equipment():
    # No bike/rower listed: the aerobic-maintenance fallback is bodyweight only.
    insert = select_gap_fill_insert(
        _athlete(key_goals=["conditioning"], weaknesses=["gas_tank"], equipment=["bodyweight"]),
        12,
        force_conditioning=True,
    )
    assert insert is not None
    assert insert["role_key"] in LOW_COST_AEROBIC_INSERTS


def test_lower_leg_injury_excludes_impact_aerobic_options():
    allowed = _allowed_inserts(
        _athlete(
            key_goals=["conditioning"],
            weaknesses=["gas_tank"],
            fatigue="low",
            fatigue_level="low",
            parsed_injuries=[{"area": "achilles", "severity": "mild", "trend": "stable"}],
        ),
        12,
    )
    aerobic = allowed & LOW_COST_AEROBIC_INSERTS
    assert aerobic, "conditioning goal should still offer a safe aerobic slot"
    assert "aerobic_skip_flush" not in aerobic
    assert "aerobic_jog_flush" not in aerobic
    assert "aerobic_shadow_flow" in aerobic


def test_low_fatigue_no_cut_allows_impact_aerobic_options():
    allowed = _allowed_inserts(
        _athlete(
            key_goals=["conditioning"],
            weaknesses=["gas_tank"],
            fatigue="low",
            fatigue_level="low",
        ),
        12,
    )
    assert {"aerobic_skip_flush", "aerobic_jog_flush"} <= allowed


def test_aerobic_maintenance_not_offered_day_before_fight():
    allowed = _allowed_inserts(
        _athlete(key_goals=["conditioning"], weaknesses=["gas_tank"]),
        1,
    )
    assert not (allowed & LOW_COST_AEROBIC_INSERTS)
    assert allowed <= ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS


def test_aerobic_maintenance_not_offered_on_hard_sparring_day():
    allowed = _allowed_inserts(
        _athlete(key_goals=["conditioning"], weaknesses=["gas_tank"]),
        10,
        on_hard_sparring_day=True,
    )
    assert not (allowed & LOW_COST_AEROBIC_INSERTS)
