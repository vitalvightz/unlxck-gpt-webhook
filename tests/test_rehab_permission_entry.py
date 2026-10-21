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


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
@pytest.mark.parametrize("restriction", ["unknown_location", "unsupported_location", "medical", "restriction", "severity", "withdrawn"])
def test_fresh_permission_preserves_injury_eligibility_and_visible_holds(monkeypatch, pilot, restriction):
    j = Journey(monkeypatch, pilot, initial_status="ongoing", edit_subtype=False)
    load_id = next(p.drill_id for p in j.policy.prescriptions if p.stage == "load")
    assert j.decision()["stage"] == "load"
    if restriction in {"unknown_location", "unsupported_location"}:
        marker, _ = pilot[3].split(":")
        location = "unknown" if restriction == "unknown_location" else (
            "insertional" if pilot[0] == "achilles_tendonitis" else "other")
        j.report("ongoing", description=f"{pilot[2]} [{marker}:{location}]")
    elif restriction in {"medical", "restriction"}:
        j.store.injury_flags[j.athlete][0][f"{restriction}_hold"] = True
    elif restriction == "severity":
        j.report("ongoing", severity="severe")
    else:
        j.permission("not_cleared")
    current = j.view()
    decision = next(i for i in current.open_injuries if i["id"] == j.injury["id"])["rehab_decision"]
    assert decision["stage"] != "load", decision
    assert not current.live_prescription or all(
        b.get("rehab_drill_id") != load_id for b in current.live_prescription["session"]["blocks"])
    assert not j.store.rehab_exposures and not j.store.session_completions.get(j.athlete)


@pytest.mark.parametrize("pilot,area,kind,held", [
    (PILOTS[2], "Right calf", "strain", True),
    (PILOTS[2], "Right wrist", "sprain", False),
    (PILOTS[3], "Right wrist", "sprain", True),
    (PILOTS[3], "Right shin", "contusion", False),
], ids=["ankle-relevant", "ankle-unrelated", "shoulder-relevant", "shoulder-unrelated"])
def test_fresh_permission_cannot_override_relevant_second_injury(monkeypatch, pilot, area, kind, held):
    from api.services import today_service
    from api.services.rehab_stage_snapshot import resolve_open_injury_rehab_context
    from fightcamp.rehab_protocols import _episode_context, _reviewed_episode_option
    from fightcamp.input_parsing import _apply_rehab_generation_context, _coerce_rehab_generation_context
    j = Journey(monkeypatch, pilot, initial_status="ongoing", edit_subtype=False)
    load_id = next(p.drill_id for p in j.policy.prescriptions if p.stage == "load")
    assert j.decision()["stage"] == "load"
    advice = deepcopy(j.store.injury_episode_events)
    today_service.submit_today_injury_checkin(j.store, athlete_id=j.athlete, athlete_timezone="UTC", now=j.now,
        payload={"injuries": [{"body_area": area, "description": kind, "severity": "mild", "status": "ongoing"}]})
    current = j.view()
    primary = next(i for i in current.open_injuries if i["id"] == j.injury["id"])
    decision = primary["rehab_decision"]
    assert decision["stage"] == ("restore" if held else "load"), decision
    blocks = (current.live_prescription or {}).get("session", {}).get("blocks", [])
    assert any(b.get("rehab_drill_id") == load_id for b in blocks) is (not held)
    raw = next(c for c in resolve_open_injury_rehab_context(j.store, j.athlete).values()
               if c["injury_id"] == j.injury["id"])
    entry = dict(injury_type=pilot[2], severity=pilot[4], laterality="left")
    _apply_rehab_generation_context(entry, _coerce_rehab_generation_context({"rehab_generation_context": raw}))
    generated = _reviewed_episode_option(_episode_context(entry), j.policy.region, "GPP")
    assert generated["decision"]["stage"] == decision["stage"]
    assert generated["drill"]["id"] == decision["prescription"]["drill_id"]
    assert current.effective_clinician_clearance["level"] == "rehab_only"
    assert primary["clinician_clearance"]["rehabilitation_permission"]["level"] == "loading"
    assert all(j.store.injury_episode_events[key] == event for key, event in advice.items())
    assert not j.store.rehab_exposures and not j.store.session_completions.get(j.athlete)


def test_shared_entry_uses_publication_not_per_pathway_flags():
    from api.contracts.rehab_progression import _permission_entry
    from fightcamp.rehab_clinical import load_clinical_policies
    policies = load_clinical_policies()
    eligible = [p for p in policies if any(_permission_entry(t, p) for t in p.transitions)]
    assert {p.policy_id for p in eligible} == {p[0] for p in PILOTS}
    for p in policies:
        for t in p.transitions:
            assert "entry_mode" not in t.model_dump() and "setback_resolution" not in t.model_dump()
    with pytest.raises(ValidationError):
        TransitionOverride.model_validate({"reason": "No extra workflow", "entry_mode": "reported_clinician_starter"})
    with pytest.raises(ValidationError):
        PathwayTransition.model_validate({"from_stage": "load", "to_stage": "return"})


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
        for prescription in restored["prescriptions"]:
            if prescription["stage"] == "load":
                assert prescription.pop("resistance") == {"mode": "bodyweight", "kg": None}
                assert prescription.pop("range_choice")
                assert prescription.pop("mandatory_restrictions")
        assert restored == before  # published exercises, dose and clinical conditions unchanged


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_another_normally_published_load_exercise_needs_no_code_registry_or_entry_flag(monkeypatch, pilot):
    from api.services import today_service
    from api.services.clinical_review_freeze import frozen_review_hold
    from fightcamp.rehab_clinical import ClinicalPolicy, content_hash, load_clinical_policies, policy_review_hash
    from fightcamp.rehab_protocols import get_rehab_bank
    j = Journey(monkeypatch, pilot)
    original = next(p for p in j.policy.prescriptions if p.stage == "load")
    bank = deepcopy(get_rehab_bank())
    group = next(g for g in bank if any(d["id"] == original.drill_id for d in g["drills"]))
    drill = deepcopy(next(d for d in group["drills"] if d["id"] == original.drill_id))
    drill.update(id=original.drill_id + "_publication_regression", name="Test-only published alternative")
    group["drills"].append(drill)
    publication = original.model_copy(update={"drill_id": drill["id"], "bank_hash": content_hash(drill),
        "priority": 100, "required_rehabilitation_level": None})
    # Normal publication: bank identity + approved prescription content. No
    # entry flag, profile-ID registration, Python option or stage override.
    draft = ClinicalPolicy.model_validate({**j.policy.model_dump(), "status": "draft", "activation": "shadow",
        "content_hash": None, "prescriptions": [*j.policy.prescriptions, publication]})
    published = ClinicalPolicy.model_validate({**draft.model_dump(), "status": "active", "activation": "live",
        "content_hash": policy_review_hash(draft)})
    policies = tuple(published if p.policy_id == j.policy.policy_id else p for p in load_clinical_policies())
    monkeypatch.setattr(today_service, "load_clinical_policies", lambda: policies)
    monkeypatch.setattr(today_service, "get_rehab_bank", lambda: bank)
    live = j.view().live_prescription
    block = live["session"]["blocks"][0]
    assert j.decision()["stage"] == "load" and block["rehab_drill_id"] == drill["id"]
    assert block["resistance"] == publication.resistance
    assert not frozen_review_hold(j.store, j.athlete, live, work_state="unstarted", as_of=j.now,
        policies=policies, bank=bank)


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
