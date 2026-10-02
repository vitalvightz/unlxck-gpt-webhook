"""Episode-scoped athlete observations; no diagnosis or fabricated clearance."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from api.contracts.training_day import resolve_training_day_str
from api.contracts.clinician_clearance import canonical_clearance_scopes


def exposure_training_day(event: dict, athlete_timezone: str | None = None) -> str:
    recorded = (event.get("provenance") or {}).get("training_day")
    if recorded:
        return str(recorded)
    occurred = datetime.fromisoformat(str(event.get("occurred_at") or "").replace("Z", "+00:00"))
    return resolve_training_day_str(occurred, athlete_timezone=athlete_timezone)


class InjuryEpisodeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    injury_id: UUID
    injury_episode_id: UUID
    event_type: Literal["clinician_clearance_report", "delayed_rehab_response"]
    scopes: list[Literal["rehab", "training", "contact"]] = Field(default_factory=list)
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
    if observation.event_type == "clinician_clearance_report":
        if canonical_clearance_scopes(observation.scopes) is None or observation.exposure_id or observation.response:
            raise HTTPException(422, "Select what your clinician cleared you for.")
        payload = {"scopes": sorted(set(observation.scopes)), "source": "athlete_reported", "externally_verified": False}
        key = f"clearance:{athlete_id}:{observation.injury_id}:{observation.injury_episode_id}:{observation.report_id}"
    else:
        if not observation.exposure_id or not observation.response or observation.scopes:
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
        return []
    return reader(athlete_id, injury_id=str(injury["id"]), injury_episode_id=str(injury["episode_id"]))


def apply_episode_observations(injury: dict, observations: list[dict]) -> dict:
    row = dict(injury)
    row.pop("clinician_clearance", None)
    observations = [e for e in observations if e.get("injury_id") == str(row.get("id"))
                    and e.get("injury_episode_id") == str(row.get("episode_id"))
                    and str(e.get("athlete_id")) == str(row.get("athlete_id"))]
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
    return row


def exposure_rows_with_observations(rows, observations):
    """Derived delayed answers; the original exposure is never rewritten."""
    delayed = {e["payload"]["exposure_id"]: e for e in observations
               if e.get("event_type") == "delayed_rehab_response"}
    result = []
    for row in rows:
        derived = dict(row)
        if row.get("id") in delayed:
            event = dict(row.get("event_json") or {})
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
    return [{"exposure_id": row["id"], "injury_id": row["injury_id"], "injury_episode_id": row["injury_episode_id"],
             "region": row["body_region"], "question": "How did this injury feel the day after rehab?",
             "options": ["better", "same", "worse", "not_sure"]} for row in reader(athlete_id, training_day)
            if exposure_training_day(row.get("event_json") or row, athlete_timezone) < training_day]
