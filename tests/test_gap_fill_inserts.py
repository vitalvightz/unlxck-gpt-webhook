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
    insert_mechanical_load_regions,
    select_gap_fill_insert,
    _apply_bank_footwork,
    _build_insert_role,
)
from fightcamp.stage2_payload import _is_meaningful_stressor, build_stage2_payload
from fightcamp.stage2_payload_late_fight import _late_fight_meaningful_stress_count
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


def _footwork_insert(athlete: dict, offset: int = 14) -> dict:
    """Build the footwork support role directly, without changing role scoring."""
    role = _build_insert_role("footwork_walkthrough", athlete, offset)
    _apply_bank_footwork(role, athlete, offset, None)
    return role


def test_mma_pressure_footwork_gap_uses_existing_sport_bank():
    role = select_gap_fill_insert(
        _athlete(
            sport="mma",
            fight_format="mma",
            style_tactical=["pressure_fighter"],
            weaknesses=["footwork"],
        ),
        14,
    )

    assert role["role_key"] == "footwork_walkthrough"
    assert role["technical_footwork_name"] == "Cage Circle and Cut-Off"
    assert role["technical_footwork_source"] == "technical_footwork_bank.json"
    assert "jab/cross" not in role["display_text"].lower()


def test_grappling_footwork_gap_uses_neutral_fallback_when_bank_has_no_match():
    banned = {"jab", "cross", "punch", "boxing", "ring", "ropes", "cage", "takedown", "kick"}
    for sport in ("wrestling", "bjj"):
        role = _footwork_insert(
            _athlete(sport=sport, fight_format=sport, weaknesses=["footwork"])
        )
        text = role["display_text"].lower()
        assert role["technical_footwork_fallback"] is True
        assert not any(term in text for term in banned), (sport, text)


def test_boxing_footwork_gap_retains_compatible_bank_specificity():
    role = _footwork_insert(
        _athlete(
            sport="boxing",
            fight_format="boxing",
            style_tactical=["counter_striker"],
            weaknesses=["footwork"],
        )
    )
    assert role["technical_footwork_fallback"] is False
    assert "jab" in role["display_text"].lower()


def test_kicking_sports_never_fall_through_to_cage_or_boxing_copy():
    for sport in ("kickboxing", "muay_thai"):
        role = _footwork_insert(
            _athlete(
                sport=sport,
                fight_format=sport,
                style_tactical=["kicker"],
                weaknesses=["footwork"],
            )
        )
        text = role["display_text"].lower()
        assert role["technical_footwork_fallback"] is False
        assert "cage" not in text
        assert "boxing rhythm" not in text


def test_late_window_footwork_falls_through_then_uses_neutral_fallback():
    boxer = _footwork_insert(
        _athlete(
            sport="boxing",
            fight_format="boxing",
            style_tactical=["counter_striker"],
            weaknesses=["footwork"],
        ),
        4,
    )
    assert boxer["technical_footwork_name"] == "Stance Reset Line Drill"

    mma = _footwork_insert(
        _athlete(
            sport="mma",
            fight_format="mma",
            style_tactical=["pressure_fighter"],
            weaknesses=["footwork"],
        ),
        4,
    )
    assert mma["technical_footwork_fallback"] is True
    assert "jab/cross" not in mma["display_text"].lower()


def test_gap_footwork_keeps_dedicated_channel_and_not_conditioning_category():
    role = _footwork_insert(
        _athlete(sport="mma", fight_format="mma", weaknesses=["footwork"])
    )
    assert role["technical_footwork_channel"] == "technical_footwork"
    assert role["support_insert_category"] == "technical_footwork"
    assert role["support_insert_category"] != "conditioning_maintenance"


def test_boxing_aerobic_shadow_flow_keeps_shadowboxing_label():
    role = _build_insert_role("aerobic_shadow_flow", _athlete(sport="boxing"), 5)

    assert role["athlete_facing_label"] == "Shadowboxing Aerobic Flow"


def test_non_boxing_aerobic_shadow_flow_label_is_sport_neutral():
    for sport in ("mma", "kickboxing", "muay_thai", "wrestling", "bjj"):
        role = _build_insert_role("aerobic_shadow_flow", _athlete(sport=sport), 5)
        assert "boxing rhythm" not in role["display_text"].lower()
        assert "boxing" not in role["athlete_facing_label"].lower()
        assert "shadowboxing" not in role["athlete_facing_label"].lower()


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


def _coach_session(offset: int, weekday: str = "tuesday") -> dict:
    return {
        "session_index": 1,
        "category": "sparring",
        "role_key": "hard_sparring_day",
        "scheduled_day_hint": weekday,
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
        "coach_owned": True,
    }


def _support_insert_session(offset: int, role_key: str = "tactical_watch", weekday: str = "tuesday") -> dict:
    return {
        "session_index": 1,
        "category": "support_insert",
        "role_key": role_key,
        "scheduled_day_hint": weekday,
        "real_weekday": weekday,
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
        "stress_class": "support",
        "cost_class": "low",
        "governance": {"meaningful_stress": False},
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


def test_back_loaded_short_camp_fills_its_opening_days():
    # A D-6 camp places both active sessions at D-3 and D-1, so the days the
    # athlete actually opens the app on — D-6 to D-4 — sat before the first
    # session. Only the gaps BETWEEN sessions and the trailing run to fight day
    # were candidates, leaving that leading span structurally unreachable: no
    # insert could land there however light, and the plan opened on blanks.
    sequence = apply_gap_fill_inserts(
        [_session(3, "fight_week_freshness_day"), _session(1, "neural_primer_day")],
        _athlete(days_until_fight=6),
    )

    leading = [insert for insert in _insert_roles(sequence) if insert["countdown_offset"] > 3]
    assert len(leading) == 1
    # Zero/low cost only — the taper must not gain physical work near the fight.
    assert leading[0]["role_key"] in ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS | PHYSICAL_INSERTS
    assert leading[0]["role_key"] not in {"fight_week_freshness_day", "neural_primer_day"}


def test_leading_span_fill_leaves_active_sessions_untouched():
    active = [_session(3, "fight_week_freshness_day"), _session(1, "neural_primer_day")]
    sequence = apply_gap_fill_inserts(active, _athlete(days_until_fight=6))

    # The two programmed sessions survive at their original days: the leading
    # fill adds support, it never moves or displaces physical work.
    kept = [
        (str(role.get("role_key")), int(role.get("countdown_offset")))
        for role in sequence
        if str(role.get("role_key")) in {"fight_week_freshness_day", "neural_primer_day"}
    ]
    assert kept == [("fight_week_freshness_day", 3), ("neural_primer_day", 1)]


def test_long_camp_keeps_its_existing_leading_shape():
    # The leading-span fill is scoped to the taper window; further out the
    # sessions already reach the front of the plan on their own.
    sequence = apply_gap_fill_inserts(
        [_session(20), _session(10, "fight_week_freshness_day")],
        _athlete(days_until_fight=30),
    )

    assert [insert for insert in _insert_roles(sequence) if insert["countdown_offset"] > 20] == []


def test_only_mandatory_watch_may_repeat_within_seven_days():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6, "fight_week_freshness_day")],
        _athlete(days_until_fight=21),
    )

    inserts = _insert_roles(sequence)
    for index, insert in enumerate(inserts):
        for other in inserts[index + 1 :]:
            if (
                abs(insert["countdown_offset"] - other["countdown_offset"]) <= 7
                and insert["role_key"] == other["role_key"]
            ):
                assert insert["role_key"] == "tactical_watch"
                assert insert.get("mandatory_tactical_watch") is True
                assert other.get("mandatory_tactical_watch") is True


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


def test_mechanical_load_regions_surface_on_built_role():
    # A punch-rhythm primer declares the striking chain AND the footwork/stance
    # load that comes with it; a pure mental / breathing insert declares nothing.
    # mobility_rehab / joint_prep are the deliberate exception: gentle,
    # pain-free, TARGETED rehab for the flagged restriction stays exempt even
    # though it touches the injured joint by design.
    assert set(insert_mechanical_load_regions("technical_shadow_rhythm")) == {
        "shoulder", "elbow", "wrist", "chest", "ankle", "knee"
    }
    assert insert_mechanical_load_regions("tactical_watch") == ()
    assert insert_mechanical_load_regions("mobility_rehab") == ()
    assert insert_mechanical_load_regions("joint_prep") == ()
    assert insert_mechanical_load_regions("breathing_reset") == ()
    # Low load is not zero load: walking and low-amplitude foot-placement work
    # still touch the lower chain enough to matter for an ankle/foot/Achilles
    # injury, so these must not be exempt.
    assert insert_mechanical_load_regions("walk_flush") == (
        "ankle", "foot", "achilles", "calf", "knee"
    )
    assert insert_mechanical_load_regions("aerobic_walk_flush") == (
        "ankle", "foot", "achilles", "calf", "knee"
    )
    assert set(insert_mechanical_load_regions("movement_quality")) == {"ankle", "foot"}

    insert = select_gap_fill_insert(_athlete(weaknesses=["footwork"]), 12)
    assert insert is not None
    assert "mechanical_load_regions" in insert
    assert isinstance(insert["mechanical_load_regions"], list)


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


def test_surface_only_injury_never_gets_rehab_or_joint_prep_filler():
    athlete = _athlete(
        has_active_injury=True,
        surface_injury_only=True,
        injuries=["minor graze on elbow"],
        parsed_injuries=[{"injury_type": "graze", "severity": "low", "flags": []}],
        weaknesses=["mobility"],
    )
    allowed = _allowed_inserts(athlete, 12)
    insert = select_gap_fill_insert(athlete, 12)

    assert not (allowed & {"mobility_rehab", "joint_prep"})
    assert insert is not None
    assert insert["role_key"] not in {"mobility_rehab", "joint_prep"}


def test_healthy_athlete_with_mobility_need_can_get_mobility_or_joint_prep_filler():
    athlete = _athlete(weaknesses=["mobility"])
    allowed = _allowed_inserts(athlete, 12)
    insert = select_gap_fill_insert(athlete, 12)

    assert allowed & {"mobility_rehab", "joint_prep"}
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


def test_gap_fill_can_attach_tactical_watch_to_declared_coach_day():
    sequence = apply_gap_fill_inserts(
        [
            _coach_session(9, "tuesday"),
            _session(6, "fight_week_freshness_day"),
            _session(1, "neural_primer_day"),
        ],
        _athlete(
            days_until_fight=9,
            plan_creation_weekday="tuesday",
            hard_sparring_days=["tuesday", "friday"],
        ),
    )

    d9_roles = [role for role in sequence if role.get("countdown_offset") == 9]
    assert any(role["role_key"] == "hard_sparring_day" for role in d9_roles)
    assert any(role["role_key"] == "tactical_watch" for role in d9_roles)
    assert all(role["role_key"] not in PHYSICAL_INSERTS for role in d9_roles)


def test_existing_d1_tactical_watch_is_promoted_without_extra_support():
    sequence = apply_gap_fill_inserts(
        [_support_insert_session(1, "tactical_watch", "tuesday")],
        _athlete(
            days_until_fight=1,
            plan_creation_weekday="tuesday",
            hard_sparring_days=["tuesday"],
        ),
    )

    d1_roles = [role for role in sequence if role.get("countdown_offset") == 1]
    support_roles = [role for role in d1_roles if role.get("category") == "support_insert"]
    assert len(support_roles) == 1
    assert support_roles[0]["role_key"] == "tactical_watch"
    assert support_roles[0]["mandatory_tactical_watch"] is True
    assert all(role["role_key"] not in PHYSICAL_INSERTS for role in d1_roles)


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


def test_moderate_plus_injury_blocks_all_aerobic_maintenance():
    # An acute/fracture state is moderate_plus: the injury guard restricts inserts
    # to recovery + mobility, and aerobic maintenance must not punch through it.
    athlete = _athlete(
        key_goals=["conditioning"],
        weaknesses=["gas_tank"],
        fatigue="low",
        fatigue_level="low",
        parsed_injuries=[{"area": "ankle", "severity": "acute", "trend": "worsening"}],
        injuries=["acute ankle fracture"],
    )
    allowed = _allowed_inserts(athlete, 12)
    assert not (allowed & LOW_COST_AEROBIC_INSERTS)

    # Forcing the conditioning guarantee must not resurrect aerobic work; it falls
    # back to a safe recovery/mobility insert instead of returning nothing.
    insert = select_gap_fill_insert(athlete, 12, force_conditioning=True)
    assert insert is not None
    assert insert["role_key"] not in LOW_COST_AEROBIC_INSERTS


def test_force_conditioning_falls_back_when_aerobic_disallowed():
    athlete = _athlete(key_goals=["conditioning"], weaknesses=["gas_tank"])

    # Day before the fight: aerobic maintenance is disallowed, but the slot still
    # gets a normal zero/recovery filler instead of being dropped.
    d1 = select_gap_fill_insert(athlete, 1, force_conditioning=True)
    assert d1 is not None
    assert d1["role_key"] not in LOW_COST_AEROBIC_INSERTS
    assert d1["role_key"] in ZERO_COST_INSERTS | LOW_COST_RECOVERY_INSERTS

    # Hard-sparring day: same fallback, no empty gap.
    hard = select_gap_fill_insert(athlete, 10, on_hard_sparring_day=True, force_conditioning=True)
    assert hard is not None
    assert hard["role_key"] not in LOW_COST_AEROBIC_INSERTS


# --- Guard rails: aerobic maintenance is a filler, never counted as a session ---
# The app moves/drops "meaningful stressor" cards to avoid two real sessions in
# one day. The aerobic-maintenance inserts are physical, so these tests lock in
# that they are still treated as low-cost support fillers (like tactical/breathing
# inserts) and never trip the per-day session logic. A future refactor that
# reclassifies them as sessions must fail here.


def test_every_aerobic_insert_is_a_non_session_filler():
    athlete = _athlete(key_goals=["conditioning"], weaknesses=["gas_tank"], fatigue="low", fatigue_level="low")
    seen = set()
    for _offset in (12, 10, 6, 4, 9, 3):
        insert = select_gap_fill_insert(athlete, _offset, force_conditioning=True)
        if insert is None or insert["role_key"] not in LOW_COST_AEROBIC_INSERTS:
            continue
        seen.add(insert["role_key"])
        assert _is_meaningful_stressor(insert) is False
        assert insert["stress_class"] == "support"
        assert insert["cost_class"] == "low"
        assert insert["governance"]["meaningful_stress"] is False
        # A single aerobic filler contributes nothing to the late-fight
        # meaningful-stress budget.
        assert _late_fight_meaningful_stress_count([insert]) == 0
    assert seen, "expected at least one aerobic-maintenance insert to be selectable"


def test_aerobic_inserts_do_not_increase_meaningful_stress_count():
    sessions = [
        _session(18),
        _session(13, "fight_week_freshness_day"),
        _session(8, "fight_week_freshness_day"),
        _session(3, "fight_week_freshness_day"),
    ]
    athlete = _athlete(
        key_goals=["power", "conditioning"],
        weaknesses=["gas_tank"],
        weight_cut_risk=True,
        weight_cut_pct=8.0,
        readiness_flags=["active_weight_cut", "high_fatigue"],
        fatigue="high",
        fatigue_level="high",
        days_until_fight=18,
    )
    meaningful_before = sum(1 for role in sessions if _is_meaningful_stressor(role))

    sequence = apply_gap_fill_inserts(sessions, athlete)
    meaningful_after = sum(1 for role in sequence if _is_meaningful_stressor(role))

    aerobic = [r for r in _insert_roles(sequence) if r["role_key"] in LOW_COST_AEROBIC_INSERTS]
    assert aerobic, "aerobic-maintenance insert should be present for this scenario"
    # Adding the physical aerobic filler must not register as an extra session.
    assert meaningful_after == meaningful_before
    assert _late_fight_meaningful_stress_count(sequence) == _late_fight_meaningful_stress_count(sessions)


def test_aerobic_insert_never_lands_on_a_hard_sparring_day():
    hard_days = ["tuesday", "thursday"]
    athlete = _athlete(
        key_goals=["conditioning"],
        weaknesses=["gas_tank"],
        fatigue="low",
        fatigue_level="low",
        days_until_fight=21,
        hard_sparring_days=hard_days,
    )
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6, "fight_week_freshness_day")],
        athlete,
    )
    aerobic = [r for r in _insert_roles(sequence) if r["role_key"] in LOW_COST_AEROBIC_INSERTS]
    for insert in aerobic:
        weekday = str(insert.get("scheduled_day_hint") or insert.get("real_weekday") or "").strip().lower()
        assert weekday not in hard_days
