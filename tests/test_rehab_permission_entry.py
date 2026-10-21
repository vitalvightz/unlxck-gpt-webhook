"""Reported advice authorises a starter; it never certifies recovery evidence."""
from copy import deepcopy
from datetime import timedelta

import pytest
from pydantic import ValidationError

from fightcamp.rehab_pathways import PathwayTransition, TransitionOverride
from tests.test_rehab_consumer_journey import Journey, PILOTS


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
@pytest.mark.parametrize("status", ["improving", "ongoing"])
def test_reported_advice_opens_exact_starter_without_work_or_good_day_counter(monkeypatch, pilot, status):
    j = Journey(monkeypatch, pilot, initial_status=status, edit_subtype=False)
    assert not j.store.rehab_exposures and not j.store.session_completions.get(j.athlete)
    d = j.decision()
    assert d["stage"] == "load", d["progression"]
    entry = d["progression"]["entry_decision"]
    assert entry["status"] == "met"
    assert d["progression"]["entry_basis"] == "reported_clinician_permission"
    assert d["progression"]["authority_event_id"] in j.store.injury_episode_events
    for r in entry["requirements"]:
        if r["kind"] in {"completed_reviewed_exposure", "during_session_response", "next_day_response"}:
            assert r["status"] == "not_applicable" and r["evidence_ids"] == []
    expected = next(p.drill_id for p in j.policy.prescriptions if p.stage == "load")
    assert j.view().live_prescription["session"]["blocks"][0]["rehab_drill_id"] == expected
    assert d["progression"]["evidence_ids"] == []


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
@pytest.mark.parametrize("permission", ["gentle_recovery", "not_cleared", "sport_specific"])
def test_advice_levels_never_create_unapproved_stages(monkeypatch, pilot, permission):
    j = Journey(monkeypatch, pilot)
    j.permission(permission)
    d = j.decision()
    assert (d["stage"] == "load") == (permission == "sport_specific")
    assert d["stage"] not in {"dynamic", "return"}
    assert j.view().effective_clinician_clearance["level"] == "rehab_only"


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
@pytest.mark.parametrize("response", ["not_yet_known", "not_sure", "worse"])
def test_known_pending_uncertain_or_adverse_response_cannot_be_bypassed_by_new_advice(monkeypatch, pilot, response):
    j = Journey(monkeypatch, pilot)
    j.complete()
    j.advance()
    if response != "not_yet_known":
        j.followup(response)
    originals = deepcopy(j.store.rehab_exposures)
    j.permission("loading")
    d = j.decision()
    assert d["stage"] != "load", d["progression"]
    assert j.store.rehab_exposures == originals


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_generation_uses_permission_entry_without_exposure_history(monkeypatch, pilot):
    from api.services.rehab_stage_snapshot import resolve_open_injury_rehab_context
    from fightcamp.rehab_protocols import _episode_context, _reviewed_episode_option
    from fightcamp.input_parsing import _apply_rehab_generation_context, _coerce_rehab_generation_context
    j = Journey(monkeypatch, pilot, initial_status="ongoing", edit_subtype=False)
    raw = next(iter(resolve_open_injury_rehab_context(j.store, j.athlete).values()))
    entry = dict(injury_type=pilot[2], severity=pilot[4], laterality="left")
    _apply_rehab_generation_context(entry, _coerce_rehab_generation_context({"rehab_generation_context": raw}))
    generated = _reviewed_episode_option(_episode_context(entry), j.policy.region, "GPP")
    assert generated["decision"]["stage"] == j.decision()["stage"] == "load"
    assert generated["drill"]["id"] == j.decision()["prescription"]["drill_id"]


@pytest.mark.parametrize("mutation", ["missing", "future", "wrong_episode", "equipment", "scope", "medical"])
def test_permission_entry_fails_closed_without_current_applicable_authority(monkeypatch, mutation):
    j = Journey(monkeypatch, PILOTS[0])
    event = next(e for e in j.store.injury_episode_events.values() if e["event_type"] == "clinician_clearance_report")
    if mutation == "missing":
        del j.store.injury_episode_events[event["id"]]
    elif mutation == "future":
        event["created_at"] = (j.now + timedelta(days=1)).isoformat()
    elif mutation == "wrong_episode":
        event["injury_episode_id"] = "00000000-0000-0000-0000-000000000001"
    elif mutation == "equipment":
        j.store.intakes[j.athlete][0]["equipment_access"] = []
    elif mutation == "scope":
        j.report("ongoing", description="tendonitis [achilles_site:unknown]")
    else:
        j.store.injury_flags[j.athlete][0]["medical_hold"] = True
    assert j.decision()["stage"] != "load"


def test_entry_rules_are_declarative_conservative_and_cannot_open_higher_stages():
    from fightcamp.rehab_clinical import load_clinical_policies
    policies = load_clinical_policies()
    opted_in = [p for p in policies if any(t.entry_mode == "reported_clinician_starter" for t in p.transitions)]
    assert {p.policy_id for p in opted_in} == {p[0] for p in PILOTS}
    for p in opted_in:
        t = next(t for t in p.transitions if t.entry_mode == "reported_clinician_starter")
        assert t.setback_resolution == "improvement_then_reviewed_restore"
        for field, value in [("entry_mode", "guess_safe"), ("setback_resolution", "any_better")]:
            with pytest.raises(ValidationError):
                TransitionOverride.model_validate({"reason": "Invalid", field: value})
        raw = t.model_dump()
        with pytest.raises(ValidationError):
            PathwayTransition.model_validate({**raw, "from_stage": "load", "to_stage": "dynamic"})
        raw.pop("entry_mode")
        raw.pop("setback_resolution")
        historical = PathwayTransition.model_validate(raw)
        assert historical.entry_mode == "observed_rehab" and historical.setback_resolution == "hold"
        assert historical.model_dump() == raw  # no historical hash/shape drift


def test_policy_revision_changes_entry_semantics_only():
    import json
    from pathlib import Path
    from fightcamp.rehab_clinical import content_hash
    revision = json.loads(Path("tools/rehab_permission_entry_revision.json").read_text())
    current = json.loads(Path("data/rehab_pathways.json").read_text())
    for p in current["profiles"]:
        if p["policy_id"] not in revision["previous_profiles"]:
            continue
        before = revision["previous_profiles"][p["policy_id"]]
        assert content_hash(p) == revision["current_profile_sha256"][p["policy_id"]]
        assert p["version"] == before["version"] + 1
        restored = deepcopy(p)
        restored.update(version=before["version"], content_hash=before["content_hash"])
        override = restored["transition_overrides"]["restore->load"]
        override.pop("entry_mode")
        override.pop("setback_resolution")
        assert restored == before  # all clinical limits and content unchanged


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_saved_starter_rechecks_pending_work_and_side_without_rewriting_snapshot(monkeypatch, pilot):
    from api.services.clinical_review_freeze import frozen_review_hold
    j = Journey(monkeypatch, pilot)
    saved = deepcopy(j.view().live_prescription)
    original = deepcopy(saved)
    assert not frozen_review_hold(j.store, j.athlete, saved, work_state="unstarted", as_of=j.now)
    j.store.injury_flags[j.athlete][0]["side"] = "right"
    assert frozen_review_hold(j.store, j.athlete, saved, work_state="unstarted", as_of=j.now)
    assert not frozen_review_hold(j.store, j.athlete, saved, work_state="started", as_of=j.now)
    assert not frozen_review_hold(j.store, j.athlete, saved, work_state="completed", as_of=j.now)
    j.store.injury_flags[j.athlete][0]["side"] = "left"
    j.complete()
    j.advance()
    assert frozen_review_hold(j.store, j.athlete, saved, work_state="unstarted", as_of=j.now)
    assert saved == original
