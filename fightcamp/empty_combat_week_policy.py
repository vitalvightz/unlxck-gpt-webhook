from __future__ import annotations

from functools import wraps
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
    """Use the canonical contact-load classifier instead of re-defining hard contact."""
    hard_days: set[str] = set()
    for entry in plan or []:
        if not isinstance(entry, dict) or not is_effective_hard_contact(entry):
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

    The resolved sparring/contact plan is authoritative when present. Technical/support
    attendance is intentionally not counted as hard. The session-types fallback
    exists only for compatibility callers that have not built the contact plan.
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
    """Bias modality only when mechanical context warrants lower impact.

    This never changes the required physiological intensity. Body mass and
    moderate fatigue alone are not lower-impact triggers.
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
    rules = compute_bridge_rules(
        days_until_fight=d_day,
        sport=_combat_sport_key(athlete_model),
        style=athlete_model.get("tactical_styles") or athlete_model.get("style"),
        fatigue=athlete_model.get("fatigue") or athlete_model.get("fatigue_level") or "low",
        weight_cut_bucket=athlete_model.get("cut_severity_bucket") or "high",
        injury_mode=athlete_model.get("injury_mode") or "full_plan",
        # Eligibility is evaluated only when resolved hard exposure is zero.
        hard_sparring_days_declared=0,
        athlete_model=athlete_model,
    )
    return not bool(rules.get("block_full_plan")) and int(rules.get("glycolytic_touch_max") or 0) >= 1


def _earliest_safe_pressure_slot(
    week_entry: dict,
    athlete_model: dict,
) -> tuple[str, int] | None:
    """Eligibility probe only; this function never owns calendar placement.

    It checks whether any declared training day is still in a canonical bridge
    window that permits glycolytic development. Actual weekday placement remains
    exclusively owned by ``stage2_role_map`` / ``normal_calendar_placement`` via
    the shared combat-load legality policy.
    """
    candidates = [
        (weekday, d_day)
        for weekday, d_day in _training_day_calendar(week_entry, athlete_model)
        if _bridge_allows_glycolytic_on_day(athlete_model, d_day)
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
        "no effective hard combat load is being protected."
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


def install() -> None:
    """Install combat hard-stimulus preservation without becoming a placement owner."""
    from . import stage2_role_map as module

    if getattr(module, "_EMPTY_COMBAT_WEEK_POLICY_INSTALLED", False):
        return

    original_blockers = module._combat_pressure_floor_blockers
    original_compression = module._apply_high_fatigue_week_compression
    original_enforce = module._enforce_combat_pressure_floor

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
        if _is_supported_combat_sport(athlete_model) and _hard_stimulus_deficit(
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
                    )
                    secondary_strength.pop("strength_session_index", None)
                    secondary_strength.pop("athlete_facing_label", None)
        return original_enforce(
            week_entry,
            session_roles,
            suppressed_roles,
            athlete_model,
        )

    module._combat_pressure_floor_blockers = combat_pressure_floor_blockers
    module._apply_high_fatigue_week_compression = apply_high_fatigue_week_compression
    module._enforce_combat_pressure_floor = enforce_combat_pressure_floor
    module._HARD_STIMULUS_DEFICIT_POLICY_INSTALLED = True
    module._EMPTY_COMBAT_WEEK_POLICY_INSTALLED = True
