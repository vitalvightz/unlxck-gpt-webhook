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


def _recent_poor_readiness_count(checkin: ReadinessCheckin, context: ReadinessContext) -> int:
    count = 1 if _current_is_poor_readiness(checkin) else 0
    prior_days_seen: set[str] = set()
    for row in context.recent_checkins:
        day = _row_training_day(row)
        if day and day == context.training_day:
            continue
        if day in prior_days_seen:
            continue
        prior_days_seen.add(day)
        if _row_is_poor_readiness(row):
            count += 1
        if len(prior_days_seen) >= 2:
            break
    return count


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


def _with_context_triggers(*triggers: str, session_risk: SessionRisk, phase: str, contact_sport: bool) -> tuple[str, ...]:
    values = [trigger for trigger in triggers if trigger]
    if session_risk != "unknown":
        values.append(f"session_risk_{session_risk}")
    values.append(f"phase_{phase.lower()}")
    if contact_sport:
        values.append("contact_sport")
    return tuple(dict.fromkeys(values))


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

    if checkin.active_injury == "worse":
        action = "No sprinting, jumping, heavy lower-body work, sparring, or hard conditioning."
        if session_risk == "low":
            action = "Use rehab or mobility only and keep all work pain-free."
        return ReadinessAdjustment(
            decision="pull_back",
            title="Rehab only today.",
            reason="The injury is worse, so loading is not appropriate.",
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
            reason="Pain is high, so loading and impact are not appropriate.",
            action="Use rehab or easy mobility only; skip heavy work, sparring, and hard conditioning.",
            triggers=_with_context_triggers(
                "pain_high",
                session_risk=session_risk,
                phase=phase,
                contact_sport=contact_sport,
            ),
            session_risk=session_risk,
        )

    return None


def _normal_base_message(
    *,
    checkin: ReadinessCheckin,
    context: ReadinessContext,
    session_risk: SessionRisk,
    phase: str,
    repeated_poor: bool,
) -> tuple[RecommendationDecision, str, str, str, list[str]]:
    decision: RecommendationDecision = "train_as_planned"
    triggers: list[str] = []
    poor = checkin.sleep == "poor"
    flat = checkin.body == "flat"
    manageable_pain = checkin.pain == "manageable"
    recent_hard = checkin.previous_session == "very_hard" or _recent_hard_session_count(context) >= 2
    tracked_injury = checkin.active_injury == "stable" or bool(context.open_injuries)

    if poor:
        decision = _more_conservative(decision, "modify")
        triggers.append("poor_sleep")
    if flat:
        decision = _more_conservative(decision, "modify")
        triggers.append("flat_body")
    if manageable_pain:
        decision = _more_conservative(decision, "modify")
        triggers.append("manageable_pain")
    if tracked_injury and session_risk == "high":
        decision = _more_conservative(decision, "modify")
        triggers.append("tracked_injury_high_risk_session")
    if recent_hard and phase in {"SPP", "TAPER", "REINTEGRATION"}:
        decision = _more_conservative(decision, "modify")
        triggers.append("recent_hard_session")
    if repeated_poor:
        decision = _more_conservative(decision, "modify")
        triggers.append("repeated_poor_readiness")
    if poor and flat and manageable_pain and phase in {"TAPER", "REINTEGRATION"}:
        decision = "pull_back"
        return (
            decision,
            "Pull back today.",
            "Poor sleep, flat body, and manageable pain during taper/reintegration require a recovery day.",
            "Skip the planned session and use recovery or light mobility work instead.",
            triggers,
        )

    if decision == "train_as_planned":
        if phase == "TAPER":
            return (
                decision,
                "Sharp work only.",
                "You are in taper, so freshness matters more than extra volume today.",
                "Complete the planned sharp work and do not add fatigue-heavy accessories.",
                triggers,
            )
        return (
            decision,
            "Full session.",
            "Sleep, body state, and pain are clear today.",
            "Run the planned work and keep the prescribed dose.",
            triggers,
        )

    if repeated_poor:
        return (
            decision,
            "Session reduced.",
            "Readiness has been poor across recent check-ins, so recovery is not rebounding.",
            "Cut volume and intensity today and do not add hard conditioning.",
            triggers,
        )

    if phase == "TAPER":
        return (
            decision,
            "Session reduced.",
            "You are in taper, so freshness matters more than extra volume today.",
            "Keep sharp work only and remove fatigue-heavy accessories.",
            triggers,
        )

    if poor and flat:
        reason = "Poor sleep plus flat body lowers output and recovery margin today."
        action = "Remove 1 set, cap intensity, and skip finishers or extra conditioning."
        if session_risk == "high":
            reason = "Poor sleep plus flat body before high-risk work lowers recovery margin today."
            action = "Remove 1 set and cut sprinting, plyos, sparring, and hard conditioning."
        elif session_risk == "low":
            action = "Keep the easy work and cut optional volume."
        return decision, "Session reduced.", reason, action, triggers

    if poor:
        reason = "Poor sleep lowers recovery margin today."
        action = "Remove 1 set from loaded work and do not add extra conditioning."
        if session_risk == "high":
            reason = "Poor sleep before high-risk work lowers recovery margin today."
            action = "Remove 1 set and cut sprinting, plyos, sparring, and hard conditioning."
        elif session_risk == "low":
            reason = "Poor sleep lowers recovery margin, but today's work is low risk."
            action = "Keep the easy work and cut optional volume."
        return decision, "Session reduced.", reason, action, triggers

    if flat:
        action = "Keep reps clean and stay below max-effort work."
        if session_risk == "high":
            action = "Cap intensity and remove max-effort, sprint, plyo, and hard conditioning work."
        return decision, "Intensity capped.", "Flat body state lowers speed and bracing quality today.", action, triggers

    if manageable_pain:
        action = "Avoid painful ranges and remove high-impact or max-effort work."
        if session_risk == "high":
            action = "Remove impact, sparring, heavy loading, and hard conditioning."
        return decision, "Load reduced.", "Manageable pain needs tissue margin today.", action, triggers

    if tracked_injury and session_risk == "high":
        return (
            decision,
            "Load controlled.",
            "A tracked injury is active, so high-risk work needs tissue margin today.",
            "Remove impact, sparring, heavy loading, and max-effort work.",
            triggers,
        )

    if recent_hard:
        return (
            decision,
            "Session reduced.",
            "The recent session load was high, so quality is the limiter today.",
            "Keep intensity controlled and remove fatigue-heavy accessories.",
            triggers,
        )

    return (
        decision,
        "Session adjusted.",
        "Readiness needs a conservative dose today.",
        "Reduce volume and keep the work technically clean.",
        triggers,
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

    repeated_poor = _recent_poor_readiness_count(checkin, context) >= 3
    decision, title, reason, action, triggers = _normal_base_message(
        checkin=checkin,
        context=context,
        session_risk=session_risk,
        phase=phase,
        repeated_poor=repeated_poor,
    )

    contact_sport = _is_combat_contact_sport(context)
    days_until_fight = _days_until_fight(context, context.training_day)
    if days_until_fight is not None and 0 <= days_until_fight <= 7 and decision != "pull_back":
        triggers.append("fight_week")
        if decision == "train_as_planned" and phase != "TAPER":
            title = "Sharp work only."
            reason = "Fight week rewards freshness, not extra fatigue."
            action = "Run the planned sharp work and leave conditioning volume alone."

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
