"""Replay actual Today/completion/episode functions; never inject stage/exposure wins.

FakeStore omits the database check-in trigger. The adapter below emits its real
persisted event shape; PostgreSQL trigger behaviour has separate integration tests.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from api.services import today_service
from api.services.injury_episode_service import InjuryEpisodeObservation, record_episode_observation, delayed_rehab_prompts
from api.services.rehab_completion_service import build_rehab_response_contexts, record_reported_permission_rehab
from fightcamp.rehab_clinical import load_clinical_policies
from tests.support import FakeStore

PILOTS = [
    ("achilles_tendonitis", "Left Achilles", "tendonitis", "achilles_site:midportion", "mild"),
    ("elbow_tendonitis", "Left elbow", "tendonitis", "elbow_site:lateral", "moderate"),
    ("ankle_sprain", "Left ankle", "sprain", "ankle_scope:uncomplicated_lateral", "mild"),
    ("shoulder_tendonitis", "Left shoulder", "tendonitis", "shoulder_scope:nontraumatic_cuff", "moderate"),
]


class Journey:
    def __init__(self, monkeypatch, pilot):
        self.now = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
        monkeypatch.setattr("tests.support._now", lambda: self.now.isoformat())
        self.store, self.athlete, self.plan = FakeStore(), str(uuid4()), str(uuid4())
        self.policy = next(p for p in load_clinical_policies() if p.policy_id == pilot[0])
        self.store.intakes[self.athlete] = [dict(id=str(uuid4()), athlete_id=self.athlete,
            equipment_access=["stable_support", "table", "chair", "wall"])]
        self.store.plans[self.plan] = dict(id=self.plan, athlete_id=self.athlete, status="ready",
            intake_id=self.store.intakes[self.athlete][0]["id"], created_at=self.now.isoformat(),
            structured_plan={"weeks": [{"phase_label": "GPP", "days": [{"date": self.day,
                "day_type": "strength", "sessions": [dict(session_id="training", session_type="strength",
                    title="Strength", blocks=[dict(block_id="training", block_type="strength",
                    display_name="Training", mechanical_load_regions=[self.policy.region], contact_level="none")])]}]}]})
        self.store.set_active_plan_id(self.athlete, self.plan)
        self.ready()
        # Creation, then the existing Edit injury declaration carries subtype.
        self.report("improving", body_area=pilot[1], description=pilot[2], severity=pilot[4])
        self.injury = self.store.injury_flags[self.athlete][0]
        self.report("improving", description=f"{pilot[2]} [{pilot[3]}]")
        self.permission("loading")

    def ready(self):
        self.store.upsert_today_checkin(self.athlete, dict(plan_id=self.plan, training_day=self.day,
            recommendation_state="train_as_planned", pain="none", body="good"))

    @property
    def day(self):
        return self.now.date().isoformat()

    def advance(self, days=1):
        self.now += timedelta(days=days)
        self.ready()

    def report(self, status, **fields):
        self.now += timedelta(minutes=1)
        # Match TodayInjuryManager.updateInjury: one existing injury tap also
        # saves yesterday's exposure-addressed responses, without another form.
        prompts = delayed_rehab_prompts(self.store, self.athlete, self.day, "UTC") if hasattr(self, "injury") else []
        declaration = dict(status=status, **fields)
        if hasattr(self, "injury"):
            declaration["flag_id"] = self.injury["id"]
        today_service.submit_today_injury_checkin(self.store, athlete_id=self.athlete, athlete_timezone="UTC",
            now=self.now, payload={"injuries": [declaration]})
        injury = self.store.injury_flags[self.athlete][0]
        event = dict(id=str(uuid4()), athlete_id=self.athlete, injury_id=injury["id"],
            injury_episode_id=injury["episode_id"], event_type="injury_checkin", created_at=self.now.isoformat(),
            payload=dict(explicit_report=True, latest_reported_status=status))
        self.store.injury_episode_events[event["id"]] = event
        for prompt in prompts:
            if prompt["injury_episode_id"] == injury["episode_id"]:
                record_episode_observation(self.store, athlete_id=self.athlete, training_day=self.day,
                    observation=InjuryEpisodeObservation(injury_id=injury["id"], injury_episode_id=injury["episode_id"],
                        event_type="delayed_rehab_response", exposure_id=prompt["exposure_id"],
                        response={"improving": "better", "ongoing": "same", "worse": "worse"}[status]))

    def permission(self, level):
        self.now += timedelta(minutes=1)
        return record_episode_observation(self.store, athlete_id=self.athlete, training_day=self.day,
            observation=InjuryEpisodeObservation(injury_id=self.injury["id"],
                injury_episode_id=self.injury["episode_id"], event_type="clinician_clearance_report",
                scopes=["rehab"], rehabilitation_permission={"schema_version": 1, "level": level}))

    def view(self):
        return today_service.build_today_command_view(self.store, athlete_id=self.athlete,
            athlete_timezone="UTC", now=self.now)

    def decision(self):
        return next(i for i in self.view().open_injuries if i["id"] == self.injury["id"])["rehab_decision"]

    def transition(self):
        from api.contracts.rehab_progression import evaluate_transition
        from api.services.injury_episode_service import apply_episode_observations, exposure_rows_with_observations
        observations = self.store.list_injury_episode_events(self.athlete, injury_id=self.injury["id"],
            injury_episode_id=self.injury["episode_id"])
        return evaluate_transition(next(t for t in self.policy.transitions if t.key == "restore->load"),
            policy=self.policy, injury=apply_episode_observations(self.injury, observations, as_of=self.now),
            exposures=exposure_rows_with_observations(list(self.store.rehab_exposures.values()), observations), as_of=self.now)

    def complete(self, response="improving", performance="done_as_shown"):
        live = self.view().live_prescription
        if not live:
            schedule = self.decision().get("schedule") or {}
            if schedule.get("state") == "recovery_day" and schedule.get("next_due_day"):
                due = datetime.fromisoformat(schedule["next_due_day"]).date()
                self.advance((due - self.now.date()).days)
                live = self.view().live_prescription
        assert live and not live["safety_hold"]
        for status in ("started", "done"):
            completion = today_service.upsert_session_completion(self.store, athlete_id=self.athlete,
                athlete_timezone="UTC", now=self.now, payload=dict(plan_id=self.plan,
                    session_id=live["session"]["session_id"], status=status,
                    prescription_revision=live["revision"], rehab_tracking="injury_checkin",
                    **({"rehab_performance": performance} if status == "done" else {})))
        _, contexts = build_rehab_response_contexts(self.store, athlete_id=self.athlete,
            plan_row=self.store.plans[self.plan], training_day=self.day,
            session_id=completion["session_id"], completion=completion)
        completion.update(self.store.initialize_session_completion_rehab_contexts(self.athlete,
            completion_id=completion["id"], plan_id=self.plan, session_id=completion["session_id"],
            training_day=self.day, contexts=contexts))
        events = record_reported_permission_rehab(self.store, athlete_id=self.athlete,
            plan_row=self.store.plans[self.plan], completion=completion)
        self.report(response)
        return events

    def followup(self, answer="same"):
        prompts = self.view().delayed_rehab_prompts
        assert prompts, self.decision()
        # The existing per-injury tap submits all exposure-addressed answers.
        for prompt in prompts:
            record_episode_observation(self.store, athlete_id=self.athlete, training_day=self.day,
                observation=InjuryEpisodeObservation(injury_id=prompt["injury_id"],
                    injury_episode_id=prompt["injury_episode_id"], event_type="delayed_rehab_response",
                    exposure_id=prompt["exposure_id"], response=answer))


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_complete_better_then_next_day_same_in_existing_injury_flow(monkeypatch, pilot):
    j = Journey(monkeypatch, pilot)
    j.complete()
    j.advance()
    assert j.decision()["stage"] == "restore"
    j.report("ongoing")
    decision = j.decision()
    assert decision["stage"] == "load", decision["progression"]
    transition = j.transition()
    assert transition["status"] == "met" and all(r["status"] == "pass" for r in transition["requirements"])
    load = next(p for p in j.policy.prescriptions if p.stage == "load")
    assert j.view().live_prescription["session"]["blocks"][0]["rehab_drill_id"] == load.drill_id


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_repeated_actual_work_then_followup_reaches_visible_load(monkeypatch, pilot):
    j = Journey(monkeypatch, pilot)
    j.permission("gentle_recovery")
    assert j.decision()["stage"] == "restore"
    originals = []
    for answer in ("improving", "ongoing", "improving"):
        if delayed_rehab_prompts(j.store, j.athlete, j.day, "UTC"):
            j.report(answer)
        events = j.complete(answer)
        assert events
        for e in events:
            assert e.provenance.policy_id == pilot[0]
            assert e.provenance.policy_version == j.policy.version
            assert e.provenance.bank_hash and e.provenance.prescription_revision
            assert str(e.injury_id) == j.injury["id"] and str(e.injury_episode_id) == j.injury["episode_id"]
            assert e.side == "left" and e.body_region == j.policy.region and e.response_group_id
            assert e.dose_completed.completion_state == "performed_amount_unknown"
        originals.extend(deepcopy(list(j.store.rehab_exposures.values())))
        j.advance()
        assert j.decision()["stage"] == "restore"  # unanswered is never safe
    j.followup()
    j.permission("loading")
    decision = j.decision()
    assert decision["stage"] == "load", decision["progression"]
    expected = next(p for p in j.policy.prescriptions if p.stage == "load")
    assert decision["prescription"]["drill_id"] == expected.drill_id
    assert j.view().live_prescription["session"]["blocks"][0]["rehab_drill_id"] == expected.drill_id
    assert j.view().delayed_rehab_prompts == []
    for row in originals:
        assert j.store.rehab_exposures[row["id"]] == row


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_setback_requires_improvement_then_new_successful_restore(monkeypatch, pilot):
    j = Journey(monkeypatch, pilot)
    j.complete("ongoing")
    j.advance()
    j.followup("worse")
    assert j.decision()["stage"] == "calm"
    j.report("improving")
    j.permission("loading")
    assert j.decision()["stage"] == "restore"
    # The routine's reviewed recovery gap is not a new progression threshold.
    gap = max(p.minimum_gap_days for p in j.policy.prescriptions if p.stage == "restore")
    if gap > 1:
        j.advance(gap - 1)
    j.complete("ongoing")
    j.advance()
    assert j.decision()["stage"] == "restore"
    j.followup()
    assert j.decision()["stage"] == "load", j.decision()["progression"]
    resolved = next(r for r in j.transition()["requirements"] if r["kind"] == "no_unresolved_setback")
    assert resolved["reason_code"] == "setback_resolved_by_improvement_and_reviewed_response"
    assert resolved["recovery_report_id"] in j.store.injury_episode_events


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_new_reviewed_session_does_not_borrow_previous_delayed_answer(monkeypatch, pilot):
    j = Journey(monkeypatch, pilot)
    j.permission("gentle_recovery")
    j.complete()
    j.advance()
    j.followup()
    gap = max(p.minimum_gap_days for p in j.policy.prescriptions if p.stage == "restore")
    if gap > 1:
        j.advance(gap - 1)
    new = j.complete()
    assert all(e.provenance.rehab_stage == "restore" for e in new)
    j.permission("loading")
    assert j.decision()["stage"] == "restore"
    assert "next_day_response_not_yet_known" in j.transition()["reason_codes"]
    j.advance()
    j.followup()
    assert j.decision()["stage"] == "load"


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_load_completion_has_defined_dose_and_still_needs_next_day_answer(monkeypatch, pilot):
    j = Journey(monkeypatch, pilot)
    j.complete()
    j.advance()
    j.report("ongoing")
    assert j.decision()["stage"] == "load"
    events = j.complete()
    prescribed = next(p for p in j.policy.prescriptions if p.stage == "load")
    assert len(events) == 1
    assert events[0].drill_id == prescribed.drill_id
    assert events[0].dose_completed.completion_state == "quantified"
    assert events[0].dose_completed.reps == prescribed.dose.reps
    j.advance()
    before = j.decision()
    assert before["stage"] == "load"
    assert before["schedule"]["state"] == "held"  # Better has not supplied the delayed answer
    j.report("ongoing")
    assert j.decision()["schedule"]["state"] == "due"
    assert j.view().live_prescription["session"]["blocks"][0]["rehab_drill_id"] == prescribed.drill_id


@pytest.mark.parametrize("pilot", PILOTS, ids=lambda p: p[0])
def test_generation_agrees_with_today_from_real_completed_work(monkeypatch, pilot):
    from api.services.rehab_stage_snapshot import resolve_open_injury_rehab_context
    from fightcamp.rehab_protocols import _episode_context, _reviewed_episode_option
    from fightcamp.input_parsing import _apply_rehab_generation_context, _coerce_rehab_generation_context
    j = Journey(monkeypatch, pilot)
    j.complete()
    j.advance()
    j.followup()
    raw = next(iter(resolve_open_injury_rehab_context(j.store, j.athlete).values()))
    entry = dict(injury_type=pilot[2], severity=pilot[4], laterality="left")
    _apply_rehab_generation_context(entry, _coerce_rehab_generation_context({"rehab_generation_context": raw}))
    generated = _reviewed_episode_option(_episode_context(entry), j.policy.region, "GPP")
    assert generated["decision"]["stage"] == j.decision()["stage"] == "load"
    assert generated["drill"]["id"] == j.decision()["prescription"]["drill_id"]
