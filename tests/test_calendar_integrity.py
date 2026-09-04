from __future__ import annotations

import pytest

from fightcamp.calendar_integrity import (
    CalendarIntegrityError,
    apply_final_calendar_integrity,
)
from fightcamp.late_camp_role_morph import apply_late_camp_role_morph


WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def _week(
    *,
    start_d: int = 24,
    roles: list[dict] | None = None,
    contacts: list[dict] | None = None,
    declared: list[str] | None = None,
    week_index: int = 1,
) -> dict:
    return {
        "week_index": week_index,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": weekday, "d_day": start_d - idx}
            for idx, weekday in enumerate(WEEKDAYS)
        ],
        "declared_training_days": declared or list(WEEKDAYS),
        "session_roles": roles or [],
        "hard_sparring_plan": contacts or [],
        "suppressed_roles": [],
        "session_count_summary": {
            "reduced_from_planned": False,
            "reduction_reasons": [],
        },
    }


def _map(*weeks: dict) -> dict:
    return {"weeks": list(weeks)}


def _strength(day: str, *, key: str = "primary_strength_day", index: int = 1) -> dict:
    return {
        "role_key": key,
        "category": "strength",
        "scheduled_day_hint": day,
        "session_index": index,
        "stress_class": "meaningful_stress",
        "cost_class": "medium",
    }


def _hard(day: str) -> dict:
    return {
        "day": day,
        "status": "hard_as_planned",
        "effective_load": "hard",
    }


def _technical(day: str) -> dict:
    return {
        "day": day,
        "status": "convert_to_technical_suggested",
        "effective_load": "technical",
    }


def _role(weekly_role_map: dict, key: str) -> dict | None:
    for week in weekly_role_map.get("weeks", []) or []:
        for role in week.get("session_roles", []) or []:
            if role.get("role_key") == key:
                return role
    return None


def test_legal_no_contact_calendar_is_unchanged():
    strength = _strength("Wednesday")
    weekly = _map(_week(roles=[strength]))

    apply_final_calendar_integrity(weekly)

    assert strength["scheduled_day_hint"] == "Wednesday"
    assert weekly["calendar_integrity"]["relocated_roles"] == 0
    assert weekly["calendar_integrity"]["suppressed_roles"] == 0
    assert weekly["calendar_integrity"]["unresolved_forbidden"] == 0


def test_meaningful_day_after_hard_contact_relocates_to_cleaner_slot():
    strength = _strength("Wednesday")
    weekly = _map(_week(roles=[strength], contacts=[_hard("Tuesday")]))

    apply_final_calendar_integrity(weekly)

    assert strength["scheduled_day_hint"] == "Thursday"
    assert strength["calendar_integrity_relocation"]["reason_code"] == "post_hard_contact_managed_stress"
    assert weekly["calendar_integrity"]["relocated_roles"] == 1


def test_pre_hard_meaningful_strength_relocates_to_cleaner_allow_day():
    strength = _strength("Monday")
    weekly = _map(_week(roles=[strength], contacts=[_hard("Tuesday")]))

    apply_final_calendar_integrity(weekly)

    assert strength["scheduled_day_hint"] == "Thursday"
    assert weekly["calendar_integrity"]["deprioritized_kept"] == 0
    assert weekly["calendar_integrity"]["relocated_roles"] == 1


def test_relocation_preserves_duplicate_weekday_calendar_occurrences():
    strength = _strength("Sunday")
    week = _week(roles=[strength], contacts=[_hard("Monday")], declared=["Monday"])
    week["calendar_days"] = [
        {"weekday": "Monday", "d_day": 24},
        {"weekday": "Tuesday", "d_day": 23},
        {"weekday": "Wednesday", "d_day": 22},
        {"weekday": "Thursday", "d_day": 21},
        {"weekday": "Friday", "d_day": 20},
        {"weekday": "Saturday", "d_day": 19},
        {"weekday": "Sunday", "d_day": 18},
        {"weekday": "Monday", "d_day": 17},
    ]
    weekly = _map(week)

    apply_final_calendar_integrity(weekly)

    assert strength["scheduled_day_hint"] == "Monday"
    assert strength["scheduled_d_day"] == 24
    assert strength["calendar_integrity_relocation"]["to_d_day"] == 24


def test_deprioritized_relocation_stamp_is_not_called_forbidden():
    strength = _strength("Wednesday")
    weekly = _map(_week(roles=[strength], contacts=[_hard("Tuesday")]))

    apply_final_calendar_integrity(weekly)

    assert "was deprioritize: post_hard_contact_managed_stress" in strength["day_assignment_reason"]


def test_two_day_gap_keeps_managed_strength_between_contacts():
    strength = _strength("Wednesday")
    weekly = _map(
        _week(
            roles=[strength],
            contacts=[_hard("Tuesday"), _hard("Friday")],
        )
    )

    apply_final_calendar_integrity(weekly)

    assert strength["scheduled_day_hint"] == "Wednesday"
    assert weekly["calendar_integrity"]["deprioritized_kept"] == 1


def test_two_day_gap_can_retain_a_secondary_meaningful_strength_role():
    anchor = _strength("Monday", key="strength_touch_day", index=1)
    secondary = _strength("Wednesday", key="transfer_strength_day", index=2)
    weekly = _map(
        _week(
            roles=[anchor, secondary],
            contacts=[_hard("Tuesday"), _hard("Friday")],
        )
    )

    apply_final_calendar_integrity(weekly)

    assert anchor in weekly["weeks"][0]["session_roles"]
    assert secondary in weekly["weeks"][0]["session_roles"]
    assert weekly["calendar_integrity"]["suppressed_roles"] == 0


def test_technical_contact_does_not_create_hard_recovery_pressure():
    strength = _strength("Wednesday")
    weekly = _map(
        _week(
            roles=[strength],
            contacts=[_technical("Tuesday"), _technical("Friday")],
        )
    )

    apply_final_calendar_integrity(weekly)

    assert strength["scheduled_day_hint"] == "Wednesday"
    assert weekly["calendar_integrity"]["relocated_roles"] == 0


def test_low_aerobic_support_is_legal_between_two_hard_contacts():
    aerobic = {
        "role_key": "aerobic_support_day",
        "category": "conditioning",
        "preferred_system": "aerobic",
        "scheduled_day_hint": "Wednesday",
        "stress_class": "support",
        "cost_class": "low",
        "meaningful_stress": False,
    }
    weekly = _map(
        _week(
            roles=[aerobic],
            contacts=[_hard("Tuesday"), _hard("Friday")],
        )
    )

    apply_final_calendar_integrity(weekly)

    assert aerobic["scheduled_day_hint"] == "Wednesday"
    assert weekly["calendar_integrity"]["relocated_roles"] == 0


def test_zero_load_tactical_watch_can_coexist_with_hard_contact():
    watch = {
        "role_key": "tactical_watch",
        "scheduled_day_hint": "Tuesday",
    }
    visible_contact_mirror = {
        "role_key": "hard_sparring_day",
        "category": "sparring",
        "scheduled_day_hint": "Tuesday",
        "hard_sparring_status": "hard_as_planned",
    }
    weekly = _map(
        _week(
            roles=[visible_contact_mirror, watch],
            contacts=[_hard("Tuesday")],
        )
    )

    apply_final_calendar_integrity(weekly)

    assert watch in weekly["weeks"][0]["session_roles"]
    assert visible_contact_mirror in weekly["weeks"][0]["session_roles"]
    assert weekly["calendar_integrity"]["unresolved_forbidden"] == 0


def test_physical_mobility_cannot_stack_on_contact_day_and_moves():
    mobility = {
        "role_key": "mobility_rehab",
        "category": "rehab",
        "scheduled_day_hint": "Tuesday",
    }
    weekly = _map(
        _week(
            roles=[mobility],
            contacts=[_hard("Tuesday"), _hard("Friday")],
        )
    )

    apply_final_calendar_integrity(weekly)

    assert mobility["scheduled_day_hint"] == "Monday"
    assert mobility["calendar_integrity_relocation"]["reason_code"] == "contact_day_extra_physical_conflict"


def test_immediate_post_hard_rule_crosses_week_boundary():
    week_one = _week(
        start_d=24,
        roles=[],
        contacts=[_hard("Friday")],
        declared=["Friday"],
        week_index=1,
    )
    # Friday in week one is D-20; Saturday-like next chronological day is
    # represented by Monday D-19 in the next planner-owned scope. Geometry is
    # chronological D-day, not weekday-name based.
    week_two = {
        "week_index": 2,
        "phase": "SPP",
        "calendar_days": [{"weekday": "Monday", "d_day": 19}],
        "declared_training_days": ["Monday"],
        "session_roles": [_strength("Monday")],
        "hard_sparring_plan": [],
        "suppressed_roles": [],
        "session_count_summary": {"reduced_from_planned": False, "reduction_reasons": []},
    }
    weekly = _map(week_one, week_two)

    apply_final_calendar_integrity(weekly)

    assert week_two["session_roles"]
    assert weekly["calendar_integrity"]["deprioritized_kept"] == 1


def test_finished_d13_tail_is_never_replanned_by_stage3():
    tail_role = _strength("Wednesday")
    tail_role["late_fight_tail_owned"] = True
    week = _week(
        start_d=12,
        roles=[tail_role],
        contacts=[_hard("Tuesday"), _hard("Thursday")],
    )
    week["late_fight_tail_days"] = [12, 11, 10, 9, 8]
    weekly = _map(week)

    apply_final_calendar_integrity(weekly)

    assert tail_role["scheduled_day_hint"] == "Wednesday"
    assert weekly["calendar_integrity"]["late_fight_tail_replanned"] is False
    assert weekly["calendar_integrity"]["relocated_roles"] == 0
    assert weekly["calendar_integrity"]["unresolved_forbidden"] == 0


def test_relocation_calls_canonical_remorph_callback_before_verification():
    strength = _strength("Wednesday")
    weekly = _map(
        _week(
            start_d=18,
            roles=[strength],
            contacts=[_hard("Tuesday")],
        )
    )
    calls = []

    def remorph(value):
        calls.append(value)
        strength["remorphed"] = True
        return value

    apply_final_calendar_integrity(weekly, remorph_callback=remorph)

    assert strength["scheduled_day_hint"] == "Thursday"
    assert strength["remorphed"] is True
    assert calls == [weekly]


def test_public_late_camp_morph_wires_integrity_and_reapplies_dose_after_move():
    strength = _strength("Wednesday")
    weekly = _map(
        _week(
            start_d=18,
            roles=[strength],
            contacts=[_hard("Tuesday")],
        )
    )

    apply_late_camp_role_morph(weekly)

    assert strength["scheduled_day_hint"] == "Thursday"
    assert strength["late_camp_strength_morph"] is True
    assert strength["strength_dose_cap"]["max_sets"] <= 3
    assert weekly["calendar_integrity"]["unresolved_forbidden"] == 0


def test_unknown_physical_semantics_fail_explicit_instead_of_guessing():
    unknown = {
        "role_key": "future_power_shape",
        "category": "power",
        "scheduled_day_hint": "Wednesday",
        "rpe_cap": "7",
    }
    weekly = _map(_week(roles=[unknown]))

    with pytest.raises(CalendarIntegrityError, match="not classifiable"):
        apply_final_calendar_integrity(weekly)
