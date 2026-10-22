"""The injury log in the progression sheet: what the athlete did and answered."""
from api.services.today_service import injury_recent_log

BANK = [{"drills": [{"id": "ankle_heel_raise", "name": "Seated heel raise"}]}]


def exposure(eid, at, during="not_reported", next_day="not_yet_known"):
    return {"id": eid, "created_at": at, "event_json": {
        "exposure_id": eid, "drill_id": "ankle_heel_raise", "occurred_at": at[:10] + "T00:00:00Z",
        "provenance": {"recorded_at": at}, "response": {"during_response": during, "next_day_response": next_day}}}


def checkin(status, at):
    return {"event_type": "injury_checkin", "created_at": at,
            "payload": {"explicit_report": True, "latest_reported_status": status}}


def test_log_is_newest_first_with_plain_labels_and_marks_what_counts():
    exposures = [exposure("old", "2026-10-22T13:16:55Z", during="better", next_day="not_yet_known"),
                 exposure("new", "2026-10-24T10:00:00Z", during="same", next_day="better")]
    observations = [checkin("worse", "2026-10-22T13:16:08Z"), checkin("improving", "2026-10-22T13:16:30Z"),
                    {"event_type": "injury_checkin", "created_at": "2026-10-22T13:00:00Z",
                     "payload": {"explicit_report": False, "latest_reported_status": "ongoing"}}]
    decision = {"progression": {"next_transition": {"requirements": [
        {"kind": "no_unresolved_setback", "evidence_ids": ["new"]}]}}}
    log = injury_recent_log(exposures, observations, decision, BANK)
    assert [(e["kind"], e["date"]) for e in log] == [
        ("rehab", "2026-10-24"), ("rehab", "2026-10-22"), ("checkin", "2026-10-22"), ("checkin", "2026-10-22")]
    assert log[0] == {"at": "2026-10-24T10:00:00Z", "date": "2026-10-24", "kind": "rehab", "label": "Seated heel raise",
                      "felt": "Same", "next_day": "Better", "counts": True}
    assert log[1]["felt"] == "Better" and log[1]["next_day"] == "waiting" and log[1]["counts"] is False
    assert [e["label"] for e in log if e["kind"] == "checkin"] == ["Better", "Worse"]  # audit rows excluded


def test_without_a_next_check_counts_is_unknown_and_log_is_capped():
    exposures = [exposure(str(i), f"2026-10-{10 + i:02d}T10:00:00Z") for i in range(9)]
    log = injury_recent_log(exposures, [], {}, BANK)
    assert len(log) == 6 and all(e["counts"] is None for e in log)
    assert log[0]["felt"] == "not answered"
