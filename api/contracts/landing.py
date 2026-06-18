"""State-dependent landing resolver (Block 4 §1).

The single source of truth for "where does the athlete go when they open the
app". Pure function over already-resolved state so the UI and API share one
implementation and never improvise landing.

The table is ordered most-specific to most-generic; the resolver evaluates rows
top-to-bottom and **the first matching row wins**:

1. No active plan                         → Intake / Create Plan empty state
2. New / cold user with an active plan     → Overview (orientation)
3. Session started but unfinished          → Resume session (Today)
4. Session completed today                 → keep normal navigation / last tab
5. Returning user, already checked in today → Today
6. Returning user, no check-in today        → Overview with one dominant CTA

All "today" inputs (``session_state`` and ``checked_in_today``) must be computed
against the athlete-local **training day** (§3), not the UTC calendar day.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .completion import LandingSessionState

LandingTarget = Literal[
    "intake",
    "overview",
    "resume_session",
    "last_tab",
    "today",
]

# The dominant call-to-action for the landing surface. Exactly one is allowed.
LandingCTA = Literal[
    "create_plan",   # row 1
    "orientation",   # row 2 (cold user on Overview)
    "resume",        # row 3
    "none",          # row 4 / row 5 (no dominant CTA needed)
    "check_in",      # row 6 ("Check in / Open Today")
]


@dataclass(frozen=True)
class LandingDecision:
    target: LandingTarget
    cta: LandingCTA
    row: int
    reason: str


def resolve_landing(
    *,
    has_active_plan: bool,
    has_interacted: bool,
    session_state: LandingSessionState,
    checked_in_today: bool,
) -> LandingDecision:
    """Resolve the landing target. First matching row wins (see module docstring).

    * ``has_active_plan`` — whether the athlete has a usable active plan.
    * ``has_interacted`` — returning (True) vs cold/new (False); about prior
      interaction, not plan freshness.
    * ``session_state`` — today's session completion state from the completion
      contract (``none`` / ``resume`` / ``completed``).
    * ``checked_in_today`` — whether a valid recommendation exists for the
      current training day.
    """
    # Row 1 — no active plan.
    if not has_active_plan:
        return LandingDecision(
            target="intake",
            cta="create_plan",
            row=1,
            reason="No active plan — start intake / create a plan.",
        )

    # Row 2 — cold user with an active plan orients on Overview first. This sits
    # above the session/check-in rows, so a brand-new user is never dropped
    # straight into a resume/Today flow.
    if not has_interacted:
        return LandingDecision(
            target="overview",
            cta="orientation",
            row=2,
            reason="New athlete with an active plan — orient on Overview.",
        )

    # Row 3 — a started-but-unfinished session beats any check-in state.
    if session_state == "resume":
        return LandingDecision(
            target="resume_session",
            cta="resume",
            row=3,
            reason="A session is started but unfinished — resume it on Today.",
        )

    # Row 4 — a completed session beats the generic checked-in state.
    if session_state == "completed":
        return LandingDecision(
            target="last_tab",
            cta="none",
            row=4,
            reason="Today's session is already complete — keep normal navigation.",
        )

    # Row 5 — returning user who has already checked in today.
    if checked_in_today:
        return LandingDecision(
            target="today",
            cta="none",
            row=5,
            reason="Already checked in today — go to Today.",
        )

    # Row 6 — returning user with no check-in today: Overview with one dominant
    # "Check in / Open Today" CTA.
    return LandingDecision(
        target="overview",
        cta="check_in",
        row=6,
        reason="No check-in yet today — Overview with a single Check in / Open Today CTA.",
    )
