from __future__ import annotations

from fightcamp.gap_fill_inserts import (
    PHYSICAL_INSERTS,
    ZERO_COST_INSERTS,
    _allowed_inserts,
    apply_gap_fill_inserts,
    select_gap_fill_insert,
)
from fightcamp.stage2_payload import _is_meaningful_stressor


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


def test_active_cut_gap_prefers_tactical_support_not_conditioning():
    sequence = apply_gap_fill_inserts(
        [_session(12), _session(8, "fight_week_freshness_day")],
        _athlete(weight_cut_risk=True, readiness_flags=["active_weight_cut"], days_until_fight=12),
    )

    inserts = _insert_roles(sequence)
    assert inserts[0]["role_key"] == "tactical_watch"
    assert inserts[0]["category"] == "support_insert"
    assert inserts[0]["stress_class"] == "support"
    assert all(insert["role_key"] not in {"conditioning", "main_conditioning_stressor"} for insert in inserts)


def test_mobility_weakness_chooses_mobility_rehab_when_not_too_close():
    far_insert = select_gap_fill_insert(_athlete(weaknesses=["mobility"]), 12)
    close_insert = select_gap_fill_insert(_athlete(weaknesses=["mobility"]), 3)

    assert far_insert is not None
    assert far_insert["role_key"] == "mobility_rehab"
    assert close_insert is not None
    assert close_insert["role_key"] != "mobility_rehab"


def test_active_cut_mobility_weakness_d8_does_not_auto_choose_mobility_rehab():
    insert = select_gap_fill_insert(
        _athlete(
            weight_cut_risk=True,
            readiness_flags=["active_weight_cut"],
            weaknesses=["mobility"],
        ),
        8,
    )

    assert insert is not None
    assert insert["role_key"] in {"tactical_watch", "neural_visualization", "recovery_reset"}
    assert insert["role_key"] != "mobility_rehab"


def test_active_cut_d8_mild_stable_injury_can_choose_mobility_rehab():
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
    assert insert["role_key"] == "mobility_rehab"


def test_power_speed_low_risk_gap_chooses_neural_support():
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

    assert allowed <= ZERO_COST_INSERTS | {"recovery_reset"}
    assert insert is not None
    assert insert["role_key"] not in PHYSICAL_INSERTS


def test_d1_blocks_physical_load():
    allowed = _allowed_inserts(_athlete(), 1)

    assert allowed == {"tactical_watch", "self_review", "neural_visualization", "recovery_reset"}
    assert not (allowed & {"mobility_rehab", "movement_quality", "technical_shadow_rhythm"})


def test_d3_blocks_physical_load():
    allowed = _allowed_inserts(_athlete(weaknesses=["mobility"]), 3)
    insert = select_gap_fill_insert(_athlete(weaknesses=["mobility"]), 3)

    assert not (allowed & {"mobility_rehab", "movement_quality", "technical_shadow_rhythm"})
    assert insert is not None
    assert insert["role_key"] not in {"mobility_rehab", "movement_quality", "technical_shadow_rhythm"}


def test_insert_does_not_increase_meaningful_stress_count():
    sessions = [_session(12), _session(8, "fight_week_freshness_day")]
    meaningful_before = sum(1 for role in sessions if _is_meaningful_stressor(role))

    sequence = apply_gap_fill_inserts(sessions, _athlete(days_until_fight=12))
    meaningful_after = sum(1 for role in sequence if _is_meaningful_stressor(role))
    insert = _insert_roles(sequence)[0]

    assert meaningful_before == meaningful_after
    assert insert["stress_class"] == "support"
    assert insert["governance"]["meaningful_stress"] is False


def test_d0_never_gets_insert():
    sequence = apply_gap_fill_inserts([_session(0, "fight_week_freshness_day")], _athlete(days_until_fight=0))

    assert _insert_roles(sequence) == []


def test_hard_sparring_day_avoids_physical_insert():
    athlete = _athlete(
        days_until_fight=14,
        plan_creation_weekday="monday",
        hard_sparring_days=["friday"],
        weaknesses=["mobility"],
    )
    sequence = apply_gap_fill_inserts(
        [_session(14), _session(6, "fight_week_freshness_day")],
        athlete,
    )

    insert = _insert_roles(sequence)[0]
    assert insert["scheduled_day_hint"] == "friday"
    assert insert["role_key"] in ZERO_COST_INSERTS | {"recovery_reset"}


def test_max_insert_caps():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6, "fight_week_freshness_day")],
        _athlete(days_until_fight=21),
    )

    assert len(_insert_roles(sequence)) <= 2
