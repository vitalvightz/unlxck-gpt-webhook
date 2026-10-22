"""One rule decides whether today's session is blocked; Today and the completion gate share it."""
import pytest

from api.services.today_service import session_hold


def live(session_type="strength", *, safety_hold=False, reason=None, session_id="s1"):
    return {"session": {"session_id": session_id, "session_type": session_type},
            "safety_hold": safety_hold, "safety_hold_reason": reason}


@pytest.mark.parametrize("tier", ["green", "modify", "not_checked_in"])
def test_go_and_adjust_never_block_without_an_injury_hold(tier):
    assert session_hold(tier, None)["held"] is False
    assert session_hold(tier, live())["held"] is False


def test_stop_always_blocks():
    assert session_hold("stop", None) == {
        "held": True, "reason": "Training is stopped by today's current safety guidance.", "source": "readiness"}
    assert session_hold("stop", live("rehab"))["held"] is True


def test_pull_back_holds_training_but_never_offered_rehab():
    held = session_hold("pull_back", live())
    assert held["held"] and held["source"] == "readiness" and "pull-back" in held["reason"]
    assert session_hold("pull_back", None)["held"] is True
    assert session_hold("pull_back", live("rehab"))["held"] is False


def test_pull_back_gate_allows_only_the_offered_rehab_session():
    offered = live("rehab", session_id="rehab-2026-10-22")
    assert session_hold("pull_back", offered, session_id="rehab-2026-10-22")["held"] is False
    assert session_hold("pull_back", offered, session_id="camp-session")["held"] is True


def test_injury_hold_names_its_source_and_reason():
    hold = session_hold("green", live(safety_hold=True, reason="Your planned training conflicts with the current injury restrictions."))
    assert hold == {"held": True, "reason": "Your planned training conflicts with the current injury restrictions.",
                    "source": "injury"}
    readiness = session_hold("pull_back", live(safety_hold=True, reason="Today's pull-back guidance holds your planned training."),
                             readiness_held=True)
    assert readiness["source"] == "readiness"
