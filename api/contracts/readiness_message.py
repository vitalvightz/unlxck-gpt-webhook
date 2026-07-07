"""Context-aware Today readiness decision and message engine.

This module is intentionally pure: it does not read from Supabase and it never
mutates a saved plan. The Today service passes in the check-in, active-plan
context, current session, injuries, and recent history; the engine returns the
decision plus the athlete-facing adjustment message.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Mapping, Sequence

RecommendationDecision = Literal["train_as_planned", "modify", "pull_back"]
SessionRisk = Literal["low", "medium", "high", "unknown"]

_DECISION_RANK: dict[str, int] = {
    "train_as_planned": 0,
    "modify": 1,
    "pull_back": 2,
}

_SAFETY_FLAG_LABELS: dict[str, str] = {
    "sharp_pain": "sharp pain",
    "instability": "instability",
    "swelling": "swelling",
    "neurological_symptoms": "neurological symptoms",
    "illness_symptoms": "illness symptoms",
    "cannot_warm_into_movement": "inability to warm into movement",
    "worse_next_day_pain": "worse next-day pain",
}

_HIGH_RISK_TERMS = (
    "sprint",
    "sprinting",
    "plyo",
    "plyometric",
    "jump",
    "heavy lower",
    "heavy squat",
    "deadlift",
    "max effort",
    "max-effort",
    "hard conditioning",
    "hard spar",
    "sparring",
    "live work",
    "competition",
)

_LOW_RISK_TERMS = (
    "mobility",
    "rehab",
    "easy aerobic",
    "aerobic bike",
    "bike",
    "recovery",
    "flush",
    "breathing",
    "rest",
    "off",
)

_MEDIUM_RISK_TERMS = (
    "accessory",
    "accessories",
    "moderate strength",
    "strength",
    "technical",
    "skill",
    "pad",
    "pads",
    "mitt",
    "drill",
)


@dataclass(frozen=True)
class ReadinessCheckin:
    sleep: str = "good"
    body: str = "normal"
    pain: str = "none"
    phase: str = "GPP"
    active_injury: str = "none"
    previous_session: str = "none"
    sharp_pain: bool = False
    instability: bool = False
    swelling: bool = False
    neurological_symptoms: bool = False
    illness_symptoms: bool = False
    cannot_warm_into_movement: bool = False
    worse_next_day_pain: bool = False


@dataclass(frozen=True)
class ReadinessContext:
    training_day: str = ""
    phase: str = ""
    today_session: Mapping[str, Any] | None = None
    active_plan: Mapping[str, Any] | None = None
    intake: Mapping[str, Any] | None = None
    athlete_profile: Mapping[str, Any] | None = None
    open_injuries: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    recent_checkins: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    recent_sessions: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReadinessAdjustment:
    decision: RecommendationDecision
    title: str
    reason: str
    action: str
    safety: str = ""
    triggers: tuple[str, ...] = ()
    session_risk: SessionRisk = "unknown"

    @property
    def message(self) -> str:
        return "\n".join(line for line in (self.title, self.reason, self.action, self.safety) if line)


@dataclass(frozen=True)
class _SoftWarningState:
    triggers: tuple[str, ...]
    effective: tuple[str, ...]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_phase(value: Any) -> str:
    phase = _clean(value).upper().replace(" ", "_")
    if phase in {"GPP", "SPP", "TAPER", "REINTEGRATION"}:
        return phase
    for candidate in ("REINTEGRATION", "TAPER", "SPP", "GPP"):
        if candidate in phase:
            return candidate
    return "GPP"


def _more_conservative(current: RecommendationDecision, candidate: RecommendationDecision) -> RecommendationDecision:
    return current if _DECISION_RANK[current] >= _DECISION_RANK[candidate] else candidate


def _session_text(session: Mapping[str, Any] | None) -> str:
    if not session:
        return ""
    parts: list[str] = []
    for key in (
        "title",
        "label",
        "session_type",
        "status",
        "objective",
        "coach_note",
        "reason",
        "primary_focus",
        "emphasis",
        "effective_load",
        "coach_led_contact",
    ):
        value = session.get(key)
        if value:
            parts.append(_clean(value))
    blocks = session.get("blocks")
    if isinstance(blocks, Sequence) and not isinstance(blocks, (str, bytes)):
        for block in blocks:
            if isinstance(block, Mapping):
                parts.extend(_clean(block.get(key)) for key in ("title", "type", "focus", "name"))
    return " ".join(part for part in parts if part).lower()


def classify_session_risk(session: Mapping[str, Any] | None) -> SessionRisk:
    text = _session_text(session)
    if not text:
        return "unknown"
    if any(term in text for term in _HIGH_RISK_TERMS):
        return "high"
    if any(term in text for term in _LOW_RISK_TERMS):
        return "low"
    if any(term in text for term in _MEDIUM_RISK_TERMS):
        return "medium"
    return "medium"


def _active_safety_flags(checkin: ReadinessCheckin) -> tuple[str, ...]:
    return tuple(flag for flag in _SAFETY_FLAG_LABELS if bool(getattr(checkin, flag, False)))


def _row_training_day(row: Mapping[str, Any]) -> str:
    return _clean(row.get("training_day") or row.get("checkin_date"))


def _row_value(row: Mapping[str, Any], key: str) -> str:
    return _clean(row.get(key)).lower()


def _row_is_poor_readiness(row: Mapping[str, Any]) -> bool:
    state = _clean(row.get("recommendation_state") or row.get("decision")).lower()
    if state in {"modify", "pull_back"}:
        return True
    if _clean(row.get("sleep")).lower() == "poor":
        return True
    if _clean(row.get("body")).lower() == "flat":
        return True
    if _clean(row.get("pain")).lower() in {"manageable", "high"}:
        return True
    if _clean(row.get("active_injury")).lower() == "worse":
        return True
    return any(bool(row.get(flag)) for flag in _SAFETY_FLAG_LABELS)


def _current_is_poor_readiness(checkin: ReadinessCheckin) -> bool:
    return (
        checkin.sleep == "poor"
        or checkin.body == "flat"
        or checkin.pain in {"manageable", "high"}
        or checkin.active_injury == "worse"
        or bool(_active_safety_flags(checkin))
    )


def _prior_unique_checkins(context: ReadinessContext, *, limit: int = 2) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    prior_days_seen: set[str] = set()
    for row in context.recent_checkins:
        day = _row_training_day(row)
        if not day:
            continue
        if context.training_day and day == context.training_day:
            continue
        if day in prior_days_seen:
            continue
        prior_days_seen.add(day)
        rows.append(row)
        if len(rows) >= limit:
            break
    return tuple(rows)


def _recent_poor_readiness_count(checkin: ReadinessCheckin, context: ReadinessContext) -> int:
    count = 1 if _current_is_poor_readiness(checkin) else 0
    for row in _prior_unique_checkins(context):
        if _row_is_poor_readiness(row):
            count += 1
    return count


def _three_day_streak(
    checkin_value: str,
    prior_rows: Sequence[Mapping[str, Any]],
    key: str,
    allowed_values: set[str],
) -> bool:
    if checkin_value not in allowed_values or len(prior_rows) < 2:
        return False
    return all(_row_value(row, key) in allowed_values for row in prior_rows[:2])


_PAIN_ORDER = {
    "none": 0,
    "manageable": 1,
    "high": 2,
}


def _pain_worsening_trend(checkin: ReadinessCheckin, prior_rows: Sequence[Mapping[str, Any]]) -> bool:
    if checkin.pain not in _PAIN_ORDER or len(prior_rows) < 2:
        return False
    yesterday, day_before = prior_rows[:2]
    pain_values = [
        _PAIN_ORDER.get(_row_value(day_before, "pain"), 0),
        _PAIN_ORDER.get(_row_value(yesterday, "pain"), 0),
        _PAIN_ORDER[checkin.pain],
    ]
    return (
        pain_values[-1] > 0
        and pain_values[1] > 0
        and pain_values[-1] > pain_values[0]
        and pain_values == sorted(pain_values)
    )


def _recent_hard_session_count(context: ReadinessContext) -> int:
    count = 0
    for row in context.recent_sessions[:3]:
        try:
            rpe = int(row.get("session_rpe") if row.get("session_rpe") is not None else row.get("rpe"))
        except (TypeError, ValueError):
            rpe = 0
        try:
            pain_after = int(row.get("pain_after") or 0)
        except (TypeError, ValueError):
            pain_after = 0
        if rpe >= 8 or pain_after >= 6:
            count += 1
    return count


def _intake_athlete(context: ReadinessContext) -> Mapping[str, Any]:
    intake = context.intake or {}
    athlete = intake.get("athlete") if isinstance(intake, Mapping) else None
    return athlete if isinstance(athlete, Mapping) else {}


def _sport_tokens(context: ReadinessContext) -> set[str]:
    values: list[Any] = []
    athlete = _intake_athlete(context)
    for val in (athlete.get("technical_style"), athlete.get("tactical_style")):
        if isinstance(val, str):
            values.append(val)
        elif isinstance(val, Sequence):
            values.extend(val)
    plan = context.active_plan or {}
    plan_tech = plan.get("technical_style")
    if isinstance(plan_tech, str):
        values.append(plan_tech)
    elif isinstance(plan_tech, Sequence):
        values.extend(plan_tech)
    text = " ".join(_clean(value).lower() for value in values if value)
    tokens = {part for part in text.replace("/", " ").replace(",", " ").replace("-", " ").split() if part}
    if "muay" in tokens or "thai" in tokens:
        tokens.add("muay_thai")
    if "jiu" in tokens or "jitsu" in tokens:
        tokens.add("bjj")
    return tokens


def _is_combat_contact_sport(context: ReadinessContext) -> bool:
    return bool(_sport_tokens(context) & {"boxing", "mma", "kickboxing", "muay_thai", "wrestling", "judo", "bjj"})


def _days_until_fight(context: ReadinessContext, training_day: str) -> int | None:
    fight_date = _clean((context.active_plan or {}).get("fight_date") or (context.intake or {}).get("fight_date"))
    if not fight_date or not training_day:
        return None
    try:
        return (date.fromisoformat(fight_date[:10]) - date.fromisoformat(training_day[:10])).days
    except ValueError:
        return None


def _is_fight_week(context: ReadinessContext) -> bool:
    days_until_fight = _days_until_fight(context, context.training_day)
    return days_until_fight is not None and 0 <= days_until_fight <= 7


def _with_context_triggers(*triggers: str, session_risk: SessionRisk, phase: str, contact_sport: bool) -> tuple[str, ...]:
    values = [trigger for trigger in triggers if trigger]
    if session_risk != "unknown":
        values.append(f"session_risk_{session_risk}")
    values.append(f"phase_{phase.lower()}")
    if contact_sport:
        values.append("contact_sport")
    return tuple(dict.fromkeys(values))

def _active_context_injury_stop(context: ReadinessContext) -> tuple[str, str] | None:
    """Return the active injury trigger/reason that should stop training."""
    for injury in context.open_injuries:
        if _clean(injury.get("status")).lower() not in {"open", "monitoring"}:
            continue
        label = (
            _clean(injury.get("label"))
            or _clean(injury.get("body_area"))
            or _clean(injury.get("description"))
            or "injury"
        )
        if _clean(injury.get("severity")).lower() == "severe":
            return "active_injury_worse", f"Active severe injury: {label}."
        if _clean(injury.get("latest_reported_status")).lower() == "worse":
            return "active_injury_worse", f"The {label} injury is worse."
    return None


def _risk_adjustment(checkin: ReadinessCheckin, context: ReadinessContext, session_risk: SessionRisk, phase: str) -> ReadinessAdjustment | None:
    flags = _active_safety_flags(checkin)
    contact_sport = _is_combat_contact_sport(context)
    if flags:
        trigger_text = ", ".join(_SAFETY_FLAG_LABELS[flag] for flag in flags)
        reason = (
            "You selected a red flag symptom, so training is not safe."
            if len(flags) == 1
            else f"You selected red flag symptoms ({trigger_text}), so training is not safe."
        )
        return ReadinessAdjustment(
            decision="pull_back",
            title="No training today.",
            reason=reason,
            action="Stop training and seek medical advice.",
            triggers=_with_context_triggers(*flags, "red_flag", session_risk=session_risk, phase=phase, contact_sport=contact_sport),
            session_risk=session_risk,
        )

    active_injury_stop = _active_context_injury_stop(context)
    if checkin.active_injury == "worse" or active_injury_stop is not None:
        _trigger, context_reason = active_injury_stop or ("active_injury_worse", "The injury is worse.")
        reason = f"{context_reason} Hard combat work is not safe today."
        action = "No sparring, live rounds, clinch work, hard bag work, or conditioning."
        if session_risk == "low":
            reason = f"{context_reason} Hard training is not safe today."
            action = "Use mobility, rehab, or light shadowboxing only."
        return ReadinessAdjustment(
            decision="pull_back",
            title="Rehab only today.",
            reason=reason,
            action=action,
            safety="Seek medical advice if pain is sharp, unstable, swollen, or neurological.",
            triggers=_with_context_triggers(
                "active_injury_worse",
                session_risk=session_risk,
                phase=phase,
                contact_sport=contact_sport,
            ),
            session_risk=session_risk,
        )

    if checkin.pain == "high":
        return ReadinessAdjustment(
            decision="pull_back",
            title="Rehab only today.",
            reason="Pain is high, so contact and impact are not safe today.",
            action="Use rehab or easy mobility only; skip sparring, pads, bag work, and conditioning.",
            triggers=_with_context_triggers(
                "pain_high",
                session_risk=session_risk,
                phase=phase,
                contact_sport=contact_sport,
            ),
            session_risk=session_risk,
        )

    return None


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _collect_soft_warnings(
    *,
    checkin: ReadinessCheckin,
    context: ReadinessContext,
    session_risk: SessionRisk,
    phase: str,
    repeated_poor: bool,
    fight_week: bool,
) -> _SoftWarningState:
    triggers: list[str] = []
    current_effective: list[str] = []
    trend_effective: list[str] = []
    context_effective: list[str] = []
    prior_rows = _prior_unique_checkins(context)
    poor = checkin.sleep == "poor"
    flat = checkin.body == "flat"
    manageable_pain = checkin.pain == "manageable"
    recent_hard_count = _recent_hard_session_count(context)
    recent_hard = checkin.previous_session == "very_hard" or recent_hard_count >= 2
    tracked_injury = checkin.active_injury == "stable" or bool(context.open_injuries)
    poor_sleep_streak = _three_day_streak(checkin.sleep, prior_rows, "sleep", {"poor"})
    flat_body_streak = _three_day_streak(checkin.body, prior_rows, "body", {"flat"})
    pain_streak = _three_day_streak(checkin.pain, prior_rows, "pain", {"manageable", "high"})
    pain_worsening = _pain_worsening_trend(checkin, prior_rows)

    if poor:
        _append_unique(triggers, "poor_sleep")
        if poor_sleep_streak:
            _append_unique(triggers, "poor_sleep_3_day_streak")
            _append_unique(trend_effective, "poor_sleep_3_day_streak")
        else:
            _append_unique(current_effective, "poor_sleep")
    if flat:
        _append_unique(triggers, "flat_body")
        if flat_body_streak:
            _append_unique(triggers, "flat_body_3_day_streak")
            _append_unique(trend_effective, "flat_body_3_day_streak")
        else:
            _append_unique(current_effective, "flat_body")
    if manageable_pain:
        _append_unique(triggers, "manageable_pain")
        if pain_streak:
            _append_unique(triggers, "pain_3_day_streak")
            _append_unique(trend_effective, "pain_3_day_streak")
        if pain_worsening:
            _append_unique(triggers, "pain_worsening_trend")
            _append_unique(trend_effective, "pain_worsening_trend")
        if not pain_streak and not pain_worsening:
            _append_unique(current_effective, "manageable_pain")
    if tracked_injury and session_risk == "high":
        _append_unique(triggers, "tracked_injury_high_risk_session")
        _append_unique(context_effective, "tracked_injury_high_risk_session")
    if recent_hard and phase in {"SPP", "TAPER", "REINTEGRATION"}:
        _append_unique(triggers, "recent_hard_session")
        _append_unique(context_effective, "recent_hard_session")
    if repeated_poor:
        _append_unique(triggers, "repeated_poor_readiness")
        if not trend_effective:
            _append_unique(context_effective, "repeated_poor_readiness")

    if recent_hard_count >= 2 and _current_is_poor_readiness(checkin):
        _append_unique(triggers, "recent_hard_load_plus_poor_today")
        if len(current_effective) == 1 and not trend_effective and not context_effective:
            current_effective.clear()
        _append_unique(context_effective, "recent_hard_load_plus_poor_today")

    has_soft_warning = bool(current_effective or trend_effective or context_effective)
    if phase == "TAPER" and has_soft_warning:
        _append_unique(triggers, "taper_poor_readiness")
        _append_unique(context_effective, "taper_poor_readiness")
    elif phase == "REINTEGRATION" and has_soft_warning:
        _append_unique(triggers, "reintegration_poor_readiness")
        _append_unique(context_effective, "reintegration_poor_readiness")

    if fight_week and (current_effective or trend_effective or context_effective):
        _append_unique(triggers, "fight_week")
        _append_unique(context_effective, "fight_week")

    return _SoftWarningState(
        triggers=tuple(dict.fromkeys(triggers)),
        effective=tuple(dict.fromkeys([*trend_effective, *current_effective, *context_effective])),
    )


def _has_pain_warning(warnings: Sequence[str]) -> bool:
    return bool({"manageable_pain", "pain_3_day_streak", "pain_worsening_trend"} & set(warnings))


def _specific_soft_warning_message(
    warning: str,
    *,
    session_risk: SessionRisk,
) -> tuple[RecommendationDecision, str, str, str]:
    if warning == "poor_sleep_3_day_streak":
        return (
            "modify",
            "Session reduced.",
            "Poor sleep has built up for 3 days, so your body has less room to recover.",
            "Cut 1 round and remove conditioning today.",
        )

    if warning == "flat_body_3_day_streak":
        return (
            "modify",
            "Intensity capped.",
            "Your body has felt flat for 3 days, so speed and reactions may drop.",
            "Keep rounds technical and stay away from all-out work.",
        )

    if warning == "pain_3_day_streak":
        return (
            "modify",
            "Load reduced.",
            "Pain has shown up for 3 days, so the area needs protection.",
            "Skip sparring, clinch pressure, hard bag work, and conditioning.",
        )

    if warning == "pain_worsening_trend":
        return (
            "modify",
            "Load reduced.",
            "Pain is getting worse, so hard combat work needs to be limited.",
            "Skip sparring, clinch pressure, hard bag work, and conditioning.",
        )

    if warning == "recent_hard_load_plus_poor_today":
        return (
            "modify",
            "Session reduced.",
            "Your recent training load was high and today's check-in is poor.",
            "Keep rounds controlled and remove tiring extras.",
        )

    if warning == "poor_sleep":
        reason = "Poor sleep means your body has less room to recover today."
        action = "Cut 1 round and do not add extra conditioning."
        if session_risk == "high":
            reason = "Poor sleep before hard combat work raises injury risk today."
            action = "Skip sparring, hard rounds, and conditioning finishers."
        elif session_risk == "low":
            reason = "Poor sleep means your body has less room to recover, but today's work is light."
            action = "Keep the easy work and cut anything extra."
        return "modify", "Session reduced.", reason, action

    if warning == "flat_body":
        reason = "A flat body lowers speed, reactions, and sharpness today."
        action = "Keep rounds technical and stay away from all-out work."
        if session_risk == "high":
            reason = "A flat body lowers reaction speed and defensive sharpness today."
            action = "No sparring, hard bag rounds, or max-output conditioning."
        return "modify", "Intensity capped.", reason, action

    if warning == "manageable_pain":
        reason = "Manageable pain means the area needs protection today."
        action = "Avoid painful shots, clinch positions, impact, and hard conditioning."
        if session_risk == "high":
            reason = "Manageable pain before contact work needs protection today."
            action = "Skip sparring, clinch pressure, hard bag work, and conditioning."
        return "modify", "Load reduced.", reason, action

    if warning == "repeated_poor_readiness":
        return (
            "modify",
            "Session reduced.",
            "Your check-ins have been poor for a few days, so your body is not bouncing back.",
            "Cut rounds and intensity today. Do not add conditioning.",
        )

    if warning == "tracked_injury_high_risk_session":
        return (
            "modify",
            "Load controlled.",
            "An active injury means hard combat work needs to be limited today.",
            "Remove sparring, clinch pressure, hard bag work, and all-out rounds.",
        )

    if warning == "recent_hard_session":
        return (
            "modify",
            "Session reduced.",
            "Your recent training load was high, so quality matters more today.",
            "Keep rounds controlled and remove tiring extras.",
        )

    if warning == "taper_poor_readiness":
        return (
            "modify",
            "Session reduced.",
            "You are in taper, so sharpness matters more than extra work today.",
            "Keep speed and timing work only; remove tiring rounds.",
        )

    if warning == "reintegration_poor_readiness":
        return (
            "modify",
            "Session reduced.",
            "You are rebuilding, so hard combat work needs to stay controlled today.",
            "Keep it light and remove tiring rounds.",
        )

    return "modify", "Session adjusted.", "Your body needs a safer dose today.", "Reduce volume and keep the work clean."


def _soft_warning_message(
    warnings: Sequence[str],
    *,
    session_risk: SessionRisk,
    phase: str,
    fight_week: bool,
) -> tuple[RecommendationDecision, str, str, str]:
    warning_count = len(warnings)
    if warning_count >= 3:
        if session_risk == "high" or _has_pain_warning(warnings) or phase in {"TAPER", "REINTEGRATION"} or fight_week:
            return (
                "pull_back",
                "Pull back today.",
                "Several warnings are showing, so your body is not ready for hard combat work.",
                "Skip combat work and use recovery or light mobility instead.",
            )
        return (
            "modify",
            "Session reduced.",
            "Several warnings are showing, so today needs a safer dose.",
            "Cut rounds, cap intensity, and remove conditioning.",
        )

    if "taper_poor_readiness" in warnings:
        return _specific_soft_warning_message("taper_poor_readiness", session_risk=session_risk)

    if "reintegration_poor_readiness" in warnings:
        return _specific_soft_warning_message("reintegration_poor_readiness", session_risk=session_risk)

    if warning_count == 2:
        return (
            "modify",
            "Session reduced.",
            "More than one warning is showing, so hard combat work needs to be reduced today.",
            "Keep rounds controlled. Skip sparring, hard rounds, and conditioning finishers.",
        )

    if warning_count == 1:
        return _specific_soft_warning_message(warnings[0], session_risk=session_risk)

    if fight_week:
        return (
            "train_as_planned",
            "Sharp work only.",
            "Fight week rewards freshness, not extra fatigue.",
            "Keep timing, speed, and rhythm work; leave conditioning volume alone.",
        )

    if phase == "TAPER":
        return (
            "train_as_planned",
            "Sharp work only.",
            "You are in taper, so sharpness matters more than extra work today.",
            "Keep speed and timing work only; remove tiring rounds.",
        )

    return (
        "train_as_planned",
        "Full session.",
        "Your sleep, body, and pain check are clear today.",
        "Run the planned work and keep the rounds clean.",
    )


def build_readiness_adjustment(
    checkin: ReadinessCheckin,
    context: ReadinessContext | None = None,
) -> ReadinessAdjustment:
    context = context or ReadinessContext()
    phase = _normalize_phase(context.phase or checkin.phase)
    session_risk = classify_session_risk(context.today_session)
    risk = _risk_adjustment(checkin, context, session_risk, phase)
    if risk:
        return risk

    contact_sport = _is_combat_contact_sport(context)
    fight_week = _is_fight_week(context)
    repeated_poor = _recent_poor_readiness_count(checkin, context) >= 3
    soft_warnings = _collect_soft_warnings(
        checkin=checkin,
        context=context,
        session_risk=session_risk,
        phase=phase,
        repeated_poor=repeated_poor,
        fight_week=fight_week,
    )

    if "pain_worsening_trend" in soft_warnings.effective and session_risk == "high":
        decision: RecommendationDecision = "pull_back"
        title = "Pull back today."
        reason = "Pain is getting worse, so hard combat work is not safe today."
        action = "Use recovery, rehab, or light mobility instead."
    else:
        decision, title, reason, action = _soft_warning_message(
            soft_warnings.effective,
            session_risk=session_risk,
            phase=phase,
            fight_week=fight_week,
        )

    triggers = list(soft_warnings.triggers)
    if fight_week and not soft_warnings.effective:
        triggers.append("fight_week")

    if contact_sport and session_risk == "high" and decision == "modify" and "contact_sport" not in triggers:
        action = action.rstrip(".") + " and do not add extra contact rounds."

    return ReadinessAdjustment(
        decision=decision,
        title=title,
        reason=reason,
        action=action,
        triggers=_with_context_triggers(
            *triggers,
            session_risk=session_risk,
            phase=phase,
            contact_sport=contact_sport,
        ),
        session_risk=session_risk,
    )
