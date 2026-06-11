"""Unit tests for the readiness/fatigue status and safe adaptation rules."""

from api.readiness import (
    HIGH_RPE_STREAK_LENGTH,
    compute_readiness_summary,
    count_recent_high_rpe,
    count_recent_missed_sessions,
    evaluate_checkin_adaptations,
    evaluate_session_log_adaptations,
)


def _checkin(**overrides: object) -> dict:
    base = {
        "readiness": 4,
        "fatigue": 2,
        "soreness": 2,
        "sleep_quality": 4,
        "sleep_hours": 8.0,
        "injury_note": "",
    }
    return {**base, **overrides}


def _log(**overrides: object) -> dict:
    base = {"completed": True, "rpe": 6}
    return {**base, **overrides}


class TestComputeReadinessSummary:
    def test_normal_checkin_is_ready(self):
        summary = compute_readiness_summary(
            latest_checkin=_checkin(), open_injury_flag_count=0
        )
        assert summary.state == "ready"
        assert summary.label == "Ready"
        assert summary.reasons == []

    def test_no_checkin_yet_is_caution(self):
        summary = compute_readiness_summary(latest_checkin=None, open_injury_flag_count=0)
        assert summary.state == "caution"
        assert summary.reasons

    def test_high_fatigue_signal(self):
        summary = compute_readiness_summary(
            latest_checkin=_checkin(fatigue=5), open_injury_flag_count=0
        )
        assert summary.state == "high_fatigue"
        assert any("Fatigue" in reason for reason in summary.reasons)

    def test_high_soreness_signal(self):
        summary = compute_readiness_summary(
            latest_checkin=_checkin(soreness=4), open_injury_flag_count=0
        )
        assert summary.state == "high_fatigue"

    def test_very_low_self_rated_readiness(self):
        summary = compute_readiness_summary(
            latest_checkin=_checkin(readiness=1), open_injury_flag_count=0
        )
        assert summary.state == "high_fatigue"

    def test_poor_short_sleep_is_high_fatigue(self):
        summary = compute_readiness_summary(
            latest_checkin=_checkin(sleep_quality=1, sleep_hours=4.5),
            open_injury_flag_count=0,
        )
        assert summary.state == "high_fatigue"

    def test_poor_sleep_quality_alone_is_caution(self):
        summary = compute_readiness_summary(
            latest_checkin=_checkin(sleep_quality=2, sleep_hours=8.0),
            open_injury_flag_count=0,
        )
        assert summary.state == "caution"

    def test_moderate_signals_are_caution(self):
        summary = compute_readiness_summary(
            latest_checkin=_checkin(fatigue=3), open_injury_flag_count=0
        )
        assert summary.state == "caution"

    def test_open_injury_flag_wins_over_everything(self):
        summary = compute_readiness_summary(
            latest_checkin=_checkin(fatigue=5), open_injury_flag_count=2
        )
        assert summary.state == "injury_flag"
        assert any("injury flag" in reason for reason in summary.reasons)

    def test_high_rpe_streak_surfaces_as_caution(self):
        logs = [_log(rpe=9) for _ in range(HIGH_RPE_STREAK_LENGTH)]
        summary = compute_readiness_summary(
            latest_checkin=_checkin(),
            open_injury_flag_count=0,
            recent_session_logs=logs,
        )
        assert summary.state == "caution"

    def test_missed_sessions_surface_as_caution(self):
        logs = [_log(completed=False), _log(completed=False), _log()]
        summary = compute_readiness_summary(
            latest_checkin=_checkin(),
            open_injury_flag_count=0,
            recent_session_logs=logs,
        )
        assert summary.state == "caution"


class TestStreakHelpers:
    def test_high_rpe_streak_counts_consecutive_completed(self):
        logs = [_log(rpe=9), _log(rpe=8), _log(rpe=9), _log(rpe=5)]
        assert count_recent_high_rpe(logs) == 3

    def test_high_rpe_streak_breaks_on_low_rpe(self):
        logs = [_log(rpe=9), _log(rpe=5), _log(rpe=9)]
        assert count_recent_high_rpe(logs) == 1

    def test_high_rpe_streak_skips_missed_sessions(self):
        logs = [_log(completed=False, rpe=None), _log(rpe=9), _log(rpe=9), _log(rpe=9)]
        assert count_recent_high_rpe(logs) == 3

    def test_missing_rpe_breaks_streak(self):
        logs = [_log(rpe=None), _log(rpe=9)]
        assert count_recent_high_rpe(logs) == 0

    def test_missed_session_count(self):
        logs = [_log(completed=False), _log(), _log(completed=False)]
        assert count_recent_missed_sessions(logs) == 2


class TestCheckinAdaptations:
    def test_normal_checkin_keeps_plan(self):
        decisions = evaluate_checkin_adaptations(checkin=_checkin(), open_injury_flag_count=0)
        assert [d.decision for d in decisions] == ["keep_plan"]
        assert not any(d.requires_admin_review for d in decisions)

    def test_high_fatigue_reduces_intensity_and_adds_recovery(self):
        decisions = evaluate_checkin_adaptations(
            checkin=_checkin(fatigue=5), open_injury_flag_count=0
        )
        assert {d.decision for d in decisions} == {"reduce_intensity", "add_recovery"}

    def test_injury_report_swaps_session_and_flags_review(self):
        decisions = evaluate_checkin_adaptations(
            checkin=_checkin(injury_note="sharp pain in right knee"),
            open_injury_flag_count=1,
        )
        assert {d.decision for d in decisions} >= {"swap_session", "flag_admin_review"}
        assert any(d.requires_admin_review for d in decisions)

    def test_existing_open_flag_keeps_substitutions(self):
        decisions = evaluate_checkin_adaptations(checkin=_checkin(), open_injury_flag_count=1)
        assert any(
            d.decision == "swap_session" and d.rule_code == "open_injury_flag"
            for d in decisions
        )


class TestSessionLogAdaptations:
    def test_normal_log_keeps_plan(self):
        logs = [_log()]
        decisions = evaluate_session_log_adaptations(log=logs[0], recent_session_logs=logs)
        assert [d.decision for d in decisions] == ["keep_plan"]

    def test_repeated_high_rpe_reduces_intensity(self):
        logs = [_log(rpe=9) for _ in range(HIGH_RPE_STREAK_LENGTH)]
        decisions = evaluate_session_log_adaptations(log=logs[0], recent_session_logs=logs)
        assert any(
            d.rule_code == "repeated_high_rpe" and d.decision == "reduce_intensity"
            for d in decisions
        )

    def test_two_missed_sessions_keep_plan_with_note(self):
        logs = [_log(completed=False), _log(completed=False), _log()]
        decisions = evaluate_session_log_adaptations(log=logs[0], recent_session_logs=logs)
        missed = [d for d in decisions if d.rule_code == "missed_sessions"]
        assert missed and missed[0].decision == "keep_plan"
        assert not missed[0].requires_admin_review

    def test_three_missed_sessions_flag_admin_review(self):
        logs = [_log(completed=False) for _ in range(3)]
        decisions = evaluate_session_log_adaptations(log=logs[0], recent_session_logs=logs)
        missed = [d for d in decisions if d.rule_code == "missed_sessions"]
        assert missed and missed[0].decision == "flag_admin_review"
        assert missed[0].requires_admin_review
