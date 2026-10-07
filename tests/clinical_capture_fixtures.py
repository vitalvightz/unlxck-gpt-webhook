"""Invented compiled criterion only; uses the production capture service."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from api.compliance import HEALTH_CONSENT_VERSION, TERMS_VERSION
from api.contracts.clinical_review_capture import ClinicalReviewCaptureRequest
from api.services.clinical_review_capture_service import build_review_context
from tests.clinical_review_fixtures import NOW
from tests.test_clinical_review_engine_and_freeze import engine_bundle
from tests.test_rehab_transition_engine import BANK

ADMIN = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
AUTHOR = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class CaptureStore:
    def __init__(self, snapshot):
        self.snapshot = deepcopy(snapshot)
        self.writes = 0

    def is_admin_email(self, email):
        return email == "operator@example.test"

    def get_clinical_review_capture_context(self, *args):
        return deepcopy(self.snapshot)

    def list_injury_episode_events(self, *args, **kwargs):
        from api.contracts.rehab_assessment import AssessmentHistory
        return AssessmentHistory(deepcopy(self.snapshot["events"]), history_complete=True)

    def record_clinical_review_event(self, athlete_id, recorder_id, context, event, supersession):
        if context != self.snapshot:
            raise HTTPException(409, "clinical review context changed")
        self.writes += 1
        result = dict(deepcopy(event), created_at=event["payload"]["recorded_at"])
        self.snapshot["events"].append(result)
        if supersession:
            self.snapshot["events"].append(dict(deepcopy(supersession), created_at=supersession["payload"]["recorded_at"]))
        return result


def capture_bundle(second=False, *, as_of=NOW):
    supplied, policy, injury = engine_bundle(second, live=("calm", "restore"))
    profile = dict(id=injury["athlete_id"], role="athlete", access_status="approved", date_of_birth="1990-01-01",
        terms_version=TERMS_VERSION, terms_accepted_at="2026-08-01T00:00:00Z", health_data_consent=True,
        health_consent_version=HEALTH_CONSENT_VERSION, health_consent_at="2026-08-01T00:00:00Z", health_consent_withdrawn_at=None)
    evidence = dict(id=str(uuid4()), athlete_id=injury["athlete_id"], injury_id=injury["id"],
        injury_episode_id=injury["episode_id"], event_type="injury_checkin", created_at="2026-09-01T00:00:00Z",
        payload=dict(latest_reported_status="improving", explicit_report=True))
    snapshot = dict(profile=profile, injury=injury, events=[evidence], exposures=[])
    definition = supplied.registry.current(supplied.context.criterion_id)
    drill = dict(id=definition.options[0].drill_id, mechanics="test-only")
    bank = [dict(drills=[drill]), *deepcopy(BANK)]
    context = build_review_context(snapshot, definition=definition, policy=policy, bank=bank, as_of=as_of)
    selection = supplied.reviews[0].selected_prescription.model_dump(mode="json", include={
        "option_id", "option_version", "range_choice", "resistance", "dose", "cadence", "restrictions"})
    statement = dict(author_reference=AUTHOR, author_display_name="Invented qualified clinician",
        qualification_reference="test-professional-registration", clinical_scope=definition.clinical_scope,
        statement_reference="test-statement-reference", statement_text="Invented test-only clinician decision for the synthetic criterion and option.",
        confirmation_reference="test-independent-confirmation",
        reviewed_at=as_of-timedelta(hours=2), confirmed_at=as_of-timedelta(hours=1),
        reviewed_packet_revision=context.current_packet.packet_revision, decision="approved",
        interpretation=supplied.reviews[0].interpretation.model_dump(mode="json"), selection=selection,
        rationale="Invented clinical decision", structured_reasons=["test_clinical_reason"])
    request = ClinicalReviewCaptureRequest(request_id=uuid4(), athlete_id=injury["athlete_id"], injury_id=injury["id"],
        injury_episode_id=injury["episode_id"], criterion_id=definition.criterion_id, criterion_version=1, statement=statement)
    recorder = SimpleNamespace(athlete_id=ADMIN, email="operator@example.test", role="admin")
    return CaptureStore(snapshot), recorder, request, dict(registry=supplied.registry, policies=(policy,), bank=bank, as_of=as_of)
