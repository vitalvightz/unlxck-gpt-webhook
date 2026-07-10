"""Fail-safe status tracking for the Today/readiness context.

Safety context reads (recent check-ins, recent completions, scheduled session,
intake, injury flags + consequence classification) used to swallow their
exceptions and return empty lists/dicts. An empty result is indistinguishable
from a genuinely healthy, no-history athlete, so a failed read could silently
produce ``train_as_planned`` — a fail-OPEN safety bug.

This module makes the readiness path fail CLOSED:

* callers record which safety reads failed via :class:`ContextStatusBuilder`;
* the resulting :class:`ReadinessContextStatus` is ``complete`` / ``degraded`` /
  ``unavailable`` with structured ``reason_codes``;
* :func:`apply_context_failsafe` floors the engine's decision so a missing read
  can never be interpreted as readiness — degraded context can only allow
  ``modify`` / ``pull_back``, and unavailable context returns a conservative
  hold.

The module is pure (no I/O) so it is trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from api.contracts.readiness_message import ReadinessAdjustment

ContextStatus = Literal["complete", "degraded", "unavailable"]

# Structured reason codes surfaced to the client (and logs). ``context_unavailable``
# is the umbrella code attached whenever the overall status is ``unavailable``.
# This is the ONE canonical reason-code vocabulary — the route boundary maps its
# internal component names (recent_checkins, schedule, ...) onto these before any
# status/signal is built (see ``reason_code_for_component``).
CONTEXT_UNAVAILABLE = "context_unavailable"
CHECKINS_UNAVAILABLE = "checkins_unavailable"
COMPLETIONS_UNAVAILABLE = "completions_unavailable"
INTAKE_UNAVAILABLE = "intake_unavailable"
SESSION_UNAVAILABLE = "session_unavailable"
INJURY_CONTEXT_UNAVAILABLE = "injury_context_unavailable"

# Reasons that escalate the whole context to UNAVAILABLE (a conservative
# ``pull_back`` hold), rather than merely DEGRADED (``modify``):
#   * injury flags / classification — we cannot rule out a severe / high-
#     consequence injury, so training must not be cleared;
#   * scheduled-session resolution — if the session's risk cannot be known for
#     the current training day, we cannot grade exposure, so we hold conservatively
#     (deliberate choice: schedule failure is UNAVAILABLE, not degraded).
# Everything else (recent check-ins, completions, intake) only degrades.
_UNAVAILABLE_REASONS = frozenset({INJURY_CONTEXT_UNAVAILABLE, SESSION_UNAVAILABLE})

# Route-boundary component name -> canonical reason code. The boundary tracks
# failures by the store method that broke; this maps each onto the single
# canonical vocabulary so status and the typed signal are built one way only.
_COMPONENT_REASON_CODES: dict[str, str] = {
    "recent_checkins": CHECKINS_UNAVAILABLE,
    "recent_sessions": COMPLETIONS_UNAVAILABLE,
    "injury_flags": INJURY_CONTEXT_UNAVAILABLE,
    "injury_classification": INJURY_CONTEXT_UNAVAILABLE,
    "schedule": SESSION_UNAVAILABLE,
    "intake": INTAKE_UNAVAILABLE,
}


def reason_code_for_component(component: str) -> str:
    """Map a boundary component name onto the canonical reason code.

    Unknown components fall back to the umbrella ``context_unavailable`` so a new
    failure source can never silently drop to a non-conservative status.
    """
    return _COMPONENT_REASON_CODES.get(component, CONTEXT_UNAVAILABLE)


@dataclass(frozen=True)
class ReadinessContextStatus:
    """The completeness of the safety context behind a readiness decision."""

    status: ContextStatus
    reason_codes: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return self.status == "complete"

    @property
    def is_unavailable(self) -> bool:
        return self.status == "unavailable"


COMPLETE_STATUS = ReadinessContextStatus(status="complete", reason_codes=())


class ContextStatusBuilder:
    """Accumulates the reason codes for failed safety reads, then resolves the
    overall status (worst-of contributing levels)."""

    def __init__(self) -> None:
        self._codes: list[str] = []

    def add(self, code: str) -> None:
        if code and code not in self._codes:
            self._codes.append(code)

    def build(self) -> ReadinessContextStatus:
        if any(code in _UNAVAILABLE_REASONS for code in self._codes):
            status: ContextStatus = "unavailable"
        elif self._codes:
            status = "degraded"
        else:
            status = "complete"

        codes = list(self._codes)
        if status == "unavailable" and CONTEXT_UNAVAILABLE not in codes:
            codes.insert(0, CONTEXT_UNAVAILABLE)
        return ReadinessContextStatus(status=status, reason_codes=tuple(codes))


def status_from_components(components: Iterable[str]) -> ReadinessContextStatus:
    """Build a canonical :class:`ReadinessContextStatus` from route-boundary
    component names (``recent_checkins``, ``injury_flags``, ``schedule``, ...).

    This is the single bridge from the boundary's per-read failure tracking to
    the canonical status/reason-code vocabulary, so both the check-in path and
    the route boundary resolve status and severity the same way.
    """
    builder = ContextStatusBuilder()
    for component in components:
        builder.add(reason_code_for_component(component))
    return builder.build()


# ---------------------------------------------------------------------------
# Conservative fallback copy. These never claim a clean check — they explain
# that the app is holding back BECAUSE it could not verify the athlete's data.
# ---------------------------------------------------------------------------
_UNAVAILABLE_ADJUSTMENT = ReadinessAdjustment(
    decision="pull_back",
    title="Safety check unavailable.",
    reason=(
        "We couldn't load the training and injury history needed to clear you to "
        "train, so we're holding you back as a precaution."
    ),
    action=(
        "Skip hard training for now. Retry your check-in shortly, or keep it to "
        "light mobility until it loads."
    ),
    safety="Do not train through pain or an injury while this can't be verified.",
    triggers=(CONTEXT_UNAVAILABLE,),
    session_risk="unknown",
)

_DEGRADED_ADJUSTMENT = ReadinessAdjustment(
    decision="modify",
    title="Training reduced.",
    reason=(
        "Some of your recent check-in history couldn't be loaded, so we can't "
        "fully confirm you're fresh today."
    ),
    action=(
        "Train lighter than planned: cut volume and skip hard sparring, heavy "
        "loading, and conditioning finishers."
    ),
    safety="Stop and reassess if anything feels off.",
    triggers=("context_degraded",),
    session_risk="unknown",
)


def apply_context_failsafe(
    adjustment: ReadinessAdjustment,
    status: ReadinessContextStatus,
) -> ReadinessAdjustment:
    """Floor a readiness decision by how complete its safety context was.

    * ``complete``   -> unchanged.
    * ``unavailable``-> conservative hold (``pull_back``). A decision that already
      pulls back is more specific (e.g. a red-flag stop), so it is preserved.
    * ``degraded``   -> a ``train_as_planned`` result is raised to ``modify`` (a
      failed read must never read as readiness); an already-conservative
      ``modify`` / ``pull_back`` is preserved.
    """
    if status.status == "complete":
        return adjustment

    if status.status == "unavailable":
        if adjustment.decision == "pull_back":
            return adjustment
        return _UNAVAILABLE_ADJUSTMENT

    # degraded
    if adjustment.decision == "train_as_planned":
        return _DEGRADED_ADJUSTMENT
    return adjustment


# ---------------------------------------------------------------------------
# Backend-owned typed safety contract (P3).
#
# The frontend must read machine-typed fields instead of parsing backend prose,
# so a copy change can never change safety behaviour. These fields are derived
# once here (after the fail-safe floor is applied) and returned alongside the
# existing response shape — they are purely additive.
# ---------------------------------------------------------------------------
_DECISION_TIER: dict[str, str] = {
    "train_as_planned": "clear",
    "modify": "caution",
    "pull_back": "stop",
}
_DISPLAY_STATE: dict[str, str] = {
    "train_as_planned": "ready",
    "modify": "modify",
    "pull_back": "hold",
}


@dataclass(frozen=True)
class ReadinessSignal:
    """Machine-typed safety fields for the Today/readiness response.

    * ``decision`` — ``train_as_planned`` / ``modify`` / ``pull_back`` (persisted).
    * ``decision_tier`` — coarse severity: ``clear`` / ``caution`` / ``stop``.
    * ``display_state`` — UI state authority: ``ready`` / ``modify`` / ``hold`` /
      ``unavailable`` (``unavailable`` when safety context could not be verified).
    * ``reason_codes`` — structured codes (context failures first, then engine
      triggers), never prose.
    * ``title`` / ``detail`` / ``action`` / ``safety`` — display copy, but the UI
      keys behaviour off the typed fields above, not these strings.
    * ``blocks_training`` — the authoritative "training is blocked" flag.
    """

    decision: str
    decision_tier: str
    display_state: str
    reason_codes: tuple[str, ...]
    title: str
    detail: str
    action: str
    safety: str
    blocks_training: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "decision_tier": self.decision_tier,
            "display_state": self.display_state,
            "reason_codes": list(self.reason_codes),
            "title": self.title,
            "detail": self.detail,
            "action": self.action,
            "safety": self.safety,
            "blocks_training": self.blocks_training,
        }


def build_readiness_signal(
    adjustment: ReadinessAdjustment,
    status: ReadinessContextStatus = COMPLETE_STATUS,
) -> ReadinessSignal:
    """Derive the typed safety signal from a (fail-safe-floored) adjustment.

    Pass the SAME adjustment that gets persisted (i.e. after
    :func:`apply_context_failsafe`) so the typed fields and the stored decision
    can never disagree.
    """
    decision = adjustment.decision
    display_state = (
        "unavailable" if status.status == "unavailable" else _DISPLAY_STATE.get(decision, "modify")
    )
    reason_codes = tuple(dict.fromkeys([*status.reason_codes, *adjustment.triggers]))
    return ReadinessSignal(
        decision=decision,
        decision_tier=_DECISION_TIER.get(decision, "caution"),
        display_state=display_state,
        reason_codes=reason_codes,
        title=adjustment.title,
        detail=adjustment.reason,
        action=adjustment.action,
        safety=adjustment.safety,
        # pull_back is the only decision that blocks training outright; modify
        # reduces load and train_as_planned allows the planned work.
        blocks_training=decision == "pull_back",
    )
