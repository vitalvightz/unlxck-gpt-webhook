"""Canonical Stage 2 athlete model construction.

Single source of truth for `_build_athlete_model` and the helpers that derive
record/competitive maturity, readiness flags, and the high-pressure weight-cut
predicate. Both ``stage2_payload`` and ``stage2_planning_brief`` re-export
these names for backwards compatibility — there must not be a second real
implementation living elsewhere.

Active-injury state is sourced from ``stage2_render_guards`` so that the
``"none"`` / ``"none."`` / ``"n/a!"`` / ``"nil"`` family of markers cannot
silently flip the athlete into an injured state.
"""
from __future__ import annotations

import re

from .normalization import clean_list
from .stage2_render_guards import _has_active_injury_from_training_context
from .training_context import TrainingContext
from .weight_cut import compute_cut_severity_score, cut_severity_bucket


_RECORD_PATTERN = re.compile(r"^(\d+)-(\d+)(?:-(\d+))?$")
_UNKNOWN_COMPETITIVE_MATURITY = "unknown_competitive_maturity"


def _parse_record(record: str) -> dict:
    normalized = str(record or "").strip()
    match = _RECORD_PATTERN.fullmatch(normalized)
    if not match:
        return {
            "record": normalized,
            "wins": None,
            "losses": None,
            "draws": None,
            "total_bouts": None,
            "competitive_maturity": _UNKNOWN_COMPETITIVE_MATURITY,
        }

    wins = int(match.group(1))
    losses = int(match.group(2))
    draws = int(match.group(3)) if match.group(3) is not None else 0
    return {
        "record": normalized,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "total_bouts": wins + losses + draws,
        "competitive_maturity": _UNKNOWN_COMPETITIVE_MATURITY,
    }


def _derive_competitive_maturity(status: str, record: str) -> dict:
    parsed_record = _parse_record(record)
    normalized_status = str(status or "").strip().lower()
    total_bouts = parsed_record.get("total_bouts")

    competitive_maturity = _UNKNOWN_COMPETITIVE_MATURITY
    if normalized_status == "amateur" and isinstance(total_bouts, int):
        if total_bouts <= 4:
            competitive_maturity = "novice_amateur"
        elif total_bouts <= 11:
            competitive_maturity = "developing_amateur"
        else:
            competitive_maturity = "experienced_amateur"

    parsed_record["competitive_maturity"] = competitive_maturity
    return parsed_record


def _derive_readiness_flags(
    *,
    fatigue: str,
    weight_cut_risk: bool,
    weight_cut_pct: float,
    injuries: list[str],
    short_notice: bool,
    days_until_fight: int | None,
) -> list[str]:
    flags: list[str] = []
    fatigue_value = (fatigue or "").strip().lower()
    if fatigue_value in {"moderate", "high"}:
        flags.append(f"{fatigue_value}_fatigue")
    if weight_cut_risk:
        flags.append("active_weight_cut")
    if weight_cut_pct >= 5.0:
        flags.append("aggressive_weight_cut")
    if injuries:
        flags.append("injury_management")
    if short_notice:
        flags.append("short_notice")
    if isinstance(days_until_fight, int) and 0 <= days_until_fight <= 7:
        flags.append("fight_week")
    return flags or ["baseline"]


def _is_high_pressure_weight_cut(*, athlete_model: dict) -> bool:
    readiness_flags = set(clean_list(athlete_model.get("readiness_flags", [])))
    if "aggressive_weight_cut" in readiness_flags:
        return True
    if not (
        athlete_model.get("weight_cut_risk")
        or "active_weight_cut" in readiness_flags
    ):
        return False
    fatigue = str(athlete_model.get("fatigue", "")).strip().lower()
    days_until_fight = athlete_model.get("days_until_fight")
    return fatigue in {"moderate", "high"} or (
        isinstance(days_until_fight, int) and days_until_fight <= 28
    )


def _build_athlete_model(
    *,
    training_context: TrainingContext,
    sport: str,
    record: str,
    rounds_format: str,
    camp_length_weeks: int,
    short_notice: bool,
) -> dict:
    # Indirect through stage2_planning_brief at call time so existing tests
    # that monkeypatch ``stage2_planning_brief._utc_now`` keep working.
    from . import stage2_planning_brief as _planning_brief

    record_profile = _derive_competitive_maturity(training_context.status, record)
    plan_creation_dt = _planning_brief._athlete_calendar_now(
        training_context.athlete_timezone,
        now_utc=_planning_brief._utc_now(),
    )
    cut_severity_score = compute_cut_severity_score(
        training_context.weight_cut_pct,
        training_context.days_until_fight,
    )
    # If support_work_days isn't declared, fall back to legacy technical_skill_days
    # so coach-led technical days are still preserved for downstream
    # role-map/late-fight/finalizer consumers.
    support_work_days = (
        training_context.support_work_days or training_context.technical_skill_days
    )
    has_active_injury = _has_active_injury_from_training_context(training_context)
    return {
        "has_active_injury": has_active_injury,
        "sport": sport,
        "status": training_context.status,
        "record": record_profile["record"],
        "wins": record_profile["wins"],
        "losses": record_profile["losses"],
        "draws": record_profile["draws"],
        "total_bouts": record_profile["total_bouts"],
        "competitive_maturity": record_profile["competitive_maturity"],
        "rounds_format": rounds_format,
        "camp_length_weeks": camp_length_weeks,
        "days_until_fight": training_context.days_until_fight,
        "fight_date": getattr(training_context, "next_fight_date", "") or "",
        "next_fight_date": getattr(training_context, "next_fight_date", "") or "",
        "fatigue": training_context.fatigue,
        "age": training_context.age,
        "weight_cut_risk": training_context.weight_cut_risk,
        "weight_cut_pct": training_context.weight_cut_pct,
        "cut_severity_score": cut_severity_score,
        "cut_severity_bucket": cut_severity_bucket(cut_severity_score),
        "technical_styles": training_context.style_technical,
        "tactical_styles": training_context.style_tactical,
        "weaknesses": training_context.weaknesses,
        "key_goals": training_context.key_goals,
        "mental_blocks": clean_list(training_context.mental_block),
        "equipment": training_context.equipment,
        "training_frequency": training_context.training_frequency,
        # Opt-in performance-bias layer (default off). Only activates for
        # low-risk profiles and never weakens safety defaults; see
        # fightcamp/performance_bias.py.
        "performance_bias": bool(getattr(training_context, "performance_bias", False)),
        "training_days": training_context.training_days,
        "hard_sparring_days": training_context.hard_sparring_days,
        "support_work_days": support_work_days,
        "technical_skill_days": training_context.technical_skill_days,
        "training_preference": training_context.training_preference,
        "injuries": training_context.injuries,
        "injuries_raw_text": training_context.injuries_raw_text,
        "parsed_injuries": [dict(item) for item in training_context.parsed_injuries],
        "guided_injury": dict(training_context.guided_injury) if training_context.guided_injury else None,
        "injury_restrictions": [dict(item) for item in training_context.injury_restrictions],
        "short_notice": short_notice,
        "plan_creation_weekday": plan_creation_dt.strftime("%A").lower(),
        "plan_creation_weekday_basis": "athlete_local_weekday",
        "readiness_flags": _derive_readiness_flags(
            fatigue=training_context.fatigue,
            weight_cut_risk=training_context.weight_cut_risk,
            weight_cut_pct=training_context.weight_cut_pct,
            injuries=training_context.injuries,
            short_notice=short_notice,
            days_until_fight=training_context.days_until_fight,
        ),
    }
