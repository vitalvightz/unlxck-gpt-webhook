"""Tests for the deterministic check-in decision evaluator (Block 4 §4)."""

from dataclasses import replace

from api.contracts.checkin_decision import (
    CheckinInputs,
    evaluate_checkin,
)

# A clean baseline: good sleep, normal body, no pain, GPP, no injuries/flags.
CLEAN = CheckinInputs(sleep="good", body="normal", pain="none", phase="GPP")


class TestNormalRules:
    def test_clean_input_trains_as_planned(self):
        decision = evaluate_checkin(CLEAN)
        assert decision.decision == "train_as_planned"
        assert decision.reason

    def test_okay_sleep_sharp_body_no_pain_trains_as_planned(self):
        decision = evaluate_checkin(replace(CLEAN, sleep="okay", body="sharp"))
        assert decision.decision == "train_as_planned"

    def test_poor_sleep_modifies(self):
        decision = evaluate_checkin(replace(CLEAN, sleep="poor"))
        assert decision.decision == "modify"
        assert decision.reason.splitlines() == [
            "Session reduced.",
            "Poor sleep means your body has less room to recover today.",
            "Cut 1 round and do not add extra conditioning.",
        ]

    def test_flat_body_modifies(self):
        decision = evaluate_checkin(replace(CLEAN, body="flat"))
        assert decision.decision == "modify"
        assert "flat body" in decision.reason.lower()

    def test_manageable_pain_modifies(self):
        decision = evaluate_checkin(replace(CLEAN, pain="manageable"))
        assert decision.decision == "modify"
        assert "manageable pain" in decision.reason.lower()

    def test_most_conservative_rule_wins_for_combo(self):
        # Two modify-level signals still resolve to modify (not escalated).
        decision = evaluate_checkin(replace(CLEAN, sleep="poor", body="flat"))
        assert decision.decision == "modify"


class TestHardOverrides:
    def test_high_pain_pulls_back(self):
        decision = evaluate_checkin(replace(CLEAN, pain="high"))
        assert decision.decision == "pull_back"
        assert decision.reason.splitlines() == [
            "Rehab only today.",
            "Pain is high, so contact and impact are not safe today.",
            "Use rehab or easy mobility only; skip sparring, pads, bag work, and conditioning.",
        ]

    def test_active_injury_worse_pulls_back(self):
        decision = evaluate_checkin(replace(CLEAN, active_injury="worse"))
        assert decision.decision == "pull_back"
        assert "Rehab only today." in decision.reason
        assert "injury is worse" in decision.reason

    def test_each_safety_flag_pulls_back(self):
        for flag in (
            "sharp_pain",
            "instability",
            "swelling",
            "neurological_symptoms",
            "illness_symptoms",
            "cannot_warm_into_movement",
            "worse_next_day_pain",
        ):
            decision = evaluate_checkin(replace(CLEAN, **{flag: True}))
            assert decision.decision == "pull_back", flag
            assert flag in decision.triggers

    def test_override_beats_otherwise_clean_signals(self):
        # Good sleep/body but a safety flag still forces pull_back.
        decision = evaluate_checkin(replace(CLEAN, sleep="good", instability=True))
        assert decision.decision == "pull_back"

    def test_multiple_overrides_produce_deterministic_reason(self):
        inputs = replace(CLEAN, pain="high", swelling=True)
        first = evaluate_checkin(inputs)
        second = evaluate_checkin(inputs)
        assert first.decision == "pull_back"
        assert first.reason == second.reason


class TestPhaseBias:
    def test_poor_flat_manageable_in_taper_pulls_back(self):
        decision = evaluate_checkin(
            replace(CLEAN, sleep="poor", body="flat", pain="manageable", phase="TAPER")
        )
        assert decision.decision == "pull_back"
        assert "Pull back today." in decision.reason
        assert "signals are stacking up" in decision.reason
        assert "Skip combat work" in decision.reason
        assert "Keep sharp work only" not in decision.reason
        assert "Remove 1 set" not in decision.reason
        assert "fatigue-heavy accessories" not in decision.reason

    def test_poor_flat_manageable_in_reintegration_pulls_back(self):
        decision = evaluate_checkin(
            replace(
                CLEAN, sleep="poor", body="flat", pain="manageable", phase="REINTEGRATION"
            )
        )
        assert decision.decision == "pull_back"

    def test_poor_flat_manageable_in_gpp_pulls_back_from_pain_stack(self):
        decision = evaluate_checkin(
            replace(CLEAN, sleep="poor", body="flat", pain="manageable", phase="GPP")
        )
        assert decision.decision == "pull_back"
        assert "signals are stacking up" in decision.reason

    def test_poor_flat_manageable_in_spp_pulls_back_from_pain_stack(self):
        decision = evaluate_checkin(
            replace(CLEAN, sleep="poor", body="flat", pain="manageable", phase="SPP")
        )
        assert decision.decision == "pull_back"
        assert "signals are stacking up" in decision.reason

    def test_phase_bias_never_makes_less_conservative(self):
        # GPP must not upgrade a modify back to train_as_planned.
        decision = evaluate_checkin(replace(CLEAN, sleep="poor", phase="GPP"))
        assert decision.decision == "modify"

    def test_very_hard_previous_session_modifies_in_spp(self):
        decision = evaluate_checkin(replace(CLEAN, previous_session="very_hard", phase="SPP"))
        assert decision.decision == "modify"
        assert "recent_hard_session" in decision.triggers

    def test_very_hard_previous_session_allowed_in_gpp(self):
        decision = evaluate_checkin(replace(CLEAN, previous_session="very_hard", phase="GPP"))
        assert decision.decision == "train_as_planned"


class TestDeterminism:
    def test_evaluator_is_deterministic_and_returns_reason(self):
        inputs = replace(CLEAN, sleep="poor", body="flat", pain="manageable", phase="TAPER")
        results = {evaluate_checkin(inputs) for _ in range(25)}
        assert len(results) == 1
        only = next(iter(results))
        assert only.reason
        assert isinstance(only.triggers, tuple)
