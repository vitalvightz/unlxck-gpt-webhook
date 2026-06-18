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
from .recommendation import RecommendationState, resolve_recommendation_state

# ---------------------------------------------------------------------------
# Risk watch (§6)
# ---------------------------------------------------------------------------

RiskCategory = Literal[
    "stop_red_flag",
    "active_injury_worse",
    "high_pain",
    "weight_cut",
    "phase_taper",
    "fatigue",
    "reminder",
]

# Lower number = higher priority (rendered first). See §6 priority order.
RISK_PRIORITY: dict[str, int] = {
    "stop_red_flag": 1,
    "active_injury_worse": 2,
    "high_pain": 3,
    "weight_cut": 4,
    "phase_taper": 5,
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
    "phase_taper": ("calendar-clock", "Taper", "caution"),
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


class CommandViewToday(BaseModel):
    training_day: str
    recommendation_state: RecommendationState = "not_checked_in"
    recommendation_reason: str | None = None
    next_session: dict[str, Any] = Field(default_factory=dict)
    completion_status: CompletionStatus = "not_started"


class CommandView(BaseModel):
    active_plan: dict[str, Any] = Field(default_factory=dict)
    today: CommandViewToday
    risk_watch: list[RiskWatchItem] = Field(default_factory=list)
    week_summary: dict[str, Any] = Field(default_factory=dict)
    quick_actions: list[QuickAction] = Field(default_factory=list)


_PLAN_IDENTITY_FIELDS = ("id", "name", "status", "phase", "fight_date", "camp_type")


def _plan_identity(plan: Mapping[str, Any] | None) -> dict[str, Any]:
    """Minimal plan identity/summary — never the full structured plan."""
    if not plan:
        return {}
    identity = {
        field: plan[field]
        for field in _PLAN_IDENTITY_FIELDS
        if plan.get(field) not in (None, "")
    }
    # A plan with no recognisable identity fields is treated as "no plan".
    return identity


def _quick_actions(has_active_plan: bool) -> list[QuickAction]:
    if not has_active_plan:
        return [
            QuickAction(
                id="complete_intake",
                label="Complete Intake / Create Plan",
                route="/intake",
            )
        ]
    return [
        QuickAction(id="open_today", label="Open Today", route="/today"),
        QuickAction(id="view_plan", label="View Plan", route="/plan"),
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
    risks: Sequence[RiskWatchItem | Mapping[str, Any]] | None = None,
    week_summary: Mapping[str, Any] | None = None,
) -> CommandView:
    """Assemble the normalized command view from derived inputs.

    Every argument is optional/nullable: a missing plan yields the empty state
    with an Intake CTA, a missing/expired recommendation yields
    ``not_checked_in``, and missing session/plan data yields clean empty objects
    rather than reaching into ``structured_plan``.
    """
    training_day = _as_iso(current_training_day)
    active_plan = _plan_identity(plan)
    has_active_plan = bool(active_plan)

    rec_view = resolve_recommendation_state(
        recommendation, current_training_day=training_day
    )

    today = CommandViewToday(
        training_day=training_day,
        recommendation_state=rec_view.state,
        recommendation_reason=rec_view.reason,
        next_session=dict(next_session) if next_session else {},
        completion_status=completion_status_of(completion),
    )

    return CommandView(
        active_plan=active_plan,
        today=today,
        risk_watch=sort_risk_watch(risks or []),
        week_summary=dict(week_summary) if week_summary else {},
        quick_actions=_quick_actions(has_active_plan),
    )
