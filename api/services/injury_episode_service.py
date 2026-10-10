"""Episode-scoped athlete observations; no diagnosis or fabricated clearance."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from api.contracts.training_day import resolve_training_day_str
from api.contracts.clinician_clearance import canonical_clearance_scopes, RehabilitationPermission
from api.contracts.rehab_assessment import (
    ASSESSMENT_EVENT, AchillesProgressionAssessment, LateralElbowProgressionAssessment, AssessmentContext, AssessmentHistory,
    assessment_payload, exact_episode_events, instant,
)


def exposure_training_day(event: dict, athlete_timezone: str | None = None) -> str:
    recorded = (event.get("provenance") or {}).get("training_day")
    if recorded:
        return str(recorded)
    occurred = datetime.fromisoformat(str(event.get("occurred_at") or event.get("created_at") or "").replace("Z", "+00:00"))
    # Logged rehab is stamped at midnight UTC on its training day (see
    # rehab_completion._training_day_instant). That stamp names the day; it is
    # not a moment to localise, or the day rollover pushes it a day early and
    # the next-day question opens on the same day the rehab was done.
    if occurred.utcoffset() == timedelta(0) and occurred.time() == time(0):
        return occurred.date().isoformat()
    return resolve_training_day_str(occurred, athlete_timezone=athlete_timezone)


class InjuryEpisodeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    injury_id: UUID
    injury_episode_id: UUID
    event_type: Literal["clinician_clearance_report", "delayed_rehab_response", "rehab_progression_assessment"]
    assessment: AchillesProgressionAssessment | LateralElbowProgressionAssessment | None = None
    scopes: list[Literal["rehab", "training", "contact"]] = Field(default_factory=list)
    rehabilitation_permission: RehabilitationPermission | None = None
    exposure_id: UUID | None = None
    response: Literal["better", "same", "worse", "not_sure"] | None = None
    report_id: UUID = Field(default_factory=uuid4)


def record_episode_observation(store, *, athlete_id: str, observation: InjuryEpisodeObservation,
                               training_day: str, athlete_timezone: str | None = None) -> dict:
    injury = store.get_injury_flag_for_athlete(str(observation.injury_id), athlete_id)
    if not injury:
        raise HTTPException(404, "injury not found")
    if observation.event_type != "delayed_rehab_response" and str(injury.get("episode_id")) != str(observation.injury_episode_id):
        raise HTTPException(409, "This injury episode changed. Refresh Today.")
    if observation.event_type == ASSESSMENT_EVENT:
        assessment = observation.assessment
        if not assessment or observation.scopes or observation.rehabilitation_permission or observation.exposure_id or observation.response:
            raise HTTPException(422, "An assessment is required without completion or clearance fields.")
        try:
            payload = assessment_payload(assessment, injury, as_of=datetime.now(timezone.utc))
        except ValueError as exc:
            code = 422 if "timestamps" in str(exc) else 409
            raise HTTPException(code, str(exc)) from exc
        key = f"assessment:{athlete_id}:{observation.injury_id}:{observation.injury_episode_id}:{observation.report_id}"
    elif observation.assessment is not None:
        raise HTTPException(422, "Assessment fields belong only to a progression assessment.")
    elif observation.event_type == "clinician_clearance_report":
        if canonical_clearance_scopes(observation.scopes) is None or observation.exposure_id or observation.response:
            raise HTTPException(422, "Select what your clinician cleared you for.")
        payload = {"scopes": sorted(set(observation.scopes)), "source": "athlete_reported", "externally_verified": False}
        if observation.rehabilitation_permission is not None:
            payload["rehabilitation_permission"] = observation.rehabilitation_permission.model_dump(mode="json")
        key = f"clearance:{athlete_id}:{observation.injury_id}:{observation.injury_episode_id}:{observation.report_id}"
    else:
        if not observation.exposure_id or not observation.response or observation.scopes or observation.rehabilitation_permission:
            raise HTTPException(422, "An exposure and next-day response are required.")
        rows = store.list_rehab_exposures_by_ids(athlete_id, [str(observation.exposure_id)])
        event = (rows[0].get("event_json") or {}) if rows else {}
        if event.get("injury_id") != str(observation.injury_id) or event.get("injury_episode_id") != str(observation.injury_episode_id):
            raise HTTPException(404, "rehab exposure not found")
        if exposure_training_day(event, athlete_timezone) >= training_day:
            raise HTTPException(409, "The next-day response opens on a later training day.")
        payload = {"exposure_id": str(observation.exposure_id), "response": observation.response}
        key = f"delayed:{athlete_id}:{observation.exposure_id}"
    event = {"id": str(uuid5(NAMESPACE_URL, key)), "injury_id": str(observation.injury_id),
             "injury_episode_id": str(observation.injury_episode_id), "event_type": observation.event_type, "payload": payload}
    return store.record_injury_episode_event(athlete_id, event)


def episode_observations(store, athlete_id: str, injury: dict) -> list[dict]:
    reader = getattr(store, "list_injury_episode_events", None)
    if not callable(reader) or not injury.get("episode_id"):
        return AssessmentHistory([], history_complete=False)
    return reader(athlete_id, injury_id=str(injury["id"]), injury_episode_id=str(injury["episode_id"]))


def apply_episode_observations(injury: dict, observations: list[dict], *, as_of: datetime | None = None) -> dict:
    row = dict(injury)
    row.pop("clinician_clearance", None)
    row["assessment_history_complete"] = getattr(observations, "history_complete", True)
    observations = exact_episode_events(row, observations)
    row["progression_assessments"] = [e for e in observations if e.get("event_type") == ASSESSMENT_EVENT]
    starts = [instant(e.get("created_at")) for e in observations if e.get("event_type") == "injury_checkin"]
    row["assessment_episode_started_at"] = min((s for s in starts if s), default=instant(row.get("created_at")))
    context = AssessmentContext.from_injury(row, as_of=as_of or datetime.now(timezone.utc))
    if context.reported_medical_concern:
        row["rehab_medical_gate"] = True
        row["progression_assessment_medical_hold"] = True
    from api.contracts.rehab_progression import _instant
    # Audit events can inherit an old status after a severity edit. Only a
    # database-marked explicit report may supply the recovery timestamp.
    reports = [e for e in observations if e.get("event_type") == "injury_checkin"
               and e.get("payload", {}).get("explicit_report") is True
               and e.get("payload", {}).get("latest_reported_status") == row.get("latest_reported_status")]
    reported_at = max((_instant(e.get("created_at")) for e in reports
                       if _instant(e.get("created_at")) is not None), default=None)
    row["latest_reported_at"] = reported_at.isoformat() if reported_at else None
    setbacks = [e.get("created_at") for e in observations
                if (e.get("event_type") == "injury_checkin" and e.get("payload", {}).get("latest_reported_status") == "worse")
                or (e.get("event_type") == "delayed_rehab_response" and e.get("payload", {}).get("response") == "worse")]
    if row.get("latest_reported_status") == "worse" and row.get("updated_at"):
        setbacks.append(row["updated_at"])
    row["assessment_setback_at"] = max((instant(v) for v in setbacks if instant(v)), default=None)
    def timestamp(value):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    last_setback = max((timestamp(value) for value in setbacks if value), default=None)
    clearances = [e for e in observations if e.get("event_type") == "clinician_clearance_report"
                  and (last_setback is None or timestamp(e["created_at"]) > last_setback)]
    if clearances:
        latest = max(clearances, key=lambda e: (timestamp(e["created_at"]), str(e.get("id") or "")))
        scopes = latest.get("payload", {}).get("scopes")
        # Preserve malformed list reports for subordinate display, but never
        # normalize a noncanonical report into a more permissive valid one.
        scopes = list(scopes) if isinstance(scopes, list) and all(isinstance(s, str) for s in scopes) else []
        row["clinician_clearance"] = {"episode_id": row["episode_id"], "scopes": scopes,
                                      "source": "athlete_reported", "externally_verified": False,
                                      "scope_reported_at": {scope: latest["created_at"] for scope in scopes}}
        if "rehabilitation_permission" in latest.get("payload", {}):
            row["clinician_clearance"]["rehabilitation_permission"] = latest["payload"]["rehabilitation_permission"]
    return row


def exposure_rows_with_observations(rows, observations, athlete_timezone=None):
    """Derived delayed answers; the original exposure is never rewritten."""
    delayed = {e["payload"]["exposure_id"]: e for e in observations
               if e.get("event_type") == "delayed_rehab_response"}
    result = []
    for row in rows:
        derived = dict(row)
        event = row.get("event_json") or {}
        # A same-day explicit injury response after logged work can describe that
        # work. Earlier check-ins never become evidence of future tolerance.
        if (event.get("response", {}).get("during_response") == "not_reported"
                and (event.get("provenance") or {}).get("response_tracking") == "injury_checkin"):
            reports = [e for e in observations if e.get("event_type") == "injury_checkin"
                and e.get("payload", {}).get("explicit_report") is True
                and e.get("payload", {}).get("latest_reported_status") in {"improving", "ongoing", "worse"}
                and e.get("injury_id") == event.get("injury_id")
                and e.get("injury_episode_id") == event.get("injury_episode_id")
                and instant(e.get("created_at")) and instant(row.get("created_at"))
                and instant(e["created_at"]) >= instant(row["created_at"])
                and exposure_training_day(e, athlete_timezone) == exposure_training_day(event, athlete_timezone)]
            if reports:
                report = max(reports, key=lambda e: (e["payload"]["latest_reported_status"] == "worse", instant(e["created_at"]), str(e.get("id"))))
                answer = {"improving": "better", "ongoing": "same", "worse": "worse"}[report["payload"]["latest_reported_status"]]
                event = {**event, "response": {**event.get("response", {}), "during_response": answer}}
                derived["event_json"] = event
        if row.get("id") in delayed:
            event = dict(derived.get("event_json") or event)
            observation = delayed[row["id"]]
            event["response"] = {**event.get("response", {}), "next_day_response": observation["payload"]["response"]}
            derived["response_recorded_at"] = observation["created_at"]
            derived["event_json"] = event
        result.append(derived)
    return result


def delayed_rehab_prompts(store, athlete_id: str, training_day: str, athlete_timezone: str | None = None) -> list[dict]:
    reader = getattr(store, "list_pending_delayed_rehab", None)
    if not callable(reader):
        return []
    # Asked on the day after only: a "day after" answer recalled days later is
    # a guess, and an unanswered prompt should not linger on Today.
    previous_day = (date.fromisoformat(training_day) - timedelta(days=1)).isoformat()
    return [{"exposure_id": row["id"], "injury_id": row["injury_id"], "injury_episode_id": row["injury_episode_id"],
             "region": row["body_region"], "question": "How did this injury feel the day after rehab?",
             "options": ["better", "same", "worse", "not_sure"]} for row in reader(athlete_id, training_day)
            if exposure_training_day(row.get("event_json") or row, athlete_timezone) == previous_day]
