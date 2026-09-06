from __future__ import annotations

from functools import wraps
from typing import Any

from .normalization import clean_list
from .stage2_payload_late_fight import compute_bridge_rules


_STALE_SPAR_REASON = "spar_first_cap"
_COARSE_BLOCKERS_OVERRIDDEN_BY_DAY_LEVEL_BRIDGE = {
    "late_bridge_glycolytic_lock_d17_to_d15",
    "bridge_suppresses_glycolytic",
    "active_cut_blocks_extra_conditioning_floor",
}
_PRIMARY_STRENGTH_ROLE_KEYS = {
    "primary_strength_day",
    "structural_strength_day",
    "neural_plus_strength_day",
    "neural_primer_day",
}
_LOW_IMPACT_READINESS_FLAGS = {
    "low_impact_required",
    "impact_restriction",
    "joint_load_restriction",
    "joint_pain",
    "tendon_pain",
    "lower_body_impact_restriction",
    "rehab_friendly_conditioning",
}


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _conditioning_is_primary(athlete_model: dict) -> bool:
    primary = _token(athlete_model.get("primary_goal"))
    if primary:
        return primary in {"conditioning", "conditioning_endurance", "endurance"}
    goals = [_token(value) for value in clean_list(athlete_model.get("key_goals", []))]
    return bool(goals and goals[0] in {"conditioning", "conditioning_endurance", "endurance"})


def _gas_tank_is_limiter(athlete_model: dict) -> bool:
    weaknesses = {
        _token(value)
        for value in clean_list(
            athlete_model.get("weaknesses") or athlete_model.get("weak_areas", [])
        )
    }
    return bool(
        weaknesses
        & {"gas_tank", "conditioning", "conditioning_endurance", "endurance", "work_capacity"}
    )


def _effective_hard_days_from_plan(plan: list[dict] | None) -> set[str]:
    hard_days: set[str] = set()
    for entry in plan or []:
        if not isinstance(entry, dict):
            continue
        if _token(entry.get("effective_load")) != "hard":
            continue
        status = _token(entry.get("status"))
        if status in {"suppressed", "convert_to_technical_suggested", "deload_suggested"}:
            continue
        day = _token(entry.get("day") or entry.get("weekday"))
        hard_days.add(day or f"hard_{len(hard_days) + 1}")
    return hard_days


def _effective_hard_exposure_days(
    week_entry: dict,
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> set[str]:
    """Return genuine external hard exposures, not merely declared gym attendance.

    The effective sparring plan is authoritative when it exists because declared
    hard sparring can be reduced or converted to technical work by readiness /
    late-camp policy. Technical/support days are deliberately absent here: the
    intake schema defines them as non-hard S&C-compatible work.
    """
    if hard_sparring_plan is not None:
        return _effective_hard_days_from_plan(hard_sparring_plan)

    if "hard_sparring_plan" in week_entry:
        return _effective_hard_days_from_plan(week_entry.get("hard_sparring_plan") or [])

    if "effective_hard_sparring_days" in week_entry:
        return {
            _token(day)
            for day in clean_list(week_entry.get("effective_hard_sparring_days", []))
            if _token(day)
        }

    session_types = athlete_model.get("session_types_by_day")
    if isinstance(session_types, dict):
        typed_hard = {
            _token(day)
            for day, session_type in session_types.items()
            if _token(session_type) == "hard_spar" and _token(day)
        }
        if typed_hard:
            return typed_hard

    return {
        _token(day)
        for day in clean_list(athlete_model.get("hard_sparring_days", []))
        if _token(day)
    }


def _hard_stimulus_deficit(
    week_entry: dict,
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> bool:
    """True when no genuine external hard exposure currently covers the week."""
    return not _effective_hard_exposure_days(
        week_entry,
        athlete_model,
        hard_sparring_plan=hard_sparring_plan,
    )


def _has_empty_external_combat_week(athlete_model: dict) -> bool:
    """Compatibility helper: literal absence of declared combat attendance.

    New policy must not use this as the hard-conditioning eligibility gate.
    """
    return not any(
        clean_list(athlete_model.get(key, []))
        for key in ("hard_sparring_days", "support_work_days", "technical_skill_days")
    )


def _prefer_low_impact_repeatability(athlete_model: dict) -> bool:
    """Choose lower mechanical cost only when mechanical context warrants it.

    This never changes the required physiological intensity. Body mass and
    moderate fatigue alone are not reasons to turn hard repeatability into easy
    aerobic work.
    """
    if bool(
        athlete_model.get("low_impact_required")
        or athlete_model.get("impact_restriction")
        or athlete_model.get("joint_load_restriction")
    ):
        return True
    readiness_flags = {
        _token(flag) for flag in clean_list(athlete_model.get("readiness_flags", []))
    }
    return bool(readiness_flags & _LOW_IMPACT_READINESS_FLAGS)


def _training_day_calendar(week_entry: dict, athlete_model: dict) -> list[tuple[str, int]]:
    declared = {
        _token(day)
        for day in clean_list(
            week_entry.get("declared_training_days") or athlete_model.get("training_days", [])
        )
        if _token(day)
    }
    result: list[tuple[str, int]] = []
    for row in week_entry.get("calendar_days") or []:
        weekday = _token(row.get("weekday"))
        d_day = row.get("d_day")
        if weekday in declared and isinstance(d_day, int):
            result.append((weekday, d_day))
    return result


def _declared_external_combat_days(week_entry: dict, athlete_model: dict) -> set[str]:
    days: set[str] = set()
    for key in (
        "declared_hard_sparring_days",
        "declared_support_work_days",
        "declared_technical_skill_days",
    ):
        days.update(_token(day) for day in clean_list(week_entry.get(key, [])) if _token(day))
    for key in ("hard_sparring_days", "support_work_days", "technical_skill_days"):
        days.update(_token(day) for day in clean_list(athlete_model.get(key, [])) if _token(day))
    return days


def _bridge_allows_glycolytic_on_day(athlete_model: dict, d_day: int) -> bool:
    rules = compute_bridge_rules(
        days_until_fight=d_day,
        sport=athlete_model.get("sport", ""),
        style=athlete_model.get("tactical_styles") or athlete_model.get("style"),
        fatigue=athlete_model.get("fatigue") or athlete_model.get("fatigue_level") or "low",
        weight_cut_bucket=athlete_model.get("cut_severity_bucket") or "high",
        injury_mode=athlete_model.get("injury_mode") or "full_plan",
        hard_sparring_days_declared=0,
        athlete_model=athlete_model,
    )
    return not bool(rules.get("block_full_plan")) and int(rules.get("glycolytic_touch_max") or 0) >= 1


def _earliest_safe_pressure_slot(
    week_entry: dict,
    athlete_model: dict,
) -> tuple[str, int] | None:
    """Choose the earliest day still allowed by canonical bridge policy.

    There is deliberately no independent D-day cutoff here. The existing
    late-camp/bridge system decides when glycolytic development must stop or
    morph; this policy only asks whether a hard stimulus is missing.
    """
    external_days = _declared_external_combat_days(week_entry, athlete_model)
    candidates = [
        (weekday, d_day)
        for weekday, d_day in _training_day_calendar(week_entry, athlete_model)
        if _bridge_allows_glycolytic_on_day(athlete_model, d_day)
    ]
    candidates.sort(key=lambda item: (item[0] in external_days, -item[1]))
    return candidates[0] if candidates else None


def _eligible_hard_stimulus_deficit(week_entry: dict, athlete_model: dict) -> bool:
    phase = str(week_entry.get("phase") or "").strip().upper()
    return bool(
        phase in {"GPP", "SPP"}
        and _conditioning_is_primary(athlete_model)
        and _gas_tank_is_limiter(athlete_model)
        and _hard_stimulus_deficit(week_entry, athlete_model)
        and _earliest_safe_pressure_slot(week_entry, athlete_model) is not None
    )


def _eligible_empty_week(week_entry: dict, athlete_model: dict) -> bool:
    """Compatibility alias for older tests/callers.

    Semantics are intentionally broader now: technical/light attendance does not
    erase a genuine hard-stimulus deficit.
    """
    return _eligible_hard_stimulus_deficit(week_entry, athlete_model)


def _scrub_stale_spar_first_state(
    week_entry: dict,
    suppressed_roles: list[dict],
) -> None:
    """Zero effective hard sparring must not retain spar-first authority."""
    compression = dict(week_entry.get("intentional_compression") or {})
    original_codes = [str(code) for code in clean_list(compression.get("reason_codes"))]
    own_codes = [code for code in original_codes if code != _STALE_SPAR_REASON]
    if own_codes != original_codes:
        compression["reason_codes"] = own_codes
        if not own_codes:
            compression.update(active=False, reason="", summary="")
        week_entry["intentional_compression"] = compression

    neutral_summary = (
        "Weekly session cap applied to app-programmed sessions; "
        "no effective hard sparring load is being protected."
    )
    for row in suppressed_roles:
        original_row_codes = [
            str(code) for code in clean_list(row.get("compression_reason_codes"))
        ]
        row_codes = [code for code in original_row_codes if code != _STALE_SPAR_REASON]
        if row_codes == original_row_codes:
            continue
        row["compression_reason_codes"] = row_codes
        if not row_codes:
            row["compression_summary"] = neutral_summary
            row["reasons"] = [neutral_summary]


def _move_pressure_to_early_slot(
    roles: list[dict],
    week_entry: dict,
    athlete_model: dict,
) -> list[dict]:
    target = _earliest_safe_pressure_slot(week_entry, athlete_model)
    if target is None:
        return roles
    target_day, target_d_day = target

    pressure = next(
        (
            role
            for role in roles
            if role.get("category") == "conditioning"
            and (
                _token(role.get("preferred_system")) == "glycolytic"
                or bool(role.get("combat_pressure_floor"))
                or bool(role.get("upgraded_from_hard_stimulus_deficit"))
                or bool(role.get("upgraded_from_empty_combat_week"))
            )
        ),
        None,
    )
    if pressure is None:
        return roles

    current_day = _token(pressure.get("scheduled_day_hint"))
    if current_day == target_day:
        return roles

    occupant = next(
        (
            role
            for role in roles
            if role is not pressure
            and _token(role.get("scheduled_day_hint")) == target_day
        ),
        None,
    )

    calendar = dict(_training_day_calendar(week_entry, athlete_model))
    occupied = {
        _token(role.get("scheduled_day_hint"))
        for role in roles
        if role is not pressure and _token(role.get("scheduled_day_hint"))
    }

    if occupant is not None:
        if _token(occupant.get("role_key")) in {"hard_sparring_day", "light_combat_day"}:
            return roles
        free_days = [
            (day, d_day)
            for day, d_day in _training_day_calendar(week_entry, athlete_model)
            if day not in occupied and day != target_day and d_day >= 15
        ]
        # This is the existing late-strength safety bound, not a conditioning cutoff.
        free_days.sort(key=lambda item: -item[1])
        destination = free_days[0][0] if free_days else ""
        if (
            not destination
            and current_day
            and current_day != target_day
            and calendar.get(current_day, -1) >= 15
        ):
            destination = current_day
        if not destination:
            return roles
        occupant["scheduled_day_hint"] = destination
        occupant["day_assignment_reason"] = (
            "Moved within the same weekly session budget so the primary "
            "conditioning goal can own a bridge-legal hard-repeatability slot."
        )
        occupant["placement_rule"] = (
            f"{str(occupant.get('placement_rule') or '').strip()} "
            "Yield a bridge-legal hard-repeatability slot when the weekly hard "
            "stimulus would otherwise be missing."
        ).strip()

    pressure["scheduled_day_hint"] = target_day
    pressure["day_assignment_reason"] = (
        f"Primary conditioning/gas-tank work uses D-{target_d_day} because "
        "the weekly hard-stimulus requirement is otherwise unmet."
    )
    pressure["placement_rule"] = (
        f"{str(pressure.get('placement_rule') or '').strip()} "
        "When the weekly hard stimulus is missing, place controlled repeatability "
        "on a canonical bridge-eligible development day; let late-camp morph rules "
        "decide when that work must become technical or taper work."
    ).strip()
    return roles


def install() -> None:
    """Install hard-stimulus preservation for combat conditioning-primary weeks."""
    from . import stage2_role_map as module

    if getattr(module, "_EMPTY_COMBAT_WEEK_POLICY_INSTALLED", False):
        return

    original_blockers = module._combat_pressure_floor_blockers
    original_compression = module._apply_high_fatigue_week_compression
    original_enforce = module._enforce_combat_pressure_floor
    original_assign = module._assign_declared_day_hints

    @wraps(original_blockers)
    def combat_pressure_floor_blockers(
        week_entry: dict,
        athlete_model: dict,
    ) -> list[str]:
        reasons = list(original_blockers(week_entry, athlete_model))
        if not _eligible_hard_stimulus_deficit(week_entry, athlete_model):
            return reasons
        return [
            reason
            for reason in reasons
            if reason not in _COARSE_BLOCKERS_OVERRIDDEN_BY_DAY_LEVEL_BRIDGE
        ]

    @wraps(original_compression)
    def apply_high_fatigue_week_compression(
        week_entry: dict,
        session_roles: list[dict],
        suppressed_roles: list[dict],
        athlete_model: dict,
        *,
        hard_sparring_plan: list[dict] | None = None,
    ) -> tuple[list[dict], list[dict]]:
        roles, suppressed = original_compression(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
        if _hard_stimulus_deficit(
            week_entry,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        ):
            _scrub_stale_spar_first_state(week_entry, suppressed)
        return roles, suppressed

    @wraps(original_enforce)
    def enforce_combat_pressure_floor(
        week_entry: dict,
        session_roles: list[dict],
        suppressed_roles: list[dict],
        athlete_model: dict,
    ) -> list[dict]:
        eligible = _eligible_hard_stimulus_deficit(week_entry, athlete_model)
        blockers = combat_pressure_floor_blockers(week_entry, athlete_model)
        if eligible and not blockers:
            already_hard = any(
                module._is_hard_pressure_conditioning_role(role)
                for role in session_roles
            )
            if not already_hard:
                secondary_strength = next(
                    (
                        role
                        for role in session_roles
                        if role.get("category") == "strength"
                        and _token(role.get("role_key")) not in _PRIMARY_STRENGTH_ROLE_KEYS
                    ),
                    None,
                )
                if secondary_strength is not None:
                    phase = str(week_entry.get("phase") or "").strip().upper()
                    role_key = (
                        "fight_pace_repeatability_day"
                        if phase == "SPP"
                        else "controlled_repeatability_day"
                    )
                    anchor = module._role_anchor(role_key)
                    style_tags = [
                        _token(style)
                        for style in clean_list(
                            athlete_model.get("tactical_styles")
                            or athlete_model.get("style_tactical")
                            or []
                        )
                        if _token(style)
                    ]
                    preferred_tags = [
                        "glycolytic",
                        "fight_pace",
                        "repeatability",
                        "gas_tank",
                        *style_tags,
                    ]
                    low_impact_preferred = _prefer_low_impact_repeatability(athlete_model)
                    if low_impact_preferred:
                        preferred_tags.extend(["low_impact", "low_joint_stress"])
                    secondary_strength.update(
                        category="conditioning",
                        role_key=role_key,
                        preferred_system="glycolytic",
                        preferred_pool="conditioning_slots",
                        preferred_tags=list(dict.fromkeys(preferred_tags)),
                        selection_rule=module._role_selection_rule(
                            role_key,
                            "conditioning",
                            "glycolytic",
                        ),
                        anchor=anchor,
                        placement_rule=module._placement_rule_for_anchor(anchor, week_entry),
                        governance=module._role_governance(
                            week_entry,
                            category="conditioning",
                            role_key=role_key,
                            athlete_model=athlete_model,
                            system="glycolytic",
                        ),
                        upgraded_from_hard_stimulus_deficit=True,
                        upgraded_from_empty_combat_week=True,
                        low_impact_preferred=low_impact_preferred,
                    )
                    secondary_strength.pop("strength_session_index", None)
                    secondary_strength.pop("athlete_facing_label", None)
        return original_enforce(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
        )

    @wraps(original_assign)
    def assign_declared_day_hints(
        ordered: list[dict],
        athlete_model: dict,
        *,
        hard_sparring_plan: list[dict] | None = None,
        week_entry: dict | None = None,
    ) -> list[dict]:
        roles = original_assign(
            ordered,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
            week_entry=week_entry,
        )
        if (
            isinstance(week_entry, dict)
            and _eligible_hard_stimulus_deficit(week_entry, athlete_model)
        ):
            roles = _move_pressure_to_early_slot(roles, week_entry, athlete_model)
        return roles

    module._combat_pressure_floor_blockers = combat_pressure_floor_blockers
    module._apply_high_fatigue_week_compression = apply_high_fatigue_week_compression
    module._enforce_combat_pressure_floor = enforce_combat_pressure_floor
    module._assign_declared_day_hints = assign_declared_day_hints
    module._HARD_STIMULUS_DEFICIT_POLICY_INSTALLED = True
    module._EMPTY_COMBAT_WEEK_POLICY_INSTALLED = True
