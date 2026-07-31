"""Normalized command-view read model (Block 4 §6 risk-watch + §7 command view).

Overview MUST NOT parse raw ``structured_plan``. It consumes this normalized,
derived read model instead, so Overview stays cheap to render and resilient to
``structured_plan`` schema changes.

The command view is **derived** state — built from the persisted plan, the
latest valid recommendation, completion records, and session data. It is not a
new source of truth. Missing inputs degrade to a clean empty state rather than
crashing.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, Field

from .completion import CompletionStatus, completion_status_of
from .readiness_message import (
    ConfidenceBand,
    confidence_band,
    confidence_note,
    context_labels,
    decision_sources,
    safety_checks,
    trigger_labels,
)
from .recommendation import RecommendationState, resolve_recommendation_state

# ---------------------------------------------------------------------------
# Risk watch (§6)
# ---------------------------------------------------------------------------

RiskCategory = Literal[
    "stop_red_flag",
    "active_injury_worse",
    "high_pain",
    "weight_cut",
    "fatigue",
    "reminder",
]

# Lower number = higher priority (rendered first). See §6 priority order.
RISK_PRIORITY: dict[str, int] = {
    "stop_red_flag": 1,
    "active_injury_worse": 2,
    "high_pain": 3,
    "weight_cut": 4,
    "fatigue": 6,
    "reminder": 7,
}

# Default presentation per category: (icon, label, tone). Meaning never relies on
# colour alone — every risk carries icon + label + text + tone (§6 encoding).
_RISK_PRESENTATION: dict[str, tuple[str, str, str]] = {
    "stop_red_flag": ("octagon-x", "Stop", "stop"),
    "active_injury_worse": ("bandage", "Injury worsening", "stop"),
    "high_pain": ("alert-triangle", "High pain", "warning"),
    "weight_cut": ("scale", "Weight cut", "warning"),
    "fatigue": ("battery-low", "Fatigue", "caution"),
    "reminder": ("info", "Reminder", "info"),
}

VISIBLE_RISK_LIMIT = 2


class RiskWatchItem(BaseModel):
    category: RiskCategory
    priority: int
    icon: str
    label: str
    text: str = ""
    tone: str


def make_risk(
    category: RiskCategory,
    *,
    text: str = "",
    icon: str | None = None,
    label: str | None = None,
    tone: str | None = None,
) -> RiskWatchItem:
    """Build a risk-watch item with sensible per-category defaults."""
    default_icon, default_label, default_tone = _RISK_PRESENTATION[category]
    return RiskWatchItem(
        category=category,
        priority=RISK_PRIORITY[category],
        icon=icon or default_icon,
        label=label or default_label,
        text=text,
        tone=tone or default_tone,
    )


def _coerce_risk(risk: RiskWatchItem | Mapping[str, Any]) -> RiskWatchItem:
    if isinstance(risk, RiskWatchItem):
        return risk
    category = str(risk.get("category") or "reminder")
    if category not in RISK_PRIORITY:
        category = "reminder"
    return make_risk(
        category,  # type: ignore[arg-type]
        text=str(risk.get("text") or ""),
        icon=risk.get("icon"),
        label=risk.get("label"),
        tone=risk.get("tone"),
    )


def sort_risk_watch(
    risks: Sequence[RiskWatchItem | Mapping[str, Any]],
) -> list[RiskWatchItem]:
    """Order risks by priority (stable within a priority band)."""
    items = [_coerce_risk(r) for r in risks]
    return sorted(items, key=lambda item: item.priority)


def visible_risk_watch(
    risks: Sequence[RiskWatchItem],
    *,
    limit: int = VISIBLE_RISK_LIMIT,
) -> tuple[list[RiskWatchItem], int]:
    """Split an ordered risk list into (visible, overflow_count) for "+N more"."""
    visible = list(risks[:limit])
    overflow = max(0, len(risks) - len(visible))
    return visible, overflow


# ---------------------------------------------------------------------------
# Command view (§7)
# ---------------------------------------------------------------------------


class QuickAction(BaseModel):
    """A declarative navigation action — a route, never an inline mutation."""

    id: str
    label: str
    route: str


# ---------------------------------------------------------------------------
# Decision tier (STOP / PULL BACK / MODIFY / GREEN) — single authoritative source
#
# The Today banner and the risk-watch footer used to be derived independently on
# the client (the banner by substring-parsing the reason, the footer from the risk
# categories), so they could disagree — e.g. a PULL BACK banner over a STOP footer.
# This tier is computed once here from the recommendation + risks + injuries, and
# both surfaces render from it, so they can never contradict.
# ---------------------------------------------------------------------------

DecisionTier = Literal["stop", "pull_back", "modify", "green", "not_checked_in"]

_TIER_RANK: dict[str, int] = {
    "not_checked_in": 0,
    "green": 1,
    "modify": 2,
    "pull_back": 3,
    "stop": 4,
}

# Stop-level risk categories: when present, the day is at minimum a STOP. NOTE:
# `stop_red_flag` is deliberately excluded — it is emitted for EVERY pull_back (it
# echoes the recommendation), so clamping on it would force a plain PULL BACK to
# read as STOP. `active_injury_worse` only fires for a severe / worse injury hold.
_STOP_RISK_CATEGORIES = frozenset({"active_injury_worse"})

# A pull_back recommendation is a hard STOP (rehab-only / no-training / injury-hold)
# rather than a plain pull-back when its first line (the title) is one of these, or
# its reason carries one of the specific stop markers. The markers are deliberately
# narrow — phrases that ONLY appear in stop copy — so a plain pull-back's generic
# "seek medical advice" safety line never falsely reads as a STOP. Every backend
# stop path already carries a distinguishing title; the markers are a backstop.
_STOP_REASON_TITLES = frozenset({"no training today", "rehab only today", "session blocked"})
_STOP_REASON_MARKERS = (
    "red flag",
    "injury is worse",
    "was reported worse",
    "pain is high",
    "head, neck, or nerve",
)


def _active_severe_injury_present(open_injuries: Sequence[Mapping[str, Any]] | None) -> bool:
    for injury in open_injuries or []:
        if (
            str(injury.get("severity") or "").lower() == "severe"
            and str(injury.get("status") or "").lower() in {"open", "monitoring"}
        ):
            return True
    return False


def resolve_decision_tier(
    *,
    recommendation_state: str,
    recommendation_reason: str | None,
    risks: Sequence[RiskWatchItem] | None = None,
    open_injuries: Sequence[Mapping[str, Any]] | None = None,
    injury_hold_exempt: bool = False,
) -> DecisionTier:
    """The single authoritative decision tier the whole Today UI renders from.

    Never weaker than the strongest risk in the footer, so the banner and footer
    cannot contradict. A severe active injury is always a STOP (injury hold), even
    before a check-in — unless ``injury_hold_exempt`` is set, which happens when
    today's scheduled session is a low-cost support / filler (mental cue, breathing
    or mobility reset) that the injury hold does not apply to.
    """
    if not injury_hold_exempt and _active_severe_injury_present(open_injuries):
        return "stop"

    state = str(recommendation_state or "not_checked_in")
    if state == "pull_back":
        reason = str(recommendation_reason or "")
        title = reason.splitlines()[0].strip().lower().rstrip(".!?") if reason else ""
        lowered = reason.lower()
        if title in _STOP_REASON_TITLES or any(marker in lowered for marker in _STOP_REASON_MARKERS):
            tier: DecisionTier = "stop"
        else:
            tier = "pull_back"
    elif state == "modify":
        tier = "modify"
    elif state == "train_as_planned":
        tier = "green"
    else:
        tier = "not_checked_in"

    # The tier can never be weaker than the strongest risk shown in the footer,
    # unless today's session is exempt from the injury hold (a safe filler).
    if not injury_hold_exempt and any((r.category in _STOP_RISK_CATEGORIES) for r in (risks or [])):
        if _TIER_RANK["stop"] > _TIER_RANK[tier]:
            tier = "stop"
    return tier


class CommandViewToday(BaseModel):
    training_day: str
    recommendation_state: RecommendationState = "not_checked_in"
    recommendation_reason: str | None = None
    # Authoritative decision tier (STOP/PULL BACK/MODIFY/GREEN). Both the banner and
    # the risk-watch footer render from this so they cannot disagree.
    decision_tier: DecisionTier = "not_checked_in"
    # True when today's scheduled session is a low-cost support / filler that an
    # injury hold does not apply to, so the UI must not block it for an injury.
    injury_hold_exempt: bool = False
    # The explanation, split by the role each part played. Computed on the
    # backend from the engine's own trigger codes (like decision_tier) so it can
    # never drift from the decision it explains. All empty until check-in.
    #
    # Triggers are what changed about the ATHLETE and set the decision. Context
    # is the camp around it, which only changes how cautious that decision is.
    # Holding them apart is what stops "Fight week" reading as a peer of
    # "High pain".
    recommendation_trigger_labels: list[str] = Field(default_factory=list)
    recommendation_context_labels: list[str] = Field(default_factory=list)
    # Safety checks are the third role: things the engine ASSESSED, which mostly
    # changed nothing. A stable skin injury lives here — never in the trigger
    # list — so the card can show it was considered without implying it reduced
    # the session. Structured ({code, label, result, result_label}) so the UI
    # never reads prose to tell a check from a cause.
    recommendation_safety_checks: list[dict[str, str]] = Field(default_factory=list)
    recommendation_sources: list[str] = Field(default_factory=list)
    # How much data the decision rests on, and what it was missing. This is data
    # completeness, NOT predictive accuracy — see readiness_message.
    #
    # ``None`` when the decision carries no trigger codes to judge it by, which
    # covers both "no decision yet" and a recommendation stored before the engine
    # recorded triggers. Deliberately not defaulted to "high": absent evidence is
    # not evidence of completeness, and asserting a band there would put a
    # confident claim on the one decision nothing is known about.
    recommendation_confidence: ConfidenceBand | None = None
    recommendation_confidence_note: str = ""
    warnings: list[str] = Field(default_factory=list)
    next_session: dict[str, Any] = Field(default_factory=dict)
    session_scope: Literal["today", "next", "none"] = "none"
    session_label: str = ""
    completion_status: CompletionStatus = "not_started"


class CommandView(BaseModel):
    active_plan: dict[str, Any] = Field(default_factory=dict)
    today: CommandViewToday
    risk_watch: list[RiskWatchItem] = Field(default_factory=list)
    # Open/monitoring injury_flags, normalized for the Today injury check-in to
    # prefill against (never the raw plan). Empty when nothing is being tracked.
    open_injuries: list[dict[str, Any]] = Field(default_factory=list)
    week_summary: dict[str, Any] = Field(default_factory=dict)
    quick_actions: list[QuickAction] = Field(default_factory=list)


_PLAN_IDENTITY_FIELDS = ("status", "phase", "fight_date", "camp_type")


def _plan_identity(plan: Mapping[str, Any] | None) -> dict[str, Any]:
    """Minimal plan identity/summary — never the full structured plan."""
    if not plan:
        return {}
    identity: dict[str, Any] = {
        field: plan[field]
        for field in _PLAN_IDENTITY_FIELDS
        if plan.get(field) not in (None, "")
    }
    plan_id = str(plan.get("id") or plan.get("plan_id") or "").strip()
    if plan_id:
        identity["id"] = plan_id
    plan_name = str(plan.get("name") or plan.get("plan_name") or "").strip()
    if plan_name:
        identity["name"] = plan_name
    # A plan with no recognisable identity fields is treated as "no plan".
    return identity


def _quick_actions(active_plan_id: str | None) -> list[QuickAction]:
    if not active_plan_id:
        return [
            QuickAction(
                id="complete_intake",
                label="Complete Intake / Create Plan",
                route="/intake",
            )
        ]
    return [
        QuickAction(id="open_today", label="Open Today", route="/today"),
        QuickAction(id="view_plan", label="View Plan", route=f"/plans/{active_plan_id}"),
    ]

def _as_iso(day: date | str) -> str:
    if hasattr(day, "date"):
        return day.date().isoformat()  # type: ignore[union-attr]
    if isinstance(day, date):
        return day.isoformat()
    return str(day or "").strip()


def build_command_view(
    *,
    current_training_day: date | str,
    plan: Mapping[str, Any] | None = None,
    recommendation: Mapping[str, Any] | None = None,
    completion: Mapping[str, Any] | None = None,
    next_session: Mapping[str, Any] | None = None,
    session_scope: Literal["today", "next", "none"] | None = None,
    warnings: Sequence[str] | None = None,
    risks: Sequence[RiskWatchItem | Mapping[str, Any]] | None = None,
    open_injuries: Sequence[Mapping[str, Any]] | None = None,
    week_summary: Mapping[str, Any] | None = None,
    injury_hold_exempt: bool = False,
) -> CommandView:
    """Assemble the normalized command view from derived inputs.

    Every argument is optional/nullable: a missing plan yields the empty state
    with an Intake CTA, a missing/expired recommendation yields
    ``not_checked_in``, and missing session/plan data yields clean empty objects
    rather than reaching into ``structured_plan``.
    """
    training_day = _as_iso(current_training_day)
    active_plan = _plan_identity(plan)

    rec_view = resolve_recommendation_state(
        recommendation, current_training_day=training_day
    )
    resolved_session_scope: Literal["today", "next", "none"] = (
        session_scope if session_scope is not None else ("next" if next_session else "none")
    )
    session_label = {
        "today": "Today's session",
        "next": "Next session",
        "none": "",
    }[resolved_session_scope]

    sorted_risks = sort_risk_watch(risks or [])
    today = CommandViewToday(
        training_day=training_day,
        recommendation_state=rec_view.state,
        recommendation_reason=rec_view.reason,
        decision_tier=resolve_decision_tier(
            recommendation_state=rec_view.state,
            recommendation_reason=rec_view.reason,
            risks=sorted_risks,
            open_injuries=open_injuries,
            injury_hold_exempt=injury_hold_exempt,
        ),
        injury_hold_exempt=injury_hold_exempt,
        recommendation_trigger_labels=list(trigger_labels(rec_view.triggers)),
        recommendation_context_labels=list(context_labels(rec_view.triggers)),
        recommendation_safety_checks=[dict(check) for check in safety_checks(rec_view.triggers)],
        recommendation_sources=(
            list(decision_sources(rec_view.triggers, has_open_injuries=bool(open_injuries)))
            if rec_view.triggers
            else []
        ),
        recommendation_confidence=(
            confidence_band(rec_view.triggers) if rec_view.triggers else None
        ),
        recommendation_confidence_note=confidence_note(rec_view.triggers),
        warnings=[str(warning) for warning in (warnings or []) if str(warning).strip()],
        next_session=dict(next_session) if next_session else {},
        session_scope=resolved_session_scope,
        session_label=session_label,
        completion_status=completion_status_of(completion),
    )

    return CommandView(
        active_plan=active_plan,
        today=today,
        risk_watch=sorted_risks,
        open_injuries=[dict(injury) for injury in (open_injuries or [])],
        week_summary=dict(week_summary) if week_summary else {},
        quick_actions=_quick_actions(active_plan.get("id")),
    )
