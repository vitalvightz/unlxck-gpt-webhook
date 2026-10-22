"""One rule decides whether today's session is blocked; Today and the completion gate share it."""
import pytest

from api.services.today_service import session_hold


def live(session_type="strength", *, safety_hold=False, reason=None, session_id="s1"):
    return {"session": {"session_id": session_id, "session_type": session_type},
            "safety_hold": safety_hold, "safety_hold_reason": reason}


def test_not_checked_in_holds_every_session_until_check_in():
    for current in (None, live(), live("rehab")):
        assert session_hold("not_checked_in", current) == {
            "held": True, "reason": "Complete today's check-in before starting.", "source": "check_in"}


def test_an_injury_hold_outranks_the_missing_check_in():
    hold = session_hold("not_checked_in", live(safety_hold=True, reason="Get this injury checked before training."))
    assert hold["source"] == "injury" and hold["reason"] == "Get this injury checked before training."


def test_a_pull_back_hold_recorded_by_the_injury_pipeline_names_readiness():
    current = {**live(safety_hold=True, reason="Today's pull-back guidance holds your planned training."),
               "training_hold_source": "readiness"}
    assert session_hold("pull_back", current)["source"] == "readiness"


@pytest.mark.parametrize("tier", ["green", "modify"])
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


def test_latest_same_day_injury_answer_is_the_rehab_response():
    from api.services.injury_episode_service import exposure_rows_with_observations
    exposure = {"id": "x1", "created_at": "2026-10-22T13:17:00Z", "event_json": {
        "injury_id": "i", "injury_episode_id": "e", "occurred_at": "2026-10-22T00:00:00Z",
        "response": {"during_response": "not_reported"},
        "provenance": {"response_tracking": "injury_checkin", "recorded_at": "2026-10-22T13:16:55Z"}}}

    def report(status, at):
        return {"id": at, "event_type": "injury_checkin", "injury_id": "i", "injury_episode_id": "e", "created_at": at,
                "payload": {"explicit_report": True, "latest_reported_status": status}}
    before = report("improving", "2026-10-22T13:16:30Z")  # before the rehab: never counts
    assert exposure_rows_with_observations([exposure], [before])[0]["event_json"]["response"]["during_response"] == "not_reported"
    # It can get worse as the day goes on, or settle again: the latest answer counts.
    worse_later = [before, report("improving", "2026-10-22T14:00:00Z"), report("worse", "2026-10-22T20:00:00Z")]
    assert exposure_rows_with_observations([exposure], worse_later)[0]["event_json"]["response"]["during_response"] == "worse"
    settled = [*worse_later, report("improving", "2026-10-22T21:00:00Z")]
    assert exposure_rows_with_observations([exposure], settled)[0]["event_json"]["response"]["during_response"] == "better"
