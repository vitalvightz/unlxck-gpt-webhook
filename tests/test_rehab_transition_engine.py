"""The one stage progression path: baseline ladder + declared pathway transitions.

All policies here are synthetic, test-only compositions of the real catalog's
families and safety baseline. No shipped profile declares a clinical criterion.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from api.contracts.injury_policy import resolve_injury_policy
from api.contracts.rehab_evidence import IGNORED_ATHLETE_MISMATCH, IGNORED_EPISODE_MISMATCH, IGNORED_SIDE_MISMATCH
from api.contracts.rehab_exposure import RehabExposureEvent
from api.contracts.rehab_progression import (
    CAPTURED_FUNCTIONAL_CHECKPOINTS, evaluate_transition, resolve_reviewed_progression,
)
from fightcamp.rehab_clinical import ClinicalPolicy, compose_policy, content_hash, load_pathway_catalog, policy_review_hash

ATHLETE = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
INJURY = "11111111-1111-1111-1111-111111111111"
EPISODE = "33333333-3333-3333-3333-333333333333"
START = datetime(2026, 9, 1, 10, tzinfo=timezone.utc)
SOURCE = "test-only://synthetic-source"
RESTORE_DRILL = {"id": "ankle_test_restore_control", "name": "Test restore control", "rehab_stage": "restore",
                 "target_regions": ["ankle"], "target_tissues": ["test tissue"], "laterality_applicability": "side_specific",
                 "allowed_severities": ["low", "moderate"], "function": "control", "equipment": [],
                 "load": "low", "impact": "none", "velocity": "low"}
LOAD_DRILL = {**RESTORE_DRILL, "id": "ankle_test_load_strength", "name": "Test load strength", "rehab_stage": "load",
              "function": "tendon_loading", "load": "moderate"}
BANK = [{"location": "ankle", "type": "sprain", "phases": ["GPP"], "drills": [RESTORE_DRILL, LOAD_DRILL]}]


def clinical(rid="test_clinical_next_day", kind="next_day_response", **kw):
    base = dict(requirement_id=rid, kind=kind, basis="clinical", description="Synthetic sourced criterion.", sources=[SOURCE])
    if kind in {"next_day_response", "during_session_response"}:
        base["allowed_responses"] = ["better", "same"]
    return {**base, **kw}


def policy(*, add=(clinical(),), remove=(), live=("calm", "restore", "load"), closed=None, load_prescription=True):
    prescriptions = [dict(drill_id=RESTORE_DRILL["id"], bank_hash=content_hash(RESTORE_DRILL), stage="restore",
                          instructions="Synthetic.", allowed_severities=["low", "moderate"], stop_when=["Stop."],
                          frequency="daily", sources=[SOURCE])]
    if load_prescription:
        prescriptions.append(dict(drill_id=LOAD_DRILL["id"], bank_hash=content_hash(LOAD_DRILL), stage="load",
                                  instructions="Synthetic load.", allowed_severities=["low", "moderate"],
                                  stop_when=["Stop."], frequency="daily", sources=[SOURCE]))
    override = dict(reason="Synthetic test criterion.", add_requirements=list(add), remove_requirement_ids=list(remove))
    if closed:
        override["closed_reason"] = closed
    profile = dict(policy_id="test_ankle_sprain", version=1, pathway_family="ligament_sprain_or_instability",
                   region="ankle", injury_type="sprain", evidence_sources=[SOURCE], prescriptions=prescriptions,
                   blocked_regions=["ankle"], live_stages=list(live),
                   transition_overrides={"restore->load": override})
    draft = compose_policy(load_pathway_catalog(), profile)
    return ClinicalPolicy.model_validate({**draft.model_dump(), "status": "active", "activation": "live",
                                          "content_hash": policy_review_hash(draft)})


def injury(**changes):
    row = dict(id=INJURY, episode_id=EPISODE, athlete_id=ATHLETE, body_region="ankle", canonical_location="ankle",
               body_area="Left ankle", description="Left ankle sprain", side="left", injury_type="sprain",
               severity="mild", status="monitoring", latest_reported_status="improving", rehab_stage="restore",
               created_at="2026-08-30T00:00:00Z", updated_at="2026-08-30T00:00:00Z")
    row.update(changes)
    return row


def event(number=1, *, drill=RESTORE_DRILL, stage="restore", policy_id="test_ankle_sprain", athlete=ATHLETE,
          episode=EPISODE, side="left", group=True, load="low", completion="performed_amount_unknown",
          during="same", next_day="same", stopped=False, prescribed=None, bank_hash=None):
    completed = {"reps": 10, "completion_state": "quantified"} if completion == "quantified" else {"completion_state": completion}
    payload = {
        "exposure_id": str(UUID(int=100 + number)),
        "response_group_id": str(UUID(int=900 + number)) if group else None,
        "injury_id": INJURY, "injury_episode_id": episode, "drill_id": drill["id"], "body_region": "ankle", "side": side,
        "demand": {"target_regions": ["ankle"], "load": load, "impact": "none", "velocity": "low"},
        "dose_completed": completed, "occurred_at": (START + timedelta(days=number)).isoformat(),
        "response": {"during_response": during, "next_day_response": next_day, "stopped_due_to_symptoms": stopped,
                     "worsening_reported": False},
        "provenance": {"source": "athlete_logged_rehab", "recorded_at": (START + timedelta(days=number)).isoformat(),
                       "policy_id": policy_id, "rehab_stage": stage,
                       "bank_hash": bank_hash or content_hash(drill)},
    }
    if prescribed:
        payload["prescribed_dose"] = prescribed
    parsed = RehabExposureEvent.model_validate(payload)
    return {"id": str(parsed.exposure_id), "athlete_id": athlete, "created_at": payload["occurred_at"],
            "event_json": parsed.model_dump(mode="json")}


def progress(rows=(), current=None, **kwargs):
    current = current or policy()
    return resolve_reviewed_progression(injury(**kwargs.pop("changes", {})), base_stage=kwargs.pop("base", "restore"),
                                        policy=current, exposures=list(rows), **kwargs)


def requirement(result, rid):
    return next(r for r in result["next_transition"]["requirements"] if r["requirement_id"] == rid)


def test_met_transition_promotes_one_rung_with_evidence():
    result = progress([event()])
    assert result["stage"] == "load"
    assert result["reason_codes"] == ["transition_met:restore->load"]
    assert str(UUID(int=101)) in result["evidence_ids"]
    # The next rung has no family or profile criteria, so it never promotes.
    assert result["next_transition"]["from_stage"] == "load"
    assert result["next_transition"]["status"] == "blocked"


def test_no_evidence_blocks_and_reports_what_is_missing():
    result = progress()
    assert result["stage"] == "restore" and result["reason_codes"] == ["baseline_only_v1"]
    nxt = result["next_transition"]
    assert nxt["status"] == "blocked" and nxt["to_stage"] == "load"
    assert "no_reviewed_stage_exposure" in nxt["reason_codes"]


def test_a_met_transition_into_an_inactive_stage_does_not_promote():
    result = progress([event()], current=policy(live=("calm", "restore")))
    assert result["stage"] == "restore"
    assert result["next_transition"]["status"] == "met"
    assert result["next_transition"]["reason_codes"] == ["target_stage_not_activated"]


def test_safety_and_data_requirements_alone_never_promote():
    result = progress([event()], current=policy(add=(), live=("calm", "restore")))
    assert result["stage"] == "restore"
    assert result["next_transition"]["reason_codes"] == ["no_clinical_criteria_declared"]
    with pytest.raises(ValueError, match="cannot be live without an open transition"):
        policy(add=())


def test_uncaptured_functional_checkpoint_is_an_explicit_missing_input():
    assert "pain_free_walking" not in CAPTURED_FUNCTIONAL_CHECKPOINTS
    checkpoint = clinical("test_walking_check", "functional_checkpoint", checkpoint="pain_free_walking")
    result = progress([event()], current=policy(add=(clinical(), checkpoint)))
    assert result["stage"] == "restore"
    assert result["next_transition"]["missing_inputs"] == ["pain_free_walking"]
    assert requirement(result, "test_walking_check")["status"] == "missing_input"


@pytest.mark.parametrize("next_day,status", [("not_yet_known", "unknown"), ("not_sure", "unknown"), ("worse", "fail")])
def test_unknown_or_worse_next_day_response_blocks(next_day, status):
    # A later explicit improvement report keeps the baseline at RESTORE.
    result = progress([event(next_day=next_day)], changes={"latest_reported_at": "2026-09-30T00:00:00Z"})
    assert result["stage"] == "restore"
    assert requirement(result, "next_day_response_not_worse")["status"] == status
    if next_day == "worse":
        # Without that report, a worse response is a baseline setback first.
        assert progress([event(next_day=next_day)])["stage"] == "calm"


def test_unreported_during_response_is_unknown_not_a_pass():
    result = progress([event(during="not_reported")])
    assert result["stage"] == "restore"
    assert requirement(result, "during_response_not_worse")["status"] == "unknown"


def test_resolved_setback_restores_baseline_but_never_counts_as_progression_evidence():
    rows = [event(1, next_day="worse"), event(2)]
    rows[0]["response_recorded_at"] = "2026-09-02T12:00:00Z"
    result = progress(rows, changes={"latest_reported_at": "2026-09-10T00:00:00Z"})
    assert result["stage"] == "restore"
    assert requirement(result, "no_unresolved_setback")["reason_code"] == "unresolved_historical_negative_response"


def test_truncated_history_cannot_promote():
    result = progress([event()], history_truncated=True)
    assert result["stage"] == "restore"
    assert requirement(result, "complete_episode_history")["status"] == "unknown"


@pytest.mark.parametrize("variant", [
    dict(load="unknown"), dict(policy_id="another_policy"), dict(stage="calm"), dict(drill=LOAD_DRILL, stage="restore"),
    dict(bank_hash="0" * 64), dict(completion="partial_amount_unknown"), dict(group=False),
])
def test_unreviewed_unknown_demand_stale_or_partial_work_is_not_evidence(variant):
    result = progress([event(**variant)])
    assert result["stage"] == "restore"


@pytest.mark.parametrize("variant,reason", [
    (dict(athlete="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"), IGNORED_ATHLETE_MISMATCH),
    (dict(episode=str(uuid4())), IGNORED_EPISODE_MISMATCH),
    (dict(side="right"), IGNORED_SIDE_MISMATCH),
])
def test_unattributable_rows_are_ignored_diagnostics(variant, reason):
    result = progress([event(**variant)])
    assert result["stage"] == "restore"
    assert result["next_transition"]["ignored_evidence"] == {reason: 1}


def test_unknown_side_injury_cannot_progress():
    assert progress([event()], changes={"side": "unknown"})["stage"] == "restore"


def test_done_as_shown_satisfies_a_defined_dose_but_not_self_paced_work():
    required = dict(clinical("test_defined_dose", "completed_reviewed_exposure"), requires_defined_dose=True)
    current = policy(add=(required,))
    assert progress([event()], current=current)["stage"] == "restore"
    assert requirement(progress([event()], current=current), "test_defined_dose")["reason_code"] == "no_defined_dose_completed"
    assert progress([event(prescribed={"sets": 2, "reps": 8})], current=current)["stage"] == "load"
    assert progress([event(completion="quantified")], current=current)["stage"] == "load"


def test_measured_dose_is_required_only_when_declared():
    current = policy(add=(clinical("test_measured", "measured_dose"),))
    assert progress([event()], current=current)["stage"] == "restore"
    assert progress([event(completion="quantified")], current=current)["stage"] == "load"
    assert progress([event()])["stage"] == "load"  # No measured-dose requirement declared.


def test_observation_minimum_is_labelled_data_sufficiency_and_counts_response_groups():
    minimum = dict(requirement_id="test_two_observations", kind="minimum_observations", basis="data_sufficiency",
                   description="Product data requirement, not readiness.", minimum=2)
    current = policy(add=(clinical(), minimum))
    result = progress([event(1)], current=current)
    assert result["stage"] == "restore"
    assert requirement(result, "test_two_observations") | {"evidence_ids": None} == {
        "requirement_id": "test_two_observations", "kind": "minimum_observations", "basis": "data_sufficiency",
        "status": "unknown", "reason_code": "observed_response_groups_1_of_2", "evidence_ids": None}
    assert progress([event(1), event(2)], current=current)["stage"] == "load"


def test_profile_can_close_a_transition_with_a_reason():
    current = policy(live=("calm", "restore"), closed="Return is clinician-led for this profile.")
    result = progress([event()], current=current)
    assert result["stage"] == "restore" and result["next_transition"]["status"] == "closed"
    assert result["next_transition"]["closed_reason"] == "Return is clinician-led for this profile."


def test_inconsistent_copied_response_group_is_unknown():
    a, b = event(1), event(2, during="better")
    b["event_json"]["response_group_id"] = a["event_json"]["response_group_id"]
    assert progress([a, b])["stage"] == "restore"


def test_camp_phase_clearance_and_whole_athlete_signals_are_not_inputs():
    params = set(inspect.signature(resolve_reviewed_progression).parameters)
    assert params == {"injury", "base_stage", "policy", "exposures", "history_truncated", "as_of"}
    cleared = progress([], changes={"clinician_clearance": {"episode_id": EPISODE, "scopes": ["rehab", "training", "contact"]}})
    assert cleared["stage"] == "restore"
    # Baseline never starts above RESTORE, whatever the record claims.
    assert progress([], base="load")["stage"] == "calm"


def test_end_to_end_policy_resolution_prescribes_reviewed_load_work_and_setbacks_demote():
    current = policy()
    decision = resolve_injury_policy(injury(), policies=(current,), bank=BANK, exposures=[event()])
    assert decision["stage"] == "load" and decision["outcome"] == "prescribed_rehab"
    assert decision["prescription"]["drill_id"] == LOAD_DRILL["id"] and decision["prescription"]["is_loading"]
    setback = resolve_injury_policy(injury(), policies=(current,), bank=BANK, exposures=[event(), event(2, during="worse")])
    assert setback["stage"] == "calm"
    gated = resolve_injury_policy(injury(severity="severe"), policies=(current,), bank=BANK, exposures=[event()])
    assert gated["outcome"] == "medical_review" and gated["prescription"] is None


def test_evaluate_transition_is_pure():
    current = policy()
    rows = [event()]
    before = repr(rows)
    first = evaluate_transition(current.transitions[0], policy=current, injury=injury(), exposures=rows)
    assert repr(rows) == before
    assert first == evaluate_transition(current.transitions[0], policy=current, injury=injury(), exposures=rows)
