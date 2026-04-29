"""Deterministic conditioning dosage normalization before Stage 2 rendering."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .selection_metadata import normalize_selection_metadata


VALID_SYSTEMS = {"aerobic", "alactic", "glycolytic"}

ALACTIC_MAX_WORK_SEC = 12
ALACTIC_MIN_REST_SEC = 60
ALACTIC_MAX_DEFAULT_ROUNDS = 6

AEROBIC_MIN_ACTIVE_MINUTES = 8
AEROBIC_TAPER_MIN_ACTIVE_MINUTES = 6
AEROBIC_MAX_RPE_FATIGUE_OR_CUT = 5

GLYCOLYTIC_DENSE_MIN_WORK_SEC = 45
GLYCOLYTIC_DENSE_MAX_REST_SEC = 90
GLYCOLYTIC_DENSE_MIN_ROUNDS = 3
GLYCOLYTIC_SUSTAINED_MIN_MINUTES = 12
GLYCOLYTIC_SUSTAINED_MIN_RPE = 7

TIGHT_TAPER_DAY_LIMIT = 7
HIGH_RISK_CUT_BUCKETS = {"high", "critical", "extreme"}


def _to_number(value: Any) -> float | int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
        return int(parsed) if parsed.is_integer() else parsed
    except (TypeError, ValueError):
        return None

def _to_int(value: Any) -> int | None:
    parsed = _to_number(value)
    if parsed is None:
        return None
    return int(parsed)


def _level(value: Any) -> str:
    return str(value or "").strip().lower()


def _system(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in VALID_SYSTEMS else "aerobic"


def _is_tight_taper(days_until_fight: Any, late_window: str | None) -> bool:
    days = _to_number(days_until_fight)
    if days is not None and days <= TIGHT_TAPER_DAY_LIMIT:
        return True
    return str(late_window or "").lower() in {"d7", "d6_to_d5", "d4_to_d2", "d1"}


def _has_bank_dose(original: dict[str, Any]) -> bool:
    has_interval_dose = all(original.get(field) is not None for field in ("work_sec", "rest_sec", "rounds"))
    return bool(has_interval_dose or original.get("total_minutes") is not None)


def _active_work_minutes(dose: dict[str, Any], system: str) -> float | None:
    work_sec = _to_number(dose.get("work_sec"))
    rounds = _to_number(dose.get("rounds"))
    total_minutes = _to_number(dose.get("total_minutes"))
    if work_sec is not None and rounds is not None:
        return round((float(work_sec) * float(rounds)) / 60, 2)
    if system == "aerobic" and total_minutes is not None:
        return round(float(total_minutes), 2)
    return None


def _elapsed_minutes(dose: dict[str, Any]) -> float | None:
    work_sec = _to_number(dose.get("work_sec"))
    rest_sec = _to_number(dose.get("rest_sec"))
    rounds = _to_number(dose.get("rounds"))
    total_minutes = _to_number(dose.get("total_minutes"))
    if work_sec is not None and rest_sec is not None and rounds is not None:
        elapsed_sec = (float(work_sec) * float(rounds)) + (float(rest_sec) * max(float(rounds) - 1, 0))
        return round(elapsed_sec / 60, 2)
    if total_minutes is not None:
        return round(float(total_minutes), 2)
    return None


def _display(dose: dict[str, Any], system: str) -> str | None:
    rpe = _to_number(dose.get("rpe"))
    work_sec = _to_int(dose.get("work_sec"))
    rest_sec = _to_int(dose.get("rest_sec"))
    rounds = _to_int(dose.get("rounds"))
    total_minutes = _to_number(dose.get("total_minutes"))
    rpe_suffix = f" @ RPE {rpe:g}" if rpe is not None else ""
    if work_sec is not None and rest_sec is not None and rounds is not None:
        return f"{rounds} x {work_sec}s / {rest_sec}s rest{rpe_suffix}"
    if total_minutes is not None:
        label = "continuous" if system == "aerobic" else "controlled"
        return f"{float(total_minutes):g} min {label}{rpe_suffix}"
    return None


def _dense_glycolytic(metadata: dict[str, Any], dose: dict[str, Any]) -> bool:
    lactate_load = _level(metadata.get("lactate_load"))
    work_sec = _to_number(dose.get("work_sec"))
    rest_sec = _to_number(dose.get("rest_sec"))
    rounds = _to_number(dose.get("rounds"))
    total_minutes = _to_number(dose.get("total_minutes"))
    rpe = _to_number(dose.get("rpe"))
    return bool(
        lactate_load == "high"
        or (
            work_sec is not None
            and rest_sec is not None
            and rounds is not None
            and work_sec >= GLYCOLYTIC_DENSE_MIN_WORK_SEC
            and rest_sec <= GLYCOLYTIC_DENSE_MAX_REST_SEC
            and rounds >= GLYCOLYTIC_DENSE_MIN_ROUNDS
        )
        or (
            total_minutes is not None
            and total_minutes >= GLYCOLYTIC_SUSTAINED_MIN_MINUTES
            and rpe is not None
            and rpe >= GLYCOLYTIC_SUSTAINED_MIN_RPE
        )
    )


def _default_dose(system: str, phase: str, days_until_fight: Any, late_window: str | None) -> dict[str, Any]:
    phase = str(phase or "").upper()
    tight_taper = _is_tight_taper(days_until_fight, late_window)
    days = _to_number(days_until_fight)

    if system == "aerobic":
        minutes = 20 if phase == "GPP" else 15
        rpe = 6
        if phase == "TAPER" or tight_taper:
            minutes = 10
            rpe = 5
        if days is not None and days <= 4:
            minutes = 6
            rpe = 4
        return {"work_sec": None, "rest_sec": None, "rounds": None, "total_minutes": minutes, "rpe": rpe}

    if system == "alactic":
        if phase == "TAPER" or tight_taper:
            rounds = 4 if days is None or days > 3 else 3
            return {"work_sec": 8, "rest_sec": 120, "rounds": rounds, "total_minutes": None, "rpe": 6}
        return {"work_sec": 10, "rest_sec": 90, "rounds": ALACTIC_MAX_DEFAULT_ROUNDS, "total_minutes": None, "rpe": 7}

    if tight_taper:
        return {"work_sec": 45, "rest_sec": 90, "rounds": 3, "total_minutes": None, "rpe": 6}
    if phase == "SPP":
        return {"work_sec": 60, "rest_sec": 60, "rounds": 4, "total_minutes": None, "rpe": 7}
    return {"work_sec": 45, "rest_sec": 90, "rounds": 3, "total_minutes": None, "rpe": 6}


def _make_result(
    *,
    status: str,
    source: str,
    intent_status: str,
    system: str,
    dose: dict[str, Any],
    original_dose: dict[str, Any],
    reason_codes: list[str],
    applied_caps: list[str] | None = None,
) -> dict[str, Any]:
    stimulus_preserved = intent_status != "violated"
    active = _active_work_minutes(dose, system) if stimulus_preserved else None
    elapsed = _elapsed_minutes(dose) if stimulus_preserved else None
    return {
        "status": status,
        "source": source,
        "intent_status": intent_status,
        "stimulus_preserved": stimulus_preserved,
        "system": system,
        "work_sec": dose.get("work_sec") if stimulus_preserved else None,
        "rest_sec": dose.get("rest_sec") if stimulus_preserved else None,
        "rounds": dose.get("rounds") if stimulus_preserved else None,
        "active_work_minutes": active,
        "elapsed_minutes": elapsed,
        "rpe": dose.get("rpe") if stimulus_preserved else None,
        "display": _display(dose, system) if stimulus_preserved else None,
        "dose_reason_codes": reason_codes,
        "original_dose": original_dose,
        "applied_caps": applied_caps or [],
    }


def _block(
    *,
    source: str,
    system: str,
    original_dose: dict[str, Any],
    reason_codes: list[str],
) -> dict[str, Any]:
    return _make_result(
        status="blocked",
        source=source,
        intent_status="violated",
        system=system,
        dose={},
        original_dose=original_dose,
        reason_codes=reason_codes,
    )


def _apply_safety_caps(
    *,
    dose: dict[str, Any],
    system: str,
    fatigue: str,
    cut_bucket: str,
    active_weight_cut: bool,
    tight_taper: bool,
) -> tuple[dict[str, Any], list[str]]:
    capped = deepcopy(dose)
    applied: list[str] = []

    def cap_rpe(limit: int, code: str) -> None:
        current = _to_number(capped.get("rpe"))
        if current is not None and current > limit:
            capped["rpe"] = limit
            applied.append(code)

    if fatigue == "high":
        cap_rpe(6 if system == "aerobic" else 7, "dose_capped_high_fatigue")
    elif fatigue == "moderate":
        cap_rpe(7, "dose_capped_moderate_fatigue")

    if active_weight_cut or cut_bucket in HIGH_RISK_CUT_BUCKETS:
        cap_rpe(AEROBIC_MAX_RPE_FATIGUE_OR_CUT if system == "aerobic" else 7, "dose_capped_weight_cut")

    if tight_taper:
        cap_rpe(5 if system == "aerobic" else 6, "dose_capped_late_taper")

    rounds = _to_int(capped.get("rounds"))
    total_minutes = _to_number(capped.get("total_minutes"))
    if system == "aerobic":
        max_minutes = 10 if tight_taper else (15 if fatigue == "high" or active_weight_cut else None)
        if max_minutes is not None and total_minutes is not None and total_minutes > max_minutes:
            capped["total_minutes"] = max_minutes
            applied.append("dose_capped_aerobic_duration")
    elif system == "alactic":
        max_rounds = 4 if tight_taper or fatigue == "high" or active_weight_cut else 6
        if rounds is not None and rounds > max_rounds:
            capped["rounds"] = max_rounds
            applied.append("dose_capped_alactic_rounds")
    elif system == "glycolytic" and not tight_taper:
        if rounds is not None and rounds > 4:
            capped["rounds"] = 4
            applied.append("dose_capped_glycolytic_rounds")
        cap_rpe(7, "dose_capped_glycolytic_rpe")

    return capped, applied


def normalize_conditioning_dose(
    drill: dict | None,
    *,
    system: str,
    phase: str,
    days_until_fight: Any = None,
    late_window: str | None = None,
    fatigue: str | None = None,
    restrictions: list[dict] | None = None,
    injuries: list[str] | None = None,
    weight_cut_risk: bool | None = None,
    weight_cut_pct: Any = None,
    cut_bucket: str | None = None,
    training_frequency: Any = None,
) -> dict[str, Any]:
    """Return the authoritative conditioning dose for a selected drill.

    Caps reduce load only when the original energy-system intent remains intact.
    If safety caps would turn the drill into a different stimulus, the option is
    blocked so Stage 2 can promote a compliant alternate instead.
    """
    del restrictions, injuries, training_frequency  # Inputs kept in the public contract for future rules.

    drill = drill or {}
    resolved_system = _system(system or drill.get("system"))
    metadata = normalize_selection_metadata(drill)
    original_dose = {
        "work_sec": _to_number(metadata.get("work_sec")),
        "rest_sec": _to_number(metadata.get("rest_sec")),
        "rounds": _to_number(metadata.get("rounds")),
        "total_minutes": _to_number(metadata.get("total_minutes")),
        "rpe": _to_number(metadata.get("rpe")),
    }
    has_bank_dose = _has_bank_dose(original_dose)
    source = "bank_metadata" if has_bank_dose else "default_template"
    dose = deepcopy(original_dose) if has_bank_dose else _default_dose(
        resolved_system,
        phase,
        days_until_fight,
        late_window,
    )
    if not has_bank_dose and original_dose.get("rpe") is not None:
        default_rpe = _to_number(dose.get("rpe"))
        original_rpe = _to_number(original_dose.get("rpe"))
        if default_rpe is not None and original_rpe is not None:
            dose["rpe"] = min(default_rpe, original_rpe)

    fatigue_level = _level(fatigue)
    bucket = _level(cut_bucket)
    cut_pct = _to_number(weight_cut_pct) or 0
    active_weight_cut = bool(weight_cut_risk or cut_pct >= 3 or bucket in {"moderate", *HIGH_RISK_CUT_BUCKETS})
    tight_taper = _is_tight_taper(days_until_fight, late_window)

    if resolved_system == "alactic":
        work_sec = (
            _to_number(original_dose.get("work_sec"))
            if original_dose.get("work_sec") is not None
            else _to_number(dose.get("work_sec"))
        )
        rest_sec = (
            _to_number(original_dose.get("rest_sec"))
            if original_dose.get("rest_sec") is not None
            else _to_number(dose.get("rest_sec"))
        )
        if work_sec is not None and work_sec > ALACTIC_MAX_WORK_SEC:
            return _block(
                source=source,
                system=resolved_system,
                original_dose=original_dose,
                reason_codes=["dose_blocked_system_metadata_conflict"],
            )
        if rest_sec is not None and rest_sec < ALACTIC_MIN_REST_SEC:
            return _block(
                source=source,
                system=resolved_system,
                original_dose=original_dose,
                reason_codes=["dose_blocked_system_metadata_conflict"],
            )

    dense_glycolytic = _dense_glycolytic(metadata, dose)
    high_lactate = _level(metadata.get("lactate_load")) == "high"
    if resolved_system == "glycolytic":
        if tight_taper and (dense_glycolytic or high_lactate):
            return _block(
                source=source,
                system=resolved_system,
                original_dose=original_dose,
                reason_codes=["dose_blocked_glycolytic_tight_window"],
            )
        if fatigue_level == "high" and (dense_glycolytic or high_lactate):
            return _block(
                source=source,
                system=resolved_system,
                original_dose=original_dose,
                reason_codes=["dose_blocked_high_fatigue_glycolytic_density"],
            )
        if bucket in HIGH_RISK_CUT_BUCKETS and (dense_glycolytic or high_lactate):
            return _block(
                source=source,
                system=resolved_system,
                original_dose=original_dose,
                reason_codes=["dose_blocked_high_lactate_cut_pressure"],
            )
        if active_weight_cut and fatigue_level in {"moderate", "high"} and (dense_glycolytic or high_lactate):
            return _block(
                source=source,
                system=resolved_system,
                original_dose=original_dose,
                reason_codes=["dose_blocked_high_lactate_cut_pressure"],
            )

    capped_dose, applied_caps = _apply_safety_caps(
        dose=dose,
        system=resolved_system,
        fatigue=fatigue_level,
        cut_bucket=bucket,
        active_weight_cut=active_weight_cut,
        tight_taper=tight_taper,
    )

    active_minutes = _active_work_minutes(capped_dose, resolved_system)
    elapsed_minutes = _elapsed_minutes(capped_dose)
    if resolved_system == "aerobic":
        minimum = AEROBIC_TAPER_MIN_ACTIVE_MINUTES if tight_taper else AEROBIC_MIN_ACTIVE_MINUTES
        minute_signals = [
            value for value in (active_minutes, elapsed_minutes, _to_number(capped_dose.get("total_minutes")))
            if value is not None
        ]
        aerobic_minutes = max(minute_signals) if minute_signals else None
        if aerobic_minutes is not None and aerobic_minutes < minimum:
            return _block(
                source=source,
                system=resolved_system,
                original_dose=original_dose,
                reason_codes=["dose_blocked_aerobic_too_short"],
            )

    if resolved_system == "glycolytic" and applied_caps:
        before_dense = _dense_glycolytic(metadata, dose)
        after_dense = _dense_glycolytic(metadata, capped_dose)
        if before_dense and not after_dense:
            return _block(
                source=source,
                system=resolved_system,
                original_dose=original_dose,
                reason_codes=["dose_blocked_caps_would_change_stimulus"],
            )

    status = "capped" if applied_caps else ("prescribed" if has_bank_dose else "defaulted")
    result_source = "capped_bank_metadata" if applied_caps and has_bank_dose else source
    reason_codes = ["dose_preserved_bank_metadata"] if has_bank_dose else ["dose_defaulted_missing_metadata"]
    reason_codes.extend(applied_caps)

    return _make_result(
        status=status,
        source=result_source,
        intent_status="preserved",
        system=resolved_system,
        dose=capped_dose,
        original_dose=original_dose,
        reason_codes=reason_codes,
        applied_caps=applied_caps,
    )
