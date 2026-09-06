from __future__ import annotations

from functools import wraps
import re
from typing import Any

from .combat_load_policy import is_effective_hard_contact
from .normalization import clean_list
from .sports import SUPPORTED_SPORTS, normalize_sport
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
_LOW_IMPACT_RESTRICTION_TOKENS = {
    "impact",
    "jump",
    "landing",
    "running",
    "sprint",
    "joint",
    "tendon",
    "weight_bearing",
    "single_leg_loading",
}
_EXPLICIT_HARD_LOAD_TOKENS = {
    "hard",
    "hard_spar",
    "hard_sparring",
    "hard_pad",
    "hard_pads",
    "hard_bag",
    "hard_conditioning",
    "fight_pace",
    "fight_pace_hard",
    "high",
    "very_high",
    "max",
    "maximal",
}
_RESOLVED_HARD_CONTACT_COUNT_KEY = "_resolved_effective_hard_contact_count"
_RESOLVED_HARD_EXPOSURE_COUNT_KEY = "_resolved_effective_hard_exposure_count"


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _combat_sport_key(athlete_model: dict) -> str:
    """Return canonical combat-sport identity from the athlete snapshot."""
    return normalize_sport(
        athlete_model.get("sport") or athlete_model.get("fight_format") or ""
    )


def _is_supported_combat_sport(athlete_model: dict) -> bool:
    """Apply the deficit policy to every officially supported combat sport."""
    return _combat_sport_key(athlete_model) in SUPPORTED_SPORTS


def _is_boxing(athlete_model: dict) -> bool:
    """Compatibility helper for older callers/tests that still ask for boxing."""
    return _combat_sport_key(athlete_model) == "boxing"


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
    """Use the canonical contact-load classifier instead of redefining hard contact."""
    hard_days: set[str] = set()
    for entry in plan or []:
        if not isinstance(entry, dict) or not is_effective_hard_contact(entry):
            continue
        day = _token(entry.get("day") or entry.get("weekday"))
        hard_days.add(day or f"hard_{len(hard_days) + 1}")
    return hard_days


def _effective_hard_contact_days(
    week_entry: dict,
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> set[str]:
    """Return resolved hard-contact days only.

    This intentionally excludes hard pads, hard bags and non-contact conditioning.
    Contact-specific protections such as ``spar_first_cap`` and bridge contact load
    must be driven by contact truth, while the broader weekly hard-exposure budget
    may also count explicit non-contact hard work.
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

    return {
        _token(day)
        for day in clean_list(athlete_model.get("hard_sparring_days", []))
        if _token(day)
    }


def _structured_load_is_hard(value: Any) -> bool:
    """Recognise only explicit hard external-load metadata; never infer from attendance."""
    if isinstance(value, dict):
        for key in ("effective_load", "load", "intensity", "session_type", "type"):
            if _token(value.get(key)) in _EXPLICIT_HARD_LOAD_TOKENS:
                return True
        try:
            if float(value.get("rpe")) >= 8:
                return True
        except (TypeError, ValueError):
            pass
        return False
    return _token(value) in _EXPLICIT_HARD_LOAD_TOKENS


def _explicit_external_hard_days(athlete_model: dict) -> set[str]:
    """Read explicit non-contact hard-load metadata when an upstream caller provides it."""
    hard_days = {
        _token(day)
        for key in ("external_hard_training_days", "hard_training_days")
        for day in clean_list(athlete_model.get(key, []))
        if _token(day)
    }
    for key in (
        "external_training_load_by_day",
        "session_load_by_day",
        "session_loads_by_day",
        "session_types_by_day",
    ):
        values = athlete_model.get(key)
        if not isinstance(values, dict):
            continue
        for day, value in values.items():
            if _structured_load_is_hard(value) and _token(day):
                hard_days.add(_token(day))
    return hard_days


def _effective_hard_exposure_days(
    week_entry: dict,
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> set[str]:
    """Return all genuine external hard exposures, contact and non-contact."""
    return _effective_hard_contact_days(
        week_entry,
        athlete_model,
        hard_sparring_plan=hard_sparring_plan,
    ) | _explicit_external_hard_days(athlete_model)


def _readiness_allows_second_hard_exposure(week_entry: dict, athlete_model: dict) -> bool:
    """Allow a second total hard exposure only in roomy low-risk GPP weeks."""
    if str(week_entry.get("phase") or "").strip().upper() != "GPP":
        return False
    frequency = int(
        athlete_model.get("training_frequency")
        or len(clean_list(athlete_model.get("training_days", [])))
        or 0
    )
    if frequency < 5 or len(clean_list(athlete_model.get("training_days", []))) < 5:
        return False
    fatigue = _token(athlete_model.get("fatigue") or athlete_model.get("fatigue_level"))
    if fatigue not in {"", "low"}:
        return False
    cut = _token(athlete_model.get("cut_severity_bucket"))
    if cut not in {"", "none", "low"} or athlete_model.get("weight_cut_risk"):
        return False
    if _token(athlete_model.get("injury_mode")) not in {"", "full_plan"}:
        return False
    if athlete_model.get("injuries") or athlete_model.get("short_notice"):
        return False
    readiness = {
        _token(flag) for flag in clean_list(athlete_model.get("readiness_flags", []))
    }
    if readiness & {
        "high_fatigue",
        "critical_fatigue",
        "fight_week",
        "aggressive_weight_cut",
        "medical_hold",
        "needs_review",
    }:
        return False
    return True


def _weekly_hard_exposure_target(week_entry: dict, athlete_model: dict) -> int:
    """Total hard-exposure budget target before app conditioning is considered."""
    return 2 if _readiness_allows_second_hard_exposure(week_entry, athlete_model) else 1


def _hard_stimulus_deficit(
    week_entry: dict,
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> bool:
    """True when genuine external hard load is below the safe weekly target."""
    count = len(
        _effective_hard_exposure_days(
            week_entry,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
    )
    return count == 0 or (
        count == 1 and _weekly_hard_exposure_target(week_entry, athlete_model) >= 2
    )


def _has_empty_external_combat_week(athlete_model: dict) -> bool:
    """Compatibility helper for callers that still need literal attendance state."""
    return not any(
        clean_list(athlete_model.get(key, []))
        for key in ("hard_sparring_days", "support_work_days", "technical_skill_days")
    )


def _restriction_blob(athlete_model: dict) -> str:
    parts: list[str] = []
    for restriction in clean_list(athlete_model.get("restrictions", [])):
        parts.append(str(restriction))
    for restriction in athlete_model.get("injury_restrictions") or []:
        if isinstance(restriction, dict):
            parts.extend(str(value) for value in restriction.values() if value)
        elif restriction:
            parts.append(str(restriction))
    return _token(" ".join(parts))


def _prefer_low_impact_repeatability(athlete_model: dict) -> bool:
    """Bias modality only when mechanical context warrants lower impact."""
    if bool(
        athlete_model.get("low_impact_required")
        or athlete_model.get("impact_restriction")
        or athlete_model.get("joint_load_restriction")
    ):
        return True
    readiness_flags = {
        _token(flag) for flag in clean_list(athlete_model.get("readiness_flags", []))
    }
    if readiness_flags & _LOW_IMPACT_READINESS_FLAGS:
        return True
    restriction_blob = _restriction_blob(athlete_model)
    return any(token in restriction_blob for token in _LOW_IMPACT_RESTRICTION_TOKENS)


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


def _bridge_allows_glycolytic_on_day(athlete_model: dict, d_day: int) -> bool:
    """Ask canonical bridge policy using resolved hard-contact load, never raw attendance."""
    resolved_hard_count = athlete_model.get(_RESOLVED_HARD_CONTACT_COUNT_KEY)
    if resolved_hard_count is None:
        resolved_hard_count = len(clean_list(athlete_model.get("hard_sparring_days", [])))
    try:
        resolved_hard_count = max(0, int(resolved_hard_count))
    except (TypeError, ValueError):
        resolved_hard_count = len(clean_list(athlete_model.get("hard_sparring_days", [])))

    rules = compute_bridge_rules(
        days_until_fight=d_day,
        sport=_combat_sport_key(athlete_model),
        style=athlete_model.get("tactical_styles") or athlete_model.get("style"),
        fatigue=athlete_model.get("fatigue") or athlete_model.get("fatigue_level") or "low",
        weight_cut_bucket=athlete_model.get("cut_severity_bucket") or "high",
        injury_mode=athlete_model.get("injury_mode") or "full_plan",
        hard_sparring_days_declared=resolved_hard_count,
        athlete_model=athlete_model,
    )
    if bool(rules.get("block_full_plan")):
        return False
    if int(rules.get("glycolytic_touch_max") or 0) >= 1:
        return True

    # The shared bridge policy describes moderate fatigue as blocking an
    # *extra* glycolytic touch.  In an otherwise empty hard-exposure week this
    # policy is considering the first controlled touch, not an extra one.  Keep
    # every other bridge restriction binding and only restore the D-21..D-18
    # baseline in that exact case.
    resolved_exposure_count = athlete_model.get(_RESOLVED_HARD_EXPOSURE_COUNT_KEY)
    reason_codes = set(clean_list(rules.get("reason_codes", [])))
    return bool(
        resolved_exposure_count == 0
        and 18 <= d_day <= 21
        and "fatigue_moderate_blocks_extra_glycolytic_touch" in reason_codes
    )


def _bridge_legal_pressure_days(
    week_entry: dict,
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> list[str]:
    """Return exact training weekdays where canonical bridge policy permits hard density."""
    external_light_days = {
        _token(day)
        for key in ("support_work_days", "technical_skill_days")
        for day in clean_list(athlete_model.get(key, []))
        if _token(day)
    }
    bridge_athlete = dict(athlete_model)
    bridge_athlete[_RESOLVED_HARD_CONTACT_COUNT_KEY] = len(
        _effective_hard_contact_days(
            week_entry,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
    )
    bridge_athlete[_RESOLVED_HARD_EXPOSURE_COUNT_KEY] = len(
        _effective_hard_exposure_days(
            week_entry,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
    )
    return [
        weekday
        for weekday, d_day in _training_day_calendar(week_entry, athlete_model)
        if weekday not in external_light_days
        and _bridge_allows_glycolytic_on_day(bridge_athlete, d_day)
    ]


def _earliest_safe_pressure_slot(
    week_entry: dict,
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None = None,
) -> tuple[str, int] | None:
    """Eligibility probe only; actual day selection stays with the canonical owner."""
    allowed = set(
        _bridge_legal_pressure_days(
            week_entry,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
        )
    )
    candidates = [
        (weekday, d_day)
        for weekday, d_day in _training_day_calendar(week_entry, athlete_model)
        if weekday in allowed
    ]
    candidates.sort(key=lambda item: -item[1])
    return candidates[0] if candidates else None


def _eligible_hard_stimulus_deficit(week_entry: dict, athlete_model: dict) -> bool:
    phase = str(week_entry.get("phase") or "").strip().upper()
    return bool(
        _is_supported_combat_sport(athlete_model)
        and phase in {"GPP", "SPP"}
        and _conditioning_is_primary(athlete_model)
        and _gas_tank_is_limiter(athlete_model)
        and _hard_stimulus_deficit(week_entry, athlete_model)
        and _earliest_safe_pressure_slot(week_entry, athlete_model) is not None
    )


def _eligible_empty_week(week_entry: dict, athlete_model: dict) -> bool:
    """Compatibility alias with hard-stimulus-deficit semantics."""
    return _eligible_hard_stimulus_deficit(week_entry, athlete_model)


def _scrub_stale_spar_first_state(
    week_entry: dict,
    suppressed_roles: list[dict],
) -> None:
    """Zero effective hard contact must not retain spar-first authority."""
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
        "no effective hard contact load is being protected."
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


def _parse_rounds_format(athlete_model: dict) -> tuple[int, int] | None:
    raw = str(athlete_model.get("rounds_format") or "").strip().lower()
    match = re.match(r"^(\d+)\s*x\s*(\d+)$", raw)
    if not match:
        return None
    rounds, minutes = int(match.group(1)), int(match.group(2))
    if rounds <= 0 or minutes <= 0:
        return None
    return rounds, minutes


def _sport_specific_pressure_metadata(
    athlete_model: dict, phase: str
) -> dict[str, Any]:
    """Keep physiological intent hard while matching SPP dose to actual bout format."""
    phase_key = str(phase or "").upper()
    parsed = _parse_rounds_format(athlete_model)
    sport = _combat_sport_key(athlete_model).replace("_", " ") or "combat"
    if phase_key != "SPP" or parsed is None:
        return {}

    rounds, round_minutes = parsed
    if round_minutes <= 2:
        reps = max(3, min(6, rounds + 1))
        work = f"{round_minutes} min"
        recovery = "60 sec"
    elif round_minutes == 3:
        reps = max(3, min(5, rounds + 1))
        work = "3 min"
        recovery = "60-75 sec"
    else:
        reps = max(3, min(4, rounds + 1))
        work = "3 min high-output segment"
        recovery = "90 sec"

    return {
        "prescribed_intensity_rpe": "8-9",
        "prescribed_dose": (
            f"{reps} x {work} fight-pace on / {recovery} off @ RPE 8-9 "
            f"(built from {rounds} x {round_minutes} min {sport} format)"
        ),
        "dose_basis": "athlete_rounds_format",
        "fight_format_rounds": rounds,
        "fight_format_round_minutes": round_minutes,
    }


def _is_deficit_hard_role(role: dict) -> bool:
    return bool(
        role.get("upgraded_from_hard_stimulus_deficit")
        or (
            role.get("mandatory_hard_conditioning_exposure")
            and _token(role.get("preferred_system")) == "glycolytic"
        )
    )


def _role_allowed_training_days(role: dict) -> list[str]:
    if "allowed_training_days" not in role:
        return []
    return [
        _token(day)
        for day in clean_list(role.get("allowed_training_days", []))
        if _token(day)
    ]


def _assign_hard_role_with_day_level_bridge(
    original_assign,
    ordered: list[dict],
    athlete_model: dict,
    *,
    hard_sparring_plan: list[dict] | None,
    week_entry: dict | None,
) -> list[dict]:
    """Give the mandatory hard role a bridge-legal set, then delegate placement.

    The canonical allocator still chooses every actual weekday and applies shared
    combat-load legality. This wrapper grants the mandatory primary-goal role first
    claim on one of its exact countdown-legal days, then delegates all remaining
    roles back to the same owner. ``allowed_training_days`` is retained so later
    canonical completion cannot reintroduce a bridge-forbidden fallback.
    """
    if not isinstance(week_entry, dict):
        return original_assign(
            ordered,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
            week_entry=week_entry,
        )

    pressure_indices = [
        idx for idx, role in enumerate(ordered) if _is_deficit_hard_role(role)
    ]
    if len(pressure_indices) != 1:
        return original_assign(
            ordered,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
            week_entry=week_entry,
        )

    pressure_idx = pressure_indices[0]
    pressure_role = dict(ordered[pressure_idx])
    allowed_days = set(_role_allowed_training_days(pressure_role))
    if "allowed_training_days" not in pressure_role:
        allowed_days = set(
            _bridge_legal_pressure_days(
                week_entry,
                athlete_model,
                hard_sparring_plan=hard_sparring_plan,
            )
        )
        pressure_role["allowed_training_days"] = sorted(allowed_days)

    original_training_days = clean_list(athlete_model.get("training_days", []))
    allowed_training_days = [
        day for day in original_training_days if _token(day) in allowed_days
    ]
    other_roles = [
        dict(role) for idx, role in enumerate(ordered) if idx != pressure_idx
    ]

    if not allowed_training_days:
        assigned_others = original_assign(
            other_roles,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
            week_entry=week_entry,
        )
        pressure_role["scheduled_day_hint"] = ""
        pressure_role["day_assignment_reason"] = (
            "No countdown-eligible hard-conditioning day remained."
        )
    else:
        pressure_athlete = dict(athlete_model)
        pressure_athlete["training_days"] = allowed_training_days
        assigned_pressure = original_assign(
            [pressure_role],
            pressure_athlete,
            hard_sparring_plan=hard_sparring_plan,
            week_entry=week_entry,
        )
        pressure_role = assigned_pressure[0]
        pressure_day = _token(pressure_role.get("scheduled_day_hint"))

        remaining_athlete = dict(athlete_model)
        if pressure_day:
            remaining_athlete["training_days"] = [
                day for day in original_training_days if _token(day) != pressure_day
            ]
        assigned_others = original_assign(
            other_roles,
            remaining_athlete,
            hard_sparring_plan=hard_sparring_plan,
            week_entry=week_entry,
        )

    result: list[dict] = []
    other_iter = iter(assigned_others)
    for idx in range(len(ordered)):
        result.append(pressure_role if idx == pressure_idx else next(other_iter))
    return result


def install() -> None:
    """Install combat hard-stimulus preservation with canonical safety authority."""
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
        if _is_supported_combat_sport(
            athlete_model
        ) and not _effective_hard_contact_days(
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
                        and _token(role.get("role_key"))
                        not in _PRIMARY_STRENGTH_ROLE_KEYS
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
                    low_impact_preferred = _prefer_low_impact_repeatability(
                        athlete_model
                    )
                    if low_impact_preferred:
                        preferred_tags.extend(["low_impact", "low_joint_stress"])

                    allowed_training_days = _bridge_legal_pressure_days(
                        week_entry,
                        athlete_model,
                    )
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
                        placement_rule=(
                            f"{module._placement_rule_for_anchor(anchor, week_entry)} "
                            "Calendar placement remains owned by canonical combat-load legality."
                        ).strip(),
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
                        allowed_training_days=allowed_training_days,
                    )
                    secondary_strength.pop("strength_session_index", None)
                    secondary_strength.pop("athlete_facing_label", None)

        roles = original_enforce(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
        )
        phase = str(week_entry.get("phase") or "").strip().upper()
        dose_metadata = _sport_specific_pressure_metadata(athlete_model, phase)
        if dose_metadata:
            for role in roles:
                if _is_deficit_hard_role(role):
                    role.update(dose_metadata)

        week_entry["hard_stimulus_budget"] = {
            "effective_hard_contact_exposures": len(
                _effective_hard_contact_days(week_entry, athlete_model)
            ),
            "external_hard_exposures": len(
                _effective_hard_exposure_days(week_entry, athlete_model)
            ),
            "target_total_hard_exposures": _weekly_hard_exposure_target(
                week_entry, athlete_model
            ),
            "conditioning_primary": _conditioning_is_primary(athlete_model),
        }
        return roles

    @wraps(original_assign)
    def assign_declared_day_hints(
        ordered: list[dict],
        athlete_model: dict,
        *,
        hard_sparring_plan: list[dict] | None = None,
        week_entry: dict | None = None,
    ) -> list[dict]:
        return _assign_hard_role_with_day_level_bridge(
            original_assign,
            ordered,
            athlete_model,
            hard_sparring_plan=hard_sparring_plan,
            week_entry=week_entry,
        )

    module._combat_pressure_floor_blockers = combat_pressure_floor_blockers
    module._apply_high_fatigue_week_compression = apply_high_fatigue_week_compression
    module._enforce_combat_pressure_floor = enforce_combat_pressure_floor
    module._assign_declared_day_hints = assign_declared_day_hints
    module._HARD_STIMULUS_DEFICIT_POLICY_INSTALLED = True
    module._EMPTY_COMBAT_WEEK_POLICY_INSTALLED = True
