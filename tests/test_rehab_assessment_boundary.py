"""Architectural conformance; the second protocol is never registered in production."""
from copy import deepcopy
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from api.contracts import rehab_assessment as boundary
from api.contracts.rehab_progression import evaluate_transition
from api.services.injury_episode_service import InjuryEpisodeObservation, apply_episode_observations, record_episode_observation
from fightcamp.rehab_clinical import load_clinical_policies
from fightcamp.rehab_pathways import FunctionalCheckpoint, PathwayTransition, TransitionRequirement
from tests.test_achilles_progression_inputs import assessment, capture, enriched, NOW, read
from tests.test_achilles_progression_inputs import context as achilles_context


@pytest.fixture
def context():
    return achilles_context.__wrapped__()


def test_available_records_cannot_satisfy_clinical_functional_requirement(context):
    injury = enriched(context)
    policy = next(p for p in load_clinical_policies() if p.policy_id == "achilles_tendonitis")
    transition = PathwayTransition(from_stage="restore", to_stage="load", requirements=[dict(
        requirement_id="synthetic_clinical", kind="functional_checkpoint", basis="clinical",
        checkpoint="achilles_heel_rise_assessed", description="Synthetic misuse fixture", sources=["fixture only"])])
    result = evaluate_transition(transition, policy=policy, injury=injury, exposures=[], as_of=NOW)
    assert read(injury)["status"] == "pass"
    assert result["status"] == "blocked"
    assert result["requirements"][0]["status"] == "missing_input"


def test_availability_alone_never_makes_transition_promotable(context):
    policy = next(p for p in load_clinical_policies() if p.policy_id == "achilles_tendonitis")
    transition = PathwayTransition(from_stage="restore", to_stage="load", requirements=[dict(
        requirement_id="synthetic_data", kind="input_availability", basis="data_sufficiency",
        checkpoint="achilles_heel_rise_assessed", description="Fixture only")])
    result = evaluate_transition(transition, policy=policy, injury=enriched(context), exposures=[], as_of=NOW)
    assert result["requirements"][0]["status"] == "pass"
    assert result["status"] == "blocked"
    assert result["reason_codes"] == ["no_clinical_criteria_declared"]
    with pytest.raises(ValidationError):
        TransitionRequirement(requirement_id="bad", kind="input_availability", basis="clinical",
            checkpoint="achilles_heel_rise_assessed", description="Fixture", sources=["fixture"])


@pytest.mark.parametrize("patch", [dict(assessment_kind="unknown"), dict(protocol_version=2),
    dict(source="clinician_verified"), dict(externally_verified=True), dict(medical_concern=False)])
def test_unknown_protocol_and_client_verification_fail_closed(patch):
    with pytest.raises(ValidationError):
        boundary.AchillesProgressionAssessment.model_validate({**assessment().model_dump(mode="json"), **patch})


def test_explicit_replay_uses_snapshot_at_as_of(context):
    old = capture(context)
    old["created_at"] = "2026-10-05T16:00:00Z"
    later = capture(context, assessment(suspected_rupture=True))
    later["created_at"] = "2026-10-05T18:00:00Z"
    before = datetime(2026, 10, 5, 17, tzinfo=timezone.utc)
    earlier = apply_episode_observations(context[2], [old, later], as_of=before)
    assert boundary.read_assessment_input("achilles_heel_rise_assessed",
        boundary.AssessmentContext.from_injury(earlier, as_of=before))["status"] == "pass"
    assert "progression_assessment_medical_hold" not in earlier
    after = apply_episode_observations(context[2], [old, later], as_of=NOW)
    assert after["progression_assessment_medical_hold"] is True


def test_incomplete_assessment_history_blocks_availability(context):
    injury = enriched(context)
    history = boundary.AssessmentHistory(injury["progression_assessments"], history_complete=False)
    injury = apply_episode_observations(context[2], history, as_of=NOW)
    assert read(injury)["reason_code"] == "assessment_history_incomplete"


def test_registry_protocol_drift_and_unknown_inputs_fail_closed(context, monkeypatch):
    declaration = next(iter(boundary.input_definitions().values()))[0]
    for change in (dict(assessment_kind="unknown"), dict(protocol_version=2)):
        monkeypatch.setattr(boundary, "_input_declarations", lambda: (declaration.model_copy(update=change),))
        with pytest.raises(ValueError, match="registration"):
            boundary.input_definitions()
    monkeypatch.undo()
    assert boundary.read_assessment_input("unknown", boundary.AssessmentContext.from_injury(
        context[2], as_of=NOW))["status"] == "unknown"
    with pytest.raises(ValueError, match="unknown"):
        boundary.validate_assessment({"assessment_kind": "unknown", "payload": {}})


def test_short_postgrest_pages_do_not_hide_an_older_concern(context):
    from types import SimpleNamespace
    from api.store import SupabaseAppStore

    concerning = capture(context, assessment(suspected_rupture=True))
    reassuring = capture(context)
    reassuring["created_at"] = "2026-10-05T18:00:00Z"

    class Query:
        def __init__(self):
            self.cursor = None
        def select(self, *args):
            return self
        def eq(self, *args):
            return self
        def order(self, *args, **kwargs):
            return self
        def limit(self, *args):
            return self
        def or_(self, value):
            self.cursor = value
            return self
        def execute(self):
            # Emulate a server page ceiling below the requested limit. Stable
            # timestamp/ID cursors must reach the older concern and empty page.
            if self.cursor is None:
                return SimpleNamespace(data=[reassuring])
            if reassuring["id"] in self.cursor:
                return SimpleNamespace(data=[concerning])
            assert concerning["id"] in self.cursor
            return SimpleNamespace(data=[])

    store = SupabaseAppStore(client=SimpleNamespace(table=lambda name: Query()), admin_emails=set())
    history = store.list_injury_episode_events(context[1], injury_id=context[2]["id"], injury_episode_id=context[2]["episode_id"])
    assert history.history_complete and len(history) == 2
    assert apply_episode_observations(context[2], history, as_of=NOW)["progression_assessment_medical_hold"]


@pytest.fixture
def synthetic_protocol(monkeypatch):
    class SyntheticPayload(BaseModel):
        model_config = ConfigDict(extra="forbid")
        observed: bool = Field(strict=True)
        concern: bool = Field(default=False, strict=True)

    class SyntheticAssessment(boundary.RehabProgressionAssessment[SyntheticPayload]):
        assessment_kind: Literal["synthetic_transport_fixture_v1"] = "synthetic_transport_fixture_v1"
        protocol_version: Literal[1] = 1

    kind = "synthetic_transport_fixture_v1"
    definition = boundary.AssessmentProtocol(SyntheticAssessment, SyntheticPayload, 1,
        "achilles", "tendonitis", "achilles_tendonitis", lambda identifier, a: {
            "status": "pass" if a.payload.observed else "unknown", "reason_code": "synthetic_fixture_only"},
        lambda payload: (), lambda payload: payload.concern)
    monkeypatch.setitem(boundary.ASSESSMENT_PROTOCOLS, kind, definition)
    catalog = boundary.load_pathway_catalog().model_copy(update={"functional_checkpoints": [FunctionalCheckpoint(
        checkpoint_id="synthetic_observed", description="Architectural fixture only", required_input="synthetic observation",
        basis="data_sufficiency", assessment_kind=kind, protocol_version=1)]})
    monkeypatch.setattr(boundary, "_input_declarations", lambda: catalog.functional_checkpoints)
    return SyntheticAssessment


def test_second_fixture_uses_same_writer_context_registry_and_engine(context, synthetic_protocol):
    value = synthetic_protocol(side="left", assessed_at="2026-10-05T15:00:00Z", assessor="coach_observed", payload={"observed": True})
    # Production HTTP schema remains Achilles-only. The fixture exercises shared
    # writer dispatch with a test-registered typed envelope, not a new pathway.
    observation = InjuryEpisodeObservation.model_construct(injury_id=context[2]["id"], injury_episode_id=context[2]["episode_id"],
        event_type=boundary.ASSESSMENT_EVENT, assessment=value, report_id=uuid4(), scopes=[], response=None, exposure_id=None)
    stored = record_episode_observation(context[0], athlete_id=context[1], observation=observation, training_day="2026-10-05")
    stored["created_at"] = "2026-10-05T16:00:00Z"
    assert stored["event_type"] == "rehab_progression_assessment"
    assert stored["payload"]["source"] == "athlete_reported"
    assert stored["payload"]["externally_verified"] is False
    injury = apply_episode_observations(context[2], [stored], as_of=NOW)
    policy = next(p for p in load_clinical_policies() if p.policy_id == "achilles_tendonitis")
    transition = PathwayTransition(from_stage="restore", to_stage="load", requirements=[dict(
        requirement_id="fixture", kind="input_availability", basis="data_sufficiency",
        checkpoint="synthetic_observed", description="Fixture only")])
    result = evaluate_transition(transition, policy=policy, injury=injury, exposures=[], as_of=NOW)
    assert result["requirements"][0]["status"] == "pass"
    assert result["status"] == "blocked"
    for field in ("athlete_id", "injury_id", "injury_episode_id"):
        other = deepcopy(stored)
        other[field] = str(uuid4())
        row = apply_episode_observations(context[2], [other], as_of=NOW)
        assert boundary.read_assessment_input("synthetic_observed",
            boundary.AssessmentContext.from_injury(row, as_of=NOW))["status"] == "unknown"
    for side in ("right", "bilateral"):
        other = deepcopy(stored)
        other["payload"]["assessment"]["side"] = side
        row = apply_episode_observations(context[2], [other], as_of=NOW)
        assert boundary.read_assessment_input("synthetic_observed",
            boundary.AssessmentContext.from_injury(row, as_of=NOW))["status"] == "unknown"
    with pytest.raises(ValidationError):
        synthetic_protocol(side="left", assessed_at=NOW, assessor="coach_observed", payload={"site": "insertional"})
    concerned = deepcopy(stored)
    concerned["payload"]["assessment"]["payload"]["concern"] = True
    assert apply_episode_observations(context[2], [concerned], as_of=NOW)["progression_assessment_medical_hold"]
