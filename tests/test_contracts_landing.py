"""Tests for the state-dependent landing resolver (Block 4 §1)."""

from api.contracts.landing import resolve_landing


def _resolve(**overrides):
    base = {
        "has_active_plan": True,
        "has_interacted": True,
        "session_state": "none",
        "checked_in_today": False,
    }
    return resolve_landing(**{**base, **overrides})


class TestLandingRows:
    def test_row1_no_active_plan_routes_to_intake(self):
        decision = _resolve(has_active_plan=False)
        assert decision.target == "intake"
        assert decision.cta == "create_plan"
        assert decision.row == 1

    def test_row2_cold_user_with_plan_routes_to_overview(self):
        decision = _resolve(has_interacted=False)
        assert decision.target == "overview"
        assert decision.cta == "orientation"
        assert decision.row == 2

    def test_row3_started_session_resumes(self):
        decision = _resolve(session_state="resume")
        assert decision.target == "resume_session"
        assert decision.row == 3

    def test_row4_completed_session_keeps_navigation(self):
        decision = _resolve(session_state="completed")
        assert decision.target == "last_tab"
        assert decision.row == 4

    def test_row5_checked_in_today_routes_to_today(self):
        decision = _resolve(checked_in_today=True)
        assert decision.target == "today"
        assert decision.row == 5

    def test_row6_no_checkin_today_routes_to_overview_cta(self):
        decision = _resolve(checked_in_today=False)
        assert decision.target == "overview"
        assert decision.cta == "check_in"
        assert decision.row == 6


class TestPrecedence:
    def test_no_plan_beats_everything(self):
        decision = _resolve(
            has_active_plan=False,
            has_interacted=False,
            session_state="resume",
            checked_in_today=True,
        )
        assert decision.row == 1

    def test_cold_user_beats_session_and_checkin_states(self):
        decision = _resolve(
            has_interacted=False, session_state="resume", checked_in_today=True
        )
        assert decision.row == 2
        assert decision.target == "overview"

    def test_session_resume_beats_check_in_state(self):
        decision = _resolve(session_state="resume", checked_in_today=True)
        assert decision.row == 3
        assert decision.target == "resume_session"

    def test_completed_session_beats_checked_in_state(self):
        decision = _resolve(session_state="completed", checked_in_today=True)
        assert decision.row == 4
        assert decision.target == "last_tab"

    def test_checked_in_beats_no_checkin(self):
        # With no session state, the check-in flag decides row 5 vs row 6.
        assert _resolve(checked_in_today=True).row == 5
        assert _resolve(checked_in_today=False).row == 6
