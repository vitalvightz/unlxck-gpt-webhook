"""Cadence and daily reservations use frozen work, never ordinary training."""
from copy import deepcopy

import pytest

from api.contracts.injury_policy import resolve_injury_policy, reconcile_session_prescription
from api.contracts.rehab_schedule import schedule_rehab
from api.contracts.rehab_completion import completed_dose_from_session
from api.services.injury_episode_service import apply_episode_observations
from fightcamp.rehab_clinical import ClinicalPolicy, load_clinical_policies, policy_review_hash
from fightcamp.rehab_protocols import get_rehab_bank


def setup(region="ankle", stage="restore"):
    row = dict(id="i", episode_id="e", athlete_id="a", canonical_location=region, body_region=region,
               body_area="Left " + region, side="left", injury_type="sprain" if region == "ankle" else "strain",
               severity="mild", status="monitoring", latest_reported_status="improving", rehab_stage=stage,
               updated_at="2026-09-20T00:00:00Z")
    decision = resolve_injury_policy(row, policies=load_clinical_policies(), bank=get_rehab_bank(), phase="TAPER")
    assert decision["prescription"] and decision["activation"] == "live"
    return row, decision


def accepted(decision, day="2026-09-30", status="done", plan="old"):
    snapshot = reconcile_session_prescription(None, decisions=[decision], plan_id=plan, training_day=day)
    return dict(id="c", athlete_id="a", plan_id=plan, training_day=day, status=status, prescription_snapshot=snapshot)


@pytest.mark.parametrize("status", ["started", "done", "modified"])
def test_any_started_performed_or_stopped_work_reserves_episode_across_plans(status):
    row, decision = setup()
    completion = accepted(decision, status=status)
    result = schedule_rehab(row, decision, training_day="2026-09-30", completions=[completion])
    assert result["state"] == "already_completed"
    row["episode_id"] = "reopened"
    assert schedule_rehab(row, decision, training_day="2026-09-30", completions=[completion])["state"] == "due"


def test_alternate_days_and_missed_days_do_not_accumulate_volume():
    row, decision = setup()
    assert decision["prescription"]["minimum_gap_days"] == 2
    completion = accepted(decision)
    assert schedule_rehab(row, decision, training_day="2026-10-01", completions=[completion]) == {
        "state": "recovery_day", "reason": "Allow the configured recovery gap before repeating this routine.", "next_due_day": "2026-10-02"}
    for day in ["2026-10-02", "2026-10-08"]:
        assert schedule_rehab(row, decision, training_day=day, completions=[completion])["state"] == "due"
    assert accepted(decision, day="2026-10-08")["prescription_snapshot"]["session"]["blocks"][0]["dose"] == {}


def test_skipped_work_has_no_credit_and_daily_chest_remains_in_taper():
    row, decision = setup("chest", "calm")
    assert decision["stage"] == "calm" and decision["prescription"]["minimum_gap_days"] == 1
    completion = accepted(decision, status="skipped")
    assert schedule_rehab(row, decision, training_day="2026-09-30", completions=[completion])["state"] == "due"
    completion["status"] = "done"
    assert schedule_rehab(row, decision, training_day="2026-10-01", completions=[completion])["state"] == "due"
    dose = completed_dose_from_session({**completion, "rehab_performance": "done_as_shown"}, prescribed={})
    assert dose.completion_state == "performed_amount_unknown" and dose.reps is None and dose.sets is None


def test_known_hard_training_defers_loading_and_is_not_rehab_credit():
    row, decision = setup()
    training = {"blocks": [{"block_type": "strength", "mechanical_load_regions": ["ankle"], "load": "high"}]}
    assert schedule_rehab(row, decision, training_day="2026-10-01", training_session=training)["state"] == "deferred"
    normal = dict(athlete_id="a", training_day="2026-10-01", status="done", session_id="strength")
    assert schedule_rehab(row, decision, training_day="2026-10-01", completions=[normal])["state"] == "due"
    assert schedule_rehab(row, decision, training_day="2026-10-01", readiness_decision="pull_back")["state"] == "held"


def test_unknown_response_holds_loading_until_explicit_injury_improvement():
    row, decision = setup()
    event = dict(athlete_id="a", created_at="2026-09-30T12:00:00Z", event_json=dict(
        injury_id="i", injury_episode_id="e", occurred_at="2026-09-30T00:00:00Z", response={}))
    assert schedule_rehab(row, decision, training_day="2026-10-02", exposures=[event])["state"] == "held"
    row.update(latest_reported_status="improving", updated_at="2026-10-01T12:00:00Z")
    assert schedule_rehab(row, decision, training_day="2026-10-02", exposures=[event])["state"] == "held"
    row["latest_reported_at"] = "2026-10-01T12:00:00Z"
    assert schedule_rehab(row, decision, training_day="2026-10-02", exposures=[event])["state"] == "due"


@pytest.mark.parametrize("stamp", [None, "invalid", "2026-09-29T12:00:00Z", "2026-09-30T12:00:00Z"])
def test_unrelated_edits_and_non_later_reports_cannot_release_a_setback(stamp):
    row, _ = setup()
    row["updated_at"] = "2026-10-02T12:00:00Z"
    report = dict(athlete_id="a", injury_id="i", injury_episode_id="e", event_type="injury_checkin",
                  created_at=stamp, payload=dict(latest_reported_status="improving", explicit_report=True))
    audit = {**report, "created_at": row["updated_at"], "payload": {**report["payload"], "explicit_report": False}}
    event = dict(athlete_id="a", created_at="2026-09-30T12:00:00Z", event_json=dict(
        injury_id="i", injury_episode_id="e", occurred_at="2026-09-30T00:00:00Z", response={"next_day_response": "worse"}))
    row = apply_episode_observations(row, [report, audit])
    decision = resolve_injury_policy(row, policies=load_clinical_policies(), bank=get_rehab_bank(), exposures=[event])
    assert decision["stage"] == "calm"
    assert not decision["prescription"]["is_loading"]
    # A new explicit report can restore only baseline work; the old event stays fixed.
    report["created_at"] = "2026-10-01T12:00:00Z"
    row = apply_episode_observations(row, [report, audit])
    decision = resolve_injury_policy(row, policies=load_clinical_policies(), bank=get_rehab_bank(), exposures=[event])
    assert decision["stage"] == "restore" and decision["prescription"]["is_loading"]
    assert schedule_rehab(row, decision, training_day="2026-10-02", exposures=[event])["state"] == "due"
    assert event["event_json"]["response"]["next_day_response"] == "worse"


@pytest.mark.parametrize("changes", [{"athlete_id": "other"}, {"injury_id": "other"}, {"injury_episode_id": "old"},
                                    {"payload": {"latest_reported_status": "improving"}},
                                    {"event_type": "clinician_clearance_report", "payload": {"scopes": ["rehab"]}}])
def test_other_or_unproven_reports_cannot_refresh_improvement(changes):
    row, _ = setup()
    report = dict(athlete_id="a", injury_id="i", injury_episode_id="e", event_type="injury_checkin",
                  created_at="2026-10-01T12:00:00Z", payload=dict(latest_reported_status="improving", explicit_report=True))
    assert apply_episode_observations(row, [{**report, **changes}])["latest_reported_at"] is None


@pytest.mark.parametrize("fields", [
    {"load": {"method": "percentage", "value": 85, "unit": "percent", "ref": "1RM"}},
    {"load": {"method": "rpe", "value": 8, "unit": "RPE"}},
    {"load": {"method": "rir", "value": 2, "unit": "reps"}},
    {"load": {"method": "rir", "value": "2 RIR", "unit": "reps"}},
    {"load": {"method": "rir", "value": "2-3 RIR", "unit": "reps"}},
    {"effort": {"method": "RIR", "value": "1 RIR"}},
    {"effective_load": {"method": "rir", "value": "0 RIR"}},
    {"effort": {"method": "RPE", "value": 9}},
    {"effort": {"method": "RIR", "value": 1}},
    {"intensity": "high"},
    {"effective_load": "low", "load": {"method": "percentage", "value": 90, "unit": "percent", "ref": "1RM"}},
])
def test_structured_high_demand_defers_same_region_loading(fields):
    row, decision = setup()
    block = dict(block_type="strength", mechanical_load_regions=["ankle"], **fields)
    training = {"blocks": [block]}
    assert schedule_rehab(row, decision, training_day="2026-10-01", training_session=training)["state"] == "deferred"
    block["mechanical_load_regions"] = ["shoulder"]
    assert schedule_rehab(row, decision, training_day="2026-10-01", training_session=training)["state"] == "due"


@pytest.mark.parametrize("load", [
    {"method": "percentage", "value": 60, "unit": "percent", "ref": "1RM"},
    {"method": "absolute", "value": 40, "unit": "kg"},
    {"method": "rpe", "value": 4, "unit": "RPE"},
    {"method": "rir", "value": "5 RIR", "unit": "reps"},
    {"method": "rir", "value": "unspecified", "unit": "reps"},
    {"method": "other", "value": 0, "unit": "unknown"},
])
def test_structured_load_does_not_hide_hard_session_or_crash_when_unknown(load):
    row, decision = setup()
    training = {"blocks": [dict(block_type="strength", mechanical_load_regions=["ankle"], load=load)]}
    assert schedule_rehab(row, decision, training_day="2026-10-01", training_session=training)["state"] == "due"
    training["effective_load"] = "hard"
    assert schedule_rehab(row, decision, training_day="2026-10-01", training_session=training)["state"] == "deferred"


def test_accepted_prescription_keeps_its_previous_gap_after_policy_change():
    row, decision = setup()
    previous = accepted(decision)
    changed = deepcopy(decision)
    changed["prescription"]["minimum_gap_days"] = 1
    assert schedule_rehab(row, changed, training_day="2026-10-01", completions=[previous])["state"] == "recovery_day"


def test_resuming_a_frozen_alternative_does_not_reselect_the_primary_routine(monkeypatch):
    # Preserve coverage of the legacy single-drill policy's alternative path.
    policy = next(p for p in load_clinical_policies() if p.policy_id == "ankle_sprain")
    draft = ClinicalPolicy.model_validate({**policy.model_dump(), "version": 3,
        "status": "draft", "activation": "shadow", "content_hash": None, "stage_bundles": {}})
    legacy = ClinicalPolicy.model_validate({**draft.model_dump(), "status": "active", "activation": "live",
        "content_hash": policy_review_hash(draft)})
    monkeypatch.setattr(__name__ + ".load_clinical_policies", lambda: (legacy,))
    row, primary = setup()
    balance = resolve_injury_policy(row, policies=load_clinical_policies(), bank=get_rehab_bank(),
        excluded_drill_ids=[primary["prescription"]["drill_id"]])
    assert balance["prescription"]["drill_id"] == "ankle_sprain_supported_balance"
    frozen = reconcile_session_prescription(None, decisions=[balance], plan_id="plan", training_day="2026-09-30")
    primary["schedule"] = {"state": "already_completed"}
    resumed = reconcile_session_prescription(None, decisions=[primary], plan_id="plan", training_day="2026-09-30", frozen=frozen)
    assert not resumed["safety_hold"] and resumed["session"] == frozen["session"]
    primary["loading_hold"] = True
    assert reconcile_session_prescription(None, decisions=[primary], plan_id="plan", training_day="2026-09-30", frozen=frozen)["safety_hold"]
