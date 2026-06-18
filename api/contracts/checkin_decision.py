"""Deterministic check-in decision evaluator (Block 4 §4).

This is the single executable contract for the check-in decision table. The
API, the Today UI, and tests must all call ``evaluate_checkin`` rather than
re-deriving the decision, so the three never drift apart.

Decision = one of ``train_as_planned`` / ``modify`` / ``pull_back``.

Evaluation order:

1. **Hard overrides** — any safety/red-flag match forces ``pull_back`` and
   dominates everything below.
2. **Normal rules** — sleep/body/pain signals; the most conservative match wins
   (``pull_back`` > ``modify`` > ``train_as_planned``).
3. **Phase bias** — may only make the decision *more* conservative, never less.

Reason strings are generated from the triggered inputs (not random canned
explanations) so the surfaced reason is deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

CheckinDecisionValue = Literal["train_as_planned", "modify", "pull_back"]

Sleep = Literal["poor", "okay", "good"]
Body = Literal["flat", "normal", "sharp"]
Pain = Literal["none", "manageable", "high"]
Phase = Literal["GPP", "SPP", "TAPER", "REINTEGRATION"]
ActiveInjury = Literal["none", "stable", "worse"]
PreviousSession = Literal["none", "normal", "very_hard"]

# Red-flag safety toggles Today must collect beyond the six structured inputs.
SAFETY_FLAGS: tuple[str, ...] = (
    "sharp_pain",
    "instability",
    "swelling",
    "neurological_symptoms",
    "illness_symptoms",
    "cannot_warm_into_movement",
    "worse_next_day_pain",
)

_CONSERVATISM: dict[str, int] = {
    "train_as_planned": 0,
    "modify": 1,
    "pull_back": 2,
}

# Phases where the conservative bias applies (never chase fatigue).
_CONSERVATIVE_PHASES: frozenset[str] = frozenset({"SPP", "TAPER", "REINTEGRATION"})


@dataclass(frozen=True)
class CheckinInputs:
    """Structured check-in inputs plus the red-flag safety toggles."""

    sleep: Sleep = "good"
    body: Body = "normal"
    pain: Pain = "none"
    phase: Phase = "GPP"
    active_injury: ActiveInjury = "none"
    previous_session: PreviousSession = "none"
    # Safety flags (red-flag inputs, not derived from sleep/body/pain).
    sharp_pain: bool = False
    instability: bool = False
    swelling: bool = False
    neurological_symptoms: bool = False
    illness_symptoms: bool = False
    cannot_warm_into_movement: bool = False
    worse_next_day_pain: bool = False


@dataclass(frozen=True)
class CheckinDecision:
    """A decision plus the deterministic reason and the triggers that fired."""

    decision: CheckinDecisionValue
    reason: str
    triggers: tuple[str, ...]


def _more_conservative(current: str, candidate: str) -> CheckinDecisionValue:
    """Return whichever of the two outcomes is more conservative."""
    winner = current if _CONSERVATISM[current] >= _CONSERVATISM[candidate] else candidate
    return winner  # type: ignore[return-value]


# Hard overrides in priority order. Each is (trigger_code, predicate, sentence).
_OVERRIDES: tuple[tuple[str, Callable[[CheckinInputs], bool], str], ...] = (
    ("pain_high", lambda i: i.pain == "high",
     "Pain is high today; pull back and use recovery work."),
    ("active_injury_worse", lambda i: i.active_injury == "worse",
     "Active injury is worse today; pull back and protect it."),
    ("sharp_pain", lambda i: i.sharp_pain,
     "Sharp pain is present; pull back today."),
    ("instability", lambda i: i.instability,
     "Joint instability is present; pull back today."),
    ("swelling", lambda i: i.swelling,
     "Swelling is present; pull back today."),
    ("neurological_symptoms", lambda i: i.neurological_symptoms,
     "Neurological symptoms are present; pull back today."),
    ("illness_symptoms", lambda i: i.illness_symptoms,
     "Illness symptoms are present; pull back today."),
    ("cannot_warm_into_movement", lambda i: i.cannot_warm_into_movement,
     "You can't warm into movement; pull back today."),
    ("worse_next_day_pain", lambda i: i.worse_next_day_pain,
     "The last session caused worse next-day pain; pull back today."),
)

# Short subject phrases used to build normal-rule reason strings.
_PHRASES: dict[str, str] = {
    "poor_sleep": "poor sleep",
    "flat_body": "flat body state",
    "manageable_pain": "manageable pain",
    "very_hard_previous": "a very hard previous session",
}

# Subjects for combining multiple hard overrides into one reason.
_OVERRIDE_SUBJECTS: dict[str, str] = {
    "pain_high": "high pain",
    "active_injury_worse": "a worsening injury",
    "sharp_pain": "sharp pain",
    "instability": "joint instability",
    "swelling": "swelling",
    "neurological_symptoms": "neurological symptoms",
    "illness_symptoms": "illness symptoms",
    "cannot_warm_into_movement": "an inability to warm into movement",
    "worse_next_day_pain": "worse next-day pain",
}


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _join_phrases(phrases: list[str]) -> str:
    if not phrases:
        return ""
    if len(phrases) == 1:
        return phrases[0]
    return f"{', '.join(phrases[:-1])} and {phrases[-1]}"


def _override_reason(fired: list[tuple[str, str]]) -> str:
    if len(fired) == 1:
        return fired[0][1]
    subjects = [_OVERRIDE_SUBJECTS.get(code, code) for code, _ in fired]
    return f"Red-flag signals are present ({_join_phrases(subjects)}); pull back today."


def _build_normal_reason(
    decision: CheckinDecisionValue,
    triggers: list[str],
    inputs: CheckinInputs,
) -> str:
    if decision == "train_as_planned":
        return "Sleep, body and pain all look good; train as planned today."
    phrases = [_PHRASES[t] for t in triggers if t in _PHRASES]
    joined = _join_phrases(phrases)
    if decision == "modify":
        return f"{_capitalize(joined)}; use the modified option today."
    # pull_back via the normal path is the poor+flat+manageable combo in a
    # conservative phase. Name the phase so the reason is explicit.
    phase_word = inputs.phase.lower()
    return f"{_capitalize(joined)} during {phase_word}; pull back today."


def evaluate_checkin(inputs: CheckinInputs) -> CheckinDecision:
    """Evaluate the check-in decision deterministically (see module docstring)."""
    # 1) Hard overrides dominate everything.
    fired = [(code, sentence) for code, pred, sentence in _OVERRIDES if pred(inputs)]
    if fired:
        return CheckinDecision(
            decision="pull_back",
            reason=_override_reason(fired),
            triggers=tuple(code for code, _ in fired),
        )

    # 2) Normal rules — most conservative match wins.
    decision: CheckinDecisionValue = "train_as_planned"
    triggers: list[str] = []
    poor = inputs.sleep == "poor"
    flat = inputs.body == "flat"
    manageable = inputs.pain == "manageable"

    if poor:
        decision = _more_conservative(decision, "modify")
        triggers.append("poor_sleep")
    if flat:
        decision = _more_conservative(decision, "modify")
        triggers.append("flat_body")
    if manageable:
        decision = _more_conservative(decision, "modify")
        triggers.append("manageable_pain")

    # poor + flat + manageable escalates to pull_back in conservative phases.
    if poor and flat and manageable and inputs.phase in {"TAPER", "REINTEGRATION"}:
        decision = "pull_back"
        triggers = ["poor_sleep", "flat_body", "manageable_pain"]

    # 3) Phase bias — conservative-only. A very hard previous session nudges
    # toward modify in SPP/TAPER/REINTEGRATION (never chase fatigue); GPP allows
    # more work, so it does not bias here. Bias can only raise conservatism.
    if inputs.previous_session == "very_hard" and inputs.phase in _CONSERVATIVE_PHASES:
        decision = _more_conservative(decision, "modify")
        if "very_hard_previous" not in triggers:
            triggers.append("very_hard_previous")

    return CheckinDecision(
        decision=decision,
        reason=_build_normal_reason(decision, triggers, inputs),
        triggers=tuple(triggers),
    )
