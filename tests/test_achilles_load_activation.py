"""Production catalog, trusted capture, actual Today/acceptance/completion flow."""
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.contracts.achilles_restore_load_pilot import ACHILLES_LOAD_OPTION as OPTION, CRITERION_ID
from api.contracts.clinical_progression_review import CLINICAL_REVIEW_REGISTRY
from api.contracts.clinical_review_capture import ClinicalReviewCaptureRequest, ClinicalReviewLifecycleRequest
from api.services import today_service
from api.services.clinical_review_capture_service import build_review_context, record_clinical_review, record_review_lifecycle
from api.services.rehab_completion_service import record_rehab_exposures
from fightcamp.rehab_clinical import content_hash, load_clinical_policies
from fightcamp.rehab_protocols import get_rehab_bank
from tests.support import FakeStore
from tests.test_achilles_progression_inputs import NOW, assessment, capture
from tests.test_achilles_shadow_pilot import shadow_bundle

DAY = NOW.date().isoformat()


class LiveCaptureStore(FakeStore):
    """Existing in-memory store plus the existing private capture boundary."""
    def is_admin_email(self, email):
        return email == "operator@example.test"

    def get_clinical_review_capture_context(self, athlete_id, injury_id, episode_id):
        injury = self.get_injury_flag_for_athlete(injury_id, athlete_id)
        return deepcopy(dict(profile=self.capture_profile, injury=injury,
            events=self.list_injury_episode_events(athlete_id, injury_id=injury_id, injury_episode_id=episode_id),
            exposures=list(self.list_rehab_exposures(athlete_id, injury_id=injury_id, injury_episode_id=episode_id).rows)))

    def record_clinical_review_event(self, athlete_id, recorder_id, context, event, supersession):
        assert context == self.get_clinical_review_capture_context(athlete_id,event["injury_id"],event["injury_episode_id"])
        result = dict(deepcopy(event), created_at=event["payload"]["recorded_at"])
        self.injury_episode_events[result["id"]] = result
        if supersession:
            self.injury_episode_events[supersession["id"]] = dict(deepcopy(supersession), created_at=result["created_at"])
        return result


def activation_bundle(**changes):
    template, recorder, request, _ = shadow_bundle()
    store = LiveCaptureStore()
    athlete, plan = str(request.athlete_id), str(uuid4())
    store.capture_profile = template.snapshot["profile"]
    store.intakes[athlete] = [dict(id=str(uuid4()),athlete_id=athlete,equipment_access=["stable_support"])]
    injury = store.create_injury_flag(athlete, template.snapshot["injury"])
    injury.update(created_at="2026-09-01T00:00:00Z",updated_at="2026-09-01T00:00:00Z")
    store.injury_flags[athlete][0].update(injury)
    opening = deepcopy(template.snapshot["events"][0])
    store.injury_episode_events[opening["id"]] = opening
    observed = capture((store,athlete,injury), assessment(**dict(site="midportion", suspected_rupture=False,
        marked_weakness=False, traumatic_loss_of_function=False, clinician_restriction=False) | changes))
    for exposure in template.snapshot["exposures"]:
        store.rehab_exposures[exposure["id"]] = deepcopy(exposure)
    store.plans[plan] = dict(id=plan,athlete_id=athlete,intake_id=store.intakes[athlete][0]["id"],status="ready",created_at="2026-09-01T00:00:00Z",
        structured_plan={"weeks":[{"phase_label":"GPP","days":[{"date":DAY,"day_type":"strength","sessions":[
            dict(session_id="original-session",session_type="strength",title="Strength",blocks=[
                dict(block_id="training",block_type="strength",display_name="Calf work",mechanical_load_regions=["achilles"],contact_level="none")])]}]}]})
    store.set_active_plan_id(athlete,plan)
    store.upsert_today_checkin(athlete,dict(plan_id=plan,training_day=DAY,recommendation_state="train_as_planned",pain="none",body="good"))
    policy=next(p for p in load_clinical_policies() if p.policy_id==OPTION.profile_id)
    context=build_review_context(store.get_clinical_review_capture_context(athlete,injury["id"],injury["episode_id"]),
        definition=CLINICAL_REVIEW_REGISTRY.current(CRITERION_ID),policy=policy,bank=get_rehab_bank(),as_of=NOW)
    raw=request.model_dump(mode="json")
    raw["statement"]["reviewed_packet_revision"]=context.current_packet.packet_revision
    raw["statement"]["interpretation"].update(assessment_event_id=observed["id"],assessment_content_hash=content_hash(observed["payload"]))
    return store,recorder,ClinicalReviewCaptureRequest.model_validate(raw),athlete,plan,injury


def view(bundle):
    return today_service.build_today_command_view(bundle[0],athlete_id=bundle[3],athlete_timezone="UTC",now=NOW)


def approve(bundle):
    return record_clinical_review(bundle[0],recorder=bundle[1],request=bundle[2],as_of=NOW)


def execute(bundle,live,status="started",**changes):
    return today_service.upsert_session_completion(bundle[0],athlete_id=bundle[3],athlete_timezone="UTC",now=NOW,
        payload=dict(plan_id=bundle[4],session_id=live["session"]["session_id"],status=status,prescription_revision=live["revision"],**changes))


def test_trusted_assessment_to_today_accept_complete_and_exact_exposure():
    bundle=activation_bundle()
    assert view(bundle).open_injuries[0]["rehab_decision"]["stage"]=="restore"
    review=approve(bundle)
    current=view(bundle)
    assert current.open_injuries[0]["rehab_decision"]["stage"]=="load"
    live=current.live_prescription
    assert live and not live["safety_hold"]
    block=live["session"]["blocks"][0]
    assert block["rehab_drill_id"]==OPTION.drill_id
    assert block["dose"]==dict(sets=1,reps=10)
    assert block["instructions"]==OPTION.instructions and block["range_choice"]=="floor_level"
    assert block["resistance"]==dict(mode="bodyweight",kg=None)
    assert block["clinical_review_pin"]["review_id"]==str(review.review_id)
    assert block["frequency"]=="daily" and block["minimum_gap_days"]==1
    assert set(block["mandatory_restrictions"])==set(OPTION.mandatory_restrictions)
    saved=execute(bundle,live)
    assert saved["prescription_snapshot"]["session"]["blocks"]==live["session"]["blocks"]
    done=execute(bundle,live,"done",rehab_performance="done_as_shown")
    events=record_rehab_exposures(bundle[0],athlete_id=bundle[3],plan_row=bundle[0].plans[bundle[4]],
        training_day=DAY,session_id=live["session"]["session_id"],completion=done,
        answers={bundle[5]["id"]:dict(injury_episode_id=bundle[5]["episode_id"],during_response="same",limit_response="no")})
    assert len(events)==1
    assert events[0].drill_id==OPTION.drill_id
    assert events[0].dose_completed.sets==1 and events[0].dose_completed.reps==10
    assert done["prescription_snapshot"]["session"]["blocks"][0]["dose"]==dict(sets=1,reps=10)
    assert view(bundle).live_prescription is None or all(b.get("rehab_drill_id")!=OPTION.drill_id
        for b in view(bundle).live_prescription["session"]["blocks"])


@pytest.mark.parametrize("changes",[{},dict(site="insertional"),dict(site="unknown"),dict(suspected_rupture=True),dict(marked_weakness=True)])
def test_no_unapproved_load_in_real_today(changes):
    bundle=activation_bundle(**changes)
    if changes:
        try:
            approve(bundle)
        except HTTPException:
            pass
    current=view(bundle)
    assert current.open_injuries[0]["rehab_decision"]["stage"]!="load"
    assert not current.live_prescription or all(b.get("rehab_drill_id")!=OPTION.drill_id for b in current.live_prescription["session"]["blocks"])


@pytest.mark.parametrize("state",["unstarted","started"])
@pytest.mark.parametrize("mutation",["revoked","assessment","side","episode","dose","missing_pin",
    "range","resistance","cadence","restrictions","instructions","stop_rules","generic_override","setback","medical","restriction"])
def test_frozen_work_invalidation_never_substitutes_or_rewrites(state,mutation):
    bundle=activation_bundle()
    approved=approve(bundle)
    live=view(bundle).live_prescription
    saved=(execute(bundle,live) if state=="started" else bundle[0].upsert_session_completion(bundle[3],
        dict(plan_id=bundle[4],session_id=live["session"]["session_id"],training_day=DAY,status="not_started",prescription_snapshot=deepcopy(live))))
    snapshot=deepcopy(saved["prescription_snapshot"])
    if mutation=="revoked":
        action=ClinicalReviewLifecycleRequest(request_id=uuid4(),athlete_id=bundle[2].athlete_id,injury_id=bundle[2].injury_id,
            injury_episode_id=bundle[2].injury_episode_id,review_id=approved.review_id,action="revoke",effective_at=NOW,
            confirmation_reference="withdrawn",reason="Clinician withdrew approval")
        record_review_lifecycle(bundle[0],recorder=bundle[1],request=action,as_of=NOW)
    elif mutation=="assessment":
        new=deepcopy(next(e for e in bundle[0].injury_episode_events.values() if e["event_type"]=="rehab_progression_assessment"))
        new.update(id=str(uuid4()),created_at=(NOW-timedelta(minutes=1)).isoformat())
        bundle[0].injury_episode_events[new["id"]]=new
    elif mutation in {"side","episode"}:
        bundle[0].injury_flags[bundle[3]][0]["side" if mutation=="side" else "episode_id"]="right" if mutation=="side" else str(uuid4())
    elif mutation in {"setback","medical","restriction"}:
        field={"setback":"latest_reported_status","medical":"medical_hold","restriction":"restriction_hold"}[mutation]
        bundle[0].injury_flags[bundle[3]][0][field]="worse" if mutation=="setback" else True
    else:
        block=saved["prescription_snapshot"]["session"]["blocks"][0]
        if mutation=="dose":
            block["dose"]["reps"]=11
        elif mutation=="missing_pin":
            block.pop("clinical_review_pin")
        else:
            key={"range":"range_choice","cadence":"frequency","restrictions":"mandatory_restrictions",
                "generic_override":"prescription"}.get(mutation,mutation)
            block[key]={"range":"below_floor","resistance":dict(mode="external_load",kg=10),"cadence":"twice_daily",
                "restrictions":[],"instructions":"Use a step", "stop_rules":[],"generic_override":"3 sets of 15 with weight"}[mutation]
        # Simulate malformed persisted work, not client-controlled acceptance.
        bundle[0].session_completions[bundle[3]][0]["prescription_snapshot"]=deepcopy(saved["prescription_snapshot"])
        snapshot=deepcopy(saved["prescription_snapshot"])
    with pytest.raises(HTTPException):
        execute(bundle,live,"done" if state=="started" else "started",rehab_performance="done_as_shown" if state=="started" else None)
    assert bundle[0].session_completions[bundle[3]][0]["prescription_snapshot"]==snapshot


def test_missing_explicit_stable_support_cannot_promote_or_execute():
    bundle=activation_bundle()
    approve(bundle)
    bundle[0].intakes[bundle[3]][0]["equipment_access"]=[]
    current=view(bundle)
    decision=current.open_injuries[0]["rehab_decision"]
    assert decision["stage"]!="load"
    assert "reviewed_target_content_unavailable" in decision["progression"]["next_transition"]["reason_codes"]
    assert not current.live_prescription or all(b.get("rehab_drill_id")!=OPTION.drill_id
        for b in current.live_prescription["session"]["blocks"])


def test_completed_snapshot_remains_historical_after_revocation():
    from api.services.clinical_review_freeze import frozen_review_hold
    bundle=activation_bundle()
    approved=approve(bundle)
    live=view(bundle).live_prescription
    done=execute(bundle,live,"done",rehab_performance="done_as_shown")
    saved=deepcopy(done["prescription_snapshot"])
    record_review_lifecycle(bundle[0],recorder=bundle[1],as_of=NOW,
        request=ClinicalReviewLifecycleRequest(request_id=uuid4(),athlete_id=bundle[2].athlete_id,injury_id=bundle[2].injury_id,
            injury_episode_id=bundle[2].injury_episode_id,review_id=approved.review_id,action="revoke",effective_at=NOW,
            confirmation_reference="withdrawn",reason="Clinician withdrew approval"))
    assert not frozen_review_hold(bundle[0],bundle[3],saved,work_state="completed",as_of=NOW)
    view(bundle)
    assert bundle[0].session_completions[bundle[3]][0]["prescription_snapshot"]==saved


def test_approval_grants_no_clearance_and_other_severe_injury_holds_started_load():
    bundle=activation_bundle()
    assert view(bundle).effective_clinician_clearance is None
    approve(bundle)
    current=view(bundle)
    assert current.effective_clinician_clearance is None
    live=current.live_prescription
    saved=deepcopy(execute(bundle,live)["prescription_snapshot"])
    bundle[0].create_injury_flag(bundle[3],dict(body_area="Wrist",description="Wrist strain",severity="severe",status="open"))
    held=view(bundle).live_prescription
    assert held and held["safety_hold"] and held["frozen"]
    with pytest.raises(HTTPException):
        execute(bundle,held,"done",rehab_performance="done_as_shown")
    assert bundle[0].session_completions[bundle[3]][0]["prescription_snapshot"]==saved


@pytest.mark.parametrize("failure",["hydration","evaluator","expected_unavailable"])
def test_review_failure_logs_are_classified_safe_and_fail_closed(monkeypatch,caplog,failure):
    from dataclasses import replace
    from api.contracts import rehab_progression
    from api.contracts.clinical_progression_review import CriterionReviewRegistry
    bundle=activation_bundle()
    approve(bundle)
    def broken(*args,**kwargs):
        raise ValueError("private clinical statement") if failure=="expected_unavailable" else RuntimeError("private clinical statement")
    if failure=="evaluator":
        registry=CriterionReviewRegistry((replace(CLINICAL_REVIEW_REGISTRY.current(CRITERION_ID),evaluate=broken),))
        monkeypatch.setattr(rehab_progression,"CLINICAL_REVIEW_REGISTRY",registry)
        monkeypatch.setattr("api.contracts.clinical_progression_review.CLINICAL_REVIEW_REGISTRY",registry)
    else:
        monkeypatch.setattr("api.services.clinical_review_capture_service.hydrate_review_input",broken)
    with caplog.at_level("INFO"):
        current=view(bundle)
    assert current.open_injuries[0]["rehab_decision"]["stage"]!="load"
    marker={"hydration":"clinical_review_hydration_failed","evaluator":"clinical_review_evaluator_failed",
        "expected_unavailable":"clinical_review_unavailable"}[failure]
    assert marker in caplog.text and "private clinical statement" not in caplog.text
    if failure=="expected_unavailable":
        assert "clinical_review_hydration_failed" not in caplog.text
