"""Real authenticated Today routes for progression presentation regressions.

Uses the existing synthetic athlete/FakeStore harness; no production data.
Run as a module with an output filename to refresh the browser payloads.
"""
from tests.test_rehab_consumer_journey import PILOTS
from tests.test_rehab_experience import HEADERS, consumer, decision, view

import pytest


SCENARIOS = ("earned_load", "missing_permission", "pending_response", "worsening", "missing_equipment")


def scenario(monkeypatch, name):
    journey, client = consumer(monkeypatch, PILOTS[0])
    if name in {"missing_permission", "pending_response"}:
        journey.permission("gentle_recovery")
    if name == "earned_load":
        journey.reach_load()
    elif name == "pending_response":
        journey.complete()
        journey.advance()
        journey.permission("loading")
    elif name == "worsening":
        journey.report("worse")
    elif name == "missing_equipment":
        journey.reach_load()
        journey.store.intakes[journey.athlete][0]["equipment_access"] = []
    return journey, client, view(client)


def assert_scenario(name, body):
    current = decision(body)
    progression = current["progression"]
    assert body["live_prescription"]["session"]["blocks"]
    if name == "earned_load":
        assert current["stage"] == "load"
        assert "entry_basis" not in progression
        assert progression["evidence_ids"]
        assert progression["next_transition"]["to_stage"] == "dynamic"
        assert progression["next_transition"]["target_stage_live"] is False
    elif name == "worsening":
        assert current["stage"] == "calm"
        assert progression["reason_codes"] == ["episode_setback_loading_held"]
        # The hold stays visible: any next step is blocked by the current Worse.
        assert progression.get("next_transition", {}).get("status") in (None, "blocked")
    else:
        assert current["stage"] == "restore"
        next_step = progression["next_transition"]
        assert next_step["target_stage_live"] and next_step["status"] == "blocked"
        reason = {"missing_permission": "rehabilitation_loading_not_reported",
                  "pending_response": "next_day_response_not_yet_known",
                  "missing_equipment": "target_equipment_unavailable"}[name]
        assert reason in next_step["reason_codes"]
        assert "entry_basis" not in progression  # attempted entry is not successful entry


@pytest.mark.parametrize("name", SCENARIOS)
def test_today_preserves_entry_authority_and_actual_blocker(monkeypatch, name):
    _, _, body = scenario(monkeypatch, name)
    assert_scenario(name, body)


def test_better_alone_does_not_erase_setback_or_supply_loading_permission(monkeypatch):
    journey, client, body = scenario(monkeypatch, "worsening")
    assert_scenario("worsening", body)
    journey.permission("gentle_recovery")
    journey.report("improving")
    current = decision(view(client))
    # Better restores the RESTORE baseline; it never proves readiness for LOAD.
    assert current["stage"] == "restore"
    assert "rehabilitation_loading_not_reported" in current["progression"]["next_transition"]["reason_codes"]


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    fixtures = {}
    for name in SCENARIOS:
        with pytest.MonkeyPatch.context() as patch:
            journey, client, body = scenario(patch, name)
            assert_scenario(name, body)
            fixtures[name] = {"view": body, "profile": client.get("/api/me", headers=HEADERS).json()}
    Path(sys.argv[1]).write_text(json.dumps(fixtures, indent=2) + "\n", encoding="utf-8")
