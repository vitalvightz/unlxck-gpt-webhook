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
    "bound",
    "explosive",
    "ballistic",
    "heavy lower",
    "heavy squat",
    "deadlift",
    "heavy press",
    "loaded carry",
    "max effort",
    "max-effort",
    "max load",
    "1rm",
    "hard conditioning",
    "hiit",
    "hard spar",
    "sparring",
    "live work",
    "live round",
    "live spar",
    "clinch",
    "wrestl",
    "grappl",
    "takedown",
    "sprawl",
    # Impact striking on the bag is high-consequence work for an injured athlete;
    # the engine's own pull-back copy already names "hard bag work" as the thing to
    # remove, so it must classify as high, not fall through to medium.
    "bag work",
    "bagwork",
    "heavy bag",
    "hard bag",
    "bag round",
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

_WARNING_SOURCE_LABELS: dict[str, str] = {
    "poor_sleep": "poor sleep",
    "poor_sleep_3_day_streak": "poor sleep for 3 days",
    "flat_body": "flat body",
    "flat_body_3_day_streak": "flat body for 3 days",
    "manageable_pain": "manageable pain",
    "pain_3_day_streak": "pain for 3 days",
    "pain_worsening_trend": "worsening pain",
    "recent_hard_load_plus_poor_today": "a heavy recent training load",
    "repeated_poor_readiness": "repeated poor check-ins",
    "tracked_injury_high_risk_session": "an active injury",
    "recent_hard_session": "a recent hard session",
    "taper_poor_readiness": "the taper phase",
    "reintegration_poor_readiness": "the return phase",
    "fight_week": "fight week",
}


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


# Distinctive labels/roles for the plan's low-cost "filler" support inserts
# (fightcamp/gap_fill_inserts.py): tactical/mental cue work, breathing & sleep
# resets, and mobility/rehab touches. These carry no meaningful physical stress,
# so an injury must not hard-block them — a neck injury cannot stop you writing a
# mental cue, and mobility/rehab is exactly what an injury STOP prescribes. The
# terms are deliberately specific (insert labels, not bare "mobility") so a real
# loaded session that merely mentions mobility in a warm-up is never misread.
_SUPPORT_SESSION_TERMS = (
    "cue card",
    "fight cue",
    "self-review",
    "self review",
    "tactical watch",
    "visualization",
    "visualisation",
    "mental rehearsal",
    "mindset",
    "breathing reset",
    "recovery reset",
    "sleep downshift",
    "downshift mobility",
    "mobility/rehab",
    "mobility rehab",
    "rehab reset",
    "movement quality",
    "restorative",
)
# Structured support-insert categories emitted by _build_insert_role.
_SUPPORT_INSERT_CATEGORIES = frozenset(
    {"tactical", "mental", "recovery", "mobility", "movement_quality"}
)

# Region-aware safe-filler gate -------------------------------------------------
# A support / filler session is normally exempt from injury blocks (see
# _safe_filler_adjustment). But a low-stress session can still include a filler or
# primer that mechanically LOADS the injured region — e.g. a fight-week freshness
# day that carries an explosive Band Row primer while the shoulder is bruised. In
# that case the blanket "safe to do around your {injury}" claim is wrong. These
# maps let the gate detect the conflict from whatever signal the Today session
# carries: the structured mechanical_load_regions the fillers now emit, the bank
# items' mechanical_risk_tags, and — as a fallback — the movement wording in the
# session's labels/blocks. Region keys match
# fightcamp.injury_exclusion_rules.INJURY_REGION_KEYWORDS.
_MECH_TAG_REGIONS: dict[str, tuple[str, ...]] = {
    "mech_upper_pull": ("shoulder", "upper_back", "elbow"),
    "mech_horizontal_pull": ("shoulder", "upper_back", "elbow"),
    "mech_vertical_pull_heavy": ("shoulder", "upper_back", "elbow"),
    "mech_upper_press": ("shoulder", "chest", "elbow"),
    "mech_horizontal_push": ("shoulder", "chest", "elbow"),
    "mech_shoulder_overhead": ("shoulder",),
    "mech_overhead_dynamic": ("shoulder",),
    "mech_overhead_static": ("shoulder",),
    "mech_grip_support": ("wrist", "hand", "forearm", "elbow"),
    "mech_grip_intensive": ("wrist", "hand", "forearm"),
    "mech_grip_static": ("wrist", "hand", "forearm"),
    "mech_hinge_eccentric": ("hamstring", "lower_back"),
    "mech_squat_deep": ("knee", "hip"),
    "mech_landing_impact": ("ankle", "knee", "calf", "achilles", "foot"),
    "mech_reactive_rebound": ("ankle", "calf", "achilles", "foot"),
    "mech_max_velocity": ("hamstring", "calf", "achilles"),
    "mech_acceleration": ("hamstring", "calf", "achilles"),
    "mech_change_of_direction": ("ankle", "knee", "groin"),
    "mech_deceleration": ("knee", "quad", "ankle"),
}

# Movement wording that loads each region, matched against the session's labels /
# block names. Scoped to the vocabulary that actually appears in fillers, primers,
# and late-camp touches so a warm-up mention never over-triggers.
_REGION_LOAD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "shoulder": (
        "row", "pull-up", "pull up", "pullup", "pulldown", "chin-up", "chin up",
        "face pull", "band pull", "scap", "press", "overhead", "shadow", "punch",
        "jab", "cross", "hook", "throw", "raise", "snatch",
    ),
    "upper_back": ("row", "pull-up", "pull up", "pullup", "pulldown", "face pull", "scap", "carry"),
    "elbow": ("row", "pull-up", "pull up", "chin-up", "curl", "press", "punch", "extension", "throw"),
    "wrist": ("row", "pull-up", "grip", "hang", "punch", "press", "push-up", "push up", "carry", "throw"),
    "hand": ("grip", "hang", "punch", "carry"),
    "forearm": ("row", "grip", "hang", "curl", "carry"),
    "chest": ("press", "push-up", "push up", "punch", "fly", "dip", "throw", "shadow"),
    "hip": ("squat", "lunge", "hinge", "step-up", "shuffle", "footwork", "sprint", "jog"),
    "groin": ("lunge", "lateral", "shuffle", "cossack", "adductor", "skater"),
    "hamstring": ("hinge", "deadlift", "rdl", "sprint", "jog", "run", "bound"),
    "quad": ("squat", "lunge", "step-up", "sprint", "jog", "jump"),
    "knee": ("squat", "lunge", "jump", "sprint", "jog", "run", "shuffle", "footwork", "skip"),
    "shin": ("jump", "skip", "sprint", "jog", "run", "bound", "footwork"),
    "calf": ("skip", "jump", "sprint", "jog", "run", "bound", "footwork", "calf raise"),
    "achilles": ("skip", "jump", "sprint", "jog", "run", "bound"),
    "ankle": ("skip", "jump", "sprint", "jog", "run", "shuffle", "footwork", "pivot", "lateral"),
    "foot": ("skip", "jump", "sprint", "jog", "run", "footwork", "pivot"),
    "toe": ("skip", "jump", "sprint", "bound"),
}


def is_support_session(session: Mapping[str, Any] | None) -> bool:
    """True for a low-cost support / filler session (mental cue work, breathing or
    sleep reset, mobility/rehab touch) that carries no meaningful physical stress.

    Prefers the authoritative structured signals the plan attaches to a support
    insert (``category``/``stress_class``/``governance.meaningful_stress``/
    ``support_insert_category``) and falls back to the distinctive athlete-facing
    labels that always survive to the Today card. Safety-first: obvious high-risk
    wording (sparring, heavy squat, ...) always vetoes the classification, even a
    structured "support" flag — the injury hold must win when the copy says hard work.
    """
    if not isinstance(session, Mapping) or not session:
        return False

    # Safety-first: build the session text up front and let obvious high-risk
    # wording VETO a support classification before any structured signal is
    # accepted. A mislabeled ``stress_class: support`` / ``meaningful_stress: False``
    # flag on a hard session (sparring, heavy squat, ...) must never open the injury
    # exemption — the injury hold has to win when the copy says hard work.
    text = _session_text(session)
    if text and any(term in text for term in _HIGH_RISK_TERMS):
        return False

    # Structured support-insert signals are the primary positive detector.
    for key in ("category", "session_type", "status"):
        if _clean(session.get(key)).lower() == "support_insert":
            return True
    if _clean(session.get("stress_class")).lower() == "support":
        return True
    governance = session.get("governance")
    if isinstance(governance, Mapping) and governance.get("meaningful_stress") is False:
        return True
    if _clean(session.get("support_insert_category")).lower() in _SUPPORT_INSERT_CATEGORIES:
        return True

    # Fall back to the distinctive athlete-facing filler labels.
    if not text:
        return False
    return any(term in text for term in _SUPPORT_SESSION_TERMS)


def _active_safety_flags(checkin: ReadinessCheckin) -> tuple[str, ...]:
    return tuple(flag for flag in _SAFETY_FLAG_LABELS if bool(getattr(checkin, flag, False)))


def _row_training_day(row: Mapping[str, Any]) -> str:
    return _clean(row.get("training_day") or row.get("checkin_date"))


def _row_value(row: Mapping[str, Any], key: str) -> str:
    return _clean(row.get(key)).lower()


# Accumulated check-in signals (streaks, worsening trends, repeated-poor counts) and
# the "recent hard session" fatigue signal must only be built from RECENT history —
# otherwise sporadic check-ins/sessions weeks apart inflate a "3-day streak" or
# "recent hard load" that never happened. These windows bound how far back a prior
# day may sit relative to today.
_CHECKIN_RECENCY_WINDOW_DAYS = 3
_SESSION_RECENCY_WINDOW_DAYS = 4


def _parse_iso_day(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_clean(value)[:10])
    except ValueError:
        return None


def _days_before(training_day: str | date, row_day: str | date) -> int | None:
    """Whole days ``row_day`` sits before ``training_day`` (0 = same day), or None
    when either date is missing/unparseable."""
    today = _parse_iso_day(training_day)
    prior = _parse_iso_day(row_day)
    if today is None or prior is None:
        return None
    return (today - prior).days


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
    """The most recent distinct prior check-in days (newest first), bounded to the
    recent window so a streak/trend can never be assembled from days weeks apart.

    When today's date is unparseable the window is not applied (there is nothing to
    measure proximity against), preserving the prior best-effort behaviour.
    """
    training_day = _clean(context.training_day)
    windowed = _parse_iso_day(training_day) is not None
    rows: list[Mapping[str, Any]] = []
    prior_days_seen: set[str] = set()
    for row in context.recent_checkins:
        day = _row_training_day(row)
        if not day:
            continue
        if training_day and day == training_day:
            continue
        if day in prior_days_seen:
            continue
        if windowed:
            delta = _days_before(training_day, day)
            if delta is None or not (1 <= delta <= _CHECKIN_RECENCY_WINDOW_DAYS):
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
    *,
    training_day: str | date,
) -> bool:
    if checkin_value not in allowed_values or len(prior_rows) < 2:
        return False
    today = _parse_iso_day(training_day)
    if today is not None:
        prior_deltas = {
            _days_before(today, _row_training_day(row))
            for row in prior_rows[:2]
        }
        if prior_deltas != {1, 2}:
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
    training_day = _clean(context.training_day)
    today_date = _parse_iso_day(training_day)
    count = 0
    for row in context.recent_sessions[:3]:
        if today_date is not None:
            # Only count hard sessions from the recent window — a hard session weeks
            # ago is not "recent load".
            delta = _days_before(today_date, _clean(row.get("training_day")))
            if delta is None or not (0 <= delta <= _SESSION_RECENCY_WINDOW_DAYS):
                continue
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

def _active_context_injury_stop(context: ReadinessContext) -> str | None:
    """Return the active injury reason that should stop training."""
    for injury in context.open_injuries:
        if _clean(injury.get("status")).lower() not in {"open", "monitoring"}:
            continue
        label = _clean(injury.get("label"))
        if not label:
            from api.contracts.injury_checkin import build_injury_label

            label = build_injury_label(injury.get("body_area"), injury.get("description"))
        if _clean(injury.get("severity")).lower() == "severe":
            return f"Active severe injury: {label}."
        if _clean(injury.get("latest_reported_status")).lower() == "worse":
            return f"The {label} injury is worse."
    return None


# Injury consequence tier + severity + session exposure -> restriction floor.
# Severe/worse injuries are already stopped by _active_context_injury_stop, so this
# grades ONLY the moderate/mild high-consequence gap that severity+worse alone
# missed. Minor injuries (tier None: surface / soft-tissue / symptom) never reach
# here, so a bruise or blister keeps training by default.
_INJURY_FLOOR_RANK: dict[str | None, int] = {None: 0, "modify": 1, "pull_back": 2}


def _injury_floor_for(tier: str, severity: str, session_risk: SessionRisk) -> str | None:
    high = session_risk == "high"
    low = session_risk == "low"
    if tier == "neuro":
        # Head / neck / nerve tissue is not safe to train through on any session.
        return "pull_back"
    if tier == "structural":
        if severity == "mild":
            return None if low else "modify"
        return "modify" if low else "pull_back"
    if tier == "load_sensitive":
        if severity == "mild":
            return "modify" if high else None
        if high:
            return "pull_back"
        if low:
            return None
        return "modify"
    return None


def _context_injury_floor(
    context: ReadinessContext, session_risk: SessionRisk
) -> tuple[str | None, str, str]:
    """Strongest injury-driven restriction floor across active open injuries.

    Returns ``(floor, label, tier)`` where ``floor`` is ``None`` / ``"modify"`` /
    ``"pull_back"``. Only open/monitoring injuries carrying a high-consequence tier
    participate; severe / worse are handled by ``_active_context_injury_stop``.
    """
    best_floor: str | None = None
    best_label = ""
    best_tier = ""
    for injury in context.open_injuries:
        if _clean(injury.get("status")).lower() not in {"open", "monitoring"}:
            continue
        tier = _clean(injury.get("consequence")).lower()
        if tier not in {"neuro", "structural", "load_sensitive"}:
            continue
        severity = _clean(injury.get("severity")).lower() or "moderate"
        floor = _injury_floor_for(tier, severity, session_risk)
        if _INJURY_FLOOR_RANK[floor] > _INJURY_FLOOR_RANK[best_floor]:
            best_floor = floor
            best_tier = tier
            label = _clean(injury.get("label"))
            if not label:
                from api.contracts.injury_checkin import build_injury_label

                label = build_injury_label(injury.get("body_area"), injury.get("description"))
            best_label = label
    return best_floor, best_label, best_tier


def _injury_floor_pull_back(
    tier: str,
    label: str,
    *,
    session_risk: SessionRisk,
    phase: str,
    contact_sport: bool,
) -> ReadinessAdjustment:
    """A type-aware pull-back for a moderate high-consequence injury. Head/neck use
    STOP-tone ``Rehab only today.`` copy; structural / tendon / joint use PULL BACK
    copy (recovery / light technical), scaled to the injury, not a blanket stop."""
    label = label or "injury"
    if tier == "neuro":
        title = "Rehab only today."
        reason = f"Your {label} involves head, neck, or nerve symptoms, so training is not safe today."
        action = "No sparring, impact, or hard work today — rest and monitor symptoms."
        safety = "Seek medical advice for worsening headache, dizziness, numbness, vision changes, or neck pain."
    elif tier == "structural":
        title = "Pull back today."
        reason = f"Your {label} needs load and impact kept off it today."
        action = "Skip sparring, clinch, rotation, heavy loading, and conditioning; keep it to light rehab or mobility."
        safety = "Seek medical advice if pain is sharp, worsening, unstable, or swelling increases."
    else:  # load_sensitive
        title = "Pull back today."
        reason = f"Hard work would overload your {label} today."
        action = "Skip sparring, hard bag work, plyos, and heavy loading; use rehab or light technical only."
        safety = "Seek medical advice if pain is sharp, unstable, swollen, or neurological."
    return ReadinessAdjustment(
        decision="pull_back",
        title=title,
        reason=reason,
        action=action,
        safety=safety,
        triggers=_with_context_triggers(
            "active_injury_restriction",
            session_risk=session_risk,
            phase=phase,
            contact_sport=contact_sport,
        ),
        session_risk=session_risk,
    )


def _risk_adjustment(
    checkin: ReadinessCheckin,
    context: ReadinessContext,
    session_risk: SessionRisk,
    phase: str,
    *,
    support_session: bool = False,
) -> ReadinessAdjustment | None:
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

    # A low-cost support / filler session (mental cue work, breathing/sleep reset,
    # mobility or rehab touch) carries no meaningful physical stress, so an injury
    # or high pain must NOT hard-block it — it is exactly the safe work an injury
    # STOP recommends. Acute red-flag symptoms above still stop everything.
    if support_session:
        return None

    active_injury_stop_reason = _active_context_injury_stop(context)
    if checkin.active_injury == "worse" or active_injury_stop_reason is not None:
        context_reason = active_injury_stop_reason or "The injury is worse."
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
    poor_sleep_streak = _three_day_streak(
        checkin.sleep,
        prior_rows,
        "sleep",
        {"poor"},
        training_day=context.training_day,
    )
    flat_body_streak = _three_day_streak(
        checkin.body,
        prior_rows,
        "body",
        {"flat"},
        training_day=context.training_day,
    )
    pain_streak = _three_day_streak(
        checkin.pain,
        prior_rows,
        "pain",
        {"manageable", "high"},
        training_day=context.training_day,
    )
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


def _filter_warnings(warnings: Sequence[str]) -> list[str]:
    """Drop labels fully covered by a stronger co-occurring signal so the athlete
    never reads the same thing twice in one sentence. The message tier keys off the
    filtered count too, so a pair that collapses to one label never claims to be
    "multiple"."""
    display = list(warnings)
    if "recent_hard_load_plus_poor_today" in display and "recent_hard_session" in display:
        display.remove("recent_hard_session")
    if "pain_worsening_trend" in display and "pain_3_day_streak" in display:
        display.remove("pain_3_day_streak")
    return display


def _warning_source_labels(warnings: Sequence[str]) -> tuple[str, ...]:
    display = _filter_warnings(warnings)
    return tuple(_WARNING_SOURCE_LABELS.get(warning, warning.replace("_", " ")) for warning in display)


def _join_warning_labels(warnings: Sequence[str]) -> str:
    labels = _warning_source_labels(warnings)
    if len(labels) <= 2:
        return " and ".join(labels)
    return f"{', '.join(labels[:-1])}, and {labels[-1]}"


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
            "Your recent training load was high, and today's check-in is poor.",
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
            reason = "Manageable pain before contact work means the area needs extra protection today."
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
    # Count off the filtered set so a pair that collapses to one display label
    # (e.g. worsening pain absorbing the pain streak) drops to the single-warning
    # message instead of claiming "multiple" and then listing one.
    warnings = _filter_warnings(warnings)
    warning_count = len(warnings)
    if warning_count >= 3:
        if session_risk == "high" or _has_pain_warning(warnings) or phase in {"TAPER", "REINTEGRATION"} or fight_week:
            return (
                "pull_back",
                "Pull back today.",
                f"Multiple warning signs are showing: {_join_warning_labels(warnings)}. Hard combat work should be reduced today.",
                "Skip combat work and use recovery or light mobility instead.",
            )
        return (
            "modify",
            "Session reduced.",
            f"Multiple warning signs are showing: {_join_warning_labels(warnings)}. Today needs a safer dose.",
            "Cut rounds, cap intensity, and remove conditioning.",
        )

    if warning_count == 2:
        return (
            "modify",
            "Session reduced.",
            f"Multiple warning signs are showing: {_join_warning_labels(warnings)}. Hard combat work should be reduced today.",
            "Skip sparring, hard rounds, and conditioning finishers, and keep the remaining rounds controlled.",
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
        "Your sleep, body, and pain checks are all clear today.",
        "Run the planned work and keep the rounds clean.",
    )


def _first_active_open_injury_label(context: ReadinessContext) -> str:
    for injury in context.open_injuries:
        if _clean(injury.get("status")).lower() not in {"open", "monitoring"}:
            continue
        label = _clean(injury.get("label"))
        if label:
            return label
        from api.contracts.injury_checkin import build_injury_label

        return build_injury_label(injury.get("body_area"), injury.get("description"))
    return ""


def _injury_text_regions(text: str) -> set[str]:
    """Canonical injury regions named anywhere in a piece of injury text.

    Uses whole-phrase matching (``fightcamp.normalization.phrase_in_text``), not a
    bare substring check — a naive ``"disc" in text`` would misfire on "knee
    DISComfort" and wrongly add lower_back as an injured region.
    """
    cleaned = _clean(text).lower().replace("_", " ")
    if not cleaned:
        return set()
    try:
        from fightcamp.injury_exclusion_rules import INJURY_REGION_KEYWORDS
        from fightcamp.normalization import phrase_in_text
    except Exception:  # pragma: no cover - region map always importable in-app
        return set()
    regions: set[str] = set()
    for region, keywords in INJURY_REGION_KEYWORDS.items():
        if any(phrase_in_text(cleaned, keyword) for keyword in keywords):
            regions.add(region)
    return regions


def _resolve_injury_regions(value: str) -> set[str]:
    """Canonical regions for one injury value, structured resolution first.

    A structured location string (the check-in's ``body_area``/``active_injury``,
    e.g. "shoulder", "quad") is resolved through the same canonical
    location/synonym registry the injury-exclusion engine uses
    (``get_exclusion_regions``) before falling back to free-text keyword
    matching, so a specific structured value is never diluted by a broader
    substring scan.
    """
    cleaned = _clean(value)
    if not cleaned:
        return set()
    try:
        from fightcamp.injury_exclusion_rules import get_exclusion_regions
    except Exception:  # pragma: no cover - always importable in-app
        return _injury_text_regions(cleaned)
    resolved = get_exclusion_regions(cleaned)
    if resolved:
        return set(resolved)
    return _injury_text_regions(cleaned)


def _active_injury_regions(checkin: ReadinessCheckin, context: ReadinessContext) -> set[str]:
    """Regions of the athlete's currently active injuries (open + this check-in).

    The structured ``body_area`` is resolved authoritatively via
    ``_resolve_injury_regions``; free-text ``label``/``description`` are also
    scanned (whole-phrase, not substring) so a region named only in prose is
    still caught.
    """
    regions: set[str] = set()
    for injury in context.open_injuries:
        if _clean(injury.get("status")).lower() not in {"open", "monitoring"}:
            continue
        body_area = _clean(injury.get("body_area"))
        if body_area:
            regions |= _resolve_injury_regions(body_area)
        text = " ".join(_clean(injury.get(key)) for key in ("label", "description"))
        regions |= _injury_text_regions(text)
    if checkin.active_injury not in {"", "none"}:
        regions |= _resolve_injury_regions(checkin.active_injury)
    return regions


def _iter_session_mappings(session: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The session mapping plus any nested block/exercise mappings that carry tags."""
    mappings: list[Mapping[str, Any]] = [session]
    for key in ("blocks", "exercises", "movements", "items"):
        nested = session.get(key)
        if isinstance(nested, Sequence) and not isinstance(nested, (str, bytes)):
            for item in nested:
                if isinstance(item, Mapping):
                    mappings.append(item)
                    for inner_key in ("exercises", "movements", "items"):
                        inner = item.get(inner_key)
                        if isinstance(inner, Sequence) and not isinstance(inner, (str, bytes)):
                            mappings.extend(m for m in inner if isinstance(m, Mapping))
    return mappings


# Fields that name an entry (its exercise/primer/block title). Deliberately
# excludes narrative fields (objective, coach_note, reason, display_text,
# primary_focus, emphasis) — those describe or review the session in prose and can
# mention a movement word ("review how they react to your jab") without the
# athlete physically throwing anything.
_ENTRY_NAME_FIELDS = ("title", "label", "name", "athlete_facing_label")
_NON_PHYSICAL_INSERT_CATEGORIES = {"tactical", "mental"}


def _is_non_physical_mapping(mapping: Mapping[str, Any]) -> bool:
    """True for a tactical/mental entry whose name must never drive a physical-load
    keyword match — a "Jab Cue Card" review is video/notes work, not a thrown jab."""
    for key in ("support_insert_category", "insert_category", "category"):
        if _clean(mapping.get(key)).lower() in _NON_PHYSICAL_INSERT_CATEGORIES:
            return True
    return False


def _physical_entry_name_text(session: Mapping[str, Any]) -> str:
    """Name-only text (title/label/name) from the session's physical entries.

    This is the ONLY text the movement-keyword fallback in
    ``_session_mechanical_load_regions`` may scan — see ``_ENTRY_NAME_FIELDS`` and
    ``_is_non_physical_mapping`` for why objective/coach_note/reason text and
    tactical/mental entries are excluded.
    """
    parts: list[str] = []
    for mapping in _iter_session_mappings(session):
        if _is_non_physical_mapping(mapping):
            continue
        for key in _ENTRY_NAME_FIELDS:
            value = mapping.get(key)
            if value:
                parts.append(_clean(value))
    return " ".join(parts).lower()


def _session_mechanical_load_regions(session: Mapping[str, Any] | None) -> set[str]:
    """Body regions a support session mechanically loads.

    Draws on three signals, most authoritative first: the structured
    ``mechanical_load_regions`` the gap-fill fillers emit, the bank items'
    ``mechanical_risk_tags``, and — as a fallback for content that only surfaces as
    a name — the movement wording in physical entries' names only (never
    objectives/notes/reasons, and never tactical/mental entries; see
    ``_physical_entry_name_text``).
    """
    if not isinstance(session, Mapping) or not session:
        return set()
    from fightcamp.normalization import phrase_in_text

    regions: set[str] = set()
    for mapping in _iter_session_mappings(session):
        declared = mapping.get("mechanical_load_regions")
        if isinstance(declared, Sequence) and not isinstance(declared, (str, bytes)):
            regions.update(_clean(region).lower() for region in declared if _clean(region))
        mech_tags = mapping.get("mechanical_risk_tags")
        if isinstance(mech_tags, Sequence) and not isinstance(mech_tags, (str, bytes)):
            for tag in mech_tags:
                regions.update(_MECH_TAG_REGIONS.get(_clean(tag).lower(), ()))
    physical_text = _physical_entry_name_text(session)
    if physical_text:
        for region, keywords in _REGION_LOAD_KEYWORDS.items():
            if any(phrase_in_text(physical_text, keyword) for keyword in keywords):
                regions.add(region)
    return regions


def _safe_filler_adjustment(
    checkin: ReadinessCheckin,
    context: ReadinessContext,
    session_risk: SessionRisk,
    phase: str,
    contact_sport: bool,
) -> ReadinessAdjustment:
    """A safe support / filler session is always allowed once red flags are clear.

    It is restorative low/zero-stress work, so neither an injury (exempted upstream)
    nor an accumulated fatigue soft-warning should reduce it — the athlete just does
    the easy session.

    The one exception: a low-stress session can still carry a filler or primer that
    mechanically loads the *injured* region (an explosive band row on a bruised
    shoulder, footwork on a sprained ankle, ...). Blanket-declaring that "safe to do
    around your injury" is exactly the failure this guard closes — when the session
    loads the active injury's region we downgrade to a targeted "protect the area"
    modify instead of the safe-session all-clear.
    """
    label = _first_active_open_injury_label(context)
    injured_regions = _active_injury_regions(checkin, context)
    loaded_regions = _session_mechanical_load_regions(context.today_session)
    if injured_regions & loaded_regions:
        injury_phrase = f"your {label}" if label else "the injured area"
        return ReadinessAdjustment(
            decision="modify",
            title="Protect the injured area.",
            reason=(
                f"This is mostly low-stress work, but part of it loads {injury_phrase}, "
                "which the check-in still flags as active."
            ),
            action=(
                "Do the rest of the session easy, but skip or replace any movement that "
                "loads the injured area, and stop anything that provokes it."
            ),
            triggers=_with_context_triggers(
                "support_session", session_risk=session_risk, phase=phase, contact_sport=contact_sport
            ),
            session_risk=session_risk,
        )
    has_signal = (
        bool(context.open_injuries)
        or checkin.active_injury != "none"
        or checkin.pain != "none"
    )
    if has_signal:
        reason = (
            f"This is low-stress recovery or skill work — safe to do around your {label}."
            if label
            else "This is low-stress recovery or skill work — safe to do today."
        )
        action = "Do the session as planned; keep it easy and stop anything that hurts."
    else:
        reason = "This is low-stress recovery or skill work."
        action = "Do the session as planned and keep it easy."
    return ReadinessAdjustment(
        decision="train_as_planned",
        title="Safe session today.",
        reason=reason,
        action=action,
        triggers=_with_context_triggers(
            "support_session", session_risk=session_risk, phase=phase, contact_sport=contact_sport
        ),
        session_risk=session_risk,
    )


def build_readiness_adjustment(
    checkin: ReadinessCheckin,
    context: ReadinessContext | None = None,
) -> ReadinessAdjustment:
    context = context or ReadinessContext()
    phase = _normalize_phase(context.phase or checkin.phase)
    session_risk = classify_session_risk(context.today_session)
    contact_sport = _is_combat_contact_sport(context)
    # A low-cost support / filler session (mental cue work, breathing/sleep reset,
    # mobility or rehab touch) is exempt from injury-driven blocks — it is the safe
    # work an injury STOP itself recommends.
    support_session = is_support_session(context.today_session)
    risk = _risk_adjustment(checkin, context, session_risk, phase, support_session=support_session)
    if risk:
        return risk

    # A safe support / filler session is always allowed once red flags are clear: it
    # is restorative, so neither an injury (exempted above) nor a fatigue soft-warning
    # should reduce it. Return the "safe session" adjustment and skip the injury floor
    # and the soft-warning fatigue logic entirely.
    if support_session:
        return _safe_filler_adjustment(checkin, context, session_risk, phase, contact_sport)

    # Type-aware injury floor: a moderate head-neck / structural / rib / tendon /
    # joint injury restricts by exposure even when it is not flagged "worse". A
    # pull-back floor is terminal; a modify floor raises the soft-warning decision.
    injury_floor, injury_label, injury_tier = _context_injury_floor(context, session_risk)
    if injury_floor == "pull_back":
        return _injury_floor_pull_back(
            injury_tier,
            injury_label,
            session_risk=session_risk,
            phase=phase,
            contact_sport=contact_sport,
        )

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

    decision, title, reason, action = _soft_warning_message(
        soft_warnings.effective,
        session_risk=session_risk,
        phase=phase,
        fight_week=fight_week,
    )

    # A pain signal before hard combat work is a pull-back, not a modify: the modify
    # copy already tells the athlete to skip the entire session, so the state must
    # match the action (fixes the amber-state / stop-action contradiction). Only
    # promote when the soft-warning stack has not already pulled back, so the
    # richer "several warnings" copy is preserved.
    if decision != "pull_back" and _has_pain_warning(soft_warnings.effective) and session_risk == "high":
        decision = "pull_back"
        title = "Pull back today."
        reason = (
            "Pain is getting worse, so hard combat work is not safe today."
            if "pain_worsening_trend" in soft_warnings.effective
            else "Pain before hard combat work is not safe today."
        )
        action = "Skip sparring and hard work; use recovery, rehab, or light mobility instead."

    # Raise a clean/soft decision to the injury modify-floor, and never tell an
    # athlete carrying an open injury that their "check is clear".
    if injury_floor == "modify" and decision == "train_as_planned":
        decision = "modify"
        label = injury_label or "your injury"
        title = "Load controlled."
        reason = f"An active injury ({label}) means hard combat work needs to be limited today."
        action = "Keep it controlled: skip sparring, clinch pressure, hard bag work, and all-out rounds."
    elif decision == "train_as_planned":
        green_label = _first_active_open_injury_label(context)
        if green_label:
            title = "Train around it."
            reason = f"Your sleep, body, and pain checks are all clear — just protect your {green_label} today."
            action = "Run the planned work, keep the area clean, and stop if it flares."

    triggers = list(soft_warnings.triggers)
    if injury_floor == "modify" and "active_injury_restriction" not in triggers:
        triggers.append("active_injury_restriction")
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
