from fightcamp.stage2_payload_open_ongoing import _uses_open_ongoing_payload
from fightcamp.stage2_payload_late_fight import _uses_late_fight_stage2_payload


def test_fight_date_route_unchanged_not_open_ongoing():
    athlete = {"fight_date": "2026-06-01", "days_until_fight": 17}
    assert _uses_open_ongoing_payload(athlete) is False


def test_late_fight_route_starts_at_d13_not_open_ongoing():
    # D-21 now uses the normal camp planner (not the late-fight route); the
    # late-fight/compressed route begins at D-13. Neither is open-ongoing.
    assert _uses_late_fight_stage2_payload(21) is False
    assert _uses_late_fight_stage2_payload(13) is True
    assert _uses_open_ongoing_payload({"days_until_fight": 21}) is False
    assert _uses_open_ongoing_payload({"days_until_fight": 13}) is False


def test_fight_day_route_unchanged():
    assert _uses_late_fight_stage2_payload(0) is True
    assert _uses_open_ongoing_payload({"days_until_fight": 0}) is False
