"""Deterministic Today check-in decision contract.

This module keeps the public check-in input and decision types stable while the
context-aware message engine in ``readiness_message`` owns the rule evaluation
and athlete-facing adjustment copy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .readiness_message import ReadinessCheckin, ReadinessContext, build_readiness_adjustment

CheckinDecisionValue = Literal["train_as_planned", "modify", "pull_back"]

Sleep = Literal["poor", "okay", "good"]
Body = Literal["flat", "normal", "sharp"]
Pain = Literal["none", "manageable", "high"]
Phase = Literal["GPP", "SPP", "TAPER", "REINTEGRATION"]
ActiveInjury = Literal["none", "stable", "worse"]
PreviousSession = Literal["none", "normal", "very_hard"]

SAFETY_FLAGS: tuple[str, ...] = (
    "sharp_pain",
    "instability",
    "swelling",
    "neurological_symptoms",
    "illness_symptoms",
    "cannot_warm_into_movement",
    "worse_next_day_pain",
)


@dataclass(frozen=True)
class CheckinInputs:
    """Structured check-in inputs plus red-flag safety toggles."""

    sleep: Sleep = "good"
    body: Body = "normal"
    pain: Pain = "none"
    phase: Phase = "GPP"
    active_injury: ActiveInjury = "none"
    previous_session: PreviousSession = "none"
    sharp_pain: bool = False
    instability: bool = False
    swelling: bool = False
    neurological_symptoms: bool = False
    illness_symptoms: bool = False
    cannot_warm_into_movement: bool = False
    worse_next_day_pain: bool = False


@dataclass(frozen=True)
class CheckinDecision:
    """A decision plus deterministic adjustment copy and trigger codes."""

    decision: CheckinDecisionValue
    reason: str
    triggers: tuple[str, ...]


def evaluate_checkin(inputs: CheckinInputs) -> CheckinDecision:
    """Evaluate a check-in without extra context.

    The Today service calls ``build_readiness_adjustment`` directly when active
    plan, session, injury, intake, and recent-history context are available.
    """
    adjustment = build_readiness_adjustment(
        ReadinessCheckin(
            sleep=inputs.sleep,
            body=inputs.body,
            pain=inputs.pain,
            phase=inputs.phase,
            active_injury=inputs.active_injury,
            previous_session=inputs.previous_session,
            sharp_pain=inputs.sharp_pain,
            instability=inputs.instability,
            swelling=inputs.swelling,
            neurological_symptoms=inputs.neurological_symptoms,
            illness_symptoms=inputs.illness_symptoms,
            cannot_warm_into_movement=inputs.cannot_warm_into_movement,
            worse_next_day_pain=inputs.worse_next_day_pain,
        ),
        ReadinessContext(phase=inputs.phase),
    )
    return CheckinDecision(
        decision=adjustment.decision,
        reason=adjustment.message,
        triggers=adjustment.triggers,
    )
