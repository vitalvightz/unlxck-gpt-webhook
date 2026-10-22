"""The injury rules as one matrix, run through the real Today pipeline.

1. Rehab depends only on the injury: go, modify and pull back give identical rehab.
   Stop and not-checked-in pause it.
2. The latest injury answer wins: Better after Worse clears the setback.
3. A reported clearance stays until the athlete changes it; Worse does not erase it.
4. Training is held by the verdict or by an uncleared injury restriction, and the
   hold names which one.
(5. One status line per injury card is covered by the web component tests.)
"""
from uuid import uuid4

import pytest

from api.contracts.injury_policy import reconcile_session_prescription, resolve_injury_policy
from api.contracts.rehab_schedule import schedule_rehab
from api.services.injury_episode_service import apply_episode_observations
from api.services.today_service import apply_readiness_hold, session_hold
from fightcamp.rehab_clinical import load_clinical_policies
from fightcamp.rehab_protocols import get_rehab_bank

DAY = "2026-10-22"
PLAN = str(uuid4())
POLICIES = load_clinical_policies()
BANK = get_rehab_bank()
LIVE = sorted({(p.region, p.injury_type, tuple(p.live_stages)) for p in POLICIES
               if p.activation == "live" and p.status == "active"})
TRAINING_VERDICTS = ["green", "modify", "pull_back"]
PAUSING_VERDICTS = ["stop", "not_checked_in"]


def injury(region, kind, stage="calm", **changes):
    row = dict(id=str(uuid4()), episode_id=str(uuid4()), athlete_id=str(uuid4()),
               body_region=region, canonical_location=region, body_area=f"Left {region}",
               description=f"{region} {kind}", side="left", injury_type=kind, severity="mild",
               status="open", created_at="2026-10-01T00:00:00Z", updated_at="2026-10-01T00:00:00Z")
    if stage == "restore":
        row.update(status="monitoring", latest_reported_status="improving", rehab_stage="restore")
    return {**row, **changes}


def event(row, kind, payload, at):
    return {"id": str(uuid4()), "athlete_id": row["athlete_id"], "injury_id": row["id"],
            "injury_episode_id": row["episode_id"], "event_type": kind, "payload": payload, "created_at": at}


def checkin(row, status, at):
    return event(row, "injury_checkin", {"explicit_report": True, "latest_reported_status": status}, at)


def clearance(row, scopes, at="2026-10-20T10:00:00Z"):
    return event(row, "clinician_clearance_report", {"scopes": sorted(scopes), "source": "athlete_reported",
        "rehabilitation_permission": {"level": "gentle_recovery", "schema_version": 1}}, at)


def decide(row, verdict, session=None):
    decision = resolve_injury_policy(row, policies=POLICIES, bank=BANK, readiness_decision=verdict)
    if decision.get("prescription"):
        decision["schedule"] = schedule_rehab(row, decision, training_day=DAY, readiness_decision=verdict,
                                              training_session=session)
    return decision


def today(row, verdict, session):
    """Policy -> schedule -> reconcile -> verdict -> the one session-hold answer."""
    decision = decide(row, verdict, session)
    live = reconcile_session_prescription(session, decisions=[decision], plan_id=PLAN, training_day=DAY, injuries=[row])
    readiness_held = apply_readiness_hold(live, verdict) if live else False
    return decision, live, session_hold(verdict, live, readiness_held=readiness_held)


# Rule 1 ----------------------------------------------------------------------

@pytest.mark.parametrize("region,kind,stages", LIVE, ids=[f"{r}-{k}" for r, k, _ in LIVE])
def test_rule1_rehab_is_identical_on_go_modify_and_pull_back(region, kind, stages):
    for stage in [s for s in ("calm", "restore") if s in stages]:
        row = injury(region, kind, stage)
        decisions = {verdict: decide(row, verdict) for verdict in TRAINING_VERDICTS}
        go = decisions["green"]
        for verdict, decision in decisions.items():
            assert decision["stage"] == go["stage"], (stage, verdict)
            assert decision["outcome"] == go["outcome"], (stage, verdict)
            assert decision["prescription"] == go["prescription"], (stage, verdict)
            assert decision.get("schedule") == go.get("schedule"), (stage, verdict)
        if go.get("prescription"):
            for verdict in PAUSING_VERDICTS:
                assert decide(row, verdict)["schedule"]["state"] == "held", (stage, verdict)


# Rules 2 and 3 ---------------------------------------------------------------

RESTORE_LIVE = [(r, k) for r, k, stages in LIVE if "restore" in stages]


@pytest.mark.parametrize("region,kind", RESTORE_LIVE, ids=[f"{r}-{k}" for r, k in RESTORE_LIVE])
def test_rule2_latest_injury_answer_wins(region, kind):
    base = injury(region, kind, "restore")
    worse_then_better = [checkin(base, "worse", "2026-10-21T10:00:00Z"), checkin(base, "improving", "2026-10-22T09:00:00Z")]
    better_then_worse = [checkin(base, "improving", "2026-10-21T10:00:00Z"), checkin(base, "worse", "2026-10-22T09:00:00Z")]
    cleared = apply_episode_observations({**base, "latest_reported_status": "improving"}, worse_then_better)
    held = apply_episode_observations({**base, "latest_reported_status": "worse"}, better_then_worse)
    for verdict in TRAINING_VERDICTS:
        recovered = decide(cleared, verdict)
        assert recovered["stage"] != "calm" or "episode_setback_loading_held" not in recovered.get("progression", {}).get("reason_codes", [])
        assert decide(held, verdict)["stage"] == "calm"


@pytest.mark.parametrize("scopes", [["rehab"], ["rehab", "training"], ["contact", "rehab", "training"]])
@pytest.mark.parametrize("region,kind", RESTORE_LIVE[:12], ids=[f"{r}-{k}" for r, k in RESTORE_LIVE[:12]])
def test_rule3_clearance_survives_a_later_worse(region, kind, scopes):
    base = injury(region, kind, "restore")
    events = [clearance(base, scopes), checkin(base, "worse", "2026-10-21T10:00:00Z")]
    row = apply_episode_observations({**base, "latest_reported_status": "worse"}, events)
    assert row["clinician_clearance"]["scopes"] == sorted(scopes)
    assert decide(row, "green")["stage"] == "calm"  # Worse still pauses rehab to CALM


# Rule 4 ----------------------------------------------------------------------

def block(title, block_type, regions, contact):
    return {"block_id": title, "block_type": block_type, "title": title, "mechanical_load_regions": regions,
            "tags": [], "contact_level": contact, "load": "high" if block_type == "strength" else None}


SESSIONS = {
    "hard_sparring": {"session_id": "camp", "session_type": "sparring", "title": "Hard sparring",
                      "blocks": [block("Hard sparring", "sparring", ["ankle"], "full")]},
    "technical_sparring": {"session_id": "camp", "session_type": "sparring", "title": "Technical sparring",
                           "blocks": [block("Technical sparring", "sparring", ["ankle"], "controlled")]},
    "ankle_strength": {"session_id": "camp", "session_type": "strength", "title": "Lower body strength",
                       "blocks": [block("Heavy calf raises", "strength", ["ankle"], "none")]},
    "upper_strength": {"session_id": "camp", "session_type": "strength", "title": "Upper body strength",
                       "blocks": [block("Bench press", "strength", ["shoulder"], "none")]},
}
CLEARANCES = {"none": None, "rehab": ["rehab"], "training": ["rehab", "training"], "contact": ["contact", "rehab", "training"]}


def ankle(clearance_level):
    base = injury("ankle", "sprain", "restore", description="sprain [ankle_scope:uncomplicated_lateral]")
    scopes = CLEARANCES[clearance_level]
    return apply_episode_observations(base, [clearance(base, scopes)]) if scopes else base


@pytest.mark.parametrize("session_name", sorted(SESSIONS))
@pytest.mark.parametrize("clearance_level", sorted(CLEARANCES))
def test_rule4_training_hold_names_its_cause(session_name, clearance_level):
    row, session = ankle(clearance_level), SESSIONS[session_name]
    _, go_live, go = today(row, "green", session)
    # Modify reduces volume but never changes what an injury allows.
    assert today(row, "modify", session)[2] == go
    # On a go day only the injury can hold training: blocked outright, or swapped for rehab.
    injury_holds = go["held"] or bool(go_live and go_live.get("training_hold_reason"))
    if go["held"]:
        assert go["source"] == "injury" and "pull-back" not in (go["reason"] or "")
    if injury_holds:
        assert "pull-back" not in (go_live.get("training_hold_reason") or "")

    _, live, pull_back = today(row, "pull_back", session)
    offered_rehab = bool(live and live["session"].get("session_type") == "rehab" and not live.get("safety_hold"))
    assert pull_back["held"] is not offered_rehab
    if not injury_holds:
        # Nothing about the injury blocks this session, so pull back must not blame it.
        assert "injury restrictions" not in (pull_back["reason"] or "")
        assert "injury restrictions" not in ((live or {}).get("training_hold_reason") or "")
        if pull_back["held"]:
            assert pull_back["source"] == "readiness" and "pull-back" in pull_back["reason"]

    assert today(row, "stop", session)[2]["held"]


def test_rule4_contact_clearance_releases_hard_sparring():
    """The original bug: cleared for contact, yet told training conflicts with injury restrictions."""
    row = ankle("contact")
    assert not today(row, "green", SESSIONS["hard_sparring"])[2]["held"]
    _, live, hold = today(row, "pull_back", SESSIONS["hard_sparring"])
    assert "injury restrictions" not in (hold["reason"] or "") + ((live or {}).get("training_hold_reason") or "")


def test_rule1_pull_back_still_offers_due_rehab_end_to_end():
    row = ankle("contact")
    decision, live, hold = today(row, "pull_back", SESSIONS["upper_strength"])
    if decision.get("schedule", {}).get("state") == "due":
        assert live["session"]["session_type"] == "rehab" and not hold["held"]
        assert any(b.get("block_type") == "rehab" for b in live["session"]["blocks"])
