from __future__ import annotations

from datetime import datetime
from typing import Any

from fightcamp.camp_phases import calculate_phase_weeks
from fightcamp.input_parsing import _compute_days_until_fight, is_short_notice_days
from fightcamp.mindset_module import classify_mental_block
from fightcamp.plan_pipeline_runtime import STYLE_MAP
from fightcamp.stage2_payload import _derive_readiness_flags, _is_high_pressure_weight_cut
from fightcamp.stage2_payload_late_fight import _fight_week_override_band
from fightcamp.weight_cut import compute_weight_cut_pct

from .models import (
    AdminAthleteRecord,
    GuidedInjuryInput,
    NutritionBodyweightLogEntry,
    NutritionCoachControlsInput,
    NutritionDerivedState,
    NutritionMonitoringInput,
    NutritionProfileInput,
    NutritionReadinessInput,
    NutritionSandCPreferences,
    NutritionSharedCampContext,
    NutritionWorkspaceState,
    NutritionWorkspaceUpdateRequest,
    ProfileRecord,
)

_DAY_ORDER = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def _coerce_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = value.split(",")
    elif isinstance(value, list):
        parts = value
    else:
        parts = [value]
    cleaned: list[str] = []
    for part in parts:
        normalized = str(part or "").strip()
        if normalized:
            cleaned.append(normalized)
    return cleaned


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    normalized = str(value).strip()
    if not normalized:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(round(float(value)))
    normalized = str(value).strip()
    if not normalized:
        return None
    try:
        return int(round(float(normalized)))
    except ValueError:
        return None


def _coerce_optional_str(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _coerce_guided_injury(value: Any) -> GuidedInjuryInput | None:
    if value is None:
        return None
    try:
        guided = GuidedInjuryInput.model_validate(value)
    except Exception:
        return None
    if not any(
        [
            guided.area.strip(),
            guided.severity.strip(),
            guided.trend.strip(),
            guided.avoid.strip(),
            guided.notes.strip(),
        ]
    ):
        return None
    return guided


def _coerce_bodyweight_log(value: Any) -> list[NutritionBodyweightLogEntry]:
    if not isinstance(value, list):
        return []
    entries: list[NutritionBodyweightLogEntry] = []
    for entry in value:
        try:
            entries.append(NutritionBodyweightLogEntry.model_validate(entry))
        except Exception:
            continue
    return entries


def _infer_weight_source(
    *,
    explicit_source: str | None,
    current_weight_kg: float | None,
    current_weight_recorded_at: str | None,
    daily_bodyweight_log: list[NutritionBodyweightLogEntry],
) -> str | None:
    if explicit_source:
        return explicit_source
    if current_weight_kg is None:
        return None
    if daily_bodyweight_log:
        latest = _latest_bodyweight_log_entry(daily_bodyweight_log)
        if latest and abs(float(latest.weight_kg) - float(current_weight_kg)) < 0.01:
            return "latest_bodyweight_log"
    if current_weight_recorded_at:
        return "manual"
    return "imported"


def _latest_bodyweight_log_entry(entries: list[NutritionBodyweightLogEntry]) -> NutritionBodyweightLogEntry | None:
    if not entries:
        return None

    def _sort_key(entry: NutritionBodyweightLogEntry) -> tuple[str, str]:
        return (entry.date, entry.time or "")

    return sorted(entries, key=_sort_key)[-1]


def _rolling_7_day_average(entries: list[NutritionBodyweightLogEntry]) -> float | None:
    if not entries:
        return None
    recent = sorted(entries, key=lambda entry: (entry.date, entry.time or ""), reverse=True)[:7]
    if not recent:
        return None
    average = sum(entry.weight_kg for entry in recent) / len(recent)
    return round(average, 1)


def _merge_unique_days(*day_lists: list[str]) -> list[str]:
    merged: list[str] = []
    for day_list in day_lists:
        for day in day_list:
            if day and day not in merged:
                merged.append(day)
    return merged


def _derive_restriction_level(
    explicit_level: str | None,
    guided_injury: GuidedInjuryInput | None,
) -> str | None:
    if explicit_level:
        return explicit_level
    severity = str(guided_injury.severity if guided_injury else "").strip().lower()
    if severity == "low":
        return "minor"
    if severity == "moderate":
        return "moderate"
    if severity == "high":
        return "major"
    return None


def _derive_session_types(
    *,
    explicit_value: dict[str, Any],
    training_availability: list[str],
    hard_sparring_days: list[str],
    technical_skill_days: list[str],
) -> dict[str, str]:
    cleaned = {
        str(day or "").strip().lower(): str(session_type or "").strip().lower()
        for day, session_type in explicit_value.items()
        if str(day or "").strip() and str(session_type or "").strip()
    }

    derived: dict[str, str] = {}
    training_days = {day.strip().lower() for day in training_availability if str(day).strip()}
    hard_days = {day.strip().lower() for day in hard_sparring_days if str(day).strip()}
    technical_days = {day.strip().lower() for day in technical_skill_days if str(day).strip()}
    for day, session_type in cleaned.items():
        if day in training_days:
            derived[day] = session_type
    for day in training_availability:
        normalized_day = str(day or "").strip().lower()
        if normalized_day in hard_days:
            derived[normalized_day] = "hard_spar"
        elif normalized_day in technical_days:
            derived[normalized_day] = "technical"
    return derived


def normalize_nutrition_update_request(
    *,
    update: NutritionWorkspaceUpdateRequest,
    existing_shared_camp_context: NutritionSharedCampContext | None = None,
) -> NutritionWorkspaceUpdateRequest:
    payload = update.model_dump(mode="json")
    shared_payload = _coerce_dict(payload.get("shared_camp_context"))
    existing_training_availability = (
        list(existing_shared_camp_context.training_availability) if existing_shared_camp_context else []
    )
    existing_session_types = (
        dict(existing_shared_camp_context.session_types_by_day) if existing_shared_camp_context else {}
    )
    hard_sparring_days = _clean_list(shared_payload.get("hard_sparring_days"))
    technical_skill_days = _clean_list(shared_payload.get("technical_skill_days"))
    training_availability = _merge_unique_days(
        _clean_list(shared_payload.get("training_availability")),
        existing_training_availability,
        hard_sparring_days,
        technical_skill_days,
    )
    shared_payload["training_availability"] = training_availability
    shared_payload["session_types_by_day"] = _derive_session_types(
        explicit_value=shared_payload.get("session_types_by_day") or existing_session_types,
        training_availability=training_availability,
        hard_sparring_days=hard_sparring_days,
        technical_skill_days=technical_skill_days,
    )
    payload["shared_camp_context"] = shared_payload
    return NutritionWorkspaceUpdateRequest.model_validate(payload)


def _has_active_workspace_data(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if any(
        key in payload
        for key in (
            "shared_camp_context",
            "nutrition_readiness",
            "nutrition_monitoring",
            "nutrition_coach_controls",
            "s_and_c_preferences",
        )
    ):
        return True
    athlete = _coerce_dict(payload.get("athlete"))
    return any(
        [
            athlete.get("weight_kg") is not None,
            athlete.get("target_weight_kg") is not None,
            athlete.get("age") is not None,
            athlete.get("height_cm") is not None,
            payload.get("fight_date"),
            payload.get("training_availability"),
            payload.get("weekly_training_frequency"),
            payload.get("fatigue_level"),
        ]
    )


def _profile_defaults(profile: ProfileRecord | AdminAthleteRecord) -> NutritionProfileInput:
    try:
        return NutritionProfileInput.model_validate(profile.nutrition_profile.model_dump(mode="json"))
    except Exception:
        return NutritionProfileInput()


def _build_nutrition_profile(
    *,
    profile: ProfileRecord | AdminAthleteRecord,
    raw_payload: dict[str, Any],
) -> NutritionProfileInput:
    defaults = _profile_defaults(profile)
    raw_athlete = _coerce_dict(raw_payload.get("athlete"))
    athlete_sex = _coerce_optional_str(raw_athlete.get("sex"))
    athlete_age = _coerce_optional_int(raw_athlete.get("age"))
    athlete_height_cm = _coerce_optional_int(raw_athlete.get("height_cm"))
    return NutritionProfileInput.model_validate(
        {
            **defaults.model_dump(mode="json"),
            "sex": athlete_sex or defaults.sex,
            "age": athlete_age if athlete_age is not None else defaults.age,
            "height_cm": athlete_height_cm if athlete_height_cm is not None else defaults.height_cm,
        }
    )


def _build_shared_camp_context(
    raw_payload: dict[str, Any],
    monitoring: NutritionMonitoringInput,
) -> NutritionSharedCampContext:
    raw_shared = _coerce_dict(raw_payload.get("shared_camp_context"))
    raw_athlete = _coerce_dict(raw_payload.get("athlete"))
    explicit_source = _coerce_optional_str(raw_shared.get("current_weight_source"))
    explicit_recorded_at = _coerce_optional_str(raw_shared.get("current_weight_recorded_at"))
    athlete_current_weight_kg = _coerce_optional_float(raw_athlete.get("weight_kg"))
    athlete_target_weight_kg = _coerce_optional_float(raw_athlete.get("target_weight_kg"))
    current_weight_kg = athlete_current_weight_kg
    if current_weight_kg is None:
        current_weight_kg = _coerce_optional_float(raw_shared.get("current_weight_kg"))
    target_weight_kg = athlete_target_weight_kg
    if target_weight_kg is None:
        target_weight_kg = _coerce_optional_float(raw_shared.get("target_weight_kg"))

    shared = NutritionSharedCampContext.model_validate(
        {
            "fight_date": _coerce_optional_str(raw_shared.get("fight_date"))
            or _coerce_optional_str(raw_payload.get("fight_date"))
            or "",
            "rounds_format": _coerce_optional_str(raw_shared.get("rounds_format"))
            or _coerce_optional_str(raw_payload.get("rounds_format"))
            or "3 x 3",
            "weigh_in_type": _coerce_optional_str(raw_shared.get("weigh_in_type")),
            "weigh_in_time": _coerce_optional_str(raw_shared.get("weigh_in_time")),
            "current_weight_kg": current_weight_kg,
            "current_weight_recorded_at": explicit_recorded_at,
            "current_weight_source": explicit_source,
            "target_weight_kg": target_weight_kg,
            "target_weight_range_kg": raw_shared.get("target_weight_range_kg"),
            "phase_override": _coerce_optional_str(raw_shared.get("phase_override")),
            "fatigue_level": _coerce_optional_str(raw_shared.get("fatigue_level"))
            or _coerce_optional_str(raw_payload.get("fatigue_level")),
            "weekly_training_frequency": raw_shared.get("weekly_training_frequency")
            if raw_shared.get("weekly_training_frequency") is not None
            else raw_payload.get("weekly_training_frequency"),
            "training_availability": raw_shared.get("training_availability")
            or raw_payload.get("training_availability")
            or [],
            "hard_sparring_days": raw_shared.get("hard_sparring_days")
            or raw_payload.get("hard_sparring_days")
            or [],
            "technical_skill_days": raw_shared.get("technical_skill_days")
            or raw_payload.get("technical_skill_days")
            or [],
            "session_types_by_day": raw_shared.get("session_types_by_day") or {},
            "injuries": _coerce_optional_str(raw_shared.get("injuries"))
            or _coerce_optional_str(raw_payload.get("injuries"))
            or "",
            "guided_injury": raw_shared.get("guided_injury") or raw_payload.get("guided_injury"),
            "training_restriction_level": _coerce_optional_str(raw_shared.get("training_restriction_level")),
        }
    )

    shared.training_availability = _merge_unique_days(
        shared.training_availability,
        shared.hard_sparring_days,
        shared.technical_skill_days,
    )
    shared.session_types_by_day = _derive_session_types(
        explicit_value=raw_shared.get("session_types_by_day") or {},
        training_availability=shared.training_availability,
        hard_sparring_days=shared.hard_sparring_days,
        technical_skill_days=shared.technical_skill_days,
    )
    shared.training_restriction_level = _derive_restriction_level(
        shared.training_restriction_level,
        shared.guided_injury,
    )

    inferred_source = _infer_weight_source(
        explicit_source=shared.current_weight_source,
        current_weight_kg=shared.current_weight_kg,
        current_weight_recorded_at=shared.current_weight_recorded_at,
        daily_bodyweight_log=monitoring.daily_bodyweight_log,
    )
    shared.current_weight_source = inferred_source  # type: ignore[assignment]

    if shared.current_weight_source == "latest_bodyweight_log" and not shared.current_weight_recorded_at:
        latest_entry = _latest_bodyweight_log_entry(monitoring.daily_bodyweight_log)
        if latest_entry:
            shared.current_weight_recorded_at = f"{latest_entry.date}T{latest_entry.time}" if latest_entry.time else latest_entry.date

    return shared


def _build_s_and_c_preferences(raw_payload: dict[str, Any]) -> NutritionSandCPreferences:
    raw_section = _coerce_dict(raw_payload.get("s_and_c_preferences"))
    return NutritionSandCPreferences.model_validate(
        {
            "equipment_access": raw_section.get("equipment_access") or raw_payload.get("equipment_access") or [],
            "key_goals": raw_section.get("key_goals") or raw_payload.get("key_goals") or [],
            "weak_areas": raw_section.get("weak_areas") or raw_payload.get("weak_areas") or [],
            "training_preference": _coerce_optional_str(raw_section.get("training_preference"))
            or _coerce_optional_str(raw_payload.get("training_preference"))
            or "",
            "mindset_challenges": _coerce_optional_str(raw_section.get("mindset_challenges"))
            or _coerce_optional_str(raw_payload.get("mindset_challenges"))
            or "",
            "notes": _coerce_optional_str(raw_section.get("notes"))
            or _coerce_optional_str(raw_payload.get("notes"))
            or "",
            "random_seed": raw_section.get("random_seed")
            if raw_section.get("random_seed") is not None
            else raw_payload.get("random_seed"),
        }
    )


def _build_readiness(raw_payload: dict[str, Any]) -> NutritionReadinessInput:
    return NutritionReadinessInput.model_validate(_coerce_dict(raw_payload.get("nutrition_readiness")))


def _build_monitoring(raw_payload: dict[str, Any]) -> NutritionMonitoringInput:
    raw_section = _coerce_dict(raw_payload.get("nutrition_monitoring"))
    return NutritionMonitoringInput(
        daily_bodyweight_log=_coerce_bodyweight_log(raw_section.get("daily_bodyweight_log")),
    )


def _build_coach_controls(raw_payload: dict[str, Any]) -> NutritionCoachControlsInput:
    raw_section = _coerce_dict(raw_payload.get("nutrition_coach_controls"))
    return NutritionCoachControlsInput.model_validate(raw_section)


def _compute_days_out(fight_date: str, athlete_timezone: str) -> int | None:
    normalized = str(fight_date or "").strip()
    if not normalized:
        return None
    try:
        fight_dt = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        try:
            fight_dt = datetime.fromisoformat(f"{normalized}T00:00:00")
        except ValueError:
            return None
    return _compute_days_until_fight(normalized, fight_dt, athlete_timezone=athlete_timezone or None)


def _resolve_effective_phase(
    *,
    phase_override: str | None,
    days_until_fight: int | None,
    current_weight_kg: float | None,
    target_weight_kg: float | None,
    fatigue_level: str | None,
    technical_style: list[str],
    tactical_style: list[str],
    professional_status: str,
    mindset_challenges: str,
) -> str | None:
    if phase_override:
        return phase_override

    if days_until_fight is None:
        return None

    primary_technical = technical_style[0].strip().lower() if technical_style else ""
    mapped_format = STYLE_MAP.get(primary_technical)
    if mapped_format:
        weight_cut_pct = compute_weight_cut_pct(current_weight_kg or 0.0, target_weight_kg or 0.0)
        weight_cut_risk = weight_cut_pct >= 3.0
        mental_block = classify_mental_block(mindset_challenges or "")
        phase_weeks = calculate_phase_weeks(
            max(1, days_until_fight // 7),
            mapped_format,
            tactical_style,
            professional_status,
            fatigue_level,
            weight_cut_risk,
            mental_block,
            weight_cut_pct,
            days_until_fight,
        )
        phase_days = phase_weeks.get("days") or {}
        taper_days = int(phase_days.get("TAPER") or 0)
        spp_days = int(phase_days.get("SPP") or 0)
        if days_until_fight <= taper_days:
            return "TAPER"
        if days_until_fight <= taper_days + spp_days:
            return "SPP"
        return "GPP"

    if days_until_fight <= 7:
        return "Fight week"
    if days_until_fight <= 14:
        return "TAPER"
    if days_until_fight <= 35:
        return "SPP"
    return "GPP"


def _missing_required_fields(
    *,
    nutrition_profile: NutritionProfileInput,
    shared_camp_context: NutritionSharedCampContext,
) -> list[str]:
    missing: list[str] = []
    if nutrition_profile.sex is None:
        missing.append("sex")
    if nutrition_profile.age is None:
        missing.append("age")
    if nutrition_profile.height_cm is None:
        missing.append("height_cm")
    if shared_camp_context.current_weight_kg is None:
        missing.append("current_weight_kg")
    if shared_camp_context.target_weight_kg is None:
        missing.append("target_weight_kg")
    if not shared_camp_context.fight_date:
        missing.append("fight_date")
    if shared_camp_context.weigh_in_type is None:
        missing.append("weigh_in_type")
    if shared_camp_context.weekly_training_frequency is None:
        missing.append("weekly_training_frequency")
    if shared_camp_context.fatigue_level is None:
        missing.append("fatigue_level")
    return missing


def _foundation_status(
    *,
    missing_required_fields: list[str],
    readiness: NutritionReadinessInput,
    monitoring: NutritionMonitoringInput,
) -> str:
    if missing_required_fields:
        return "incomplete"
    if readiness.sleep_quality and monitoring.daily_bodyweight_log:
        return "complete"
    return "sufficient"


def build_nutrition_workspace(
    *,
    profile: ProfileRecord | AdminAthleteRecord,
    latest_intake_row: dict[str, Any] | None = None,
) -> NutritionWorkspaceState:
    draft_payload = profile.onboarding_draft if isinstance(profile.onboarding_draft, dict) else None
    latest_intake_payload = (
        latest_intake_row.get("intake")
        if isinstance(latest_intake_row, dict) and isinstance(latest_intake_row.get("intake"), dict)
        else None
    )

    if _has_active_workspace_data(draft_payload):
        source = "draft"
        intake_id = None
        raw_payload = draft_payload or {}
    elif latest_intake_payload is not None:
        source = "intake"
        intake_id = str(latest_intake_row.get("id") or "") or None
        raw_payload = latest_intake_payload
    else:
        source = "default"
        intake_id = None
        raw_payload = {}

    monitoring = _build_monitoring(raw_payload)
    shared_camp_context = _build_shared_camp_context(raw_payload, monitoring)
    nutrition_profile = _build_nutrition_profile(profile=profile, raw_payload=raw_payload)
    s_and_c_preferences = _build_s_and_c_preferences(raw_payload)
    readiness = _build_readiness(raw_payload)
    coach_controls = _build_coach_controls(raw_payload)

    raw_athlete = _coerce_dict(raw_payload.get("athlete"))
    technical_style = _clean_list(raw_athlete.get("technical_style") or profile.technical_style)
    tactical_style = _clean_list(raw_athlete.get("tactical_style") or profile.tactical_style)
    professional_status = _coerce_optional_str(raw_athlete.get("professional_status")) or profile.professional_status
    days_until_fight = _compute_days_out(shared_camp_context.fight_date, profile.athlete_timezone)
    weight_cut_pct = compute_weight_cut_pct(shared_camp_context.current_weight_kg or 0.0, shared_camp_context.target_weight_kg or 0.0)
    weight_cut_risk = weight_cut_pct >= 3.0
    injuries_for_flags = []
    if shared_camp_context.injuries.strip():
        injuries_for_flags.append(shared_camp_context.injuries.strip())
    if shared_camp_context.guided_injury and shared_camp_context.guided_injury.area.strip():
        injuries_for_flags.append(shared_camp_context.guided_injury.area.strip())
    short_notice = is_short_notice_days(days_until_fight)
    readiness_flags = _derive_readiness_flags(
        fatigue=shared_camp_context.fatigue_level or "",
        weight_cut_risk=weight_cut_risk,
        weight_cut_pct=weight_cut_pct,
        injuries=injuries_for_flags,
        short_notice=short_notice,
        days_until_fight=days_until_fight,
    )
    athlete_model = {
        "readiness_flags": readiness_flags,
        "weight_cut_risk": weight_cut_risk,
        "fatigue": shared_camp_context.fatigue_level or "",
        "days_until_fight": days_until_fight,
    }
    effective_phase = _resolve_effective_phase(
        phase_override=shared_camp_context.phase_override,
        days_until_fight=days_until_fight,
        current_weight_kg=shared_camp_context.current_weight_kg,
        target_weight_kg=shared_camp_context.target_weight_kg,
        fatigue_level=shared_camp_context.fatigue_level,
        technical_style=technical_style,
        tactical_style=tactical_style,
        professional_status=professional_status,
        mindset_challenges=s_and_c_preferences.mindset_challenges,
    )
    missing_required_fields = _missing_required_fields(
        nutrition_profile=nutrition_profile,
        shared_camp_context=shared_camp_context,
    )

    derived = NutritionDerivedState(
        days_until_fight=days_until_fight,
        weight_cut_pct=weight_cut_pct,
        weight_cut_risk=weight_cut_risk,
        aggressive_weight_cut=weight_cut_pct >= 5.0,
        high_pressure_weight_cut=_is_high_pressure_weight_cut(athlete_model=athlete_model),
        short_notice=short_notice,
        fight_week=isinstance(days_until_fight, int) and 0 <= days_until_fight <= 7,
        readiness_flags=readiness_flags,
        fight_week_override_band=_fight_week_override_band(days_until_fight),
        current_phase_effective=effective_phase,
        rolling_7_day_average_weight=_rolling_7_day_average(monitoring.daily_bodyweight_log),
        foundation_status=_foundation_status(
            missing_required_fields=missing_required_fields,
            readiness=readiness,
            monitoring=monitoring,
        ),
        missing_required_fields=missing_required_fields,
    )

    return NutritionWorkspaceState(
        athlete_id=profile.athlete_id,
        source=source,
        intake_id=intake_id,
        nutrition_profile=nutrition_profile,
        shared_camp_context=shared_camp_context,
        s_and_c_preferences=s_and_c_preferences,
        nutrition_readiness=readiness,
        nutrition_monitoring=monitoring,
        nutrition_coach_controls=coach_controls,
        derived=derived,
    )


def merge_workspace_into_payload(
    *,
    base_payload: dict[str, Any] | None,
    workspace: NutritionWorkspaceUpdateRequest,
    profile: ProfileRecord | AdminAthleteRecord,
) -> dict[str, Any]:
    merged = dict(base_payload or {})
    raw_athlete = _coerce_dict(merged.get("athlete"))
    shared = workspace.shared_camp_context
    s_and_c_preferences = workspace.s_and_c_preferences
    athlete_sex = _coerce_optional_str(raw_athlete.get("sex"))
    athlete_age = _coerce_optional_int(raw_athlete.get("age"))
    athlete_weight_kg = _coerce_optional_float(raw_athlete.get("weight_kg"))
    athlete_target_weight_kg = _coerce_optional_float(raw_athlete.get("target_weight_kg"))
    athlete_height_cm = _coerce_optional_int(raw_athlete.get("height_cm"))
    base_shared = _coerce_dict(merged.get("shared_camp_context"))
    training_availability = _merge_unique_days(
        list(shared.training_availability),
        _clean_list(base_shared.get("training_availability") or merged.get("training_availability")),
        list(shared.hard_sparring_days),
        list(shared.technical_skill_days),
    )

    athlete_payload = {
        **raw_athlete,
        "full_name": _coerce_optional_str(raw_athlete.get("full_name")) or profile.full_name,
        "sex": athlete_sex or workspace.nutrition_profile.sex,
        "age": athlete_age if athlete_age is not None else workspace.nutrition_profile.age,
        "weight_kg": athlete_weight_kg if athlete_weight_kg is not None else shared.current_weight_kg,
        "target_weight_kg": athlete_target_weight_kg if athlete_target_weight_kg is not None else shared.target_weight_kg,
        "height_cm": athlete_height_cm if athlete_height_cm is not None else workspace.nutrition_profile.height_cm,
        "technical_style": raw_athlete.get("technical_style") or list(profile.technical_style),
        "tactical_style": raw_athlete.get("tactical_style") or list(profile.tactical_style),
        "stance": _coerce_optional_str(raw_athlete.get("stance")) or profile.stance,
        "professional_status": _coerce_optional_str(raw_athlete.get("professional_status")) or profile.professional_status,
        "record": _coerce_optional_str(raw_athlete.get("record")) or profile.record,
        "athlete_timezone": _coerce_optional_str(raw_athlete.get("athlete_timezone")) or profile.athlete_timezone,
        "athlete_locale": _coerce_optional_str(raw_athlete.get("athlete_locale")) or profile.athlete_locale,
    }

    session_types_by_day = {
        day: session_type
        for day, session_type in _derive_session_types(
            explicit_value=base_shared.get("session_types_by_day") or workspace.shared_camp_context.session_types_by_day,
            training_availability=training_availability,
            hard_sparring_days=shared.hard_sparring_days,
            technical_skill_days=shared.technical_skill_days,
        ).items()
        if day and session_type
    }
    shared_payload = {
        **shared.model_dump(mode="json"),
        "current_weight_kg": athlete_payload.get("weight_kg"),
        "target_weight_kg": athlete_payload.get("target_weight_kg"),
        "training_availability": training_availability,
        "session_types_by_day": session_types_by_day,
    }

    merged.update(
        {
            "athlete": athlete_payload,
            "fight_date": shared.fight_date,
            "rounds_format": shared.rounds_format,
            "weekly_training_frequency": shared.weekly_training_frequency,
            "fatigue_level": shared.fatigue_level,
            "equipment_access": list(s_and_c_preferences.equipment_access),
            "training_availability": training_availability,
            "hard_sparring_days": list(shared.hard_sparring_days),
            "technical_skill_days": list(shared.technical_skill_days),
            "injuries": shared.injuries,
            "guided_injury": shared.guided_injury.model_dump(mode="json") if shared.guided_injury else None,
            "key_goals": list(s_and_c_preferences.key_goals),
            "weak_areas": list(s_and_c_preferences.weak_areas),
            "training_preference": s_and_c_preferences.training_preference,
            "mindset_challenges": s_and_c_preferences.mindset_challenges,
            "notes": s_and_c_preferences.notes,
            "random_seed": s_and_c_preferences.random_seed,
            "shared_camp_context": shared_payload,
            "s_and_c_preferences": s_and_c_preferences.model_dump(mode="json"),
            "nutrition_readiness": workspace.nutrition_readiness.model_dump(mode="json"),
            "nutrition_monitoring": workspace.nutrition_monitoring.model_dump(mode="json"),
            "nutrition_coach_controls": workspace.nutrition_coach_controls.model_dump(mode="json"),
        }
    )
    return merged

