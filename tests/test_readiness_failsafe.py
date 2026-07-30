"""Unit coverage for the pure fail-safe layer (api/services/readiness_failsafe).

These prove the fail-CLOSED contract in isolation from the store: a degraded or
unavailable safety context can never leave a ``train_as_planned`` decision
standing, and the typed signal reflects the floored decision.
"""

from __future__ import annotations

from api.contracts.readiness_message import ReadinessAdjustment
from api.services.readiness_failsafe import (
    CHECKINS_UNAVAILABLE,
    COMPLETIONS_UNAVAILABLE,
    CONTEXT_UNAVAILABLE,
    INJURY_CONTEXT_UNAVAILABLE,
    INTAKE_UNAVAILABLE,
    SESSION_UNAVAILABLE,
    COMPLETE_STATUS,
    ContextStatusBuilder,
    ReadinessContextStatus,
    apply_context_failsafe,
    build_readiness_signal,
    status_from_components,
)


def _train_as_planned() -> ReadinessAdjustment:
    return ReadinessAdjustment(
        decision="train_as_planned",
        title="Full session.",
        reason="All clear.",
        action="Run the planned work.",
        triggers=("phase_gpp",),
        session_risk="medium",
    )


def _pull_back() -> ReadinessAdjustment:
    return ReadinessAdjustment(
        decision="pull_back",
        title="No training today.",
        reason="Red flag symptom.",
        action="Stop and seek medical advice.",
        triggers=("red_flag",),
        session_risk="high",
    )


def test_builder_complete_when_no_failures():
    status = ContextStatusBuilder().build()
    assert status.status == "complete"
    assert status.reason_codes == ()
    assert status.is_complete


def test_builder_degraded_for_soft_read_failures():
    builder = ContextStatusBuilder()
    builder.add(CHECKINS_UNAVAILABLE)
    builder.add(INTAKE_UNAVAILABLE)
    status = builder.build()
    assert status.status == "degraded"
    assert CHECKINS_UNAVAILABLE in status.reason_codes
    assert INTAKE_UNAVAILABLE in status.reason_codes
    assert CONTEXT_UNAVAILABLE not in status.reason_codes


def test_builder_unavailable_when_injury_context_fails():
    builder = ContextStatusBuilder()
    builder.add(CHECKINS_UNAVAILABLE)
    builder.add(INJURY_CONTEXT_UNAVAILABLE)
    status = builder.build()
    assert status.status == "unavailable"
    # The umbrella code is attached and the specific codes are preserved.
    assert status.reason_codes[0] == CONTEXT_UNAVAILABLE
    assert INJURY_CONTEXT_UNAVAILABLE in status.reason_codes
    assert CHECKINS_UNAVAILABLE in status.reason_codes


def test_complete_context_leaves_decision_unchanged():
    adjustment = _train_as_planned()
    out = apply_context_failsafe(adjustment, ReadinessContextStatus("complete", ()))
    assert out is adjustment
    assert out.decision == "train_as_planned"


def test_degraded_context_blocks_train_as_planned():
    out = apply_context_failsafe(
        _train_as_planned(),
        ReadinessContextStatus("degraded", (CHECKINS_UNAVAILABLE,)),
    )
    assert out.decision == "modify"
    assert out.decision != "train_as_planned"


def test_degraded_context_preserves_already_conservative_decision():
    # The decision and its specific copy survive untouched. Only the trigger list
    # grows, so the record of the failed read travels with the decision.
    pull_back = _pull_back()
    out = apply_context_failsafe(
        pull_back, ReadinessContextStatus("degraded", (CHECKINS_UNAVAILABLE,))
    )
    assert out.decision == "pull_back"
    assert (out.title, out.reason, out.action) == (
        pull_back.title,
        pull_back.reason,
        pull_back.action,
    )
    assert set(pull_back.triggers) <= set(out.triggers)
    assert CHECKINS_UNAVAILABLE in out.triggers


def test_unavailable_context_forces_hold():
    out = apply_context_failsafe(
        _train_as_planned(),
        ReadinessContextStatus("unavailable", (CONTEXT_UNAVAILABLE, INJURY_CONTEXT_UNAVAILABLE)),
    )
    assert out.decision == "pull_back"
    assert "couldn't load" in out.reason.lower() or "unavailable" in out.title.lower()


def test_unavailable_context_keeps_specific_pull_back_copy():
    # An already-specific stop (red flag) is more informative than the generic
    # unavailable copy and still blocks training, so it is preserved.
    pull_back = _pull_back()
    out = apply_context_failsafe(
        pull_back,
        ReadinessContextStatus("unavailable", (CONTEXT_UNAVAILABLE, INJURY_CONTEXT_UNAVAILABLE)),
    )
    assert out.decision == "pull_back"
    assert (out.title, out.reason, out.action) == (
        pull_back.title,
        pull_back.reason,
        pull_back.action,
    )
    assert CONTEXT_UNAVAILABLE in out.triggers


def test_signal_typed_fields_for_normal_ready():
    signal = build_readiness_signal(_train_as_planned())
    assert signal.decision == "train_as_planned"
    assert signal.decision_tier == "clear"
    assert signal.display_state == "ready"
    assert signal.blocks_training is False


def test_signal_typed_fields_for_hold():
    signal = build_readiness_signal(_pull_back())
    assert signal.decision == "pull_back"
    assert signal.decision_tier == "stop"
    assert signal.display_state == "hold"
    assert signal.blocks_training is True


def test_signal_display_state_unavailable_and_reason_codes():
    status = ReadinessContextStatus(
        "unavailable", (CONTEXT_UNAVAILABLE, INJURY_CONTEXT_UNAVAILABLE)
    )
    adjustment = apply_context_failsafe(_train_as_planned(), status)
    signal = build_readiness_signal(adjustment, status)
    assert signal.decision == "pull_back"
    assert signal.display_state == "unavailable"
    assert signal.blocks_training is True
    assert CONTEXT_UNAVAILABLE in signal.reason_codes
    assert INJURY_CONTEXT_UNAVAILABLE in signal.reason_codes


class TestPreservedDecisionsCarryTheirStatusCodes:
    """A preserved decision keeps its own copy but inherits the codes for the
    reads that failed, so the record of what broke travels with the decision."""

    def _cautious(self) -> ReadinessAdjustment:
        return ReadinessAdjustment(
            decision="modify",
            title="Session reduced.",
            reason="Poor sleep.",
            action="Cut a round.",
            triggers=("poor_sleep", "sparse_history"),
        )

    def test_a_degraded_read_tags_a_preserved_modify(self):
        result = apply_context_failsafe(self._cautious(), status_from_components(["recent_checkins"]))
        assert result.decision == "modify"
        assert result.triggers[0] == CHECKINS_UNAVAILABLE
        assert "poor_sleep" in result.triggers

    def test_an_unavailable_read_tags_a_preserved_pull_back(self):
        stop = ReadinessAdjustment(
            decision="pull_back",
            title="No training today.",
            reason="Red flag.",
            action="Seek medical advice.",
            triggers=("sharp_pain", "red_flag"),
        )
        result = apply_context_failsafe(stop, status_from_components(["injury_flags"]))
        assert result.decision == "pull_back"
        assert result.title == "No training today."  # its own copy is preserved
        assert CONTEXT_UNAVAILABLE in result.triggers
        assert "sharp_pain" in result.triggers

    def test_a_complete_context_leaves_the_decision_untouched(self):
        original = self._cautious()
        assert apply_context_failsafe(original, COMPLETE_STATUS) is original


class TestReplacedDecisionsKeepTheSpecificFailureCode:
    """A replaced decision carries the component code, not just the umbrella.

    The fallbacks carry only "degraded"/"unavailable", and that is what gets
    persisted on the check-in row. Without the merge, a failed session-history or
    profile read read back later as "check-in history incomplete", and a failed
    schedule read read back as a claim about training and injury history that was
    never true.
    """

    def _green(self) -> ReadinessAdjustment:
        return ReadinessAdjustment(
            decision="train_as_planned",
            title="Full session.",
            reason="All clear.",
            action="Run the planned work.",
            triggers=("phase_gpp",),
        )

    def test_a_failed_completions_read_is_named(self):
        out = apply_context_failsafe(self._green(), status_from_components(["recent_sessions"]))
        assert out.decision == "modify"
        assert COMPLETIONS_UNAVAILABLE in out.triggers

    def test_a_failed_intake_read_is_named(self):
        out = apply_context_failsafe(self._green(), status_from_components(["intake"]))
        assert INTAKE_UNAVAILABLE in out.triggers

    def test_a_failed_schedule_read_is_named(self):
        out = apply_context_failsafe(self._green(), status_from_components(["schedule"]))
        assert out.decision == "pull_back"
        assert SESSION_UNAVAILABLE in out.triggers

    def test_the_fallback_copy_names_no_particular_input(self):
        # Several different reads reach the same fallback, so its prose must not
        # claim one of them. The specific component rides in the triggers.
        for component in ("recent_sessions", "intake", "schedule", "injury_flags"):
            out = apply_context_failsafe(self._green(), status_from_components([component]))
            assert "injury history" not in out.reason
            assert "check-in history" not in out.reason
